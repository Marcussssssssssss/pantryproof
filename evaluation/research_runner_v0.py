"""Offline, reference-blind development/validation prediction runner."""

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

from evaluation.manifest_schema import EvaluationManifest, PartitionRole, serialize_evaluation_manifest
from evaluation.prediction_adapters import (
    adapt_b1_result_to_prediction_receipt,
    adapt_b2_result_to_prediction_receipt,
    adapt_b3_result_to_prediction_receipt,
)
from evaluation.prediction_schema import (
    EvaluationRunScope, PredictionBundle, PredictionExecutionState, PredictionProvenance, PredictionReceipt,
)
from evaluation.prediction_validation import validate_prediction_bundle
from pipeline.baseline_b1 import extract_b1
from pipeline.baseline_b3 import apply_b3
from pipeline.contracts import (
    FailureStage, FieldStatus, OutputStage, PolicyState, PreResolutionDisposition,
    ReceiptSourceEvidence, SourceEvidenceDecision, SourceProcessingStatus,
)
from pipeline.layout_b2 import B2ExtractionResult, extract_b2


def canonical_bytes(record: object) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def source_digest(source: ReceiptSourceEvidence) -> str:
    """Digest the typed, ordered OCR package consumed by all methods."""
    return sha256(canonical_bytes(asdict(source))).hexdigest()


@dataclass(frozen=True)
class OcrInput:
    source: ReceiptSourceEvidence
    approved_sha256: str


@dataclass(frozen=True)
class FieldDecision:
    field_id: str
    state: PolicyState
    pantry_relevant: bool
    original_value: str | None
    prediction: str | None
    correctness_probability: float | None = None
    decision_evidence_sha256: str | None = None

    def __post_init__(self):
        if not self.field_id or type(self.pantry_relevant) is not bool:
            raise ValueError("A runtime decision requires its field identity and pantry scope.")
        if self.state not in (PolicyState.AUTO_RESOLVED, PolicyState.REVIEW_REQUIRED):
            raise ValueError("Fall back and failure are receipt-level outcomes here.")
        if self.state is PolicyState.AUTO_RESOLVED and self.prediction is None:
            raise ValueError("Automatic permission requires a prediction.")
        if self.correctness_probability is not None and (
            self.prediction is None or type(self.correctness_probability) not in (int, float)
            or not 0 <= self.correctness_probability <= 1
        ):
            raise ValueError("A correctness probability requires a value and must be in [0, 1].")
        digest = self.decision_evidence_sha256
        if digest is not None and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("Decision evidence must have a canonical SHA-256.")


@dataclass(frozen=True)
class SystemOutput:
    prediction: PredictionReceipt
    disposition: PreResolutionDisposition
    decisions: tuple[FieldDecision, ...] = ()
    completeness_issues: tuple[str, ...] = ()

    def __post_init__(self):
        prediction = self.prediction
        if prediction.runtime_receipt_id != self.disposition.gate_result.receipt_id:
            raise ValueError("Receipt and disposition identities differ.")
        if type(self.decisions) is not tuple:
            raise TypeError("Field decisions must be an immutable tuple.")
        if (type(self.completeness_issues) is not tuple
                or any(not isinstance(issue, str) or not issue for issue in self.completeness_issues)
                or len(set(self.completeness_issues)) != len(self.completeness_issues)):
            raise ValueError("Completeness issues must be unique, immutable reason codes.")
        state = self.disposition.state
        expected_execution = {
            PolicyState.FAILED: PredictionExecutionState.EXECUTION_FAILED,
            PolicyState.FALLBACK_NO_UPDATE: PredictionExecutionState.FALLBACK_NO_UPDATE,
        }.get(state, PredictionExecutionState.STRUCTURED_OUTPUT)
        if prediction.execution_state is not expected_execution:
            raise ValueError("Prediction and disposition disagree.")
        if expected_execution is not PredictionExecutionState.STRUCTURED_OUTPUT:
            if self.decisions or self.completeness_issues:
                raise ValueError("Absent output cannot include decisions or completeness issues.")
            return
        fields = prediction.receipt_fields + tuple(f for row in prediction.rows for f in row.fields)
        by_id = {f.runtime_field_id: f for f in fields}
        by_decision = {d.field_id: d for d in self.decisions}
        if len(by_decision) != len(self.decisions) or by_id.keys() != by_decision.keys():
            raise ValueError("Every emitted field needs exactly one frozen decision.")
        if any(by_id[d.field_id].value != d.prediction for d in self.decisions):
            raise ValueError("A frozen decision cannot disagree with its pre-review prediction.")
        expected = (PolicyState.REVIEW_REQUIRED
                    if self.completeness_issues or any(d.state is PolicyState.REVIEW_REQUIRED for d in self.decisions)
                    else PolicyState.AUTO_RESOLVED)
        if state is not expected:
            raise ValueError("Receipt disposition must aggregate system decisions before reference access.")


@dataclass(frozen=True)
class OracleOutput:
    completed: bool
    substitutions: tuple[tuple[str, str], ...]


def resolve_oracle(output: SystemOutput, eligible_truth: dict[str, str]) -> OracleOutput:
    """Use adjudicated eligibility supplied by the evaluator after freeze."""
    reviews = {d.field_id for d in output.decisions if d.state is PolicyState.REVIEW_REQUIRED}
    if not eligible_truth.keys() <= reviews:
        raise ValueError("Oracle substitution is confined to actual REVIEW_REQUIRED fields.")
    if any(type(value) is not str or not value.strip() for value in eligible_truth.values()):
        raise ValueError("Oracle substitutions need an adjudicated value.")
    completed = (output.disposition.state in (PolicyState.AUTO_RESOLVED, PolicyState.REVIEW_REQUIRED)
                 and not output.completeness_issues and eligible_truth.keys() == reviews)
    return OracleOutput(completed, tuple(sorted(eligible_truth.items())))


@dataclass(frozen=True)
class RealisedOutcome:
    """Actual application evidence, retained separately from system and oracle records."""

    receipt_id: str
    user_action: str
    write_outcome: str | None = None

    def __post_init__(self):
        if not self.receipt_id or self.user_action not in ("USER_CONFIRMED", "USER_MODIFIED", "REJECTED"):
            raise ValueError("Actual user action is required.")
        if self.write_outcome not in (None, "COMMITTED", "FAILED/INVENTORY_PERSISTENCE"):
            raise ValueError("Invalid later write outcome.")
        if self.user_action == "REJECTED" and self.write_outcome is not None:
            raise ValueError("Rejection must not attempt inventory persistence.")


@dataclass(frozen=True)
class FrozenPredictions:
    """Canonical prediction/disposition bytes and a reproducible content identity."""

    payload: bytes

    @property
    def sha256(self) -> str:
        return sha256(self.payload).hexdigest()

    def write_new(self, path: Path) -> None:
        """Publish all predictions atomically without overwriting a prior run."""
        temporary = NamedTemporaryFile(dir=path.parent, delete=False)
        temp_path = Path(temporary.name)
        try:
            with temporary:
                temporary.write(self.payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.link(temp_path, path)
        finally:
            temp_path.unlink()


# The common completeness rule is supplied at the evaluation boundary and bound
# by the configuration digest. B3 itself remains the existing non-selective rule baseline.
BaselineDisposition = Callable[[PredictionReceipt], tuple[FieldDecision, ...]]
ProposedMethod = Callable[[ReceiptSourceEvidence, B2ExtractionResult, EvaluationRunScope], SystemOutput]


def scope_digest(scopes: tuple[EvaluationRunScope, ...]) -> str:
    return sha256(canonical_bytes([asdict(s) for s in sorted(scopes, key=lambda s: s.identity_key)])).hexdigest()


@dataclass(frozen=True)
class HeldOutFreeze:
    """Exact artifact bindings from the custodian's existing held-out authorization."""

    partition_id: str
    cohort_id: str
    manifest_sha256: str
    configuration_sha256: str
    scopes_sha256: str
    ocr_manifest_sha256: str
    references_sha256: str
    alignment_sha256: str
    comparison_rules_sha256: str
    validation_selection_sha256: str
    pt1_configuration_id: str | None
    pt2_configuration_id: str | None
    software_freeze_reference: str
    authorization_reference: str

    def __post_init__(self):
        digests = (self.manifest_sha256, self.configuration_sha256, self.scopes_sha256, self.ocr_manifest_sha256,
                   self.references_sha256, self.alignment_sha256, self.comparison_rules_sha256,
                   self.validation_selection_sha256)
        if any(not isinstance(d, str) or len(d) != 64 or any(c not in "0123456789abcdef" for c in d) for d in digests):
            raise ValueError("Held-out freeze requires SHA-256 for each required artifact.")
        if any(not isinstance(ref, str) or not ref.strip() for ref in (
            self.partition_id, self.cohort_id, self.software_freeze_reference, self.authorization_reference,
        )):
            raise ValueError("Held-out freeze requires recorded software and access authorization references.")

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(asdict(self))).hexdigest()

    def check(self, approved_sha256, *, partition_id, cohort_id, manifest_sha256, configuration_sha256,
              scopes_sha256, ocr_sha256_by_receipt):
        if self.sha256 != approved_sha256 or (
            self.partition_id, self.cohort_id, self.manifest_sha256,
            self.configuration_sha256, self.scopes_sha256, self.ocr_manifest_sha256,
        ) != (
            partition_id, cohort_id, manifest_sha256, configuration_sha256,
            scopes_sha256, sha256(canonical_bytes(ocr_sha256_by_receipt)).hexdigest(),
        ):
            raise ValueError("Held-out inputs do not match the custodian-approved freeze.")


def _baseline(system: str, source: ReceiptSourceEvidence, provenance: PredictionProvenance,
              disposition_rule: BaselineDisposition) -> SystemOutput:
    if system == "B1":
        result, adapter = extract_b1(source), adapt_b1_result_to_prediction_receipt
    elif system == "B2":
        result, adapter = extract_b2(source), adapt_b2_result_to_prediction_receipt
    else:
        result, adapter = apply_b3(extract_b2(source)), adapt_b3_result_to_prediction_receipt
    output = result.receipt_output
    rows = () if output is None else tuple((row.row_id, i) for i, row in enumerate(output.items))
    prediction = adapter(result, provenance=provenance, row_ordinals=rows,
                         state_detail="SOURCE_EVIDENCE_INSUFFICIENT" if output is None else None)
    if output is None:
        return SystemOutput(prediction, result.pre_resolution_disposition)
    decisions = disposition_rule(prediction)
    if any(d.original_value != d.prediction or d.correctness_probability is not None for d in decisions):
        raise ValueError("Baseline disposition rules must preserve values and cannot create calibration.")
    state = (PolicyState.REVIEW_REQUIRED if any(d.state is PolicyState.REVIEW_REQUIRED for d in decisions)
             else PolicyState.AUTO_RESOLVED)
    return SystemOutput(prediction, PreResolutionDisposition(state, source.gate_result), decisions)


def _failed(source: ReceiptSourceEvidence, provenance: PredictionProvenance, reason: str) -> SystemOutput:
    return SystemOutput(
        PredictionReceipt(source.receipt_id, False, PredictionExecutionState.EXECUTION_FAILED,
                          None, (), (), provenance, reason),
        PreResolutionDisposition(PolicyState.FAILED, source.gate_result, FailureStage.PRE_RESOLUTION, reason),
    )


def _run_method(scope, source, provenance, baseline_disposition, proposed):
    if source.gate_result.decision is SourceEvidenceDecision.INSUFFICIENT:
        baseline_system = "B2" if scope.system_id == "PROPOSED" else scope.system_id
        return _baseline(baseline_system, source, provenance, baseline_disposition)
    if source.processing_status is SourceProcessingStatus.OCR_FAILED:
        return _failed(source, provenance, "OCR_FAILED")
    system = scope.system_id
    try:
        result = (proposed(source, extract_b2(source), scope) if system == "PROPOSED"
                  else _baseline(system, source, provenance, baseline_disposition))
        if not isinstance(result, SystemOutput) or result.disposition.gate_result != source.gate_result:
            raise ValueError("Output does not bind to the recorded upstream gate.")
        fields = result.prediction.receipt_fields + tuple(f for row in result.prediction.rows for f in row.fields)
        if any(not source.token_ids.issuperset(f.source_token_ids) for f in fields):
            raise ValueError("Prediction cites evidence outside the shared OCR package.")
        if result.prediction.runtime_receipt_id != source.receipt_id:
            raise ValueError("Prediction does not bind to the current receipt.")
        return replace(result, prediction=replace(result.prediction, provenance=provenance))
    except Exception:
        return _failed(source, provenance, "METHOD_PRE_RESOLUTION_FAILURE")


def run_predictions(
    manifest: EvaluationManifest,
    scopes: tuple[EvaluationRunScope, ...],
    inputs: tuple[OcrInput, ...],
    *,
    configuration_sha256: str,
    baseline_disposition: BaselineDisposition,
    proposed: ProposedMethod | None = None,
    completeness_issues: Callable[[PredictionReceipt], tuple[str, ...]] | None = None,
    held_out_freeze: HeldOutFreeze | None = None,
    approved_held_out_sha256: str | None = None,
) -> FrozenPredictions:
    """Run without references, with held-out scopes bound to a separately approved freeze."""
    if len(configuration_sha256) != 64 or any(c not in "0123456789abcdef" for c in configuration_sha256):
        raise ValueError("A frozen configuration digest is required.")
    systems = {s.system_id for s in scopes}
    if systems != ({"B1", "B2", "B3", "PROPOSED"} if proposed else {"B1", "B2", "B3"}):
        raise ValueError("B1, B2 and B3 plus the configured proposed method are required.")
    if len({s.identity_key for s in scopes}) != len(scopes):
        raise ValueError("Duplicate run scope.")
    partition_ids = {s.partition_id for s in scopes}
    cohort_ids = {s.cohort_id for s in scopes}
    if len(partition_ids) != 1 or len(cohort_ids) != 1 or any(
        s.dataset_id != manifest.dataset_id or s.dataset_tier is not manifest.dataset_tier
        or s.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC for s in scopes
    ):
        raise ValueError("All configurations must use the same dataset, cohort and partition.")
    partition_id = partition_ids.pop()
    roles = {p.partition_id: p.role for p in manifest.partitions}
    role = roles.get(partition_id)
    if role is PartitionRole.HELD_OUT_TEST and (held_out_freeze is None or approved_held_out_sha256 is None):
        raise ValueError("Held-out execution requires a separately approved freeze.")
    if role is None or (role is not PartitionRole.HELD_OUT_TEST
                        and (held_out_freeze is not None or approved_held_out_sha256 is not None)):
        raise ValueError("Run a declared partition with its applicable access scope.")
    cohort = next((c for c in manifest.cohorts if c.cohort_id in cohort_ids), None)
    if cohort is None:
        raise ValueError("Unknown evaluation cohort.")
    eligible = set(cohort.receipt_ids) & {r.receipt_id for r in manifest.receipts if r.partition_id == partition_id}
    by_id = {item.source.receipt_id: item for item in inputs}
    if not eligible or eligible != by_id.keys() or len(by_id) != len(inputs):
        raise ValueError("OCR inputs must cover the eligible population exactly once.")
    manifest_sha256 = sha256(serialize_evaluation_manifest(manifest).encode("utf-8")).hexdigest()
    ocr_hashes = {key: item.approved_sha256 for key, item in by_id.items()}
    if held_out_freeze is not None:
        held_out_freeze.check(approved_held_out_sha256, partition_id=partition_id, cohort_id=cohort.cohort_id,
                              manifest_sha256=manifest_sha256, configuration_sha256=configuration_sha256,
                              scopes_sha256=scope_digest(scopes), ocr_sha256_by_receipt=ocr_hashes)
    for item in inputs:
        if item.approved_sha256 != source_digest(item.source):
            raise ValueError("OCR package differs from its approved identity.")

    frozen = []
    for scope in sorted(scopes, key=lambda s: s.identity_key):
        outputs = []
        for receipt_id, item in sorted(by_id.items()):
            provenance = PredictionProvenance("ocr-" + item.approved_sha256, item.approved_sha256, "research-runner-v0")
            output = _run_method(scope, item.source, provenance, baseline_disposition, proposed)
            if completeness_issues is not None and output.prediction.structured_output_present:
                issues = completeness_issues(output.prediction)
                if issues:
                    output = replace(output, completeness_issues=issues, disposition=replace(
                        output.disposition, state=PolicyState.REVIEW_REQUIRED,
                    ))
            outputs.append(output)
        bundle = PredictionBundle("bundle-" + sha256(canonical_bytes(scope.identity_key)).hexdigest(),
                                  scope, tuple(o.prediction for o in outputs),
                                  PredictionProvenance("configuration", configuration_sha256, "research-runner-v0"))
        validate_prediction_bundle(bundle, manifest=manifest)
        frozen.append({"scope": asdict(scope), "bundle_id": bundle.bundle_id,
                       "outputs": [asdict(o) for o in outputs]})
    return FrozenPredictions(canonical_bytes({
        "schema": "research-predictions-v0",
        "manifest_sha256": manifest_sha256,
        "configuration_sha256": configuration_sha256,
        "ocr_sha256_by_receipt": ocr_hashes,
        **({"held_out_freeze_sha256": approved_held_out_sha256} if held_out_freeze is not None else {}),
        "methods": frozen,
    }))
