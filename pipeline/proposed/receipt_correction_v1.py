"""Candidate evidence and development recommendations from a stored B2 receipt."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from itertools import islice

from pipeline.baseline_b3 import (
    ArithmeticDiagnostic, B3ParseState, B3Result, _WEIGHT_DENOMINATOR_RE,
    _source_currency_markers, apply_b3, parse_generic_date, parse_money,
)
from pipeline.contracts import (
    FieldStatus, OcrSourceToken, PreResolutionDisposition, ReceiptFieldName as Name,
    ReceiptOutput, StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.adapter import adapt_b2_to_proposed
from pipeline.proposed.candidate_deduplication import (
    NormalizationParseStatusV0, normalize_candidate_value,
)
from pipeline.proposed.candidate_ranking import _make_similarity
from pipeline.proposed.contracts import (
    FEATURE_SLOT_ORDER, CandidateAuditStatus as Audit, CandidateLimitStatus as Limit,
    CandidateSourceKind as Kind, FeatureSlot, SourceCharacterSpanV1,
)
from pipeline.proposed.purchase_date_correction_v0 import (
    PurchaseDateCorrectionOutcomeV0, PurchaseDateCorrectionResultV0, correct_purchase_date_v0,
)
from pipeline.proposed.purchase_date_source_contracts_v1 import DateObservationKindV1
from pipeline.proposed.receipt_context_v1 import (
    CONTRADICTION, EXACT, EXCEPTION, MATCH, NUMERIC, associated_split_date, check_arithmetic,
    find_receipt_anchors, has_promotion, ordered_fields, replace_fields, weight_state,
)
from pipeline.proposed.receipt_resources_v1 import PriceBasis, PromotionScope, ReceiptResources, text_key
from pipeline.proposed.suspicion import SuspicionReasonCode as Suspicion

VERSION = "receipt-correction-development-v1"
_MAX_TEXT = 256
_PRIORITY = {kind: index for index, kind in enumerate(Kind)}
_MONEY = NUMERIC - {Name.QUANTITY}


class Recommendation(str, Enum):
    CORRECT = "CORRECT"
    RETAIN = "RETAIN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class PriceStatus(str, Enum):
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
    PRICE_INCONCLUSIVE = "PRICE_INCONCLUSIVE"
    PRICE_SUPPORTED = "PRICE_SUPPORTED"
    PRICE_CONFLICT = "PRICE_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = PRICE_UNAVAILABLE
    AGREES = PRICE_SUPPORTED
    IMPLAUSIBLE = PRICE_CONFLICT


@dataclass(frozen=True, slots=True)
class ReceiptMethodConfig:
    candidate_limit: int = 4
    proposal_limit: int = 24
    confidence_floor: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        if (type(self.candidate_limit) is not int or type(self.proposal_limit) is not int
                or not 1 <= self.candidate_limit <= self.proposal_limit <= 128):
            raise ValueError("Candidate and proposal limits must be ordered positive integers up to 128.")
        floor = self.confidence_floor
        if not isinstance(floor, Decimal) or not floor.is_finite() or not 0 <= floor <= 1:
            raise ValueError("Confidence floor must be in [0, 1].")


@dataclass(frozen=True, slots=True)
class CandidateOrigin:
    kind: Kind
    reference: str
    observed_value: str | None
    token_ids: tuple[str, ...] = ()
    spans: tuple[SourceCharacterSpanV1, ...] = ()
    event_ids: tuple[str, ...] = ()
    resource_reference: str | None = None
    displacement: int | None = None


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    slot: FeatureSlot
    value: Decimal | None
    references: tuple[str, ...] = ()
    missing_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PriceEvidence:
    status: PriceStatus
    reason: str
    resource_reference: str | None = None
    entry_ids: tuple[str, ...] = ()
    rule_id: str | None = None
    actual_myr: Decimal | None = None
    basis: PriceBasis | None = None
    band_myr: tuple[Decimal, Decimal] | None = None
    source_token_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReceiptCandidate:
    candidate_id: str
    value: str | None
    normalized_key: str | None
    provenance: tuple[CandidateOrigin, ...]
    limit_status: Limit = Limit.RETAINED
    audit_status: Audit | None = None
    constraint_reasons: tuple[str, ...] = ()
    arithmetic: tuple[ArithmeticDiagnostic, ...] = ()
    features: tuple[EvidenceValue, ...] | None = None
    price: PriceEvidence | None = None
    replacement_support: tuple[str, ...] = ()
    preliminary_rank: int | None = None
    similarity: Decimal | None = None
    displacement: int | None = None
    output_value: str | None = None
    output_token_ids: tuple[str, ...] = ()

    @property
    def missing_mask(self) -> tuple[bool, ...] | None:
        return None if self.features is None else tuple(slot.value is None for slot in self.features)


@dataclass(frozen=True, slots=True)
class ReceiptFieldEvidence:
    original: StructuredField
    suspicion: tuple[Suspicion, ...]
    candidates: tuple[ReceiptCandidate, ...]
    recommendation: Recommendation
    reason: str
    recommended_candidate_id: str
    pre_review_preview: StructuredField
    proposal_limit_exceeded: bool = False

    @property
    def c0(self) -> ReceiptCandidate:
        return self.candidates[0]


@dataclass(frozen=True, slots=True)
class CandidateScoringInput:
    receipt_id: str
    field_id: str
    item_row_id: str | None
    field_name: Name
    candidate_id: str
    c0_candidate_id: str
    values: tuple[Decimal | None, ...]
    missing_mask: tuple[bool, ...]
    replacement_support: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReceiptCorrectionResult:
    baseline: B2ExtractionResult
    b3: B3Result
    fields: tuple[ReceiptFieldEvidence, ...]
    preview: ReceiptOutput | None
    purchase_date_trace: PurchaseDateCorrectionResultV0 | None
    config: ReceiptMethodConfig
    resource_references: tuple[str, ...]
    region: str | None
    version: str = VERSION

    @property
    def fallback_disposition(self) -> PreResolutionDisposition | None:
        return self.baseline.pre_resolution_disposition

    def scoring_inputs(self) -> tuple[CandidateScoringInput, ...]:
        """Emit admitted candidates in receipt field order and then candidate order."""
        return tuple(
            CandidateScoringInput(
                field.original.receipt_id, field.original.field_id, field.original.item_row_id,
                field.original.field_name, candidate.candidate_id, field.c0.candidate_id,
                tuple(slot.value for slot in candidate.features), candidate.missing_mask,
                candidate.replacement_support,
            )
            for field in self.fields for candidate in field.candidates
            if candidate.audit_status is Audit.SCORING_ELIGIBLE
        )


@dataclass(frozen=True, slots=True)
class _Context:
    output: ReceiptOutput
    b3: B3Result
    config: ReceiptMethodConfig
    resources: ReceiptResources
    region: str | None
    tokens: dict[str, OcrSourceToken]
    cross_row_token_ids: frozenset[str]
    purchased: date | None = None
    retailer: str | None = None


def _confidence(value) -> Decimal | None:
    if value is None:
        return None
    confidence = Decimal(str(value))
    return confidence if 0 <= confidence <= 1 else None


def _ocr_confidence(ids, tokens) -> Decimal | None:
    values = tuple(_confidence(tokens[token_id].raw_confidence) for token_id in ids)
    return min(values) if values and all(value is not None for value in values) else None


def _normalize(field, value):
    return normalize_candidate_value(field_name=field.field_name, exact_value=value)


def _key(field, value):
    if value is None:
        return None
    if field.field_name in (Name.STORE_NAME, Name.ITEM_DESCRIPTION):
        return text_key(value)
    if field.field_name in _MONEY:
        parsed = parse_money(value)
        if parsed.state is B3ParseState.VALID:
            currency = "$" if parsed.currency_marker == "$" else "MYR"
            return f"{currency}:{parsed.normalized_value}"
    return _normalize(field, value).normalized_key


def _valid(field, value):
    if not value or not value.strip():
        return False
    if field.field_name in (Name.STORE_NAME, Name.ITEM_DESCRIPTION):
        return any(character.isalpha() for character in value)
    return _normalize(field, value).parse_status is NormalizationParseStatusV0.PARSED_VALID


def _render(field, value):
    if field.field_name in _MONEY:
        parsed = parse_money(value)
        return value if parsed.currency_marker == "$" else parsed.normalized_value or value
    if field.field_name is Name.QUANTITY and _valid(field, value):
        return _normalize(field, value).canonical_value
    return value


def _substitute(field, value, ids):
    return replace(field, value=value, source_token_ids=ids, status=FieldStatus.EXTRACTED,
                   unresolved_reason=None, confidence=None)


def _spans(ids, tokens):
    return tuple(SourceCharacterSpanV1(token_id, 0, len(tokens[token_id].original_text),
                                       tokens[token_id].original_text) for token_id in ids)


def _original(field, tokens, output_field=None):
    display = field if output_field is None else output_field
    origin = CandidateOrigin(Kind.ORIGINAL, field.field_id, field.value, field.source_token_ids,
                             _spans(field.source_token_ids, tokens))
    return ReceiptCandidate(f"{field.field_id}:c0", field.value, _key(field, field.value), (origin,),
                            output_value=display.value, output_token_ids=display.source_token_ids)



def _b3_origin(seed, field):
    ids = tuple(dict.fromkeys(span.token_id for span in seed.source_spans))
    return CandidateOrigin(
        seed.source_kind, seed.seed_id, seed.proposed_value, ids or field.source_token_ids,
        seed.source_spans, seed.b3_event_ids, displacement=0 if ids else None,
    )


def _suspicion(field, anchors, arithmetic, tokens, config, association_conflict=False):
    ocr = _ocr_confidence(field.source_token_ids, tokens)
    extractor = _confidence(field.confidence)
    original_key = _key(field, field.value)
    checks = {
        Suspicion.LOW_OCR_CONFIDENCE: ocr is not None and ocr < config.confidence_floor,
        Suspicion.LOW_EXTRACTOR_CONFIDENCE: extractor is not None and extractor < config.confidence_floor,
        Suspicion.MISSING_REQUIRED_CONTENT: field.value is None,
        Suspicion.PARSE_TYPE_FAILURE: field.value is not None and not _valid(field, field.value),
        Suspicion.LINE_ASSOCIATION_CONFLICT: association_conflict or field.status is FieldStatus.UNRESOLVED or any(
            _key(field, anchor.span.text) != original_key for anchor in anchors
        ),
        Suspicion.ARITHMETIC_CONTRADICTION: any(check.outcome in CONTRADICTION for check in arithmetic),
    }
    return tuple(reason for reason in Suspicion if checks[reason])


def _proposals(field, anchors, seeds, terminology, retailer, tokens):
    for anchor in anchors:
        span = anchor.span
        spans = (span,) if anchor.label_span is None else (anchor.label_span, span)
        yield span.text, CandidateOrigin(
            Kind.SOURCE_TOKEN_OR_NEIGHBOUR, f"{span.token_id}:explicit-{field.field_name.value}",
            span.text, tuple(part.token_id for part in spans), spans, displacement=anchor.displacement,
        )
    for seed in seeds:
        yield seed.proposed_value, _b3_origin(seed, field)
    if terminology is None or field.value is None:
        return
    entries = terminology.match(field.field_name, field.value, retailer)
    for kind in (Kind.RETAILER_MAPPING, Kind.PANTRY_TERMINOLOGY):
        for entry in entries:
            if entry.source_kind is not kind or text_key(entry.literal) != text_key(field.value):
                continue
            yield entry.receipt_value, CandidateOrigin(
                kind, entry.entry_id, field.value, field.source_token_ids,
                _spans(field.source_token_ids, tokens), resource_reference=terminology.reference,
                displacement=0,
            )


def _gather(field, c0, anchors, seeds, terminology, retailer, tokens, config):
    # Price evidence is absent from proposal generation and preliminary rank.
    groups = defaultdict(list)
    proposals = _proposals(field, anchors, seeds, terminology, retailer, tokens)
    collected = list(islice(proposals, config.proposal_limit + 1))
    exceeded = len(collected) > config.proposal_limit
    for value, origin in collected[:config.proposal_limit]:
        if len(value) <= _MAX_TEXT:
            groups[_key(field, value)].append((value, origin))
        else:
            exceeded = True

    def ordered(members):
        return sorted(members, key=lambda pair: (
            _PRIORITY[pair[1].kind], pair[1].displacement is None,
            pair[1].displacement or 0, pair[0], pair[1].reference,
        ))

    equivalent = ordered(groups.pop(c0.normalized_key, ()))
    c0 = replace(c0, provenance=(*c0.provenance, *(origin for _, origin in equivalent)))
    ranked = []
    for key, members in groups.items():
        members = ordered(members)
        value, first = members[0]
        origins = tuple(dict.fromkeys(origin for _, origin in members))
        similarity = _similarity(field.value, value)
        sort_key = (_PRIORITY[first.kind], -(similarity or Decimal(0)), first.displacement is None,
                    first.displacement or 0, text_key(value), key, value)
        digest = sha256(key.encode("utf-8")).hexdigest()
        # A raw literal may share a candidate group with a lexicon entry. Only
        # the primary source family supplies the replacement's output linkage.
        ids = tuple(dict.fromkeys(token_id for origin in origins if origin.kind is first.kind
                                  for token_id in origin.token_ids))
        ranked.append((sort_key, ReceiptCandidate(
            f"{field.field_id}:candidate:{digest}", value, key, origins,
            similarity=similarity, displacement=first.displacement,
            output_value=_render(field, value), output_token_ids=ids,
        )))
    ranked.sort(key=lambda pair: pair[0])
    return (c0, *(replace(
        candidate, preliminary_rank=rank,
        limit_status=Limit.RETAINED if rank < config.candidate_limit else Limit.LIMIT_OVERFLOW,
    ) for rank, (_, candidate) in enumerate(ranked, 1))), exceeded


def _similarity(original, value):
    if original is None or len(original) > _MAX_TEXT:
        return None
    left, right = text_key(original), text_key(value)
    return _make_similarity(left, right).decimal_value if left and right else None


def _price(context, field, candidate_field, row_index):
    if row_index is None:
        return PriceEvidence(PriceStatus.NOT_APPLICABLE, "NOT_AN_ITEM_FIELD")
    prices, rule = context.resources.prices, context.resources.discrepancy_rule
    if prices is None:
        return PriceEvidence(PriceStatus.PRICE_UNAVAILABLE, "PRICE_SNAPSHOT_UNAVAILABLE")

    def missing(reason, *, ids=(), invoice_ids=(), status=PriceStatus.PRICE_UNAVAILABLE):
        return PriceEvidence(status, reason, prices.reference, ids, rule.rule_id,
                             source_token_ids=invoice_ids)

    def inconclusive(reason, *, ids=(), invoice_ids=()):
        return missing(reason, ids=ids, invoice_ids=invoice_ids, status=PriceStatus.PRICE_INCONCLUSIVE)

    if context.retailer is None or context.purchased is None or context.region is None:
        return missing("RETAILER_DATE_OR_REGION_UNRESOLVED")
    row = context.output.items[row_index]
    description = candidate_field if field.field_name is Name.ITEM_DESCRIPTION else row.description
    price = candidate_field if field.field_name is Name.UNIT_PRICE else row.unit_price
    if description.value is None:
        return missing("ITEM_DESCRIPTION_MISSING")
    if price.value is None:
        return missing("UNIT_PRICE_MISSING")
    if has_promotion(context.output, row_index):
        return inconclusive("ITEM_PROMOTION", invoice_ids=price.source_token_ids)
    row_ids = tuple(dict.fromkeys(token_id for item in row.fields for token_id in item.source_token_ids))
    if any(a.source_slice.token_id in row_ids for a in context.b3.adjustments):
        return inconclusive("ITEM_ADJUSTMENT", invoice_ids=price.source_token_ids)
    weight = weight_state(context.output, row_index)
    if weight not in ("NONE", "MATCHED"):
        return inconclusive("WEIGHT_BASIS_UNRESOLVED", invoice_ids=price.source_token_ids)
    basis = PriceBasis.EACH
    if weight == "MATCHED":
        aliases = {"kg": PriceBasis.KG, "g": PriceBasis.G, "lb": PriceBasis.LB,
                   "lbs": PriceBasis.LB, "oz": PriceBasis.OZ}
        observed = {aliases[match["unit"].casefold()] for token_id in row_ids for match in
                    _WEIGHT_DENOMINATOR_RE.finditer(context.tokens[token_id].original_text)}
        if len(observed) != 1 or (field.field_name in (Name.QUANTITY, Name.UNIT_PRICE)
                                  and candidate_field.value != field.value):
            return inconclusive("WEIGHT_BASIS_UNRESOLVED", invoice_ids=price.source_token_ids)
        basis = next(iter(observed))

    parsed = parse_money(price.value)
    if (parsed.state is not B3ParseState.VALID or parsed.currency_marker == "$"
            or any(marker != "MYR" for marker in _source_currency_markers(context.output, price))):
        return inconclusive("UNIT_PRICE_OR_CURRENCY_UNRESOLVED", invoice_ids=price.source_token_ids)
    matches = context.resources.terminology.match(Name.ITEM_DESCRIPTION, description.value, context.retailer)
    products = {entry.product_key for entry in matches if entry.product_key is not None}
    if not products:
        return missing("ITEM_PRODUCT_UNRESOLVED")
    if len(products) > 1:
        return inconclusive("ITEM_PRODUCT_AMBIGUOUS", invoice_ids=price.source_token_ids)
    bands = prices.match(context.retailer, next(iter(products)), context.region, context.purchased, basis)
    if not bands:
        return missing("NO_MATCHING_PRICE", invoice_ids=price.source_token_ids)
    if len(bands) > 1:
        return inconclusive("AMBIGUOUS_PRICE_REFERENCE", ids=tuple(entry.entry_id for entry in bands),
                            invoice_ids=price.source_token_ids)

    band, = bands
    if rule.compare(parsed.decimal_value, band):
        status, reason = PriceStatus.PRICE_SUPPORTED, "WITHIN_CONFIGURED_BAND"
    elif band.promotion_scope is PromotionScope.UNSPECIFIED:
        status, reason = PriceStatus.PRICE_INCONCLUSIVE, "REFERENCE_PROMOTION_UNSPECIFIED"
    else:
        status, reason = PriceStatus.PRICE_CONFLICT, "OUTSIDE_CONFIGURED_BAND"
    return PriceEvidence(
        status, reason, prices.reference, (band.entry_id,), rule.rule_id, parsed.decimal_value, basis,
        (band.low_myr, band.high_myr), price.source_token_ids,
    )



def _features(context, field, candidate, candidate_field, arithmetic, price):
    ids = candidate_field.source_token_ids
    retailer_refs = [
        reference for origin in candidate.provenance if origin.kind is Kind.RETAILER_MAPPING
        for reference in (origin.resource_reference, origin.reference)
    ]
    terminology = context.resources.terminology
    if terminology is not None and field.field_name in (Name.STORE_NAME, Name.ITEM_DESCRIPTION):
        retailer = (terminology.retailer_id(candidate_field.value)
                    if field.field_name is Name.STORE_NAME else context.retailer)
        for entry in terminology.match(field.field_name, candidate_field.value, retailer):
            if entry.source_kind is Kind.RETAILER_MAPPING and (
                text_key(entry.receipt_value) == text_key(candidate_field.value)
            ):
                retailer_refs.extend((terminology.reference, entry.entry_id))
    retailer_refs = tuple(dict.fromkeys(retailer_refs))
    checkable = tuple(check for check in arithmetic if check.outcome in MATCH | CONTRADICTION)
    inputs = (
        (_ocr_confidence(ids, context.tokens), ids, "OCR_CONFIDENCE_MISSING"),
        (_confidence(field.confidence), (field.field_id,), "EXTRACTOR_CONFIDENCE_MISSING"),
        (Decimal(1) if candidate.candidate_id.endswith(":c0") else candidate.similarity,
         (field.field_id,), "ORIGINAL_SURFACE_UNAVAILABLE"),
        (Decimal(1) if ids else None, ids, "FIELD_ASSOCIATION_UNAVAILABLE"),
        (Decimal(1) if retailer_refs else None, retailer_refs,
         "RETAILER_SNAPSHOT_UNAVAILABLE" if context.resources.terminology is None
         else "NO_APPLICABLE_RETAILER_SUPPORT"),
        (Decimal(int(all(check.outcome in MATCH for check in checkable))) if checkable else None,
         tuple(check.diagnostic_id for check in arithmetic),
         "ARITHMETIC_EXCEPTION" if any(check.outcome in EXCEPTION for check in arithmetic)
         else "ARITHMETIC_NOT_APPLICABLE_OR_INCOMPLETE"),
        (Decimal(1) if price.status is PriceStatus.PRICE_SUPPORTED else
         Decimal(0) if price.status is PriceStatus.PRICE_CONFLICT else None,
         () if price.resource_reference is None else (price.resource_reference, *price.entry_ids),
         price.reason),
    )
    return tuple(EvidenceValue(slot, value, refs, reason if value is None else None)
                 for slot, (value, refs, reason) in zip(FEATURE_SLOT_ORDER, inputs, strict=True))


def _audit(context, field, candidate, row_index, anchors, c0):
    if candidate.limit_status is Limit.LIMIT_OVERFLOW:
        return candidate
    reasons = []
    original = candidate is c0
    candidate_field = field
    if not _valid(field, candidate.value):
        reasons.append("MISSING_VALUE" if candidate.value is None else "FIELD_TYPE_INVALID")
    if not original:
        if not candidate.output_token_ids:
            reasons.append("SOURCE_UNSUPPORTED")
        elif candidate.value and candidate.value.strip():
            candidate_field = _substitute(field, candidate.value, candidate.output_token_ids)
    if context.cross_row_token_ids.intersection(candidate_field.source_token_ids):
        reasons.append("CROSS_ROW_SOURCE_ASSOCIATION")
    arithmetic = check_arithmetic(context.output, candidate_field, context.b3.adjustments,
                                  row_index=row_index)
    if any(check.outcome in CONTRADICTION for check in arithmetic):
        reasons.append("ARITHMETIC_CONTRADICTION")
    anchor_keys = {_key(field, anchor.span.text) for anchor in anchors}
    if anchor_keys - {candidate.normalized_key}:
        reasons.append("EXPLICIT_SOURCE_CONFLICT")

    support = ()
    if not original:
        direct = any(origin.kind is Kind.SOURCE_TOKEN_OR_NEIGHBOUR for origin in candidate.provenance)
        if field.field_name in NUMERIC:
            if direct and arithmetic and arithmetic[0].outcome in EXACT:
                support = ("ROLE_BOUND_SOURCE", "EXACT_RECEIPT_ARITHMETIC")
            else:
                reasons.append("NO_DIRECT_SOURCE_AND_EXACT_ARITHMETIC_SUPPORT")
        elif direct:
            support = ("ROLE_BOUND_SOURCE",)
        else:
            support = tuple(dict.fromkeys(origin.kind.value for origin in candidate.provenance
                                          if origin.kind in (Kind.RETAILER_MAPPING, Kind.PANTRY_TERMINOLOGY)))
        if not support and not reasons:
            reasons.append("NO_NON_PRICE_REPLACEMENT_SUPPORT")
    if reasons:
        return replace(candidate, audit_status=Audit.CONSTRAINT_REJECTED,
                       constraint_reasons=tuple(reasons), arithmetic=arithmetic)
    if field.field_name is Name.ITEM_DESCRIPTION and row_index is not None:
        row = context.output.items[row_index]
        arithmetic = check_arithmetic(context.output, row.quantity, context.b3.adjustments,
                                      row_index=row_index)
    price = _price(context, field, candidate_field, row_index)
    return replace(candidate, audit_status=Audit.SCORING_ELIGIBLE,
                   arithmetic=arithmetic, replacement_support=support, price=price,
                   features=_features(context, field, candidate, candidate_field, arithmetic, price))


def _decide(field, suspicion, candidates, exceeded, conflict):
    c0, *alternatives = candidates
    eligible = tuple(candidate for candidate in alternatives if candidate.audit_status is Audit.SCORING_ELIGIBLE)
    choice, preview = c0, field
    recommendation = Recommendation.REVIEW_REQUIRED
    if exceeded:
        reason = "PROPOSAL_LIMIT_EXCEEDED"
    elif conflict or len(eligible) > 1:
        reason = "CONFLICTING_NON_PRICE_EVIDENCE"
    elif len(eligible) == 1:
        choice, = eligible
        preview = _substitute(field, choice.output_value, choice.output_token_ids)
        recommendation, reason = Recommendation.CORRECT, "UNIQUE_NON_PRICE_SUPPORTED_ALTERNATIVE"
    elif c0.audit_status is Audit.SCORING_ELIGIBLE and (
        not suspicion or any(origin.kind is Kind.SOURCE_TOKEN_OR_NEIGHBOUR for origin in c0.provenance)
    ):
        recommendation, reason = Recommendation.RETAIN, "ORIGINAL_SUPPORTED"
        if c0.output_value != field.value:
            preview = replace(field, value=c0.output_value)
    else:
        reason = "NO_SUPPORTED_ALTERNATIVE" if field.value is not None else "FIELD_VALUE_UNAVAILABLE"
    return ReceiptFieldEvidence(field, suspicion, candidates, recommendation, reason,
                                choice.candidate_id, preview, exceeded)


def _regular_field(context, field, row_index, anchors, seeds):
    generic = next((seed for seed in seeds if seed.source_kind is Kind.GENERIC_NORMALIZATION
                    and _key(field, seed.proposed_value) == _key(field, field.value)), None)
    c0 = _original(field, context.tokens)
    if generic is not None:
        c0 = replace(c0, output_value=generic.proposed_value)
    checks = check_arithmetic(context.output, field, context.b3.adjustments, row_index=row_index)
    suspicion = _suspicion(
        field, anchors, checks, context.tokens, context.config,
        bool(context.cross_row_token_ids.intersection(field.source_token_ids)),
    )
    terminology = context.resources.terminology
    retailer = context.retailer
    if field.field_name is Name.STORE_NAME and terminology is not None:
        retailer = terminology.retailer_id(field.value)
    if suspicion:
        candidates, exceeded = _gather(field, c0, anchors, seeds, terminology, retailer,
                                       context.tokens, context.config)
    else:
        if generic is not None:
            c0 = replace(c0, provenance=(*c0.provenance, _b3_origin(generic, field)))
        candidates, exceeded = (c0,), False
    audited = tuple(_audit(context, field, candidate, row_index, anchors, candidates[0])
                    for candidate in candidates)
    explicit_values = {_key(field, anchor.span.text) for anchor in anchors}
    term_values = {candidate.normalized_key for candidate in candidates if any(
        origin.kind in (Kind.RETAILER_MAPPING, Kind.PANTRY_TERMINOLOGY)
        for origin in candidate.provenance
    )}
    return _decide(field, suspicion, audited, exceeded, len(explicit_values | term_values) > 1
                   or any(candidate.limit_status is Limit.LIMIT_OVERFLOW for candidate in candidates))


def _date_field(context, field, b3_field, trace):
    c0 = _original(field, context.tokens, b3_field)
    suspicion = trace.suspicion.reasons if trace.suspicion is not None else _suspicion(
        field, (), (), context.tokens, context.config,
    )

    def project(record, status, result=None, vector=None):
        origins = tuple(CandidateOrigin(
            origin.source_kind, origin.provenance_id, origin.original_observed_value,
            origin.source_token_ids, origin.source_spans, resource_reference=origin.resource_snapshot_id,
        ) for origin in record.provenance)
        original = record.candidate_id == c0.candidate_id
        slots = None if vector is None else tuple(EvidenceValue(
            slot.slot, slot.value if isinstance(slot.value, Decimal) else None,
            slot.provenance_references, slot.reason.value if slot.reason is not None else None,
        ) for slot in vector.slot_values)
        reasons = () if result is None or vector is not None else (result.aggregate_reason.value,)
        ids = field.source_token_ids if original else tuple(dict.fromkeys(
            token_id for origin in origins for token_id in origin.token_ids
        ))
        return ReceiptCandidate(
            record.candidate_id, record.value, record.normalized_dedup_key, origins, status,
            None if result is None else (Audit.SCORING_ELIGIBLE if vector is not None
                                         else Audit.CONSTRAINT_REJECTED),
            reasons, features=slots, output_value=c0.output_value if original else record.value,
            output_token_ids=ids,
            replacement_support=("EXPLICIT_DATE_ANCHOR",) if (
                trace.recommendation is not None and trace.recommendation.preferred is record
                and not original
            ) else (),
        )

    if trace.features is not None:
        features = trace.features
        eligible = {vector.candidate.candidate_id: vector for vector in features.candidate_features}
        candidates = tuple(project(
            result.candidate, Limit.RETAINED, result, eligible.get(result.candidate.candidate_id),
        ) for result in features.constraint_results)
        candidates += tuple(project(record, Limit.LIMIT_OVERFLOW) for record in
                            features.operand_audit.hard_constraint_input.finalization_result.overflow_records)
        c0 = candidates[0]
    else:
        c0 = replace(c0, audit_status=Audit.CONSTRAINT_REJECTED, constraint_reasons=(trace.reason,))
        candidates = (c0,)

    split = None
    reason = trace.reason
    if reason == "AMBIGUOUS_DATE_ANCHORS" and trace.recommendation is not None:
        anchors = trace.recommendation.anchors
        if len(anchors) == 1 and anchors[0].observation_kind is DateObservationKindV1.ANCHOR_ONLY:
            split = associated_split_date(context.output, anchors[0].source_token.token_id)
        if split is not None and c0.features is not None:
            ids = tuple(token.token_id for token in split)
            origin = CandidateOrigin(Kind.SOURCE_TOKEN_OR_NEIGHBOUR, "B2_SPLIT_DATE_LABEL",
                                     field.value, ids, _spans(ids, context.tokens))
            slots = tuple(
                EvidenceValue(value.slot, Decimal(1), ids)
                if value.slot is FeatureSlot.LAYOUT_AGREEMENT else value for value in c0.features
            )
            c0 = replace(c0, provenance=(*c0.provenance, origin), features=slots)
            candidates = (c0, *candidates[1:])
            suspicion = tuple(item for item in suspicion if item is not Suspicion.LINE_ASSOCIATION_CONFLICT)
            reason = "SPLIT_DATE_LABEL_CONFIRMS_ORIGINAL"
    if trace.outcome is PurchaseDateCorrectionOutcomeV0.CORRECT:
        recommendation = Recommendation.CORRECT
        preview = trace.final_output.purchase_date
        choice = trace.recommendation.preferred.candidate_id
    elif (split is not None and c0.features is not None
          or trace.outcome is PurchaseDateCorrectionOutcomeV0.PRESERVE or not suspicion
          and trace.reason == "NO_DATE_ANCHOR" and c0.audit_status is Audit.SCORING_ELIGIBLE):
        recommendation, preview, choice = Recommendation.RETAIN, b3_field, c0.candidate_id
    else:
        recommendation, preview, choice = Recommendation.REVIEW_REQUIRED, field, c0.candidate_id
    return ReceiptFieldEvidence(field, suspicion, candidates, recommendation, reason, choice, preview)



def conflicting_numeric_changes(output, adjustments, fields, changed_ids, *, require_exact=False):
    """Return changed field IDs that cannot coexist under shared receipt equations."""
    corrected = {field_id for field_id in changed_ids if fields[field_id].field_name in NUMERIC}
    rejected = set()
    while corrected - rejected:
        combined = replace_fields(output, {
            field_id: field for field_id, field in fields.items()
            if field_id not in rejected
        })
        additions = set()
        row_by_id = {row.row_id: index for index, row in enumerate(combined.items)}
        for field_id in corrected - rejected:
            field = fields[field_id]
            checks = check_arithmetic(combined, field, adjustments,
                                      row_index=row_by_id.get(field.item_row_id))
            if require_exact and (not checks or checks[0].outcome not in EXACT):
                additions.add(field_id)
            for position, check in enumerate(checks):
                if check.outcome in CONTRADICTION or (position == 0 and check.outcome in EXCEPTION):
                    additions.update(corrected.intersection(check.field_ids))
        if not additions - rejected:
            break
        rejected.update(additions)
    return rejected


def _reconcile(context, decisions):
    rejected = conflicting_numeric_changes(
        context.output, context.b3.adjustments,
        {decision.original.field_id: decision.pre_review_preview for decision in decisions},
        {decision.original.field_id for decision in decisions if decision.recommendation is Recommendation.CORRECT},
    )
    return tuple(replace(
        decision, recommendation=Recommendation.REVIEW_REQUIRED, reason="JOINT_ARITHMETIC_CONFLICT",
        recommended_candidate_id=decision.c0.candidate_id, pre_review_preview=decision.original,
    ) if decision.original.field_id in rejected else decision for decision in decisions)


def correct_receipt_v1(
    baseline: B2ExtractionResult, *, resources: ReceiptResources = ReceiptResources(),
    config: ReceiptMethodConfig = ReceiptMethodConfig(), region: str | None = None,
) -> ReceiptCorrectionResult:
    """Build field evidence and a development preview from one stored B2 result.

    The B2 source gate has already run. A recorded fallback is passed through.
    Unexpected processing errors propagate for the caller to record.
    """
    b3 = apply_b3(baseline)
    adapter = adapt_b2_to_proposed(baseline, b3)
    references = tuple(snapshot.reference for snapshot in (resources.terminology, resources.prices)
                       if snapshot is not None)
    if resources.discrepancy_rule is not None:
        references += (resources.discrepancy_rule.reference,)
    output = baseline.receipt_output
    if output is None:
        return ReceiptCorrectionResult(baseline, b3, (), None, None, config, references, region)
    tokens = {token.token_id: token for token in output.source_evidence.tokens}
    token_rows = defaultdict(set)
    for field in ordered_fields(output):
        for token_id in field.source_token_ids:
            token_rows[token_id].add(field.item_row_id)
    cross_row = frozenset(token_id for token_id, rows in token_rows.items() if len(rows) > 1)
    context = _Context(output, b3, config, resources, region, tokens, cross_row)
    anchors = find_receipt_anchors(output)
    seeds = defaultdict(list)
    for seed in adapter.b3_seeds:
        seeds[seed.field_id].append(seed)

    def run(ctx, field, row_index=None):
        return _regular_field(ctx, field, row_index, anchors.get(field.field_id, ()),
                              seeds[field.field_id])

    store = run(context, output.store_name)
    date_trace = correct_purchase_date_v0(baseline, include_diagnostic_scores=False)
    purchase_date = _date_field(context, output.purchase_date, b3.receipt_output.purchase_date, date_trace)
    if store.recommendation is not Recommendation.REVIEW_REQUIRED and resources.terminology is not None:
        retailer = resources.terminology.retailer_id(store.pre_review_preview.value)
        context = replace(context, retailer=retailer)
    if purchase_date.recommendation is not Recommendation.REVIEW_REQUIRED:
        parsed = parse_generic_date(purchase_date.pre_review_preview.value)
        if parsed.state is B3ParseState.VALID:
            context = replace(context, purchased=date.fromisoformat(parsed.normalized_value))
    decisions = _reconcile(context, (
        store, purchase_date,
        *(run(context, field, index) for index, row in enumerate(output.items) for field in row.fields),
        run(context, output.receipt_total),
    ))
    preview = replace_fields(output, {decision.original.field_id: decision.pre_review_preview
                                      for decision in decisions})
    return ReceiptCorrectionResult(baseline, b3, decisions, replace(preview, extractor_version=VERSION),
                                   date_trace, config, references, region)

