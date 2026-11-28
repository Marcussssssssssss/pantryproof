"""Project retained operational evidence into the negotiated review response."""

from decimal import Decimal
import json

from pipeline.contracts import PolicyState
from pipeline.presentation_v1 import conformance as v1
from pipeline.presentation_v1.b2_synthetic_projection_v0 import _aliases
from pipeline.presentation_v1.local_image_projection_v0 import (
    LocalImageProjectionError, _automatic_output, project_retained_local_image_presentation_v1,
)
from pipeline.presentation_v1.review_conformance import (
    METHOD, METHOD_VERSION, _CODE, canonical_value, decode_and_validate_receipt_review_v1,
)
from pipeline.proposed.contracts import CandidateLimitStatus, FeatureSlot
from pipeline.proposed.receipt_research_v1 import ResearchMethodState

_PRICE_REASONS = {
    "REFERENCE_PROMOTION_UNSPECIFIED": "PROMOTION_SCOPE_UNSPECIFIED",
    "AMBIGUOUS_PRICE_REFERENCE": "AMBIGUOUS_PRICE_BAND",
}


def _public_reason(value):
    if isinstance(value, str):
        value = _PRICE_REASONS.get(value, value)
        if _CODE.fullmatch(value) and not v1._reason_has_unsafe_provenance(value):
            return value
    return "DETAIL_UNAVAILABLE"


def _money(value):
    if value is None:
        return None
    text = format(value, ".2f")
    if Decimal(text) != value:
        raise LocalImageProjectionError("Price evidence is outside the approved decimal grammar.")
    return text


def _price(candidate, field, tokens, *, reverted=False):
    price = candidate.price
    if price is None:
        if reverted:
            status, reason = "PRICE_INCONCLUSIVE", "PRICE_CONTEXT_CHANGED"
        elif field.item_row_id is not None:
            status, reason = "PRICE_UNAVAILABLE", "PRICE_NOT_ASSESSED"
        else:
            status, reason = "NOT_APPLICABLE", "NOT_AN_ITEM_FIELD"
        return {"status": status, "reason": reason, "observedUnitPriceMyr": None, "priceBasis": None,
                "bandLowMyr": None, "bandHighMyr": None, "ruleId": None, "resourceReference": None,
                "entryIds": [], "sourceTokenIds": []}
    low, high = price.band_myr or (None, None)
    return {
        "status": "PRICE_INCONCLUSIVE" if reverted else price.status.value,
        "reason": "PRICE_CONTEXT_CHANGED" if reverted else _public_reason(price.reason),
        "observedUnitPriceMyr": _money(price.actual_myr),
        "priceBasis": price.basis.value if price.basis else None,
        "bandLowMyr": _money(low), "bandHighMyr": _money(high), "ruleId": price.rule_id,
        "resourceReference": price.resource_reference, "entryIds": price.entry_ids,
        "sourceTokenIds": [tokens[t] for t in price.source_token_ids],
    }


def _retailer(candidate, field, terminology):
    if field.field_name.value not in ("ITEM_DESCRIPTION", "STORE_NAME"):
        return {"status": "NOT_APPLICABLE", "retailerId": None, "sourceReferences": [],
                "reason": "NOT_APPLICABLE_ROLE"}
    feature = next((f for f in candidate.features or () if f.slot is FeatureSlot.RETAILER_SUPPORT), None)
    if feature is None or feature.value is None or terminology is None:
        reason = (feature.missing_reason if feature is not None else "NO_APPLICABLE_RETAILER_SUPPORT")
        return {"status": "UNAVAILABLE", "retailerId": None, "sourceReferences": [],
                "reason": _public_reason(reason)}
    if terminology.reference not in feature.references:
        raise LocalImageProjectionError("Retailer support has no retained snapshot binding.")
    related = set(feature.references) - {terminology.reference}
    entries = [e for e in terminology.entries if e.entry_id in related]
    if not entries or {e.entry_id for e in entries} != related:
        raise LocalImageProjectionError("Retailer support has no matching retained entries.")
    keys = {e.retailer_id for e in entries}
    return {"status": "SUPPORTED", "retailerId": next(iter(keys)) if len(keys) == 1 else None,
            "sourceReferences": [{"resourceReference": terminology.reference, "entryId": entry.entry_id}
                                 for entry in entries],
            "reason": "RETAILER_MAPPING_MATCHED"}


def _probability(value):
    return {"calibratedProbability": value, "probabilityAvailable": value is not None}


def _alternative(candidate, alias, rank, field, evidence, terminology, tokens):
    status, probability = evidence.get(candidate.candidate_id, (None, None))
    status = "REJECTED_PRICE_ONLY" if status == "REJECTED_PRICE_ONLY" else candidate.audit_status.value
    role = field.field_name.value
    origins = []
    for i, source in enumerate(candidate.provenance, 1):
        origins.append({
            "sourceKind": source.kind.value,
            "reference": f"origin-{alias}-{i}",
            "observedValue": source.observed_value,
            "sourceTokenIds": [tokens[t] for t in source.token_ids],
            "characterSpans": [{"tokenId": tokens[s.token_id], "start": s.start, "end": s.end, "text": s.text}
                               for s in source.spans],
            "resourceReference": source.resource_reference,
        })
    return {
        "candidateId": alias, "value": candidate.value,
        "canonicalValue": canonical_value(role, candidate.value),
        "candidateStatus": status,
        "constraintReasons": list(dict.fromkeys(map(_public_reason, candidate.constraint_reasons))),
        "replacementSupport": candidate.replacement_support if status == "SCORING_ELIGIBLE" else [],
        "preliminaryRank": rank, "sourceTokenIds": [tokens[t] for t in candidate.output_token_ids],
        "sourceReferences": origins, **_probability(probability),
        "retailerEvidence": _retailer(candidate, field, terminology),
        "priceEvidence": _price(candidate, field, tokens),
    }


def _field(field, audit, wire, row_id, aliases, candidates, terminology, tokens):
    original, c0 = field.original, field.c0
    role = original.field_name.value
    verified = audit.verifier_result if audit else None
    evidence = {e.candidate_id: (e.status, e.probability) for e in verified.audit} if verified else {}
    c0_prob = evidence.get(c0.candidate_id, (None, None))[1]
    selected_id = audit.selected_candidate_id if audit else c0.candidate_id
    selected = next(c for c in candidates if c.candidate_id == selected_id)
    reason = _public_reason(audit.reason) if audit else "EMPIRICAL_POLICY_UNAVAILABLE"
    probability = audit.decision.correctness_probability if audit else None
    disposition = ("UNVERIFIED_DRAFT" if audit is None else
                   "AUTO_ACCEPTED" if audit.decision.state is PolicyState.AUTO_RESOLVED else "REVIEW_REQUIRED")
    recommendation = None
    if field.recommended_candidate_id in aliases:
        recommendation = {"recommendation": field.recommendation.value,
                          "recommendedCandidateId": aliases[field.recommended_candidate_id],
                          "reason": _public_reason(field.reason)}
    return {
        "fieldId": wire["fieldId"], "itemRowId": row_id, "role": role,
        "optionalWhenMissing": role == "UNIT_PRICE",
        "originalB2": {
            "c0CandidateId": aliases[c0.candidate_id], "status": original.status.value,
            "value": original.value, "canonicalValue": canonical_value(role, original.value),
            "absenceReason": original.unresolved_reason, "sourceTokenIds": [tokens[t] for t in original.source_token_ids],
            "nativeConfidence": original.confidence, "candidateStatus": c0.audit_status.value,
            "constraintReasons": list(dict.fromkeys(map(_public_reason, c0.constraint_reasons))),
            **_probability(c0_prob),
        },
        "selectedPreReview": {
            "candidateId": aliases[selected_id], "status": wire["status"],
            "value": wire["originalAutomaticValue"], "canonicalValue": wire["presentationValue"],
            "absenceReason": wire["absenceReason"], "sourceTokenIds": wire["sourceTokenIds"],
            "changedFromC0": selected_id != c0.candidate_id,
        },
        "fieldDisposition": disposition, "automaticCommitPermitted": disposition == "AUTO_ACCEPTED",
        **_probability(probability), "probabilityUnavailableReason": reason if probability is None else None,
        "unresolvedConflict": audit.unresolved_conflict if audit else None,
        "suspicionReasons": [s.value for s in field.suspicion], "correctionReason": reason,
        "developmentRecommendation": recommendation,
        "retailerEvidence": _retailer(selected, original, terminology),
        "priceEvidence": _price(selected, original, tokens, reverted=reason == "PRICE_CONTEXT_CHANGED"),
        "alternativeCandidates": [
            _alternative(c, aliases[c.candidate_id], rank, original, evidence, terminology, tokens)
            for rank, c in enumerate(candidates[1:], 1)
        ],
    }


def _pantry(row, wire, terminology, retailer):
    identities = {}
    if terminology is not None and row.description.value is not None:
        for entry in terminology.pantry_matches(row.description.value, retailer):
            identities.setdefault(entry.pantry_identity, {
                "entryId": entry.entry_id, "pantryIdentity": entry.pantry_identity,
                "pantryCategory": entry.pantry_category, "referenceUnit": entry.reference_unit,
                "resourceReference": terminology.reference,
            })
    values = list(identities.values())
    status = ("RESOURCE_UNAVAILABLE" if terminology is None else
              "UNRESOLVED" if not values else "MAPPED" if len(values) == 1 else "AMBIGUOUS")
    return {"rowId": wire["rowId"], "descriptionFieldId": wire["fields"][0]["fieldId"],
            "mappingStatus": status, "selectedIdentity": values[0] if len(values) == 1 else None,
            "candidateIdentities": values}


def _available(review, presentation, attempt, context, tokens, terminology):
    result = attempt.proposed
    output, _ = _automatic_output(attempt)
    if result is None or result.correction.baseline is not attempt.b2_result or output is None:
        raise LocalImageProjectionError("Review requires a retained seven-field result.")
    policy = result.state is ResearchMethodState.POLICY_APPLIED
    review.update(methodVersion=METHOD_VERSION, methodReadiness=result.state.value,
                  receiptDisposition=result.output.disposition.state.value if policy else "UNVERIFIED_DRAFT")
    originals = {f.original.field_id: f for f in result.correction.fields}
    audits = {a.decision.field_id: a for a in result.audits}
    if policy and originals.keys() != audits.keys():
        raise LocalImageProjectionError("Incomplete verification audit.")
    receipt = presentation["receipt"]
    top = zip((output.store_name, output.purchase_date, output.receipt_total), receipt["receiptFields"], strict=True)
    pairs = [(f, w, None) for f, w in top]
    for item, row in zip(output.items, receipt["itemRows"], strict=True):
        pairs.extend((f, w, row["rowId"]) for f, w in zip(item.fields, row["fields"], strict=True))
    ordinal = 0
    for field, wire, row_id in pairs:
        evidence = originals[field.field_id]
        candidates = tuple(c for c in evidence.candidates if c.limit_status is CandidateLimitStatus.RETAINED)
        aliases = {}
        for candidate in candidates:
            ordinal += 1
            aliases[candidate.candidate_id] = f"cand-v1-{context.alias_namespace}-{ordinal}"
        review["fields"].append(_field(evidence, audits.get(field.field_id), wire, row_id,
                                       aliases, candidates, terminology, tokens))
    retailer = terminology.retailer_id(output.store_name.value) if terminology is not None else None
    review["pantryMappings"] = [_pantry(item, wire, terminology, retailer)
                               for item, wire in zip(output.items, receipt["itemRows"], strict=True)]


def project_retained_local_image_review_v1(*, context, attempt, method, expected_dimensions):
    presentation_bytes = project_retained_local_image_presentation_v1(context=context, attempt=attempt)
    presentation = json.loads(presentation_bytes)
    outcome = presentation["outcome"]
    review = None
    if outcome["status"] != "PROCESSING_UNAVAILABLE":
        review = {"methodId": METHOD, "methodVersion": None, "methodReadiness": "NOT_EVALUATED",
                  "receiptDisposition": "FALLBACK_NO_UPDATE", "failure": None, "region": method.region,
                  "ocrEvidence": None, "fields": [], "pantryMappings": []}
        tokens = {}
        if attempt.adapted_source is not None and attempt.image_dimensions is not None:
            source_tokens = attempt.adapted_source.tokens
            width, height = attempt.image_dimensions
            tokens = _aliases(tuple(t.token_id for t in source_tokens), "tok", context.alias_namespace)
            review["ocrEvidence"] = {
                "coordinateFrame": {"origin": "TOP_LEFT", "unit": "SUBMITTED_IMAGE_PIXELS",
                                    "imageWidth": width, "imageHeight": height},
                "tokens": [{"tokenId": tokens[t.token_id], "originalText": t.original_text,
                            "polygon": [[p.x, p.y] for p in t.polygon], "rawConfidence": t.raw_confidence}
                           for t in source_tokens],
            }
        if outcome["status"] == "RESULT_AVAILABLE":
            _available(review, presentation, attempt, context, tokens, method.resources.terminology)
        elif outcome["status"] == "PROCESSING_FAILED":
            code = outcome["failure"]["code"]
            if code == "PRESENTATION_PROJECTION_FAILURE" and attempt.proposed_failure is not None:
                code = attempt.proposed_failure
            review.update(receiptDisposition="FAILED", failure={"stage": "PRE_RESOLUTION", "code": code})
            if code == "PROPOSED_CONFIGURATION_INVALID":
                review["methodReadiness"] = "NOT_VALID"
    review_bytes = json.dumps(review, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    result = (b'{"schemaName":"receipt-review","schemaVersion":"1","presentation":' +
              presentation_bytes + b',"review":' + review_bytes + b'}')
    decode_and_validate_receipt_review_v1(
        result, expected_request_id=context.request_id, expected_image_id=context.image_id, consumer_mode="LIVE",
        expected_image_width=expected_dimensions[0], expected_image_height=expected_dimensions[1],
    )
    return result
