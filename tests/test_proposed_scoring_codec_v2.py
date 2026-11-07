"""Synthetic conformance tests for the strict scoring-evidence V2 codec."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import unittest

from pipeline.proposed.scoring_codec_v2 import (
    SCORING_CODEC_SCHEMA_VERSION,
    ScoringCodecError,
    ScoringCodecSourceBindingError,
    canonical_decimal_string,
    canonical_json_bytes,
    expected_admission_id,
    expected_field_audit_id,
    expected_field_failure_id,
    expected_operation_result_id,
    expected_score_evidence_id,
    expected_source_snapshot_id,
    parse_canonical_decimal,
    parse_canonical_json_bytes,
    scoring_operation_result_v2_from_json_bytes,
    scoring_operation_result_v2_to_json_bytes,
)
from pipeline.proposed.scoring_contracts_v2 import (
    FieldScoringFailureStateV2,
    FieldScoringFailureV2,
    ScorerInvocationStateV2,
    ScoringOperationResultV2,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    TrustedResolverStateV1,
)
try:
    import test_proposed_scoring_contracts_v2 as structural_fixtures
except ModuleNotFoundError:  # Focused ``python -m unittest tests...`` invocation.
    from tests import test_proposed_scoring_contracts_v2 as structural_fixtures


_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "proposed"
    / "scoring_contract_v2.json"
)


def _canonical_operation() -> ScoringOperationResultV2:
    records = structural_fixtures.build_structural_records()
    snapshot = records["snapshot"]
    snapshot = replace(
        snapshot,
        source_snapshot_id=expected_source_snapshot_id(snapshot),
    )
    admissions = tuple(
        replace(
            rebound,
            admission_id=expected_admission_id(rebound),
        )
        for item in records["admissions"]
        for rebound in (replace(item, source_snapshot_id=snapshot.source_snapshot_id),)
    )
    scores = []
    for prior, admission in zip(records["scores"], admissions, strict=True):
        rebound = replace(prior, admission=admission)
        scores.append(
            replace(
                rebound,
                score_evidence_id=expected_score_evidence_id(rebound),
            )
        )
    audit = replace(
        records["audit"],
        source_snapshot=snapshot,
        candidate_scores=tuple(scores),
    )
    audit = replace(audit, field_audit_id=expected_field_audit_id(audit))
    operation = ScoringOperationResultV2(
        operation_result_id="placeholder",
        outcome=audit,
    )
    return replace(
        operation,
        operation_result_id=expected_operation_result_id(operation),
    )


def _canonical_bypass_operation() -> ScoringOperationResultV2:
    records = structural_fixtures.build_structural_records()
    audit = structural_fixtures.build_zero_admitted_audit(records)
    snapshot = replace(
        audit.source_snapshot,
        source_snapshot_id=expected_source_snapshot_id(audit.source_snapshot),
    )
    scores = []
    for prior in audit.candidate_scores:
        admission_with_source = replace(
            prior.admission,
            source_snapshot_id=snapshot.source_snapshot_id,
        )
        admission = replace(
            admission_with_source,
            admission_id=expected_admission_id(admission_with_source),
        )
        rebound = replace(prior, admission=admission)
        scores.append(
            replace(
                rebound,
                score_evidence_id=expected_score_evidence_id(rebound),
            )
        )
    audit = replace(audit, source_snapshot=snapshot, candidate_scores=tuple(scores))
    audit = replace(audit, field_audit_id=expected_field_audit_id(audit))
    operation = ScoringOperationResultV2("placeholder", audit)
    return replace(operation, operation_result_id=expected_operation_result_id(operation))


def _canonical_failure_operation() -> ScoringOperationResultV2:
    records = structural_fixtures.build_structural_records()
    snapshot = replace(
        records["snapshot"],
        source_snapshot_id=expected_source_snapshot_id(records["snapshot"]),
    )
    admissions = tuple(
        replace(
            rebound,
            admission_id=expected_admission_id(rebound),
        )
        for item in records["admissions"]
        for rebound in (replace(item, source_snapshot_id=snapshot.source_snapshot_id),)
    )
    resolver = structural_fixtures._resolver(
        snapshot.theta_a_reference,
        TrustedResolverStateV1.NOT_READY,
    )
    failure = FieldScoringFailureV2(
        failure_id="placeholder",
        source_snapshot=snapshot,
        admissions=admissions,
        admitted_candidate_ids=(snapshot.candidates[0].candidate_id,),
        resolver_invocation=ScorerInvocationStateV2.INVOKED,
        resolver_result=resolver,
        failure_state=FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY,
        failure_code="SYNTHETIC_NOT_READY",
        component_id="synthetic-structural-scoring",
        component_version="v0",
    )
    failure = replace(failure, failure_id=expected_field_failure_id(failure))
    operation = ScoringOperationResultV2("placeholder", failure)
    return replace(operation, operation_result_id=expected_operation_result_id(operation))


class ProposedScoringCodecV2Tests(unittest.TestCase):
    def test_restricted_canonical_json_is_deterministic(self) -> None:
        value = {"z": [True, None, 7], "a": "receipt"}
        expected = b'{"a":"receipt","z":[true,null,7]}'
        self.assertEqual(expected, canonical_json_bytes(value))
        self.assertEqual(value, parse_canonical_json_bytes(expected))
        self.assertEqual(expected, canonical_json_bytes(value))

    def test_noncanonical_bom_whitespace_float_and_duplicate_key_reject(self) -> None:
        invalid = (
            b'\xef\xbb\xbf{"a":1}',
            b'{"a": 1}',
            b'{"a":1.0}',
            b'{"a":1,"a":1}',
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ScoringCodecError):
                    parse_canonical_json_bytes(payload)

    def test_unsupported_json_values_and_integer_range_reject(self) -> None:
        for value in (Decimal("1"), 1 << 60, {"é": "value"}):
            with self.subTest(value=value):
                with self.assertRaises(ScoringCodecError):
                    canonical_json_bytes(value)

    def test_decimal_grammar_accepts_exact_fixed_scale(self) -> None:
        accepted = ("0.0000", "0.8750", "-1.2500", "100.0000")
        for value in accepted:
            with self.subTest(value=value):
                parsed = parse_canonical_decimal(value, precision=16, scale=4)
                self.assertEqual(value, canonical_decimal_string(parsed, precision=16, scale=4))

    def test_decimal_grammar_rejects_noncanonical_or_silent_rounding(self) -> None:
        rejected = (
            None,
            0.875,
            "NaN",
            "Infinity",
            "8.750e-1",
            "+0.8750",
            "00.8750",
            "-0.0000",
            "0.875",
            "0.87500",
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ScoringCodecError):
                    parse_canonical_decimal(value, precision=16, scale=4)
        with self.assertRaises(ScoringCodecError):
            canonical_decimal_string(Decimal("0.875"), precision=16, scale=4)

    def test_decimal_precision_and_scale_are_independent(self) -> None:
        self.assertEqual(
            Decimal("0.0001"),
            parse_canonical_decimal("0.0001", precision=1, scale=4),
        )
        with self.assertRaises(ScoringCodecError):
            parse_canonical_decimal("12.3400", precision=5, scale=4)

    def test_complete_audit_round_trip_preserves_exact_live_sources(self) -> None:
        original = _canonical_operation()
        payload = scoring_operation_result_v2_to_json_bytes(original)
        decoded = scoring_operation_result_v2_from_json_bytes(
            payload,
            source_snapshot=original.outcome.source_snapshot,
        )
        self.assertEqual(original, decoded)
        self.assertIs(decoded.outcome.source_snapshot, original.outcome.source_snapshot)
        for entry, candidate, result in zip(
            decoded.outcome.candidate_scores,
            original.outcome.source_snapshot.candidates,
            original.outcome.source_snapshot.constraint_results,
            strict=True,
        ):
            self.assertIs(entry.candidate, candidate)
            self.assertIs(entry.constraint_result, result)
        self.assertEqual(payload, scoring_operation_result_v2_to_json_bytes(decoded))

    def test_zero_admitted_bypass_round_trip_has_no_resolver_or_binding(self) -> None:
        original = _canonical_bypass_operation()
        payload = scoring_operation_result_v2_to_json_bytes(original)
        decoded = scoring_operation_result_v2_from_json_bytes(
            payload,
            source_snapshot=original.outcome.source_snapshot,
        )
        self.assertIsNone(decoded.outcome.resolver_result)
        self.assertIsNone(decoded.outcome.trusted_scorer_binding)
        self.assertEqual((), decoded.outcome.admitted_candidate_ids)

    def test_atomic_failure_round_trip_has_no_partial_scores(self) -> None:
        original = _canonical_failure_operation()
        payload = scoring_operation_result_v2_to_json_bytes(original)
        decoded = scoring_operation_result_v2_from_json_bytes(
            payload,
            source_snapshot=original.outcome.source_snapshot,
        )
        self.assertIsInstance(decoded.outcome, FieldScoringFailureV2)
        self.assertFalse(hasattr(decoded.outcome, "candidate_scores"))
        self.assertIs(
            TrustedResolverStateV1.NOT_READY,
            decoded.outcome.resolver_result.state,
        )

    def test_source_content_substitution_rejects(self) -> None:
        original = _canonical_operation()
        payload = scoring_operation_result_v2_to_json_bytes(original)
        substituted = replace(original.outcome.source_snapshot)
        object.__setattr__(substituted, "source_snapshot_id", "tampered-source-id")
        with self.assertRaises(ScoringCodecSourceBindingError):
            scoring_operation_result_v2_from_json_bytes(
                payload,
                source_snapshot=substituted,
            )

    def test_missing_unknown_version_enum_and_id_tampering_reject(self) -> None:
        original = _canonical_operation()
        decoded = json.loads(scoring_operation_result_v2_to_json_bytes(original))
        mutations = []
        missing = json.loads(json.dumps(decoded))
        del missing["record"]["record_version"]
        mutations.append(missing)
        extra = json.loads(json.dumps(decoded))
        extra["unexpected"] = None
        mutations.append(extra)
        version = json.loads(json.dumps(decoded))
        version["schema_version"] = SCORING_CODEC_SCHEMA_VERSION + 1
        mutations.append(version)
        enum = json.loads(json.dumps(decoded))
        enum["record"]["outcome"]["completion_state"] = "COMPLETE_OTHER"
        mutations.append(enum)
        identifier = json.loads(json.dumps(decoded))
        identifier["record"]["operation_result_id"] = "tampered-id"
        mutations.append(identifier)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ScoringCodecError):
                    scoring_operation_result_v2_from_json_bytes(
                        canonical_json_bytes(mutation),
                        source_snapshot=original.outcome.source_snapshot,
                    )

    def test_source_content_order_and_score_lexeme_tampering_reject(self) -> None:
        original = _canonical_operation()
        decoded = json.loads(scoring_operation_result_v2_to_json_bytes(original))
        reordered = json.loads(json.dumps(decoded))
        candidates = reordered["record"]["outcome"]["source_snapshot"]["candidate_ids"]
        candidates[0], candidates[1] = candidates[1], candidates[0]
        with self.assertRaises(ScoringCodecSourceBindingError):
            scoring_operation_result_v2_from_json_bytes(
                canonical_json_bytes(reordered),
                source_snapshot=original.outcome.source_snapshot,
            )
        bad_decimal = json.loads(json.dumps(decoded))
        bad_decimal["record"]["outcome"]["candidate_scores"][0]["raw_score"] = "8.750e-1"
        with self.assertRaises(ScoringCodecError):
            scoring_operation_result_v2_from_json_bytes(
                canonical_json_bytes(bad_decimal),
                source_snapshot=original.outcome.source_snapshot,
            )

    def test_fixture_is_synthetic_language_neutral_and_self_consistent(self) -> None:
        fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual("scoring-contract-v2-synthetic-v1", fixture["fixture_version"])
        self.assertTrue(fixture["synthetic_only"])
        self.assertFalse(fixture["claims_operational_trust"])
        self.assertEqual(
            ["q_o", "q_e", "a_l", "a_y", "s_r", "s_a", "s_p"],
            fixture["feature_slot_order"],
        )
        for case in fixture["decimal_cases"]:
            action = parse_canonical_decimal
            if case["accepted"]:
                action(
                    case["value"],
                    precision=case["precision"],
                    scale=case["scale"],
                )
            else:
                with self.assertRaises(ScoringCodecError):
                    action(
                        case["value"],
                        precision=case["precision"],
                        scale=case["scale"],
                    )


if __name__ == "__main__":
    unittest.main()
