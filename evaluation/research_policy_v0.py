"""Deterministic development scorer, held-back calibration, and PT1/PT2 selection."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from math import exp, fsum, isfinite

from evaluation.manifest_schema import EvaluationManifest, PartitionRole, serialize_evaluation_manifest
from evaluation.research_runner_v0 import FieldDecision, canonical_bytes
from pipeline.contracts import PolicyState
from pipeline.proposed.contracts import FEATURE_SLOT_ORDER


class NotAssessable(ValueError):
    """The prerequisites for an empirical configuration were not met."""


def _digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def _manifest_digest(manifest):
    return sha256(serialize_evaluation_manifest(manifest).encode("utf-8")).hexdigest()


def _probability(value):
    return type(value) in (int, float) and isfinite(value) and 0 <= value <= 1


@dataclass(frozen=True)
class CandidateEvidence:
    """Session A adapter boundary after upstream source and feature audit.

    Send retained candidates in frozen order, including c0. Each feature value
    follows FEATURE_SLOT_ORDER. None means unavailable, not measured zero.
    Constraint, source support and replacement checks come from the source-bound audit.
    """

    candidate_id: str
    value: str
    is_original: bool
    constraints_pass: bool
    has_non_price_support: bool
    price_supports_change: bool
    replacement_checks_pass: bool
    source_reference: str
    features: tuple[float | None, ...]

    def __post_init__(self):
        flags = (self.is_original, self.constraints_pass, self.has_non_price_support,
                 self.price_supports_change, self.replacement_checks_pass)
        if (not self.candidate_id or not self.value or not self.source_reference
                or any(type(flag) is not bool for flag in flags)):
            raise ValueError("Candidate identity, value and audited Boolean flags are required.")
        if type(self.features) is not tuple or len(self.features) != len(FEATURE_SLOT_ORDER):
            raise ValueError("Use the exact seven-slot Equation 4.1 order.")
        if any(value is not None and not _probability(value) for value in self.features):
            raise ValueError("Every observed feature must belong to the frozen [0, 1] domain.")
        if self.price_supports_change and self.features[-1] is None:
            raise ValueError("Missing price evidence cannot support a change.")

    @property
    def price_only(self):
        return self.price_supports_change and not self.has_non_price_support

    @property
    def admitted(self):
        return self.is_original or (self.constraints_pass and not self.price_only)

    def vector(self):
        return (tuple(0.0 if value is None else float(value) for value in self.features)
                + tuple(float(value is None) for value in self.features))


@dataclass(frozen=True)
class LabelledCandidate:
    receipt_id: str
    field_id: str
    candidate: CandidateEvidence
    correct: bool


def _checked_examples(manifest, examples, partition_role):
    partition_roles = {p.partition_id: p.role for p in manifest.partitions}
    membership = {r.receipt_id: partition_roles[r.partition_id] for r in manifest.receipts}
    fitting_exclusions = frozenset(manifest.fitting_exclusion_evidence.excluded_receipt_ids
                                   if manifest.fitting_exclusion_evidence else ())
    keys = [(e.receipt_id, e.field_id, e.candidate.candidate_id) for e in examples]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate candidate identity.")
    if any(not e.field_id or type(e.correct) is not bool or not e.candidate.admitted
           or membership.get(e.receipt_id) is not partition_role or e.receipt_id in fitting_exclusions
           for e in examples):
        raise ValueError("Examples must be adjudicated admitted candidates in the designated partition.")
    if {e.correct for e in examples} != {False, True}:
        raise NotAssessable("Fitting requires adjudicated positive and negative examples.")
    return sorted(examples, key=lambda e: (e.receipt_id, e.field_id, e.candidate.candidate_id))


@dataclass(frozen=True)
class FitConfiguration:
    iterations: int
    learning_rate: float
    l2: float

    def __post_init__(self):
        if (type(self.iterations) is not int or self.iterations < 1
                or not _probability(self.learning_rate) or self.learning_rate == 0
                or not _probability(self.l2) or self.l2 == 0):
            raise ValueError("Declare a positive fit budget, update rate and L2 penalty before fitting.")


def _sigmoid(value):
    if value >= 0:
        return 1 / (1 + exp(-value))
    z = exp(value)
    return z / (1 + z)


def _logit(weights, row):
    return fsum(a * b for a, b in zip(weights, row, strict=True))


def _logistic_fit(rows, labels, config, *, monotone=False):
    """Fixed-budget full-batch logistic regression with an unpenalized intercept."""
    weights = (0.0,) * len(rows[0])
    for _ in range(config.iterations):
        errors = tuple(_sigmoid(_logit(weights, row)) - label for row, label in zip(rows, labels))
        gradient = tuple(
            fsum(err * row[i] for err, row in zip(errors, rows)) / len(rows)
            + (config.l2 * weight if i else 0.0)
            for i, weight in enumerate(weights)
        )
        weights = tuple(w - config.learning_rate * g for w, g in zip(weights, gradient))
        if monotone:
            weights = (weights[0], max(0.0, weights[1]))
    if not all(isfinite(weight) for weight in weights):
        raise NotAssessable("Fitted weights are not finite.")
    return weights


@dataclass(frozen=True)
class FrozenScorer:
    membership_sha256: str
    training_examples_sha256: str
    configuration: FitConfiguration
    weights: tuple[float, ...]

    @property
    def sha256(self):
        return _digest({"family": "regularized-additive-v0", "slot_order": FEATURE_SLOT_ORDER,
                        **asdict(self)})

    def raw(self, candidate):
        if not candidate.admitted:
            raise ValueError("Rejected candidates have no raw score.")
        return _logit(self.weights, (1.0, *candidate.vector()))


def fit_scorer(manifest: EvaluationManifest, examples: tuple[LabelledCandidate, ...],
               configuration: FitConfiguration) -> FrozenScorer:
    ranked = _checked_examples(manifest, examples, PartitionRole.TRAINING)
    rows = tuple((1.0, *e.candidate.vector()) for e in ranked)
    weights = _logistic_fit(rows, tuple(e.correct for e in ranked), configuration)
    return FrozenScorer(_manifest_digest(manifest), _digest([asdict(e) for e in ranked]),
                        configuration, weights)


@dataclass(frozen=True)
class FrozenCalibration:
    scorer_sha256: str
    validation_predictions_sha256: str
    configuration: FitConfiguration
    center: float
    scale: float
    intercept: float
    slope: float

    @property
    def sha256(self):
        return _digest({"family": "monotone-platt-v0", **asdict(self)})

    def probability(self, scorer: FrozenScorer, raw: float) -> float:
        if scorer.sha256 != self.scorer_sha256 or not isfinite(raw):
            raise ValueError("Calibration must use the bound frozen scorer and finite raw score.")
        return _sigmoid(self.intercept + self.slope * ((raw - self.center) / self.scale))


def fit_calibration(manifest: EvaluationManifest, scorer: FrozenScorer,
                    examples: tuple[LabelledCandidate, ...],
                    configuration: FitConfiguration) -> FrozenCalibration:
    if scorer.membership_sha256 != _manifest_digest(manifest):
        raise ValueError("The scorer and validation fixtures must share the same partition manifest.")
    ranked = _checked_examples(manifest, examples, PartitionRole.VALIDATION)
    scores = tuple(scorer.raw(e.candidate) for e in ranked)
    low, high = min(scores), max(scores)
    if low == high:
        raise NotAssessable("Constant validation scores cannot fit this calibration.")
    scale = high - low
    weights = _logistic_fit(
        tuple((1.0, (score - low) / scale) for score in scores),
        tuple(e.correct for e in ranked), configuration, monotone=True,
    )
    if weights[1] == 0:
        raise NotAssessable("Validation did not support a positive monotone calibration slope.")
    digest = _digest([(e.receipt_id, e.field_id, e.candidate.candidate_id, s, e.correct)
                      for e, s in zip(ranked, scores)])
    return FrozenCalibration(scorer.sha256, digest, configuration, low, scale, *weights)


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    source_reference: str
    status: str
    raw_score: float | None = None
    probability: float | None = None


@dataclass(frozen=True)
class VerifiedField:
    decision: FieldDecision
    selected_candidate_id: str
    audit: tuple[CandidateScore, ...]
    reason: str


@dataclass(frozen=True)
class VerificationPolicy:
    """Prospectively supplied settings for one field/impact category."""

    acceptance_threshold: float
    force_review: bool

    def __post_init__(self):
        if not (_probability(self.acceptance_threshold) and type(self.force_review) is bool):
            raise ValueError("The named policy needs valid, predeclared parameters.")


def verify_field(field_id: str, pantry_relevant: bool, candidates: tuple[CandidateEvidence, ...],
                 scorer: FrozenScorer | None, calibration: FrozenCalibration | None,
                 policy: VerificationPolicy, *, replacement_margin: float, unresolved_conflict: bool) -> VerifiedField:
    """Apply post-source-gate scoring and the minimum selective controller.

    The adapter owns source gate validation, audited ordering and determining
    unresolved conflict/field impact under the frozen rules. These are never
    derived from reference labels.
    """
    if (not candidates or not candidates[0].is_original or sum(c.is_original for c in candidates) != 1
            or len({c.candidate_id for c in candidates}) != len(candidates)
            or type(unresolved_conflict) is not bool):
        raise ValueError("An audited list must begin with its unique c0.")
    if not _probability(replacement_margin):
        raise ValueError("Theta_A requires a predeclared replacement margin.")
    if calibration is not None and scorer is None:
        raise ValueError("Calibration requires its frozen scorer.")
    if calibration is not None and calibration.scorer_sha256 != scorer.sha256:
        raise ValueError("Mismatched frozen scorer and calibration.")
    original = candidates[0]
    audit = []
    for candidate in candidates:
        if not candidate.admitted:
            status = "CONSTRAINT_REJECTED" if not candidate.constraints_pass else "REJECTED_PRICE_ONLY"
            audit.append(CandidateScore(candidate.candidate_id, candidate.source_reference, status))
        elif scorer is None:
            audit.append(CandidateScore(candidate.candidate_id, candidate.source_reference, "PROBABILITY_UNAVAILABLE"))
        else:
            raw = scorer.raw(candidate)
            probability = calibration.probability(scorer, raw) if calibration is not None else None
            status = "SCORED" if probability is not None else "PROBABILITY_UNAVAILABLE"
            audit.append(CandidateScore(candidate.candidate_id, candidate.source_reference, status, raw, probability))

    selected = original
    confidence = audit[0].probability
    reason = "PROBABILITY_UNAVAILABLE"
    if confidence is not None:
        probabilities = {a.candidate_id: a.probability for a in audit if a.probability is not None}
        best = max((c for c in candidates if c.candidate_id in probabilities),
                   key=lambda c: probabilities[c.candidate_id])
        if best.replacement_checks_pass and probabilities[best.candidate_id] - confidence >= replacement_margin:
            selected = best
            confidence = probabilities[best.candidate_id]
        if not selected.constraints_pass:
            reason = "CONSTRAINT_INELIGIBLE"
        elif unresolved_conflict:
            reason = "UNRESOLVED_CONFLICT"
        elif policy.force_review or confidence < policy.acceptance_threshold:
            reason = "REVIEW_POLICY"
        else:
            reason = "ACCEPTED"
    state = PolicyState.AUTO_RESOLVED if reason == "ACCEPTED" else PolicyState.REVIEW_REQUIRED
    evidence_digest = _digest({
        "candidates": [asdict(c) for c in candidates],
        "audit": [asdict(a) for a in audit],
        "scorer_sha256": scorer.sha256 if scorer is not None else None,
        "calibration_sha256": calibration.sha256 if calibration is not None else None,
        "policy": asdict(policy),
        "replacement_margin": replacement_margin,
        "conflict": unresolved_conflict,
        "selected_candidate": selected.candidate_id,
        "reason": reason,
    })
    field = FieldDecision(field_id, state, pantry_relevant, original.value, selected.value,
                          confidence, evidence_digest)
    return VerifiedField(field, selected.candidate_id, tuple(audit), reason)


@dataclass(frozen=True)
class OperatingPoint:
    configuration_id: str
    automatic_coverage: Fraction
    confirmation_rate: Fraction | None
    upper_residual_cier_95: Fraction | float | None

    def __post_init__(self):
        if (not self.configuration_id or not 0 <= self.automatic_coverage <= 1
                or (self.confirmation_rate is not None and not 0 <= self.confirmation_rate <= 1)
                or (self.upper_residual_cier_95 is not None and not (isfinite(self.upper_residual_cier_95) and 0 <= self.upper_residual_cier_95 <= 1))):
            raise ValueError("Invalid validation operating-point evidence.")


@dataclass(frozen=True)
class ValidationSelection:
    pt1: str | None
    pt2: str | None
    membership_sha256: str
    validation_partition: str
    grid_sha256: str

    @property
    def pt1_status(self):
        return "SELECTED" if self.pt1 is not None else "NO_VALID_PAIR"

    @property
    def pt2_status(self):
        return "SELECTED" if self.pt2 is not None else "NO_VALID_POINT"


def select_operating_points(
    manifest: EvaluationManifest,
    partition_id: str,
    *,
    predeclared_order: tuple[str, ...],
    validation_points: tuple[OperatingPoint, ...],
    b3_automatic_coverage: Fraction,
    b3_automatic_cier: Fraction | None,
    pt1_tolerance: Fraction,
) -> ValidationSelection:
    """Select PT1 by coverage proximity and PT2 by admissible workload.

    Predeclared order breaks ties. This function receives validation estimates,
    including the oracle residual CIER percentile bound, after prediction freeze.
    """
    if not any(p.partition_id == partition_id and p.role is PartitionRole.VALIDATION
               for p in manifest.partitions):
        raise ValueError("Operating points may be selected only on validation.")
    ids = {p.configuration_id: p for p in validation_points}
    if not ids or len(ids) != len(validation_points) or len(predeclared_order) != len(ids) or set(predeclared_order) != ids.keys():
        raise ValueError("Every predeclared operating point must be accounted for exactly once.")
    if (not 0 <= b3_automatic_coverage <= 1 or not 0 <= pt1_tolerance <= 1
            or (b3_automatic_cier is not None and not 0 <= b3_automatic_cier <= 1)):
        raise ValueError("Baseline rates and tolerance must be in [0, 1].")
    ordered = [ids[key] for key in predeclared_order]
    eligible_pt1 = [p for p in ordered if abs(p.automatic_coverage - b3_automatic_coverage) <= pt1_tolerance]
    pt1 = min(eligible_pt1, key=lambda p: abs(p.automatic_coverage - b3_automatic_coverage), default=None)
    eligible_pt2 = [
        p for p in ordered if p.confirmation_rate is not None and b3_automatic_cier is not None
        and p.upper_residual_cier_95 is not None and p.upper_residual_cier_95 <= b3_automatic_cier
    ]
    pt2 = min(eligible_pt2, key=lambda p: p.confirmation_rate, default=None)
    grid = {
        "b3_automatic_coverage": str(b3_automatic_coverage),
        "b3_automatic_cier": str(b3_automatic_cier) if b3_automatic_cier is not None else None,
        "pt1_tolerance": str(pt1_tolerance),
        "ordered_points": [
            (p.configuration_id, str(p.automatic_coverage), str(p.confirmation_rate),
             str(p.upper_residual_cier_95))
            for p in ordered
        ],
    }
    return ValidationSelection(pt1.configuration_id if pt1 else None, pt2.configuration_id if pt2 else None,
                               _manifest_digest(manifest), partition_id, _digest(grid))
