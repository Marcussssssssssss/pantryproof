"""Synthetic adversarial tests for raw hard-constraint operand audit V0."""

from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from unittest.mock import patch

from pipeline.contracts import (
    FieldStatus,
    ReceiptFieldName,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_finalization import (
    CandidateFinalizationCoverageStatusV0,
    materialize_ranked_candidate_records,
)
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import prepare_candidate_identities
from pipeline.proposed.candidate_limiting import (
    CandidateLimitingConfigurationV0,
    apply_candidate_limit,
)
from pipeline.proposed.candidate_provenance import materialize_altered_provenance
from pipeline.proposed.candidate_ranking import (
    CandidateRankingConfigurationV0,
    compute_preliminary_candidate_ranking,
)
from pipeline.proposed.contracts import (
    CandidateEvidenceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConstraintResultV1,
)
from pipeline.proposed.hard_constraint_context import (
    HardConstraintInputResultV0,
    prepare_hard_constraint_inputs,
)
from pipeline.proposed.hard_constraint_operands import (
    HARD_CONSTRAINT_OPERANDS_COMPONENT_VERSION,
    HARD_CONSTRAINT_OPERANDS_RECORD_VERSION,
    CandidateOperandAuditV0,
    CandidateSubstitutionPositionV0,
    CandidateSubstitutionScopeV0,
    HardConstraintOperandAuditResultV0,
    HardConstraintOperandIntegrityError,
    ItemRowOperandEvidenceV0,
    OperandAvailabilityV0,
    OperandEvidenceV0,
    RelationshipAvailabilityV0,
    audit_hard_constraint_operands,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
SOURCE = CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR


class _LayoutCandidateFixture(_SyntheticCandidateFixture):
    """Existing candidate fixture with a locally selected synthetic OCR layout."""

    def __init__(self, receipt_id: str, token_specs: tuple[tuple, ...]) -> None:
        super().__init__(receipt_id)
        self.token_specs = token_specs

    def evidence(self) -> ReceiptSourceEvidence:
        tokens = tuple(self.token(*spec) for spec in self.token_specs)
        gate = SourceEvidenceGateResult(
            gate_result_id=f"{self.receipt_id}:gate",
            receipt_id=self.receipt_id,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )
        return ReceiptSourceEvidence(
            receipt_id=self.receipt_id,
            image_id=f"{self.receipt_id}:image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference=f"memory://{self.receipt_id}",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens,
            gate_result=gate,
        )


class ProposedHardConstraintOperandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture(
            receipt_id="hard-constraint-operands-receipt"
        )

    @staticmethod
    def configuration(ranking, candidate_limit: int = 3):
        return CandidateLimitingConfigurationV0(
            theta_a_ref=ranking.configuration.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference="synthetic:hard-constraint-operands:test-v0",
        )

    def ranking(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        fixture: _SyntheticCandidateFixture | None = None,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
        multi_provenance: bool = False,
    ):
        selected = fixture or self.fixture
        drafts = selected.drafts(
            field_name=field_name,
            seed_specs=specs,
            multi_provenance=multi_provenance,
        )
        provenance = materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=drafts.suspicion_result.theta_a_ref
            ),
        )

    def ranking_from_builder(self, builder):
        adapter, method = self.fixture.adapter_and_method()
        seeds = builder(adapter, method)
        adapter, method = self.fixture.with_seeds(adapter, method, seeds)
        drafts = generate_candidate_drafts(
            suspicion_result=self.fixture.suspicion(method),
            adapter_result=adapter,
        )
        provenance = materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=drafts.suspicion_result.theta_a_ref
            ),
        )

    def finalize(self, ranking, candidate_limit: int = 3):
        return materialize_ranked_candidate_records(
            limit_result=apply_candidate_limit(
                ranking_result=ranking,
                configuration=self.configuration(ranking, candidate_limit),
            )
        )

    def prepared(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        candidate_limit: int = 3,
        *,
        fixture: _SyntheticCandidateFixture | None = None,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
    ) -> HardConstraintInputResultV0:
        finalization = self.finalize(
            self.ranking(specs, fixture=fixture, field_name=field_name),
            candidate_limit,
        )
        return prepare_hard_constraint_inputs(finalization_result=finalization)

    def audited(self, *args, **kwargs) -> HardConstraintOperandAuditResultV0:
        context = self.prepared(*args, **kwargs)
        return audit_hard_constraint_operands(hard_constraint_input=context)

    @staticmethod
    def missing_unit_fixture() -> _LayoutCandidateFixture:
        return _LayoutCandidateFixture(
            "operand-missing-unit-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("description", "BREAD", 10, 45, 55),
                ("line-total", "8.40", 220, 45, 45),
                ("total", "TOTAL 8.40", 140, 75, 125),
            ),
        )

    @staticmethod
    def unresolved_fixture() -> _LayoutCandidateFixture:
        return _LayoutCandidateFixture(
            "operand-unresolved-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("whole-item", "MILK 2 5.50 11.00", 10, 45, 255),
                ("total", "TOTAL 11.00", 130, 75, 135),
            ),
        )

    @staticmethod
    def multiple_rows_fixture(*, duplicate_text: bool = False):
        second = "MILK" if duplicate_text else "RICE"
        return _LayoutCandidateFixture(
            "operand-multiple-row-receipt" + ("-same" if duplicate_text else ""),
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("d1", "MILK", 10, 45, 45),
                ("q1", "2", 110, 45, 10),
                ("u1", "5.50", 155, 45, 38),
                ("l1", "11.00", 220, 45, 45),
                ("d2", second, 10, 65, 45),
                ("q2", "1", 109, 65, 11),
                ("u2", "12.90", 154, 65, 39),
                ("l2", "12.90", 219, 65, 46),
                ("total", "TOTAL 23.90", 130, 95, 135),
            ),
        )

    @staticmethod
    def missing_total_fixture():
        return _LayoutCandidateFixture(
            "operand-missing-total-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("description", "BREAD", 10, 45, 55),
                ("line-total", "8.40", 220, 45, 45),
            ),
        )

    def test_public_api_has_one_keyword_only_input(self) -> None:
        signature = inspect.signature(audit_hard_constraint_operands)
        self.assertEqual(("hard_constraint_input",), tuple(signature.parameters))
        self.assertIs(
            signature.parameters["hard_constraint_input"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def test_exact_input_context_reference_is_preserved(self) -> None:
        context = self.prepared()
        result = audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertIs(result.hard_constraint_input, context)

    def test_exact_candidate_references_are_preserved(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        self.assertTrue(
            all(
                audit.candidate is candidate
                for audit, candidate in zip(
                    result.candidate_audits,
                    result.hard_constraint_input.candidates,
                    strict=True,
                )
            )
        )

    def test_permanent_c0_is_first(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        self.assertIs(result.candidate_audits[0].candidate.role, CandidateRole.ORIGINAL)

    def test_c0_only_candidate_set(self) -> None:
        result = self.audited()
        self.assertEqual(1, len(result.candidate_audits))

    def test_one_retained_altered_candidate(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        self.assertEqual(2, len(result.candidate_audits))

    def test_multiple_retained_candidates(self) -> None:
        result = self.audited(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            candidate_limit=3,
        )
        self.assertEqual(3, len(result.candidate_audits))

    def test_candidate_audit_order_matches_context(self) -> None:
        result = self.audited(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            candidate_limit=3,
        )
        self.assertEqual(
            tuple(item.candidate_id for item in result.hard_constraint_input.candidates),
            tuple(item.candidate.candidate_id for item in result.candidate_audits),
        )

    def test_materialized_overflow_is_excluded(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=1)
        self.assertEqual(1, len(result.candidate_audits))
        self.assertEqual(1, len(result.overflow_audit_records))

    def test_blocked_overflow_is_excluded(self) -> None:
        def builder(_adapter, method):
            return (
                self.fixture.seed(
                    method,
                    suffix="materialized",
                    source_kind=GENERIC,
                    proposed_value="pantry mars",
                ),
                self.fixture.seed(
                    method,
                    suffix="blocked",
                    source_kind=GENERIC,
                    proposed_value="shop",
                    event_ids=("blocked:event:a", "blocked:event:b"),
                    rule_ids=("blocked:rule:a", "blocked:rule:b"),
                ),
            )

        finalization = self.finalize(self.ranking_from_builder(builder), 2)
        context = prepare_hard_constraint_inputs(finalization_result=finalization)
        result = audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertEqual(2, len(result.candidate_audits))
        self.assertEqual(1, len(result.blocked_audits))

    def test_overflow_only_incomplete_coverage_remains_visible(self) -> None:
        def builder(_adapter, method):
            return (
                self.fixture.seed(
                    method,
                    suffix="materialized",
                    source_kind=GENERIC,
                    proposed_value="pantry mars",
                ),
                self.fixture.seed(
                    method,
                    suffix="blocked",
                    source_kind=GENERIC,
                    proposed_value="shop",
                    event_ids=("blocked:event:a", "blocked:event:b"),
                    rule_ids=("blocked:rule:a", "blocked:rule:b"),
                ),
            )

        finalization = self.finalize(self.ranking_from_builder(builder), 2)
        result = audit_hard_constraint_operands(
            hard_constraint_input=prepare_hard_constraint_inputs(
                finalization_result=finalization
            )
        )
        self.assertIs(
            result.full_ledger_coverage_status,
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )

    def test_missing_unit_price_operand(self) -> None:
        result = self.audited(
            fixture=self.missing_unit_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        row = result.candidate_audits[0].item_rows[0]
        self.assertIs(row.operands[2].availability, OperandAvailabilityV0.MISSING)
        self.assertIsNone(row.operands[2].raw_value)

    def test_unresolved_quantity_operand(self) -> None:
        result = self.audited(
            fixture=self.unresolved_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        row = result.candidate_audits[0].item_rows[0]
        self.assertIs(row.operands[1].availability, OperandAvailabilityV0.UNRESOLVED)

    def test_extracted_raw_quantity_is_retained_exactly(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.QUANTITY)
        target = result.candidate_audits[0].target_field
        self.assertEqual("2", target.value)
        self.assertIs(target, result.candidate_audits[0].item_rows[0].operands[1].b2_field)

    def test_extracted_raw_unit_price_is_retained_exactly(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.UNIT_PRICE)
        self.assertEqual("RM 5.50", result.candidate_audits[0].original_b2_value)

    def test_extracted_raw_line_total_is_retained_exactly(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.LINE_TOTAL)
        self.assertEqual("11.00", result.candidate_audits[0].original_b2_value)

    def test_raw_numeric_text_is_not_parsed(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.UNIT_PRICE)
        value = result.candidate_audits[0].original_b2_value
        self.assertIsInstance(value, str)
        self.assertEqual("RM 5.50", value)

    def test_audit_contains_no_arithmetic_outcome(self) -> None:
        names = {item.name for item in fields(CandidateOperandAuditV0)}
        for forbidden in ("arithmetic", "difference", "tolerance", "eligible"):
            self.assertNotIn(forbidden, names)

    def test_item_target_uses_exact_stored_row_association(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.QUANTITY)
        audit = result.candidate_audits[0]
        self.assertIs(
            audit.substitution_position.item_row,
            result.hard_constraint_input.receipt_output.items[0],
        )
        self.assertIs(audit.item_row_relationship, RelationshipAvailabilityV0.AVAILABLE)

    def test_item_fields_preserve_b2_row_order(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.ITEM_DESCRIPTION)
        self.assertEqual(
            (
                ReceiptFieldName.ITEM_DESCRIPTION,
                ReceiptFieldName.QUANTITY,
                ReceiptFieldName.UNIT_PRICE,
                ReceiptFieldName.LINE_TOTAL,
            ),
            tuple(
                operand.field_name
                for operand in result.candidate_audits[0].item_rows[0].operands
            ),
        )

    def test_non_item_target_has_no_invented_row(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.PURCHASE_DATE)
        position = result.candidate_audits[0].substitution_position
        self.assertIs(position.scope, CandidateSubstitutionScopeV0.RECEIPT_FIELD)
        self.assertIsNone(position.item_row)
        self.assertIs(
            result.candidate_audits[0].item_row_relationship,
            RelationshipAvailabilityV0.NOT_APPLICABLE,
        )

    def test_receipt_total_target_is_receipt_level(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.RECEIPT_TOTAL)
        audit = result.candidate_audits[0]
        self.assertIs(
            audit.target_field,
            result.hard_constraint_input.receipt_output.receipt_total,
        )
        self.assertIs(
            audit.substitution_position.scope,
            CandidateSubstitutionScopeV0.RECEIPT_FIELD,
        )
        self.assertIsNone(audit.substitution_position.item_row)

    def test_non_item_operand_relationships_are_explicitly_not_applicable(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.STORE_NAME)
        self.assertTrue(
            all(
                state is OperandAvailabilityV0.NOT_APPLICABLE
                for _, state in result.candidate_audits[0].item_operand_availability
            )
        )

    def test_exact_receipt_total_operand_is_preserved(self) -> None:
        result = self.audited()
        evidence = result.candidate_audits[0].receipt_total_operand
        self.assertIs(evidence.b2_field, result.hard_constraint_input.receipt_output.receipt_total)
        self.assertEqual("11.00", evidence.raw_value)

    def test_partial_b2_item_row_is_preserved(self) -> None:
        result = self.audited(
            fixture=self.missing_unit_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        self.assertEqual(
            (
                OperandAvailabilityV0.AVAILABLE,
                OperandAvailabilityV0.MISSING,
                OperandAvailabilityV0.MISSING,
                OperandAvailabilityV0.AVAILABLE,
            ),
            tuple(
                item.availability
                for item in result.candidate_audits[0].item_rows[0].operands
            ),
        )

    def test_multiple_receipt_rows_preserve_order(self) -> None:
        result = self.audited(
            fixture=self.multiple_rows_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        output = result.hard_constraint_input.receipt_output
        self.assertEqual(
            tuple(row.row_id for row in output.items),
            tuple(row.row_id for row in result.candidate_audits[0].item_rows),
        )

    def test_no_hidden_purchase_rows_are_inferred(self) -> None:
        result = self.audited(
            fixture=self.missing_unit_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        self.assertEqual(
            len(result.hard_constraint_input.receipt_output.items),
            len(result.candidate_audits[0].item_rows),
        )

    def test_missing_receipt_total_is_not_computed(self) -> None:
        result = self.audited(
            fixture=self.missing_total_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        total = result.candidate_audits[0].receipt_total_operand
        self.assertIs(total.availability, OperandAvailabilityV0.MISSING)
        self.assertIsNone(total.raw_value)

    def test_candidate_substitution_does_not_mutate_b2(self) -> None:
        context = self.prepared((("one", GENERIC, "shop"),), candidate_limit=2)
        original = deepcopy(context.receipt_output)
        audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertEqual(original, context.receipt_output)

    def test_altered_candidate_value_remains_distinct_from_b2_raw_value(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        altered = result.candidate_audits[1]
        self.assertEqual("shop", altered.candidate_value)
        self.assertEqual("ＰＡＮＴＲＹ MART", altered.original_b2_value)

    def test_original_source_token_relationships_are_retained(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.UNIT_PRICE)
        audit = result.candidate_audits[0]
        self.assertEqual(
            audit.target_field.source_token_ids,
            result.hard_constraint_input.method_ready_field.source_token_ids,
        )

    def test_target_source_availability_means_only_extracted_raw_evidence(self) -> None:
        audit = self.audited().candidate_audits[0]
        self.assertIs(
            audit.target_source_availability, OperandAvailabilityV0.AVAILABLE
        )
        self.assertIs(
            audit.target_source_relationship,
            RelationshipAvailabilityV0.AVAILABLE,
        )
        self.assertFalse(hasattr(audit, "parse_valid"))

    def test_forged_target_field_is_rejected(self) -> None:
        result = self.audited()
        object.__setattr__(
            result.candidate_audits[0].substitution_position,
            "target_field",
            result.hard_constraint_input.receipt_output.receipt_total,
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_forged_target_source_relationship_is_rejected(self) -> None:
        result = self.audited()
        object.__setattr__(
            result.candidate_audits[0],
            "target_source_relationship",
            RelationshipAvailabilityV0.UNAVAILABLE,
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_forged_row_identity_is_rejected(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.QUANTITY)
        row = result.hard_constraint_input.receipt_output.items[0]
        object.__setattr__(row, "row_id", "forged-row")
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_missing_candidate_audit_is_rejected(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        object.__setattr__(result, "candidate_audits", result.candidate_audits[:1])
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_duplicate_candidate_audit_is_rejected(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        object.__setattr__(
            result,
            "candidate_audits",
            (result.candidate_audits[0], result.candidate_audits[0]),
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_reordered_candidate_audits_are_rejected(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        object.__setattr__(result, "candidate_audits", tuple(reversed(result.candidate_audits)))
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_substituted_equal_candidate_object_is_rejected(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        copied = deepcopy(result.candidate_audits[1].candidate)
        object.__setattr__(result.candidate_audits[1], "candidate", copied)
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_overflow_candidate_injection_is_rejected(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=1)
        injected = replace(
            result.candidate_audits[0],
            candidate=result.overflow_audit_records[0],
        )
        object.__setattr__(result, "candidate_audits", (injected,))
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_mutated_nested_field_status_is_rejected(self) -> None:
        result = self.audited()
        object.__setattr__(result.candidate_audits[0].target_field, "status", FieldStatus.MISSING)
        with self.assertRaises(HardConstraintOperandIntegrityError) as caught:
            result.__post_init__()
        self.assertIsNotNone(caught.exception.__cause__)

    def test_mutated_raw_source_reference_is_rejected(self) -> None:
        result = self.audited()
        object.__setattr__(
            result.candidate_audits[0].target_field,
            "source_token_ids",
            ("forged-token",),
        )
        with self.assertRaises(HardConstraintOperandIntegrityError) as caught:
            result.__post_init__()
        self.assertIsNotNone(caught.exception.__cause__)

    def test_changed_receipt_total_raw_value_is_rejected_after_observation(self) -> None:
        result = self.audited()
        observed = result.candidate_audits[0].receipt_total_operand
        self.assertEqual("11.00", observed.raw_value)
        object.__setattr__(observed.b2_field, "value", "12.00")
        self.assertEqual("11.00", observed.raw_value)
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_changed_unit_price_raw_value_is_rejected_after_observation(self) -> None:
        result = self.audited()
        observed = result.candidate_audits[0].item_rows[0].operands[2]
        self.assertEqual("RM 5.50", observed.raw_value)
        object.__setattr__(observed.b2_field, "value", "RM 6.50")
        self.assertEqual("RM 5.50", observed.raw_value)
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_changed_quantity_raw_value_is_rejected_after_observation(self) -> None:
        result = self.audited()
        observed = result.candidate_audits[0].item_rows[0].operands[1]
        self.assertEqual("2", observed.raw_value)
        object.__setattr__(observed.b2_field, "value", "3")
        self.assertEqual("2", observed.raw_value)
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_changed_sibling_source_reference_is_rejected_after_observation(self) -> None:
        result = self.audited()
        observed = result.candidate_audits[0].item_rows[0].operands[3]
        self.assertEqual(("line-total",), observed.source_token_ids)
        object.__setattr__(observed.b2_field, "source_token_ids", ("unit",))
        self.assertEqual(("line-total",), observed.source_token_ids)
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_changed_literal_ocr_text_is_rejected_after_observation(self) -> None:
        result = self.audited()
        token = next(
            item
            for item in result.hard_constraint_input.source_evidence.tokens
            if item.token_id == "total-label"
        )
        object.__setattr__(token, "original_text", "AMOUNT")
        with self.assertRaisesRegex(
            HardConstraintOperandIntegrityError,
            "OCR token payload changed",
        ):
            result.__post_init__()

    def test_changed_ocr_polygon_is_rejected_after_observation(self) -> None:
        result = self.audited()
        token = next(
            item
            for item in result.hard_constraint_input.source_evidence.tokens
            if item.token_id == "total-label"
        )
        changed = replace(token.polygon[0], x=token.polygon[0].x + 1.0)
        object.__setattr__(token, "polygon", (changed, *token.polygon[1:]))
        with self.assertRaisesRegex(
            HardConstraintOperandIntegrityError,
            "OCR token payload changed",
        ):
            result.__post_init__()

    def test_changed_ocr_confidence_is_rejected_after_observation(self) -> None:
        result = self.audited()
        token = next(
            item
            for item in result.hard_constraint_input.source_evidence.tokens
            if item.token_id == "total-label"
        )
        object.__setattr__(token, "raw_confidence", 0.77)
        with self.assertRaisesRegex(
            HardConstraintOperandIntegrityError,
            "OCR token payload changed",
        ):
            result.__post_init__()

    def test_no_association_by_matching_display_text(self) -> None:
        result = self.audited(
            fixture=self.multiple_rows_fixture(duplicate_text=True),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        audit = result.candidate_audits[0]
        self.assertEqual(2, len(audit.item_rows))
        self.assertEqual(0, audit.substitution_position.item_row_index)
        self.assertIs(
            audit.substitution_position.item_row,
            result.hard_constraint_input.receipt_output.items[0],
        )

    def test_repeated_execution_is_deterministic(self) -> None:
        context = self.prepared((("one", GENERIC, "shop"),), candidate_limit=2)
        first = audit_hard_constraint_operands(hard_constraint_input=context)
        second = audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertEqual(first, second)
        self.assertTrue(
            all(
                left.candidate is right.candidate
                for left, right in zip(
                    first.candidate_audits, second.candidate_audits, strict=True
                )
            )
        )

    def test_discovery_order_independence_is_inherited(self) -> None:
        specs = (
            ("a", GENERIC, "pantry mars"),
            ("b", GENERIC, "pantry shop"),
            ("c", GENERIC, "shop"),
        )
        first = self.audited(specs, candidate_limit=3)
        second = self.audited(tuple(reversed(specs)), candidate_limit=3)
        self.assertEqual(
            tuple(item.candidate.candidate_id for item in first.candidate_audits),
            tuple(item.candidate.candidate_id for item in second.candidate_audits),
        )

    def test_records_are_frozen_slotted_and_versioned(self) -> None:
        result = self.audited()
        records = (
            result,
            result.candidate_audits[0],
            result.candidate_audits[0].substitution_position,
            result.candidate_audits[0].item_rows[0],
            result.candidate_audits[0].item_rows[0].operands[0],
        )
        self.assertTrue(all(not hasattr(record, "__dict__") for record in records))
        self.assertEqual(HARD_CONSTRAINT_OPERANDS_COMPONENT_VERSION, result.component_version)
        self.assertEqual(HARD_CONSTRAINT_OPERANDS_RECORD_VERSION, result.record_version)
        with self.assertRaises(FrozenInstanceError):
            result.record_version = "changed"  # type: ignore[misc]

    def test_invalid_versions_are_rejected(self) -> None:
        result = self.audited()
        cases = (
            (result, "component_version"),
            (result, "record_version"),
            (result.candidate_audits[0], "record_version"),
            (result.candidate_audits[0].substitution_position, "record_version"),
            (result.candidate_audits[0].item_rows[0], "record_version"),
            (result.candidate_audits[0].item_rows[0].operands[0], "record_version"),
        )
        for record, name in cases:
            with self.subTest(record=type(record).__name__, name=name):
                with self.assertRaises(ValueError):
                    replace(record, **{name: "future-version"})

    def test_public_boundary_does_not_rerun_upstream_pipeline_functions(self) -> None:
        context = self.prepared((("one", GENERIC, "shop"),), candidate_limit=2)
        targets = (
            "pipeline.layout_b2.extract_b2",
            "pipeline.baseline_b3.apply_b3",
            "pipeline.proposed.adapter.adapt_b2_to_proposed",
            "pipeline.proposed.suspicion.detect_suspicion",
            "pipeline.proposed.candidate_generation.generate_candidate_drafts",
            "pipeline.proposed.candidate_deduplication.deduplicate_candidate_drafts",
            "pipeline.proposed.candidate_identity.prepare_candidate_identities",
            "pipeline.proposed.candidate_provenance.materialize_altered_provenance",
            "pipeline.proposed.candidate_ranking.compute_preliminary_candidate_ranking",
            "pipeline.proposed.candidate_limiting.apply_candidate_limit",
            "pipeline.proposed.candidate_finalization.materialize_ranked_candidate_records",
        )
        patches = [patch(target, side_effect=AssertionError(target)) for target in targets]
        started = [item.start() for item in patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.assertEqual(len(targets), len(started))
        result = audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertEqual(2, len(result.candidate_audits))

    def test_output_contains_no_constraint_or_candidate_evidence_records(self) -> None:
        result = self.audited((("one", GENERIC, "shop"),), candidate_limit=2)
        self.assertTrue(
            all(
                not isinstance(audit, (ConstraintResultV1, CandidateEvidenceV1))
                for audit in result.candidate_audits
            )
        )

    def test_no_price_or_retailer_provider_inputs(self) -> None:
        parameters = inspect.signature(audit_hard_constraint_operands).parameters
        for forbidden in ("price", "retailer", "provider", "resources"):
            self.assertNotIn(forbidden, parameters)

    def test_no_ground_truth_or_held_out_inputs(self) -> None:
        parameters = inspect.signature(audit_hard_constraint_operands).parameters
        for forbidden in ("ground_truth", "reference", "held_out", "validation"):
            self.assertNotIn(forbidden, parameters)

    def test_no_scoring_calibration_review_or_persistence_inputs(self) -> None:
        parameters = inspect.signature(audit_hard_constraint_operands).parameters
        for forbidden in ("score", "calibration", "review", "persistence"):
            self.assertNotIn(forbidden, parameters)

    def test_no_rules_grammars_tolerances_or_candidate_overrides(self) -> None:
        parameters = inspect.signature(audit_hard_constraint_operands).parameters
        for forbidden in ("rules", "grammar", "tolerance", "candidate"):
            self.assertNotIn(forbidden, parameters)

    def test_result_shape_contains_only_approved_stored_fields(self) -> None:
        self.assertEqual(
            {
                "hard_constraint_input",
                "candidate_audits",
                "component_version",
                "record_version",
            },
            {
                item.name
                for item in fields(HardConstraintOperandAuditResultV0)
                if not item.name.startswith("_")
            },
        )
        self.assertEqual(
            {"_source_token_observations"},
            {
                item.name
                for item in fields(HardConstraintOperandAuditResultV0)
                if item.name.startswith("_")
            },
        )

    def test_private_observations_are_integrity_metadata_only(self) -> None:
        result = self.audited()
        result_private = {
            item.name
            for item in fields(HardConstraintOperandAuditResultV0)
            if item.name.startswith("_")
        }
        operand_private = {
            item.name
            for item in fields(OperandEvidenceV0)
            if item.name.startswith("_")
        }
        self.assertEqual({"_source_token_observations"}, result_private)
        self.assertEqual({"_field_observation"}, operand_private)
        for forbidden in ("parsed", "eligible", "authentic", "score"):
            self.assertNotIn(forbidden, " ".join(result_private | operand_private))

    def test_new_valid_audit_reconstructs_with_private_observations(self) -> None:
        result = self.audited()
        result.__post_init__()
        self.assertEqual("11.00", result.candidate_audits[0].receipt_total_operand.raw_value)

    def test_candidate_audit_has_no_eligibility_or_decision_fields(self) -> None:
        names = {item.name for item in fields(CandidateOperandAuditV0)}
        for forbidden in (
            "eligibility",
            "passed",
            "constraint_result",
            "score",
            "probability",
            "review",
            "decision",
        ):
            self.assertNotIn(forbidden, names)

    def test_operand_availability_enum_has_exact_observational_states(self) -> None:
        self.assertEqual(
            {"AVAILABLE", "MISSING", "UNRESOLVED", "NOT_APPLICABLE"},
            {item.value for item in OperandAvailabilityV0},
        )

    def test_valid_current_item_contract_has_available_row_relationship(self) -> None:
        audit = self.audited(
            field_name=ReceiptFieldName.ITEM_DESCRIPTION
        ).candidate_audits[0]
        self.assertIs(audit.item_row_relationship, RelationshipAvailabilityV0.AVAILABLE)
        self.assertNotEqual(
            audit.item_row_relationship, RelationshipAvailabilityV0.UNAVAILABLE
        )

    def test_receipt_rows_retain_exact_source_token_references(self) -> None:
        result = self.audited(
            fixture=self.multiple_rows_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        output = result.hard_constraint_input.receipt_output
        observed = result.candidate_audits[0].item_rows
        for row_evidence, row in zip(observed, output.items, strict=True):
            self.assertEqual(
                tuple(field.source_token_ids for field in row.fields),
                tuple(item.source_token_ids for item in row_evidence.operands),
            )

    def test_reordered_row_operand_wrappers_are_rejected(self) -> None:
        result = self.audited(field_name=ReceiptFieldName.ITEM_DESCRIPTION)
        row = result.candidate_audits[0].item_rows[0]
        object.__setattr__(row, "operands", tuple(reversed(row.operands)))
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_reordered_receipt_rows_are_rejected(self) -> None:
        result = self.audited(
            fixture=self.multiple_rows_fixture(),
            field_name=ReceiptFieldName.ITEM_DESCRIPTION,
        )
        audit = result.candidate_audits[0]
        object.__setattr__(audit, "item_rows", tuple(reversed(audit.item_rows)))
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_deepcopied_target_field_is_rejected(self) -> None:
        result = self.audited()
        object.__setattr__(
            result.candidate_audits[0].substitution_position,
            "target_field",
            deepcopy(result.candidate_audits[0].target_field),
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            result.__post_init__()

    def test_existing_upstream_equal_method_copy_remains_supported(self) -> None:
        finalization = self.finalize(self.ranking())
        generation = (
            finalization.limit_result.ranking_result.provenance_result
            .identity_preparation.deduplication_result.candidate_drafts
        )
        copied_method = deepcopy(generation.original.method_ready_field)
        object.__setattr__(generation.original, "method_ready_field", copied_method)
        context = prepare_hard_constraint_inputs(finalization_result=finalization)
        result = audit_hard_constraint_operands(hard_constraint_input=context)
        self.assertIs(
            result.candidate_audits[0].target_field,
            context.receipt_output.store_name,
        )
        self.assertEqual(copied_method.original_b2_field, result.candidate_audits[0].target_field)

    def test_nested_operand_record_mutation_is_rejected(self) -> None:
        result = self.audited()
        operand = result.candidate_audits[0].item_rows[0].operands[0]
        object.__setattr__(operand, "record_version", "forged-version")
        with self.assertRaises(HardConstraintOperandIntegrityError) as caught:
            result.__post_init__()
        self.assertIsNotNone(caught.exception.__cause__)

    def test_invalid_public_input_type_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            audit_hard_constraint_operands(hard_constraint_input=object())  # type: ignore[arg-type]

    def test_module_does_not_import_forbidden_downstream_or_parser_modules(self) -> None:
        source = Path("pipeline/proposed/hard_constraint_operands.py").read_text(
            encoding="utf-8"
        )
        import_lines = "\n".join(
            line for line in source.splitlines() if line.startswith(("import ", "from "))
        )
        for forbidden in (
            "baseline_b3",
            "decimal import",
            "ConstraintResultV1",
            "CandidateEvidenceV1",
            "features",
            "scoring",
            "calibration",
            "price_reference",
        ):
            self.assertNotIn(forbidden, import_lines)


if __name__ == "__main__":
    unittest.main()
