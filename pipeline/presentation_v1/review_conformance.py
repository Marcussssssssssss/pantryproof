"""Strict receipt-review v1 decoding over the original UTF-8 response bytes."""

from dataclasses import dataclass
from decimal import Decimal
import json
import re
from typing import Mapping

from pipeline.presentation_v1 import conformance as v1

PRESENTATION_SCHEMA = "receipt-presentation-v1"
REVIEW_SCHEMA = "receipt-review-v1"
MAX_PRESENTATION_BYTES = 1_048_576
MAX_REVIEW_BYTES = 2_097_152
METHOD = "PROPOSED_RECEIPT_V1"
METHOD_VERSION = "proposed-receipt-research-v1"
DRAFT_PRODUCER = "PROPOSED_UNVERIFIED_REVIEW_V1"

_REFERENCE = "REJECT_INVALID_REVIEW_REFERENCE"
_STATE = "REJECT_REVIEW_STATE"
_VALUE = "REJECT_INVALID_REVIEW_VALUE"
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_SNAPSHOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9._-]*:sha256:[0-9a-f]{64}")
_WS = b" \t\r\n"
_STATUS = "EXTRACTED MISSING UNRESOLVED"
_ORIGINAL = "c0CandidateId status value canonicalValue absenceReason sourceTokenIds nativeConfidence candidateStatus constraintReasons calibratedProbability probabilityAvailable"
_SELECTED = "candidateId status value canonicalValue absenceReason sourceTokenIds changedFromC0"
_ALTERNATIVE = "candidateId value canonicalValue candidateStatus constraintReasons replacementSupport preliminaryRank calibratedProbability probabilityAvailable sourceTokenIds sourceReferences retailerEvidence priceEvidence"
_FIELD = "fieldId itemRowId role optionalWhenMissing originalB2 selectedPreReview fieldDisposition automaticCommitPermitted calibratedProbability probabilityAvailable probabilityUnavailableReason unresolvedConflict suspicionReasons correctionReason developmentRecommendation retailerEvidence priceEvidence alternativeCandidates"
_PRICE = "status reason observedUnitPriceMyr priceBasis bandLowMyr bandHighMyr ruleId resourceReference entryIds sourceTokenIds"
_IDENTITY = "entryId pantryIdentity pantryCategory referenceUnit resourceReference"
_SUSPICION = "LOW_OCR_CONFIDENCE LOW_EXTRACTOR_CONFIDENCE MISSING_REQUIRED_CONTENT PARSE_TYPE_FAILURE LINE_ASSOCIATION_CONFLICT ARITHMETIC_CONTRADICTION"


@dataclass(frozen=True, slots=True)
class ReceiptReviewV1:
    presentation: v1.ReceiptPresentationV1
    review: Mapping[str, object] | None


def _require(condition, path, code=_STATE):
    if not condition:
        v1._reject(code, path, "receipt review contract violation")


def _members(value, path, names):
    return v1._members(value, path, frozenset(names.split()))


def _choice(value, path, choices):
    value = v1._string(value, path)
    _require(value in choices.split(), path, _VALUE)
    return value


def _integer(value, path, low, high):
    _require(type(value) is int, path, "REJECT_INVALID_JSON")
    _require(low <= value <= high, path, _VALUE)
    return value


def _number(value, path, low, high):
    _require(type(value) in (int, Decimal, float), path, "REJECT_INVALID_JSON")
    _require(low <= value <= high, path, _VALUE)
    return value


def _nullable_text(value, path):
    return None if value is None else v1._nonblank_string(value, path, _VALUE)


def _reason(value, path):
    result = v1._privacy_safe_reason(value, path, _VALUE)
    _require(_CODE.fullmatch(result), path, _VALUE)
    return result


def _key(value, path, pattern=_KEY):
    result = v1._nonblank_string(value, path, _VALUE)
    _require(not v1._PRIVATE_ID_MARKER_RE.search(result.replace(":", ".").replace("@", "."))
             and not re.match(r"(?:[a-z]|https?|file|ftp|mailto|data|content):", result, re.I)
             and not any(char in result for char in "/\\"),
             path, "REJECT_UNSAFE_PROVENANCE")
    _require(pattern.fullmatch(result), path, _VALUE)
    return result


def _unique(value, path, validate):
    items = tuple(validate(x, f"{path}[{i}]") for i, x in enumerate(v1._array(value, path)))
    _require(len(items) == len(set(items)), path, _REFERENCE)
    return items


def _links(value, path, tokens):
    ids = _unique(value, path, v1._protocol_id)
    for index, token in enumerate(ids):
        _require(token in tokens, f"{path}[{index}]", _REFERENCE)
    return ids


def _frames(value, presentation, expected_width, expected_height, mode):
    path = "$.review.ocrEvidence"
    expected_ids = presentation.source_evidence.token_ids if presentation.source_evidence else ()
    _require((expected_width is None) == (expected_height is None), "$context.expectedImageWidth", _VALUE)
    if expected_width is not None:
        _integer(expected_width, "$context.expectedImageWidth", 1, 1600)
        _integer(expected_height, "$context.expectedImageHeight", 1, 1600)
    if value is None:
        _require(not expected_ids, path, _REFERENCE)
        return {}
    _require(presentation.source_evidence is not None, path)
    evidence = _members(value, path, "coordinateFrame tokens")
    frame_path = path + ".coordinateFrame"
    frame = _members(evidence["coordinateFrame"], frame_path, "origin unit imageWidth imageHeight")
    _choice(frame["origin"], frame_path + ".origin", "TOP_LEFT")
    _choice(frame["unit"], frame_path + ".unit", "SUBMITTED_IMAGE_PIXELS")
    width = _integer(frame["imageWidth"], frame_path + ".imageWidth", 1, 1600)
    height = _integer(frame["imageHeight"], frame_path + ".imageHeight", 1, 1600)
    _require(mode != "LIVE" or expected_width is not None, "$context.expectedImageWidth", _REFERENCE)
    if expected_width is not None:
        _require(width == expected_width, frame_path + ".imageWidth", _REFERENCE)
        _require(height == expected_height, frame_path + ".imageHeight", _REFERENCE)
    rows = v1._array(evidence["tokens"], path + ".tokens")
    _require(len(rows) <= 128, path + ".tokens", _VALUE)
    _require(len(rows) == len(expected_ids), path + ".tokens", _REFERENCE)
    result = {}
    point_count = char_count = byte_count = 0
    for i, row in enumerate(rows):
        p = f"{path}.tokens[{i}]"
        token = _members(row, p, "tokenId originalText polygon rawConfidence")
        token_id = v1._protocol_id(token["tokenId"], p + ".tokenId")
        _require(token_id == expected_ids[i], p + ".tokenId", _REFERENCE)
        text = v1._string(token["originalText"], p + ".originalText")
        size = len(text.encode("utf-8"))
        char_count += len(text)
        byte_count += size
        _require(0 < len(text) <= 256 and size <= 1024 and char_count <= 16384 and byte_count <= 49152,
                 p + ".originalText", _VALUE)
        pts = v1._array(token["polygon"], p + ".polygon")
        point_count += len(pts)
        _require(3 <= len(pts) <= 8 and point_count <= 1024, p + ".polygon", _VALUE)
        xs, ys = set(), set()
        for j, point in enumerate(pts):
            at = f"{p}.polygon[{j}]"
            pair = v1._array(point, at)
            _require(len(pair) == 2, at, _VALUE)
            xs.add(_number(pair[0], at + "[0]", 0, width))
            ys.add(_number(pair[1], at + "[1]", 0, height))
        _require(len(xs) >= 2 and len(ys) >= 2, p + ".polygon", _VALUE)
        if token["rawConfidence"] is not None:
            _number(token["rawConfidence"], p + ".rawConfidence", 0, 1)
        result[token_id] = text
    return result


def canonical_value(role, value):
    """Return the exact Presentation V1 rendering, or None if unrepresentable."""
    if not value or not value.strip():
        return None
    if role in v1._TEXT_ROLES:
        return value
    if role in v1._MONEY_ROLES:
        match = v1._ORIGINAL_MONEY_RE.fullmatch(value)
        if not match:
            return None
        canonical = match["integer"].replace(",", "") + "." + match["fraction"]
        validate = v1._validate_money
    else:
        canonical = value
        validate = v1._validate_date if role == "PURCHASE_DATE" else v1._validate_quantity
    try:
        validate(value, canonical, "$")
    except v1.ConformanceViolation:
        return None
    return canonical


def _candidate_probability(row, path, allowed):
    value = row["calibratedProbability"]
    if value is not None:
        _number(value, path + ".calibratedProbability", 0, 1)
        _require(allowed, path + ".calibratedProbability")
    flag = v1._boolean(row["probabilityAvailable"], path + ".probabilityAvailable")
    _require(flag == (value is not None), path + ".probabilityAvailable")
    return value


def _retailer(value, path):
    row = _members(value, path, "status retailerId sourceReferences reason")
    status = _choice(row["status"], path + ".status", "SUPPORTED UNAVAILABLE NOT_APPLICABLE")
    if row["retailerId"] is not None:
        _key(row["retailerId"], path + ".retailerId")
        _require(status != "NOT_APPLICABLE", path + ".retailerId")
    references = v1._array(row["sourceReferences"], path + ".sourceReferences")
    _require(bool(references) == (status == "SUPPORTED"), path + ".sourceReferences")
    for i, reference in enumerate(references):
        p = f"{path}.sourceReferences[{i}]"
        pair = _members(reference, p, "resourceReference entryId")
        _key(pair["resourceReference"], p + ".resourceReference", _SNAPSHOT)
        _key(pair["entryId"], p + ".entryId")
    _reason(row["reason"], path + ".reason")


def _price(value, path, tokens):
    row = _members(value, path, _PRICE)
    status = _choice(row["status"], path + ".status",
                     "PRICE_SUPPORTED PRICE_CONFLICT PRICE_UNAVAILABLE PRICE_INCONCLUSIVE NOT_APPLICABLE")
    _reason(row["reason"], path + ".reason")
    money = ("observedUnitPriceMyr", "bandLowMyr", "bandHighMyr")
    for field in money:
        if row[field] is not None:
            raw = v1._string(row[field], path + "." + field)
            _require(v1._MONEY_RE.fullmatch(raw), path + "." + field, _VALUE)
    if row["priceBasis"] is not None:
        _choice(row["priceBasis"], path + ".priceBasis", "EACH KG G LB OZ")
    if row["ruleId"] is not None:
        _key(row["ruleId"], path + ".ruleId")
    if row["resourceReference"] is not None:
        _key(row["resourceReference"], path + ".resourceReference", _SNAPSHOT)
    entries = _unique(row["entryIds"], path + ".entryIds", _key)
    linked = _links(row["sourceTokenIds"], path + ".sourceTokenIds", tokens)
    low, high = row["bandLowMyr"], row["bandHighMyr"]
    _require((low is None) == (high is None), path + ".bandHighMyr")
    if low is not None:
        _require(Decimal(low) <= Decimal(high), path + ".bandHighMyr")
        _require(len(entries) == 1 and row["resourceReference"] is not None, path + ".entryIds")
    if entries:
        _require(row["resourceReference"] is not None, path + ".resourceReference")
    if row["observedUnitPriceMyr"] is not None:
        _require(bool(linked), path + ".sourceTokenIds", _REFERENCE)
    if status in ("PRICE_SUPPORTED", "PRICE_CONFLICT"):
        for field in (*money, "priceBasis", "ruleId", "resourceReference"):
            _require(row[field] is not None, path + "." + field)
    if status in ("PRICE_UNAVAILABLE", "NOT_APPLICABLE"):
        _require(all(row[field] is None for field in money), path)
    if status == "NOT_APPLICABLE":
        _require(not entries and not linked and all(row[f] is None for f in
                 ("priceBasis", "ruleId", "resourceReference")), path)


def _origins(value, path, tokens):
    refs = v1._array(value, path)
    _require(bool(refs), path, _VALUE)
    for i, origin in enumerate(refs):
        p = f"{path}[{i}]"
        row = _members(origin, p, "sourceKind reference observedValue sourceTokenIds characterSpans resourceReference")
        kind = _choice(row["sourceKind"], p + ".sourceKind",
                       "SOURCE_TOKEN_OR_NEIGHBOUR GENERIC_NORMALIZATION RETAILER_MAPPING PANTRY_TERMINOLOGY")
        _key(row["reference"], p + ".reference")
        _nullable_text(row["observedValue"], p + ".observedValue")
        linked = _links(row["sourceTokenIds"], p + ".sourceTokenIds", tokens)
        if kind in ("RETAILER_MAPPING", "PANTRY_TERMINOLOGY"):
            _key(row["resourceReference"], p + ".resourceReference", _SNAPSHOT)
        else:
            _require(row["resourceReference"] is None, p + ".resourceReference")
        for j, span in enumerate(v1._array(row["characterSpans"], p + ".characterSpans")):
            at = f"{p}.characterSpans[{j}]"
            part = _members(span, at, "tokenId start end text")
            ref = v1._protocol_id(part["tokenId"], at + ".tokenId")
            _require(ref in linked, at + ".tokenId", _REFERENCE)
            text = tokens[ref]
            start = _integer(part["start"], at + ".start", 0, len(text)-1)
            end = _integer(part["end"], at + ".end", start+1, len(text))
            _require(v1._string(part["text"], at + ".text") == text[start:end], at + ".text", _REFERENCE)


def _register(value, path, ids, namespace, mode):
    candidate_id = v1._protocol_id(value, path)
    _require(candidate_id not in ids, path, _REFERENCE)
    ids.add(candidate_id)
    if mode == "LIVE":
        _require(candidate_id == f"cand-v1-{namespace}-{len(ids)}", path, _REFERENCE)
    return candidate_id


def _original(value, path, role, tokens, policy):
    row = _members(value, path, _ORIGINAL)
    status = _choice(row["status"], path + ".status", _STATUS)
    raw = _nullable_text(row["value"], path + ".value")
    _require((raw is not None) == (status == "EXTRACTED"), path + ".value")
    linked = _links(row["sourceTokenIds"], path + ".sourceTokenIds", tokens)
    confidence = v1._parse_confidence(row["nativeConfidence"], path + ".nativeConfidence")
    if raw is None:
        v1._privacy_safe_reason(row["absenceReason"], path + ".absenceReason", _STATE)
        _require(confidence is None, path + ".nativeConfidence")
    else:
        _require(row["absenceReason"] is None, path + ".absenceReason")
        _require(bool(linked), path + ".sourceTokenIds", _REFERENCE)
    actual = _nullable_text(row["canonicalValue"], path + ".canonicalValue")
    _require(actual == canonical_value(role, raw), path + ".canonicalValue", _VALUE)
    candidate_status = _choice(row["candidateStatus"], path + ".candidateStatus",
                               "SCORING_ELIGIBLE CONSTRAINT_REJECTED")
    _require(raw is not None or candidate_status == "CONSTRAINT_REJECTED", path + ".candidateStatus")
    reasons = _unique(row["constraintReasons"], path + ".constraintReasons", _reason)
    _require(bool(reasons) == (candidate_status == "CONSTRAINT_REJECTED"), path + ".constraintReasons")
    _candidate_probability(row, path, policy and candidate_status == "SCORING_ELIGIBLE")
    return row


def _alternatives(value, path, role, tokens, policy, ids, namespace, mode):
    rows = v1._array(value, path)
    _require(len(rows) <= 127, path, _VALUE)
    result = {}
    for i, item in enumerate(rows):
        p = f"{path}[{i}]"
        row = _members(item, p, _ALTERNATIVE)
        cid = _register(row["candidateId"], p + ".candidateId", ids, namespace, mode)
        raw = v1._nonblank_string(row["value"], p + ".value", _VALUE)
        actual = _nullable_text(row["canonicalValue"], p + ".canonicalValue")
        _require(actual == canonical_value(role, raw), p + ".canonicalValue", _VALUE)
        status = _choice(row["candidateStatus"], p + ".candidateStatus",
                         "SCORING_ELIGIBLE CONSTRAINT_REJECTED REJECTED_PRICE_ONLY")
        reasons = _unique(row["constraintReasons"], p + ".constraintReasons", _reason)
        _require(bool(reasons) == (status == "CONSTRAINT_REJECTED"), p + ".constraintReasons")
        support = _unique(row["replacementSupport"], p + ".replacementSupport", _reason)
        _require((not support or status == "SCORING_ELIGIBLE") and
                 all("PRICE" not in reason.split("_") for reason in support), p + ".replacementSupport")
        _integer(row["preliminaryRank"], p + ".preliminaryRank", i+1, i+1)
        _candidate_probability(row, p, policy and status == "SCORING_ELIGIBLE")
        _links(row["sourceTokenIds"], p + ".sourceTokenIds", tokens)
        _origins(row["sourceReferences"], p + ".sourceReferences", tokens)
        _retailer(row["retailerEvidence"], p + ".retailerEvidence")
        _price(row["priceEvidence"], p + ".priceEvidence", tokens)
        result[cid] = row
    return result


def _field(value, path, wire, row_id, tokens, policy, ids, namespace, mode):
    field = _members(value, path, _FIELD)
    _require(v1._protocol_id(field["fieldId"], path + ".fieldId") == wire.field_id,
             path + ".fieldId", _REFERENCE)
    _require(v1._string(field["role"], path + ".role") == wire.role, path + ".role", _REFERENCE)
    item_id = field["itemRowId"]
    if item_id is not None:
        v1._protocol_id(item_id, path + ".itemRowId")
    _require(item_id == row_id, path + ".itemRowId", _REFERENCE)
    role = wire.role
    _require(v1._boolean(field["optionalWhenMissing"], path + ".optionalWhenMissing") ==
             (role == "UNIT_PRICE"), path + ".optionalWhenMissing")
    c0 = _original(field["originalB2"], path + ".originalB2", role, tokens, policy)
    original_id = _register(c0["c0CandidateId"], path + ".originalB2.c0CandidateId", ids, namespace, mode)
    alternatives = _alternatives(field["alternativeCandidates"], path + ".alternativeCandidates",
                                  role, tokens, policy, ids, namespace, mode)
    selected_path = path + ".selectedPreReview"
    selected = _members(field["selectedPreReview"], selected_path, _SELECTED)
    cid = v1._protocol_id(selected["candidateId"], selected_path + ".candidateId")
    changed = cid != original_id
    record = alternatives.get(cid) if changed else c0
    _require(record is not None and (not changed or (policy and
             record["candidateStatus"] == "SCORING_ELIGIBLE" and record["replacementSupport"])),
             selected_path + ".candidateId", _REFERENCE)
    _require(v1._boolean(selected["changedFromC0"], selected_path + ".changedFromC0") == changed,
             selected_path + ".changedFromC0")
    v1._string(selected["status"], selected_path + ".status")
    for member in ("value", "canonicalValue", "absenceReason"):
        _nullable_text(selected[member], selected_path + "." + member)
    _links(selected["sourceTokenIds"], selected_path + ".sourceTokenIds", tokens)
    for member, expected in (("status", wire.status), ("value", wire.original_automatic_value),
                             ("canonicalValue", wire.presentation_value), ("absenceReason", wire.absence_reason),
                             ("sourceTokenIds", wire.source_token_ids)):
        _require(selected[member] == expected, selected_path + "." + member, _REFERENCE)
        if member in record:
            _require(selected[member] == record[member], selected_path + "." + member, _REFERENCE)
    if changed:
        _require(wire.status == "EXTRACTED" and c0["calibratedProbability"] is not None,
                 selected_path + ".candidateId")
    _require(wire.native_confidence == (None if policy else c0["nativeConfidence"]), path + ".originalB2.nativeConfidence")
    disposition = _choice(field["fieldDisposition"], path + ".fieldDisposition",
                          "AUTO_ACCEPTED REVIEW_REQUIRED" if policy else "UNVERIFIED_DRAFT")
    accepted = disposition == "AUTO_ACCEPTED"
    _require(v1._boolean(field["automaticCommitPermitted"], path + ".automaticCommitPermitted") ==
             accepted, path + ".automaticCommitPermitted")
    probability = _candidate_probability(field, path, policy)
    conflict = field["unresolvedConflict"]
    if conflict is not None:
        v1._boolean(conflict, path + ".unresolvedConflict")
    _require(policy or conflict is None, path + ".unresolvedConflict")
    reason = _reason(field["correctionReason"], path + ".correctionReason")
    _require(policy or reason == "EMPIRICAL_POLICY_UNAVAILABLE", path + ".correctionReason")
    if probability is None:
        unavailable = _reason(field["probabilityUnavailableReason"], path + ".probabilityUnavailableReason")
        if policy and c0["status"] == "MISSING":
            _require(unavailable == "ORIGINAL_NOT_SCORING_ELIGIBLE", path + ".probabilityUnavailableReason")
        _require(not changed and not accepted, path + ".calibratedProbability")
        _require(record["calibratedProbability"] is None or reason in
                 ("PRICE_CONTEXT_CHANGED", "JOINT_ARITHMETIC_CONFLICT"), path + ".calibratedProbability")
    else:
        _require(probability == record["calibratedProbability"], path + ".calibratedProbability")
        _require(field["probabilityUnavailableReason"] is None, path + ".probabilityUnavailableReason")
    _require(not accepted or (wire.status == "EXTRACTED" and conflict is False and
             record["candidateStatus"] == "SCORING_ELIGIBLE"), path + ".fieldDisposition")
    _unique(field["suspicionReasons"], path + ".suspicionReasons",
            lambda x, p: _choice(x, p, _SUSPICION))
    if field["developmentRecommendation"] is not None:
        p = path + ".developmentRecommendation"
        advice = _members(field["developmentRecommendation"], p, "recommendation recommendedCandidateId reason")
        _choice(advice["recommendation"], p + ".recommendation", "CORRECT RETAIN REVIEW_REQUIRED")
        aid = v1._protocol_id(advice["recommendedCandidateId"], p + ".recommendedCandidateId")
        _require(aid == original_id or aid in alternatives, p + ".recommendedCandidateId", _REFERENCE)
        _reason(advice["reason"], p + ".reason")
    _retailer(field["retailerEvidence"], path + ".retailerEvidence")
    _price(field["priceEvidence"], path + ".priceEvidence", tokens)
    return disposition


def _pantry(value, path, item):
    row = _members(value, path, "rowId descriptionFieldId mappingStatus selectedIdentity candidateIdentities")
    _require(v1._protocol_id(row["rowId"], path + ".rowId") == item.row_id, path + ".rowId", _REFERENCE)
    _require(v1._protocol_id(row["descriptionFieldId"], path + ".descriptionFieldId") == item.fields[0].field_id,
             path + ".descriptionFieldId", _REFERENCE)
    status = _choice(row["mappingStatus"], path + ".mappingStatus",
                     "MAPPED AMBIGUOUS UNRESOLVED RESOURCE_UNAVAILABLE")
    candidates = v1._array(row["candidateIdentities"], path + ".candidateIdentities")
    identities = set()
    for i, candidate in enumerate(candidates):
        p = f"{path}.candidateIdentities[{i}]"
        obj = _members(candidate, p, _IDENTITY)
        identifier = _key(obj["pantryIdentity"], p + ".pantryIdentity")
        _require(identifier not in identities, p + ".pantryIdentity", _REFERENCE)
        identities.add(identifier)
        _key(obj["entryId"], p + ".entryId")
        _key(obj["resourceReference"], p + ".resourceReference", _SNAPSHOT)
        for name in ("pantryCategory", "referenceUnit"):
            if obj[name] is not None:
                v1._privacy_safe_reason(obj[name], p + "." + name, _VALUE)
    selected = row["selectedIdentity"]
    if status == "MAPPED":
        _members(selected, path + ".selectedIdentity", _IDENTITY)
        _require(len(candidates) == 1 and selected == candidates[0], path + ".selectedIdentity", _REFERENCE)
    else:
        _require(selected is None, path + ".selectedIdentity")
        _require(len(candidates) >= 2 if status == "AMBIGUOUS" else not candidates,
                 path + ".candidateIdentities")
    _require(item.fields[0].status == "EXTRACTED" or not candidates, path + ".candidateIdentities")


def _review(value, p, width, height, mode):
    path = "$.review"
    outcome = p.outcome.status
    if outcome == "PROCESSING_UNAVAILABLE":
        _require(value is None, path)
        return None
    row = _members(value, path, "methodId methodVersion methodReadiness receiptDisposition failure region ocrEvidence fields pantryMappings")
    _choice(row["methodId"], path + ".methodId", METHOD)
    if row["region"] is not None:
        v1._privacy_safe_reason(row["region"], path + ".region", _VALUE)
    readiness = _choice(row["methodReadiness"], path + ".methodReadiness",
                        "POLICY_APPLIED NOT_READY NOT_EVALUATED NOT_VALID")
    disposition = _choice(row["receiptDisposition"], path + ".receiptDisposition",
                          "AUTO_RESOLVED REVIEW_REQUIRED UNVERIFIED_DRAFT FALLBACK_NO_UPDATE FAILED")
    if row["methodVersion"] is not None:
        v1._string(row["methodVersion"], path + ".methodVersion")
    fields = v1._array(row["fields"], path + ".fields")
    mappings = v1._array(row["pantryMappings"], path + ".pantryMappings")
    tokens = _frames(row["ocrEvidence"], p, width, height, mode)
    if outcome != "RESULT_AVAILABLE":
        _require(not fields, path + ".fields")
        _require(not mappings, path + ".pantryMappings")
        _require(row["methodVersion"] is None, path + ".methodVersion")
        failure = row["failure"]
        expected_readiness = "NOT_EVALUATED"
        if outcome == "PROCESSING_FAILED":
            f = _members(failure, path + ".failure", "stage code")
            _choice(f["stage"], path + ".failure.stage", "PRE_RESOLUTION")
            codes = p.outcome.failure.code
            if codes == "PRESENTATION_PROJECTION_FAILURE":
                codes += " PROPOSED_METHOD_FAILURE PROPOSED_CONFIGURATION_INVALID"
            if _choice(f["code"], path + ".failure.code", codes) == "PROPOSED_CONFIGURATION_INVALID":
                expected_readiness = "NOT_VALID"
        else:
            _require(failure is None, path + ".failure")
        _require(readiness == expected_readiness, path + ".methodReadiness")
        _require(disposition == ("FAILED" if outcome == "PROCESSING_FAILED" else "FALLBACK_NO_UPDATE"),
                 path + ".receiptDisposition")
        return row

    producer = p.automatic_extraction.producer
    policy = producer.producer_id == METHOD
    _require(producer.producer_id in (METHOD, DRAFT_PRODUCER), "$.presentation.automaticExtraction.producer.producerId")
    _require(readiness == ("POLICY_APPLIED" if policy else "NOT_READY"), path + ".methodReadiness")
    _require(row["methodVersion"] == METHOD_VERSION == producer.producer_version, path + ".methodVersion")
    _require(row["failure"] is None, path + ".failure")
    _require(row["ocrEvidence"] is not None, path + ".ocrEvidence", _REFERENCE)
    receipt = p.receipt
    expected = [(f, None) for f in receipt.receipt_fields]
    expected.extend((f, item.row_id) for item in receipt.item_rows for f in item.fields)
    _require(len(fields) == len(expected), path + ".fields", _REFERENCE)
    ids = set()
    namespace = None
    if mode == "LIVE":
        match = re.fullmatch(r"rct-v1-([0-9a-f]{32})-1", receipt.receipt_id)
        _require(match is not None, "$.presentation.receipt.receiptId", _REFERENCE)
        namespace = match[1]
    decisions = [_field(f, f"{path}.fields[{i}]", wire, item_id, tokens, policy, ids, namespace, mode)
                 for i, (f, (wire, item_id)) in enumerate(zip(fields, expected, strict=True))]
    expected_disposition = ("UNVERIFIED_DRAFT" if not policy else
                            "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in decisions else "AUTO_RESOLVED")
    _require(disposition == expected_disposition, path + ".receiptDisposition")
    _require(len(mappings) == len(receipt.item_rows), path + ".pantryMappings", _REFERENCE)
    for i, (mapping, item) in enumerate(zip(mappings, receipt.item_rows, strict=True)):
        _pantry(mapping, f"{path}.pantryMappings[{i}]", item)
    return row


def _skip_space(raw, index):
    while index < len(raw) and raw[index] in _WS:
        index += 1
    return index


def _end_string(raw, index):
    index += 1
    while raw[index] != 34:
        index += 2 if raw[index] == 92 else 1
    return index + 1


def _end_value(raw, index):
    initial = raw[index]
    if initial == 34:
        return _end_string(raw, index)
    if initial not in (123, 91):
        while raw[index] not in b",]}" + _WS:
            index += 1
        return index
    depth = 1
    index += 1
    while depth:
        ch = raw[index]
        if ch == 34:
            index = _end_string(raw, index)
            continue
        depth += (ch in (123, 91)) - (ch in (125, 93))
        index += 1
    return index


def object_member_bytes(raw: bytes, name: str) -> bytes:
    """Slice a top-level member of an already strictly validated JSON object."""
    index = _skip_space(raw, _skip_space(raw, 0) + 1)
    while raw[index] != 125:
        end = _end_string(raw, index)
        key = json.loads(raw[index:end])
        start = _skip_space(raw, _skip_space(raw, end) + 1)
        end = _end_value(raw, start)
        if key == name:
            return raw[start:end]
        index = _skip_space(raw, end)
        if raw[index] == 44:
            index = _skip_space(raw, index + 1)
    raise KeyError(name)


def decode_and_validate_receipt_review_v1(
    raw: bytes, *, expected_request_id: str, expected_image_id: str,
    consumer_mode: str, expected_image_width: int | None = None,
    expected_image_height: int | None = None,
) -> ReceiptReviewV1:
    if type(raw) is bytes and len(raw) > MAX_REVIEW_BYTES:
        v1._reject("REJECT_RESPONSE_TOO_LARGE", "$", "review body exceeds 2 MiB")
    root = v1.decode_strict_json_object(raw)
    for key in ("schemaName", "schemaVersion"):
        if key not in root:
            v1._reject("REJECT_MISSING_MEMBER", "$", f"missing member {key!r}")
    version = (v1._string(root["schemaName"], "$.schemaName"),
               v1._string(root["schemaVersion"], "$.schemaVersion"))
    if version != ("receipt-review", "1"):
        v1._reject("REJECT_UNSUPPORTED_SCHEMA_VERSION", "$.schemaVersion", "unsupported receipt review version")
    _members(root, "$", "schemaName schemaVersion presentation review")
    v1._object(root["presentation"], "$.presentation")
    inner = object_member_bytes(raw, "presentation")
    if len(inner) > MAX_PRESENTATION_BYTES:
        v1._reject("REJECT_RESPONSE_TOO_LARGE", "$.presentation", "embedded Presentation V1 exceeds 1 MiB")
    try:
        presentation = v1.decode_and_validate_presentation_v1(
            inner, expected_request_id=expected_request_id,
            expected_image_id=expected_image_id, consumer_mode=consumer_mode,
        )
    except v1.ConformanceViolation as error:
        path = error.path if error.path.startswith("$context") else "$.presentation" + error.path[1:]
        raise v1.ConformanceViolation(error.code, path, error.detail) from None
    return ReceiptReviewV1(presentation, _review(root["review"], presentation,
                                               expected_image_width, expected_image_height, consumer_mode))
