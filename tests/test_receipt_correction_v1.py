"""Generated OCR fixtures only. The real B2/B3 and date stages run in-process."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from pipeline.baseline_b3 import ArithmeticOutcome, apply_b3
from pipeline.contracts import FieldStatus, ReceiptFieldName as Name, SourceEvidenceDecision
from pipeline.layout_b2 import extract_b2
from pipeline.proposed.contracts import (
    FEATURE_SLOT_ORDER, CandidateAuditStatus as Audit, CandidateLimitStatus as Limit,
    CandidateSourceKind as Kind, FeatureSlot,
)
from pipeline.proposed.receipt_correction_v1 import (
    PriceStatus, ReceiptMethodConfig, Recommendation, correct_receipt_v1,
)
from pipeline.proposed.receipt_resources_v1 import (
    MalaysianPriceBand, MalaysianPriceSnapshot, PriceBasis, PriceDiscrepancyRule,
    ReceiptResources, ResourceOrigin, ResourceProvenance, TerminologyEntry, TerminologySnapshot,
)
from pipeline.proposed.suspicion import SuspicionReasonCode
from tests import test_baseline_b3 as b3_fixtures


FIXTURE = b3_fixtures.BaselineB3Tests()
REFERENCE_DATE = date(2026, 10, 13)
RETAILER = "test-retailer"
REGION = "fixture-region"


def provenance(resource_id):
    return ResourceProvenance(
        resource_id, "test-v1", REFERENCE_DATE, ResourceOrigin.EXTERNAL_FIXED_SNAPSHOT,
        "memory://generated-test-fixture", "memory://synthetic-test-only",
    )


def lexicon(*extra):
    return TerminologySnapshot(provenance("fixture-lexicon"), (
        TerminologyEntry("store", Name.STORE_NAME, "TEST MRT", "PANTRYPROOF TEST MART",
                         Kind.RETAILER_MAPPING, RETAILER),
        TerminologyEntry("milk", Name.ITEM_DESCRIPTION, "MLK", "MILK",
                         Kind.RETAILER_MAPPING, RETAILER, "fixture-milk-pack"),
        TerminologyEntry("milk-term", Name.ITEM_DESCRIPTION, "MLK", "Milk",
                         Kind.PANTRY_TERMINOLOGY, product_key="fixture-milk-pack"),
        *extra,
    ))


def resources(*extra, with_prices=False, basis=PriceBasis.EACH, begin=REFERENCE_DATE, region=REGION):
    terminology = lexicon(*extra)
    if not with_prices:
        return ReceiptResources(terminology)
    band = MalaysianPriceBand("milk-band", RETAILER, "fixture-milk-pack", region,
                              begin, begin, basis, Decimal("1.00"), Decimal("2.00"))
    prices = MalaysianPriceSnapshot(provenance("fixture-prices"), (band,))
    return ReceiptResources(terminology, prices, PriceDiscrepancyRule("test-rule", Decimal("0.10")))


def simple(**overrides):
    return FIXTURE.b2_result(FIXTURE.simple_tokens(**overrides))


def low_ocr(baseline, *ids):
    output = baseline.receipt_output
    tokens = tuple(replace(token, raw_confidence=0.20) if token.token_id in ids else token
                   for token in output.source_evidence.tokens)
    return replace(baseline, receipt_output=replace(
        output, source_evidence=replace(output.source_evidence, tokens=tokens),
    ))


def field(result, name, row=0):
    return tuple(decision for decision in result.fields if decision.original.field_name is name)[row]


def slot(candidate, name):
    return next(value for value in candidate.features if value.slot is name)


def test_clean_seven_fields_keep_c0_and_share_frozen_baselines():
    baseline = simple()
    result = correct_receipt_v1(baseline, resources=resources())
    assert result.baseline is baseline
    assert result.b3 == apply_b3(baseline)
    assert result.preview.source_evidence is baseline.receipt_output.source_evidence
    assert {decision.original.field_name for decision in result.fields} == set(Name)
    for decision in result.fields:
        assert decision.recommendation is Recommendation.RETAIN
        assert decision.c0.value == decision.original.value
        assert len(decision.candidates) == 1
        assert tuple(value.slot for value in decision.c0.features) == FEATURE_SLOT_ORDER
        assert decision.c0.audit_status is Audit.SCORING_ELIGIBLE
    assert slot(field(result, Name.ITEM_DESCRIPTION).c0, FeatureSlot.PRICE_REFERENCE_SUPPORT).value is None
    assert result.purchase_date_trace.scores == ()
    assert len(result.scoring_inputs()) == len(Name)
    assert all(record.candidate_id == record.c0_candidate_id for record in result.scoring_inputs())
    assert all(record.missing_mask == tuple(value is None for value in record.values)
               for record in result.scoring_inputs())


def test_store_and_item_corrections_keep_exact_provenance_and_item_row():
    baseline = low_ocr(simple(store="TEST MRT", description="MLK"), "store", "description")
    result = correct_receipt_v1(baseline, resources=resources(with_prices=True), region=REGION)
    store = field(result, Name.STORE_NAME)
    item = field(result, Name.ITEM_DESCRIPTION)
    for decision, value in ((store, "PANTRYPROOF TEST MART"), (item, "MILK")):
        assert decision.recommendation is Recommendation.CORRECT
        assert decision.pre_review_preview.value == value
        assert decision.suspicion == (SuspicionReasonCode.LOW_OCR_CONFIDENCE,)
    candidate = item.candidates[1]
    assert len(item.candidates) == 2
    assert {origin.kind for origin in candidate.provenance} == {Kind.RETAILER_MAPPING, Kind.PANTRY_TERMINOLOGY}
    assert {origin.reference for origin in candidate.provenance} == {"milk", "milk-term"}
    assert {origin.spans[0].text for origin in candidate.provenance} == {"MLK"}
    assert candidate.price.status is PriceStatus.IMPLAUSIBLE
    assert candidate.price.source_token_ids == ("unit-price",)
    assert candidate.price.resource_reference.startswith("fixture-prices@test-v1:sha256:")
    assert slot(candidate, FeatureSlot.PRICE_REFERENCE_SUPPORT).value == 0
    assert slot(candidate, FeatureSlot.ARITHMETIC_SUPPORT).value == 1
    assert item.pre_review_preview.item_row_id == baseline.receipt_output.items[0].row_id
    assert result.preview.items[0].pantry_product_identity is None


def test_purchase_date_preserves_all_duplicate_anchor_spans():
    tokens = (
        FIXTURE.token("store", "TEST MART", 10, 5, width=150),
        FIXTURE.token("original", "2026-10-14", 10, 20, width=110),
        FIXTURE.token("ref1", "REFERENCE", 10, 38, width=74),
        FIXTURE.token("date1", "PURCHASE DATE: 2026-10-15", 85, 38, width=230),
        FIXTURE.token("ref2", "REFERENCE", 10, 56, width=74),
        FIXTURE.token("date2", "PURCHASE DATE: 15/10/2026", 85, 56, width=230),
        FIXTURE.token("item", "MILK 2 x 5.50 11.00", 10, 98, width=230),
        FIXTURE.token("total", "TOTAL RM 11.00", 130, 125, width=130),
    )
    result = correct_receipt_v1(FIXTURE.b2_result(tokens))
    decision = field(result, Name.PURCHASE_DATE)
    assert decision.recommendation is Recommendation.CORRECT
    assert decision.c0.value == "2026-10-14"
    assert decision.pre_review_preview.value == "2026-10-15"
    assert tuple(value.slot for value in decision.candidates[1].features) == FEATURE_SLOT_ORDER
    assert {origin.spans[0].text for origin in decision.candidates[1].provenance} == {
        "2026-10-15", "15/10/2026",
    }


@pytest.mark.parametrize(("name", "overrides", "label", "value"), (
    (Name.QUANTITY, {"quantity": "3"}, "QTY: 2", "2"),
    (Name.UNIT_PRICE, {"unit_price": "6.00"}, "UNIT PRICE: RM 5.50", "5.50"),
    (Name.LINE_TOTAL, {"line_total": "12.00"}, "LINE TOTAL: 11.00", "11.00"),
))
def test_role_bound_numeric_correction_requires_exact_arithmetic(name, overrides, label, value):
    baseline = simple(**overrides)
    anchor = FIXTURE.token("role-anchor", label, 340, 45, width=105)
    # An extra OCR box keeps the original B2 field associations fixed while
    # exercising geometric linkage, character spans, and alternative arithmetic.
    baseline = FIXTURE.with_extra_source_tokens(baseline, anchor)
    result = correct_receipt_v1(baseline)
    decision = field(result, name)
    assert decision.recommendation is Recommendation.CORRECT
    assert decision.pre_review_preview.value == value
    assert decision.pre_review_preview.source_token_ids == ("role-anchor",)
    assert decision.c0.value != value
    assert decision.c0.audit_status is Audit.CONSTRAINT_REJECTED
    assert decision.c0.features is None
    candidate = decision.candidates[1]
    assert candidate.replacement_support == ("ROLE_BOUND_SOURCE", "EXACT_RECEIPT_ARITHMETIC")
    assert candidate.provenance[0].spans[0].text == label.partition(": ")[2]


def test_anchored_receipt_total_recovery_from_normal_b2_entry():
    tokens = (*FIXTURE.simple_tokens()[:-2],
              FIXTURE.token("qual-total", "TOTAL PAYABLE RM 11.00", 140, 100, width=180))
    baseline = FIXTURE.b2_result(tokens)
    assert baseline.receipt_output.receipt_total.status is FieldStatus.UNRESOLVED
    result = correct_receipt_v1(baseline)
    total = field(result, Name.RECEIPT_TOTAL)
    assert total.c0.value is None
    assert total.recommendation is Recommendation.CORRECT
    assert result.preview.receipt_total.value == "11.00"
    assert result.preview.receipt_total.source_token_ids == ("qual-total",)



def test_conflicting_terminology_rejects_replacement_even_with_a_price_match():
    conflicting = TerminologyEntry("other-milk", Name.ITEM_DESCRIPTION, "MLK", "OAT DRINK",
                                   Kind.RETAILER_MAPPING, RETAILER, "fixture-oats")
    baseline = low_ocr(simple(description="MLK", unit_price="1.50", line_total="3.00",
                              receipt_total="3.00"), "description")
    result = correct_receipt_v1(baseline, resources=resources(conflicting, with_prices=True), region=REGION)
    item = field(result, Name.ITEM_DESCRIPTION)
    assert item.recommendation is Recommendation.REVIEW_REQUIRED
    assert item.reason == "CONFLICTING_NON_PRICE_EVIDENCE"
    assert item.pre_review_preview is item.original
    assert {c.price.status for c in item.candidates[1:]} == {PriceStatus.MISSING, PriceStatus.AGREES}


def test_price_disagreement_cannot_trigger_suspicion_or_create_a_candidate():
    baseline = simple(description="MLK")
    result = correct_receipt_v1(baseline, resources=resources(with_prices=True), region=REGION)
    item = field(result, Name.ITEM_DESCRIPTION)
    assert item.suspicion == ()
    assert len(item.candidates) == 1
    assert item.c0.price.status is PriceStatus.IMPLAUSIBLE
    assert item.recommendation is Recommendation.RETAIN
    without_price = field(correct_receipt_v1(baseline), Name.ITEM_DESCRIPTION)
    assert item.c0.value == "MLK"
    assert item.pre_review_preview == without_price.pre_review_preview


@pytest.mark.parametrize("missing", ("region", "date", "basis", "price"))
def test_unmatched_prices_are_explicit_nulls(missing):
    if missing == "price":
        tokens = (*FIXTURE.simple_tokens()[:4], *FIXTURE.simple_tokens()[7:])
        baseline = FIXTURE.b2_result(tokens)
    else:
        baseline = simple()
    result = correct_receipt_v1(
        baseline, region=REGION,
        resources=resources(with_prices=True,
                            region="irrelevant-region" if missing == "region" else REGION,
                            begin=date(2026, 10, 14) if missing == "date" else REFERENCE_DATE,
                            basis=PriceBasis.KG if missing == "basis" else PriceBasis.EACH),
    )
    item = field(result, Name.ITEM_DESCRIPTION)
    assert item.c0.price.status is PriceStatus.MISSING
    assert slot(item.c0, FeatureSlot.PRICE_REFERENCE_SUPPORT).value is None
    assert item.c0.missing_mask[-1]
    if missing == "price":
        assert item.c0.price.reason == "UNIT_PRICE_MISSING"
        price = field(result, Name.UNIT_PRICE)
        assert price.recommendation is Recommendation.REVIEW_REQUIRED
        assert price.c0.value is None and price.c0.features is None


def test_arithmetic_does_not_supply_an_unobserved_numeric_replacement():
    result = correct_receipt_v1(simple(unit_price="6.00"))
    unit = field(result, Name.UNIT_PRICE)
    assert unit.recommendation is Recommendation.REVIEW_REQUIRED
    assert len(unit.candidates) == 1
    assert unit.pre_review_preview.value == "6.00"
    assert "ARITHMETIC_CONTRADICTION" in unit.c0.constraint_reasons


def test_item_price_uses_same_row_and_neighbour_numeric_evidence_cannot_cross_rows():
    tokens = FIXTURE.simple_tokens(description="MILK", quantity="3", receipt_total="19.00")
    extra = (
        FIXTURE.token("second-item", "BREAD 2 x 4.00 8.00", 10, 70, width=300),
    )
    baseline = FIXTURE.b2_result((*tokens[:8], *extra, *tokens[8:]))
    anchor = FIXTURE.token("second-qty", "QTY: 2", 340, 70, width=105)
    baseline = FIXTURE.with_extra_source_tokens(baseline, anchor)
    result = correct_receipt_v1(baseline, resources=resources(with_prices=True), region=REGION)
    first, second = (field(result, Name.QUANTITY, row) for row in range(2))
    assert first.recommendation is Recommendation.REVIEW_REQUIRED
    assert len(first.candidates) == 1
    assert second.recommendation is Recommendation.RETAIN
    assert field(result, Name.ITEM_DESCRIPTION, 0).c0.price.actual_myr == Decimal("5.50")
    assert field(result, Name.ITEM_DESCRIPTION, 1).c0.price.reason == "ITEM_PRODUCT_UNRESOLVED"


def test_competing_numeric_repairs_are_reverted_when_combined():
    baseline = simple(quantity="4", unit_price="3.00", line_total="6.00", receipt_total="6.00")
    baseline = FIXTURE.with_extra_source_tokens(
        baseline, FIXTURE.token("quantity-alt", "QTY: 2", 340, 45, width=80),
        FIXTURE.token("price-alt", "UNIT PRICE: 1.50", 425, 45, width=120),
    )
    result = correct_receipt_v1(baseline)
    for name in (Name.QUANTITY, Name.UNIT_PRICE):
        decision = field(result, name)
        assert decision.reason == "JOINT_ARITHMETIC_CONFLICT"
        assert decision.recommendation is Recommendation.REVIEW_REQUIRED
        assert decision.candidates[1].audit_status is Audit.SCORING_ELIGIBLE
        assert decision.pre_review_preview is decision.original


def test_discount_and_promotion_are_exceptions():
    tokens = FIXTURE.simple_tokens(description="MILK PROMO", line_total="9.00", receipt_total="8.00")
    tokens = (*tokens[:8], FIXTURE.token("discount", "DISCOUNT -1.00", 180, 75, width=130), *tokens[8:])
    result = correct_receipt_v1(FIXTURE.b2_result(tokens), resources=resources(with_prices=True), region=REGION)
    for name in (Name.UNIT_PRICE, Name.LINE_TOTAL, Name.RECEIPT_TOTAL):
        decision = field(result, name)
        assert decision.recommendation is Recommendation.RETAIN
        assert any(check.outcome is ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION
                   for check in decision.c0.arithmetic)
    assert field(result, Name.UNIT_PRICE).c0.price.reason == "ITEM_PROMOTION"


def test_weighted_operand_without_denominator_remains_incomparable():
    result = correct_receipt_v1(simple(description="MILK 0.5 kg", quantity="0.5",
                                        unit_price="5.50", line_total="2.75", receipt_total="2.75"),
                                resources=resources(with_prices=True), region=REGION)
    assert field(result, Name.UNIT_PRICE).c0.arithmetic[0].outcome is (
        ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS
    )
    assert slot(field(result, Name.UNIT_PRICE).c0, FeatureSlot.ARITHMETIC_SUPPORT).value is None
    assert field(result, Name.UNIT_PRICE).c0.price.reason == "WEIGHT_BASIS_UNRESOLVED"


def test_cap_retains_c0_and_overflow_provenance():
    baseline = low_ocr(simple(description="MLK"), "description")
    result = correct_receipt_v1(baseline, resources=resources(),
                                config=ReceiptMethodConfig(candidate_limit=1))
    item = field(result, Name.ITEM_DESCRIPTION)
    assert item.recommendation is Recommendation.REVIEW_REQUIRED
    assert item.c0.value == "MLK"
    assert item.candidates[1].limit_status is Limit.LIMIT_OVERFLOW
    assert len(item.candidates[1].provenance) == 2
    assert item.candidates[1].features is None


def test_provenance_rejects_non_training_splits_and_requires_training_manifest():
    with pytest.raises(ValueError):
        replace(provenance("fixture"), origin="HELD_OUT")
    with pytest.raises(ValueError):
        replace(provenance("fixture"), origin=ResourceOrigin.TRAINING_ONLY)
    approved_shape = replace(provenance("fixture"), origin=ResourceOrigin.TRAINING_ONLY,
                             training_manifest_reference="memory://training-only-fixture")
    assert TerminologySnapshot(approved_shape, ()).reference != lexicon().reference


def test_recorded_gate_fallback_is_preserved():
    gate = FIXTURE.gate(SourceEvidenceDecision.INSUFFICIENT)
    baseline = extract_b2(FIXTURE.evidence(gate_result=gate))
    result = correct_receipt_v1(baseline)
    assert result.fallback_disposition is baseline.pre_resolution_disposition
    assert result.fields == ()
    assert result.preview is None



def test_b3_semantic_seed_is_preserved_with_events_and_exact_source():
    baseline = simple()
    output = baseline.receipt_output
    row, = output.items
    baseline = replace(baseline, receipt_output=replace(
        output, items=(replace(row, unit_price=replace(row.unit_price, value="6.00")),),
    ))
    result = correct_receipt_v1(baseline)
    unit = field(result, Name.UNIT_PRICE)
    assert result.b3.receipt_output.items[0].unit_price.value == "5.50"
    assert unit.recommendation is Recommendation.CORRECT
    assert unit.candidates[1].provenance[0].event_ids
    assert unit.candidates[1].provenance[0].spans[0].text == "5.50"
    assert unit.pre_review_preview.value == result.b3.receipt_output.items[0].unit_price.value


def test_weighted_item_compares_only_with_the_exact_rate_basis():
    receipt_description = "MILK 0.750 kg RM 10.00/kg"
    weighted = TerminologyEntry("weighted", Name.ITEM_DESCRIPTION, receipt_description,
                                receipt_description, Kind.RETAILER_MAPPING, RETAILER,
                                "fixture-milk-pack")
    baseline = simple(description=receipt_description, quantity="0.750",
                      unit_price="10.00", line_total="7.50", receipt_total="7.50")
    matching = correct_receipt_v1(
        baseline, resources=resources(weighted, with_prices=True, basis=PriceBasis.KG), region=REGION,
    )
    price = field(matching, Name.UNIT_PRICE).c0.price
    assert price.status is PriceStatus.IMPLAUSIBLE
    assert price.basis is PriceBasis.KG and price.actual_myr == Decimal("10.00")
    mismatch = correct_receipt_v1(baseline, resources=resources(weighted, with_prices=True), region=REGION)
    assert field(mismatch, Name.UNIT_PRICE).c0.price.reason == "NO_MATCHING_PRICE"


def test_two_explicit_receipt_totals_preserve_unresolved_value():
    baseline = simple(extra_tokens=(FIXTURE.token("payable", "TOTAL PAYABLE: 12.00", 85, 83, width=190),))
    # The alternate occurs in the footer but the two literal bodies disagree.
    result = correct_receipt_v1(baseline)
    decision = field(result, Name.RECEIPT_TOTAL)
    assert decision.recommendation is Recommendation.REVIEW_REQUIRED
    assert decision.reason == "CONFLICTING_NON_PRICE_EVIDENCE"
    assert decision.pre_review_preview is decision.original
    assert result.scoring_inputs()
    assert all(record.field_id != decision.original.field_id
               for record in result.scoring_inputs())



def test_item_description_can_use_direct_same_row_evidence_without_a_lexicon():
    baseline = simple(description="M1LK")
    source = FIXTURE.token("item-text", "ITEM DESCRIPTION: MILK", 340, 45, width=160)
    result = correct_receipt_v1(FIXTURE.with_extra_source_tokens(baseline, source))
    item = field(result, Name.ITEM_DESCRIPTION)
    assert item.recommendation is Recommendation.CORRECT
    assert item.pre_review_preview.value == "MILK"
    assert item.pre_review_preview.item_row_id == item.original.item_row_id
    assert item.candidates[1].replacement_support == ("ROLE_BOUND_SOURCE",)
    assert item.candidates[1].provenance[0].spans[0].text == "MILK"

