"""Manifest-driven cross-language receipt-presentation-v1 conformance tests."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from collections import Counter
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

from pipeline.presentation_v1.conformance import (
    ConformanceViolation,
    decode_and_validate_presentation_v1,
    decode_strict_json_object,
    validate_presentation_v1_object,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = (
    _REPOSITORY_ROOT / "tests" / "fixtures" / "receipt_presentation_v1" / "v1"
)
_MANIFEST_PATH = _FIXTURE_ROOT / "manifest.json"
_FIXTURES_DIRECTORY = _FIXTURE_ROOT / "fixtures"

_MANIFEST_MEMBERS = {
    "schemaName",
    "schemaVersion",
    "fixtureCount",
    "acceptCount",
    "rejectCount",
    "fixtures",
}
_WRAPPER_REQUIRED_MEMBERS = {
    "fixtureStatus",
    "scenario",
    "expectedResult",
    "envelope",
}
_WRAPPER_ALLOWED_MEMBERS = _WRAPPER_REQUIRED_MEMBERS | {"consumerContext"}
_CONTEXT_MEMBERS = {"expectedRequestId", "expectedImageId", "mode"}
_MANIFEST_ENTRY_MEMBERS = {
    "path",
    "expectedResult",
    "decisionIds",
    "sha256",
    "byteLength",
    "sourceClassification",
}
_SOURCE_CLASSIFICATIONS = {
    "HISTORICAL_BYTES_UNCHANGED",
    "HISTORICAL_SUCCESSOR",
    "NEW_APPROVED_SCENARIO",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PresentationV1SharedFixtureConformanceTest(unittest.TestCase):
    def test_canonical_manifest_bytes_and_expected_results(self) -> None:
        raw_manifest = _strict_object(_MANIFEST_PATH.read_bytes(), label="manifest")
        manifest = _require_exact_object(
            raw_manifest,
            allowed=_MANIFEST_MEMBERS,
            required=_MANIFEST_MEMBERS,
            label="manifest",
        )
        self.assertEqual(
            "receipt-presentation-v1-conformance-fixtures", manifest["schemaName"]
        )
        self.assertEqual("1", manifest["schemaVersion"])
        self.assertIs(type(manifest["fixtureCount"]), int)
        self.assertIs(type(manifest["acceptCount"]), int)
        self.assertIs(type(manifest["rejectCount"]), int)
        self.assertEqual(32, manifest["fixtureCount"])
        self.assertEqual(17, manifest["acceptCount"])
        self.assertEqual(15, manifest["rejectCount"])

        entries = manifest["fixtures"]
        # The strict decoder freezes JSON arrays as tuples before returning.
        self.assertIsInstance(entries, tuple, "manifest.fixtures must be an array")
        assert isinstance(entries, tuple)
        self.assertGreater(len(entries), 0, "zero-fixture success is forbidden")
        self.assertEqual(32, len(entries), "the frozen M3E-1 suite has 32 cases")

        listed_paths: set[str] = set()
        expected_distribution: Counter[str] = Counter()
        executed_distribution: Counter[str] = Counter()

        for index, raw_entry in enumerate(entries):
            with self.subTest(manifest_index=index):
                entry = _require_exact_object(
                    raw_entry,
                    allowed=_MANIFEST_ENTRY_MEMBERS,
                    required=_MANIFEST_ENTRY_MEMBERS,
                    label=f"manifest.fixtures[{index}]",
                )
                relative_path = _require_string(entry["path"], f"entry {index} path")
                expected = _require_string(
                    entry["expectedResult"], f"entry {index} expectedResult"
                )
                digest = _require_string(entry["sha256"], f"entry {index} sha256")
                byte_length = entry["byteLength"]
                decision_ids = entry["decisionIds"]
                source_classification = _require_string(
                    entry["sourceClassification"],
                    f"entry {index} sourceClassification",
                )

                _assert_safe_fixture_path(self, relative_path)
                self.assertNotIn(relative_path, listed_paths, "duplicate manifest path")
                listed_paths.add(relative_path)
                self.assertRegex(digest, _SHA256)
                self.assertIs(type(byte_length), int)
                self.assertGreater(byte_length, 0)
                self.assertIsInstance(decision_ids, tuple)
                assert isinstance(decision_ids, tuple)
                self.assertGreater(len(decision_ids), 0)
                self.assertTrue(
                    all(isinstance(value, str) and value for value in decision_ids)
                )
                self.assertEqual(len(decision_ids), len(set(decision_ids)))
                self.assertIn(source_classification, _SOURCE_CLASSIFICATIONS)
                self.assertTrue(
                    expected == "ACCEPT" or expected.startswith("REJECT_"),
                    f"invalid expected result {expected!r}",
                )

                fixture_path = _FIXTURE_ROOT / Path(*PurePosixPath(relative_path).parts)
                self.assertTrue(fixture_path.is_file(), f"missing fixture: {relative_path}")
                raw_fixture = fixture_path.read_bytes()
                self.assertEqual(byte_length, len(raw_fixture), "raw byte length mismatch")
                self.assertEqual(
                    digest,
                    hashlib.sha256(raw_fixture).hexdigest(),
                    "raw-byte SHA-256 mismatch",
                )

                actual = _run_fixture(raw_fixture, expected_from_manifest=expected)
                self.assertEqual(expected, actual)
                expected_distribution[
                    "ACCEPT" if expected == "ACCEPT" else "REJECT"
                ] += 1
                executed_distribution[
                    "ACCEPT" if actual == "ACCEPT" else "REJECT"
                ] += 1

        actual_json_paths = {
            PurePosixPath("fixtures", *path.relative_to(_FIXTURES_DIRECTORY).parts).as_posix()
            for path in _FIXTURES_DIRECTORY.rglob("*.json")
            if path.is_file()
        }
        self.assertEqual(listed_paths, actual_json_paths, "missing or unlisted fixture JSON")
        self.assertEqual(Counter({"ACCEPT": 17, "REJECT": 15}), expected_distribution)
        self.assertEqual(expected_distribution, executed_distribution)
        self.assertEqual(32, sum(executed_distribution.values()))


class PresentationV1LocalBoundaryTest(unittest.TestCase):
    """Language-local boundaries intentionally outside the canonical 32 cases."""

    def test_strict_decoder_rejects_nonstandard_or_ambiguous_json(self) -> None:
        cases = (
            ("bom", b"\xef\xbb\xbf{}", "REJECT_INVALID_JSON"),
            ("malformed-utf8", b'{"value":"\xff"}', "REJECT_INVALID_JSON"),
            ("comment", b"// comment\n{}", "REJECT_INVALID_JSON"),
            ("trailing-comma", b'{"value":1,}', "REJECT_INVALID_JSON"),
            ("trailing-content", b'{} true', "REJECT_INVALID_JSON"),
            ("nan", b'{"value":NaN}', "REJECT_INVALID_JSON"),
            ("lone-surrogate", b'{"value":"\\ud800"}', "REJECT_INVALID_JSON"),
            (
                "duplicate-key",
                b'{"value":1,"value":2}',
                "REJECT_DUPLICATE_JSON_KEY",
            ),
        )
        for name, raw_json, expected_code in cases:
            with self.subTest(name=name):
                with self.assertRaises(ConformanceViolation) as caught:
                    decode_strict_json_object(raw_json)
                self.assertEqual(expected_code, caught.exception.code)

    def test_production_validator_does_not_accept_fixture_wrapper_root(self) -> None:
        wrapper = decode_strict_json_object(
            (_FIXTURES_DIRECTORY / "01-complete-extracted-receipt.json").read_bytes()
        )
        with self.assertRaises(ConformanceViolation) as caught:
            validate_presentation_v1_object(
                wrapper,
                expected_request_id="request-synthetic-complete-001",
                expected_image_id="image-synthetic-complete-001",
                consumer_mode="FIXTURE",
            )
        self.assertEqual("REJECT_MISSING_MEMBER", caught.exception.code)

    def test_semantic_boundaries_fail_closed_without_normalization(self) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        quantity = envelope["receipt"]["itemRows"][0]["fields"][1]
        quantity["originalAutomaticValue"] = "0"
        quantity["presentationValue"] = "0"
        self._assert_rejected(envelope, "REJECT_INVALID_QUANTITY")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["requestId"] = "request/unsafe"
        self._assert_rejected(envelope, "REJECT_INVALID_ID")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["source"]["provenance"]["sourceReference"] = (
            r"C:\synthetic\receipt.png"
        )
        self._assert_rejected(envelope, "REJECT_UNSAFE_PROVENANCE")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["source"]["provenance"]["sourceReference"] = "participant-001"
        self._assert_rejected(envelope, "REJECT_UNSAFE_PROVENANCE")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["receiptFields"].reverse()
        self._assert_rejected(envelope, "REJECT_ROLE_ORDER")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["currencyCode"] = "USD"
        self._assert_rejected(envelope, "REJECT_CURRENCY_METADATA")

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        self._assert_rejected(
            envelope,
            "REJECT_SOURCE_MODE_MISMATCH",
            consumer_mode="LIVE",
        )

        envelope = _mutable_envelope("06-processing-unavailable.json")
        del envelope["sourceGate"]
        self._assert_rejected(
            envelope,
            "REJECT_MISSING_MEMBER",
            expected_request_id="request-synthetic-unavailable-001",
            expected_image_id="image-synthetic-unavailable-001",
        )

    def test_failure_matrix_and_confidence_boundaries(self) -> None:
        # An OCR-stage technical failure may genuinely have no evidence.
        envelope = _mutable_envelope("07-processing-failure.json")
        envelope["sourceEvidence"] = None
        validated = validate_presentation_v1_object(
            envelope,
            expected_request_id="request-synthetic-failure-001",
            expected_image_id="image-synthetic-failure-001",
            consumer_mode="FIXTURE",
        )
        self.assertIsNone(validated.source_evidence)

        envelope = _mutable_envelope("07-processing-failure.json")
        envelope["outcome"]["failure"]["stage"] = "AVAILABILITY"
        self._assert_rejected(
            envelope,
            "REJECT_OUTCOME_STAGE_MISMATCH",
            expected_request_id="request-synthetic-failure-001",
            expected_image_id="image-synthetic-failure-001",
        )

        envelope = _mutable_envelope(
            "s06-04-extraction-failure-after-completed-ocr-and-sufficient-gate.json"
        )
        envelope["automaticExtraction"] = _mutable_envelope(
            "01-complete-extracted-receipt.json"
        )["automaticExtraction"]
        self._assert_rejected(
            envelope,
            "REJECT_OUTCOME_STATE_MISMATCH",
            expected_request_id="request-extraction-failure-completed-001",
            expected_image_id="image-extraction-failure-completed-001",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["receiptFields"][0]["nativeConfidence"] = Decimal(
            "1e10000"
        )
        self._assert_rejected(envelope, "REJECT_INVALID_CONFIDENCE")

    def test_privacy_sensitive_gate_and_field_reasons_are_rejected(self) -> None:
        unsafe_gate_reasons = (
            "file:///tmp/participant-001.jpg",
            "content://com.pantryproof.receipts/receipt-001",
            "https://example.test/source/receipt-001.jpg",
            r"C:\receipts\receipt-001.jpg",
            r"\\fileserver\receipts\receipt-001.jpg",
            "/tmp/receipt-001.jpg",
            "participant-001",
            "evaluation-2026-001",
            "reference-id-001",
        )
        for unsafe_reason in unsafe_gate_reasons:
            with self.subTest(location="sourceGate.reasons", reason=unsafe_reason):
                envelope = _mutable_envelope("01-complete-extracted-receipt.json")
                envelope["sourceGate"]["reasons"] = [unsafe_reason]
                self._assert_rejected(
                    envelope,
                    "REJECT_UNSAFE_PROVENANCE",
                    expected_path="$.sourceGate.reasons[0]",
                )

        field_cases = (
            ("03-missing-required-store-name.json", 0, "MISSING"),
            ("04-unresolved-purchase-date.json", 1, "UNRESOLVED"),
        )
        for filename, field_index, expected_status in field_cases:
            with self.subTest(status=expected_status):
                envelope = _mutable_envelope(filename)
                field = envelope["receipt"]["receiptFields"][field_index]
                self.assertEqual(expected_status, field["status"])
                field["absenceReason"] = "file:///tmp/participant-001.jpg"
                self._assert_rejected(
                    envelope,
                    "REJECT_UNSAFE_PROVENANCE",
                    expected_request_id=envelope["requestId"],
                    expected_image_id=envelope["imageId"],
                    expected_path=(
                        f"$.receipt.receiptFields[{field_index}].absenceReason"
                    ),
                )

    def test_privacy_reason_guard_rejects_non_authority_uri_forms(self) -> None:
        unsafe_reasons = (
            "file:/tmp/receipt.jpg",
            "mailto:user@example.test",
            "urn:receipt:001",
            "tel:+60123456789",
            "data:text/plain,receipt",
            "android.resource:com.pantryproof/raw/sample",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

    def test_privacy_reason_guard_rejects_labelled_and_relative_paths(self) -> None:
        unsafe_reasons = (
            r"path=C:\receipts\receipt.jpg",
            "path=/tmp/receipt.jpg",
            r"path=\\server\share\receipt.jpg",
            "../private/receipt.jpg",
            "./private/receipt.jpg",
            r"receipts\receipt.jpg",
            "path=receipts/receipt.jpg",
            "receipts/receipt.jpg",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

    def test_privacy_reason_guard_rejects_contextual_protected_identifiers(self) -> None:
        unsafe_reasons = (
            "Participant ID 001",
            "participant#001",
            "participant-id-alpha",
            "Reference ID ABC",
            "reference-id-ABC",
            "held out case 7",
            "annotation ID sampleA",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

    def test_privacy_reason_guard_accepts_ref_prefixed_natural_language(self) -> None:
        safe_reasons = (
            "Refresh2 attempt could not read the image.",
            "Refill2 operation failed.",
            "Refactor2 parser was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_r3_spaced_protected_identifier_policy(self) -> None:
        unsafe_reasons = (
            "Participant #001",
            "Participant 001",
            "Reference #001",
            "Evaluation #ABC",
            "Annotation #sampleA",
            "pArTiCiPaNt   # alpha-7",
            "REFERENCE   002",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Participant evidence was unavailable.",
            "Evaluation evidence was unavailable.",
            "Annotation evidence was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_r3_extensionless_relative_path_policy(self) -> None:
        unsafe_reasons = (
            "receipts/receipt",
            "private/2026/receipt",
            "path: receipts/receipt",
            "Could not read path: private/2026/receipt during capture.",
            "Could not open private/2026/receipt during capture.",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Input or output processing failed.",
            "The disjunction rule was unavailable.",
            "Ratio comparison was unsupported.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_r3_strict_uri_scheme_policy(self) -> None:
        unsafe_reasons = (
            "file:/tmp/receipt.jpg",
            "file:///tmp/receipt.jpg",
            "mailto:user@example.test",
            "urn:receipt:001",
            "tel:+60123456789",
            "data:text/plain,receipt",
            "android.resource:com.pantryproof/raw/sample",
            "content://com.pantryproof.receipts/receipt-001",
            "https://example.test/source/receipt-001.jpg",
            "OCR:failed to recognize total.",
            "Reason:missing text.",
            "Import failed at CuStOm+V1:opaque-payload during capture.",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "OCR: failed to recognize total.",
            "Reason: missing text.",
            "Diagnostic label: value was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_r4_colon_and_equals_protected_identifier_policy(self) -> None:
        unsafe_reasons = (
            "Participant: 001",
            "Reference: ABC",
            "Annotation: sampleA",
            "Evaluation: 001",
            "Participant = 001",
            "held out: 7",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Refresh2 attempt could not read the image.",
            "Refill2 operation failed.",
            "Refactor2 parser was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_r4_strict_forward_slash_compound_policy(self) -> None:
        unsafe_reasons = (
            "receipts/receipt",
            "private/2026/receipt",
            "Could not read receipts/receipt during capture.",
            "path: receipts/receipt",
            "A/B",
            "and/or",
            "2026/11/06",
            "Ratio A/B was unsupported.",
            "Input/output processing failed.",
            "The and/or rule was unavailable.",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Input / output processing failed.",
            "The and / or rule was unavailable.",
            "Ratio A / B was unsupported.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = ["A/B", "A/B"]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

    def test_r5_protected_identifier_composition_matrix(self) -> None:
        unsafe_reasons = (
            "Participant ID = 001",
            "Participant: #001",
            "participant# 001",
            "held\tout: 7",
            "Reference case = ABC",
            "Evaluation ID = alpha-7",
            "Annotation: #sampleA",
            "HELD-OUT = #7",
            "Ground Truth# ABC",
            "ground_truth\tcase\t=\tA1-2",
            "REF# X9",
            "rEf ID = ABC_2",
            "Participant 001",
            "Reference ID ABC",
            "Evaluation case: alpha-7",
            "Annotation_case_sampleA",
            "held-out case 7",
            "ground truth ID#ABC",
            "participant-id-alpha",
            "reference#001",
            "REFERENCE  #  ABC",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Refresh2 attempt could not read the image.",
            "Refill2 operation failed.",
            "Refactor2 parser was unavailable.",
            "Participant evidence was unavailable.",
            "Evaluation evidence was unavailable.",
            "Annotation evidence was unavailable.",
            "held\tout evidence was unavailable.",
            "Ground\ttruth evidence was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

        unsafe_reason = "Participant ID = 001"
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [unsafe_reason, unsafe_reason]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = ["   "]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[0]",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["receiptFields"][0]["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_path="$.receipt.receiptFields[0].absenceReason",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["originalAutomaticValue"] = "unexpected"
        field["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0]",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["status"] = "INVALID"
        field["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_UNKNOWN_ENUM",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0].status",
        )

    def test_r6_qualified_hash_identifier_matrix(self) -> None:
        unsafe_reasons = (
            "Participant ID: #001",
            "Participant case = #001",
            "Reference ID: #ABC",
            "Evaluation ID = #ABC",
            "Annotation ID: #sampleA",
            "Held out ID: #7",
            "participant\tID\t:\t#\tP-01",
            "REFERENCE  case  =  #  ABC_2",
            "evaluation\tcase\t:\t#\tE-7",
            "annotation ID = #sample-A",
            "HELD-OUT CASE = #H7",
            "ground\ttruth id : #GT-1",
            "ReF ID = #R2",
            "Participant ID=#001",
            "Reference case=#ABC",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Refresh2 attempt could not read the image.",
            "Refill2 operation failed.",
            "Refactor2 parser was unavailable.",
            "Participant evidence was unavailable.",
            "held\tout evidence was unavailable.",
            "Ground\ttruth evidence was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

        unsafe_reason = "Participant ID: #001"
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [unsafe_reason, unsafe_reason]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["receiptFields"][0]["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_path="$.receipt.receiptFields[0].absenceReason",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["status"] = "INVALID"
        field["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_UNKNOWN_ENUM",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0].status",
        )

    def test_candidate02_detection_view_normalization_and_invisibles(self) -> None:
        unsafe_reasons = (
            "Ｐａｒｔｉｃｉｐａｎｔ：００１",
            "ｆｉｌｅ：／tmp／receipt.jpg",
            "ｒｅｃｅｉｐｔｓ／ｒｅｃｅｉｐｔ",
            "Reference\u00a0P００１",
            "Reference\u2003A12",
            "Reference\tA12",
            "Reference\u200b:A12",
            "Reference\u00adnote",
            "Reference\u034fnote",
            "Reference\u061cnote",
            "Reference\u180enote",
            "Reference\u202anote",
            "Reference\u2060note",
            "Reference\ufeffnote",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Participant identifier was unavailable.",
            "Imej café tidak tersedia.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_candidate02_full_tail_identifier_and_unicode_scan(self) -> None:
        unsafe_reasons = (
            "Reference evidence A12",
            "Reference evidence (A12)",
            "Reference information 123",
            "Reference version 2",
            "Reference version ٢",
            "Reference @note",
            "Reference @A12",
            "Reference A12é",
            "Reference résumé",
            "Reference А12",
            "Reference 证据",
            "Participant (P001)",
            "The participant can review 2 options.",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference evidence was unavailable.",
            "Reference information is unavailable.",
            "The reference has been removed.",
            "Reference N_A",
            "No participant information was retained.",
            "The participant can review the result.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_candidate02_delimiters_unsupported_ascii_and_wrappers(self) -> None:
        unsafe_reasons = (
            "Reference A12,",
            "Reference ,A12",
            "Reference ((A12))",
            "Reference ([A12]),",
            'Reference "A12"',
            "Reference 'A12'",
            "Reference “A12”",
            "Reference ‘A12’",
            "Reference «A12»",
            "Reference ‹A12›",
            "Reference ( A12 )",
            "Reference A12),”",
            "Reference @note",
            "Reference A12+",
            "Reference @@A12",
            "Reference A12+B34",
            "Reference A12/path",
            "Reference A12\\path",
            "Reference ()",
            "Reference ((",
            "Reference (note",
            "Reference note)",
            "Reference ([note)]",
            'Reference "note',
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Reference note,",
            "Reference (note)",
            "Reference [note]",
            "Reference {note}",
            "Reference ((note))",
            'Reference "note"',
            "Reference 'note'",
            "Reference “note”",
            "Reference ‘note’",
            "Reference «note»",
            "Reference ‹note›",
            "Reference ABC",
            "Reference ABC-DEF",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_candidate02_structured_prefix_and_mixed_label_policy(self) -> None:
        unsafe_reasons = (
            "Reference:",
            "Reference -",
            "Ref #",
            "Reference ==id 7",
            "Reference - - evidence",
            "Participant :# 001",
            "Participant ID",
            "Reference 7",
            "Café: unavailable",
            "Partіcipant:001",
        )
        for unsafe_reason in unsafe_reasons:
            with self.subTest(reason=unsafe_reason):
                self._assert_reason_rejected_at_all_boundaries(unsafe_reason)

        safe_reasons = (
            "Participant identifier was unavailable.",
            "Participant identity was unavailable.",
            "Participant idempotent check was unavailable.",
            "Participant casework was unavailable.",
            "Imej café tidak tersedia.",
            "Refresh2 attempt could not read the image.",
            "Refill2 operation failed.",
            "Refactor2 parser was unavailable.",
        )
        for safe_reason in safe_reasons:
            with self.subTest(reason=safe_reason):
                self._assert_reason_accepted_at_all_boundaries(safe_reason)

    def test_candidate02_preserves_raw_duplicate_and_field_state_precedence(self) -> None:
        unsafe_reason = "Reference evidence A12"
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [unsafe_reason, unsafe_reason]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["originalAutomaticValue"] = "unexpected"
        field["absenceReason"] = unsafe_reason
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0]",
        )

    def test_privacy_safe_free_text_reasons_remain_accepted(self) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [
            "File was unavailable during capture.",
            "Reference evidence was unavailable.",
            "Participant could not supply a readable receipt.",
        ]
        validate_presentation_v1_object(
            envelope,
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            consumer_mode="FIXTURE",
        )

        field_cases = (
            (
                "03-missing-required-store-name.json",
                0,
                "File contents could not be read during extraction.",
            ),
            (
                "04-unresolved-purchase-date.json",
                1,
                "Evaluation could not resolve the purchase date.",
            ),
        )
        for filename, field_index, safe_reason in field_cases:
            with self.subTest(filename=filename):
                envelope = _mutable_envelope(filename)
                envelope["receipt"]["receiptFields"][field_index][
                    "absenceReason"
                ] = safe_reason
                validate_presentation_v1_object(
                    envelope,
                    expected_request_id=envelope["requestId"],
                    expected_image_id=envelope["imageId"],
                    consumer_mode="FIXTURE",
                )

    def test_privacy_reason_guard_preserves_state_rejection_codes(self) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = ["   "]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[0]",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = ["Unreadable image", "Unreadable image"]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        unsafe_reason = "file:///tmp/receipt.jpg"
        envelope["sourceGate"]["reasons"] = [unsafe_reason, unsafe_reason]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_GATE_STATE",
            expected_path="$.sourceGate.reasons[1]",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        envelope["receipt"]["receiptFields"][0]["absenceReason"] = "\t"
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0].absenceReason",
        )

        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["receipt"]["receiptFields"][0][
            "absenceReason"
        ] = "file:///tmp/participant-001.jpg"
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_path="$.receipt.receiptFields[0].absenceReason",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["originalAutomaticValue"] = "unexpected"
        field["absenceReason"] = "file:/tmp/receipt.jpg"
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_CONTRADICTORY_FIELD_STATE",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0]",
        )

        envelope = _mutable_envelope("03-missing-required-store-name.json")
        field = envelope["receipt"]["receiptFields"][0]
        field["status"] = "INVALID"
        field["absenceReason"] = "file:/tmp/receipt.jpg"
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_UNKNOWN_ENUM",
            expected_request_id=envelope["requestId"],
            expected_image_id=envelope["imageId"],
            expected_path="$.receipt.receiptFields[0].status",
        )

    def test_validated_dto_is_deeply_immutable(self) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        validated = validate_presentation_v1_object(
            envelope,
            expected_request_id="request-synthetic-complete-001",
            expected_image_id="image-synthetic-complete-001",
            consumer_mode="FIXTURE",
        )
        self.assertIsInstance(validated.receipt.receipt_fields, tuple)
        with self.assertRaises(FrozenInstanceError):
            validated.request_id = "request-mutated"  # type: ignore[misc]

    def _assert_rejected(
        self,
        envelope: Mapping[str, object],
        expected_code: str,
        *,
        expected_request_id: str = "request-synthetic-complete-001",
        expected_image_id: str = "image-synthetic-complete-001",
        consumer_mode: str = "FIXTURE",
        expected_path: str | None = None,
    ) -> None:
        with self.assertRaises(ConformanceViolation) as caught:
            validate_presentation_v1_object(
                envelope,
                expected_request_id=expected_request_id,
                expected_image_id=expected_image_id,
                consumer_mode=consumer_mode,
            )
        self.assertEqual(expected_code, caught.exception.code)
        if expected_path is not None:
            self.assertEqual(expected_path, caught.exception.path)

    def _assert_rejected_at_both_entry_points(
        self,
        envelope: Mapping[str, object],
        expected_code: str,
        *,
        expected_request_id: str | None = None,
        expected_image_id: str | None = None,
        consumer_mode: str = "FIXTURE",
        expected_path: str | None = None,
    ) -> None:
        request_id = (
            expected_request_id
            if expected_request_id is not None
            else _require_string(envelope.get("requestId"), "envelope.requestId")
        )
        image_id = (
            expected_image_id
            if expected_image_id is not None
            else _require_string(envelope.get("imageId"), "envelope.imageId")
        )
        self._assert_rejected(
            envelope,
            expected_code,
            expected_request_id=request_id,
            expected_image_id=image_id,
            consumer_mode=consumer_mode,
            expected_path=expected_path,
        )
        with self.assertRaises(ConformanceViolation) as caught:
            decode_and_validate_presentation_v1(
                _json_bytes(envelope),
                expected_request_id=request_id,
                expected_image_id=image_id,
                consumer_mode=consumer_mode,
            )
        self.assertEqual(expected_code, caught.exception.code)
        if expected_path is not None:
            self.assertEqual(expected_path, caught.exception.path)

    def _assert_reason_rejected_at_all_boundaries(self, unsafe_reason: str) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [unsafe_reason]
        self._assert_rejected_at_both_entry_points(
            envelope,
            "REJECT_UNSAFE_PROVENANCE",
            expected_path="$.sourceGate.reasons[0]",
        )

        field_cases = (
            ("03-missing-required-store-name.json", 0),
            ("04-unresolved-purchase-date.json", 1),
        )
        for filename, field_index in field_cases:
            with self.subTest(filename=filename):
                envelope = _mutable_envelope(filename)
                envelope["receipt"]["receiptFields"][field_index][
                    "absenceReason"
                ] = unsafe_reason
                self._assert_rejected_at_both_entry_points(
                    envelope,
                    "REJECT_UNSAFE_PROVENANCE",
                    expected_request_id=envelope["requestId"],
                    expected_image_id=envelope["imageId"],
                    expected_path=(
                        f"$.receipt.receiptFields[{field_index}].absenceReason"
                    ),
                )

    def _assert_reason_accepted_at_all_boundaries(self, safe_reason: str) -> None:
        envelope = _mutable_envelope("01-complete-extracted-receipt.json")
        envelope["sourceGate"]["reasons"] = [safe_reason]
        self._assert_accepted_at_both_entry_points(envelope)

        field_cases = (
            ("03-missing-required-store-name.json", 0),
            ("04-unresolved-purchase-date.json", 1),
        )
        for filename, field_index in field_cases:
            with self.subTest(filename=filename):
                envelope = _mutable_envelope(filename)
                envelope["receipt"]["receiptFields"][field_index][
                    "absenceReason"
                ] = safe_reason
                self._assert_accepted_at_both_entry_points(envelope)

    def _assert_accepted_at_both_entry_points(
        self, envelope: Mapping[str, object]
    ) -> None:
        request_id = _require_string(envelope.get("requestId"), "envelope.requestId")
        image_id = _require_string(envelope.get("imageId"), "envelope.imageId")
        for entry_point in ("object", "json"):
            with self.subTest(entry_point=entry_point):
                if entry_point == "object":
                    validate_presentation_v1_object(
                        envelope,
                        expected_request_id=request_id,
                        expected_image_id=image_id,
                        consumer_mode="FIXTURE",
                    )
                else:
                    decode_and_validate_presentation_v1(
                        _json_bytes(envelope),
                        expected_request_id=request_id,
                        expected_image_id=image_id,
                        consumer_mode="FIXTURE",
                    )


def _run_fixture(raw_fixture: bytes, *, expected_from_manifest: str) -> str:
    """Run one wrapper while passing only its nested envelope to production."""

    try:
        wrapper = decode_strict_json_object(raw_fixture)
    except ConformanceViolation as violation:
        # The canonical duplicate-key case cannot become an ordinary wrapper.
        # A test-only pair tree preserves every key without overwriting or
        # reserializing, so wrapper metadata can still be checked independently.
        if violation.code == "REJECT_DUPLICATE_JSON_KEY":
            _verify_duplicate_fixture_wrapper(raw_fixture, expected_from_manifest)
        return violation.code

    wrapper = _require_exact_object(
        wrapper,
        allowed=_WRAPPER_ALLOWED_MEMBERS,
        required=_WRAPPER_REQUIRED_MEMBERS,
        label="fixture wrapper",
    )
    fixture_status = _require_string(wrapper["fixtureStatus"], "fixtureStatus")
    if fixture_status != "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY":
        raise AssertionError(f"unexpected fixtureStatus: {fixture_status!r}")
    _require_string(wrapper["scenario"], "scenario")
    wrapper_expected = _require_string(wrapper["expectedResult"], "expectedResult")
    if wrapper_expected != expected_from_manifest:
        raise AssertionError(
            "fixture expectedResult disagrees with manifest: "
            f"{wrapper_expected!r} != {expected_from_manifest!r}"
        )

    envelope = wrapper["envelope"]
    if not isinstance(envelope, Mapping):
        raise AssertionError("fixture envelope must be an object")
    expected_request_id, expected_image_id, mode = _consumer_context(
        wrapper.get("consumerContext"), envelope
    )

    try:
        # Only the nested runtime object crosses the production API boundary.
        validate_presentation_v1_object(
            envelope,
            expected_request_id=expected_request_id,
            expected_image_id=expected_image_id,
            consumer_mode=mode,
        )
    except ConformanceViolation as violation:
        return violation.code
    return "ACCEPT"


class _ObjectPairs(tuple[tuple[str, object], ...]):
    """Duplicate-preserving JSON object used only by the fixture harness."""


def _verify_duplicate_fixture_wrapper(raw_fixture: bytes, expected: str) -> None:
    def reject_constant(token: str) -> None:
        raise AssertionError(f"duplicate fixture contains nonstandard number {token}")

    decoded = json.loads(
        raw_fixture.decode("utf-8", errors="strict"),
        object_pairs_hook=lambda pairs: _ObjectPairs(pairs),
        parse_constant=reject_constant,
    )
    if not isinstance(decoded, _ObjectPairs):
        raise AssertionError("duplicate fixture wrapper must be an object")
    keys = [key for key, _ in decoded]
    if len(keys) != len(set(keys)):
        raise AssertionError("duplicate fixture must not duplicate wrapper members")
    if set(keys) - _WRAPPER_ALLOWED_MEMBERS:
        raise AssertionError("duplicate fixture wrapper has unknown members")
    if _WRAPPER_REQUIRED_MEMBERS - set(keys):
        raise AssertionError("duplicate fixture wrapper is missing required members")
    values = dict(decoded)
    wrapper_expected = _require_string(values["expectedResult"], "expectedResult")
    if wrapper_expected != expected:
        raise AssertionError("duplicate fixture expectedResult disagrees with manifest")
    fixture_status = _require_string(values["fixtureStatus"], "fixtureStatus")
    if fixture_status != "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY":
        raise AssertionError(f"unexpected fixtureStatus: {fixture_status!r}")
    _require_string(values["scenario"], "scenario")
    envelope = values["envelope"]
    if not isinstance(envelope, _ObjectPairs):
        raise AssertionError("duplicate fixture envelope must be an object")
    if not _contains_duplicate_object_member(envelope):
        raise AssertionError("duplicate fixture contains no preserved duplicate member")


def _contains_duplicate_object_member(value: object) -> bool:
    if isinstance(value, _ObjectPairs):
        keys = [key for key, _ in value]
        return len(keys) != len(set(keys)) or any(
            _contains_duplicate_object_member(member) for _, member in value
        )
    if isinstance(value, list):
        return any(_contains_duplicate_object_member(member) for member in value)
    return False


def _mutable_envelope(filename: str) -> dict[str, Any]:
    """Load a known canonical wrapper and copy its envelope for local mutations."""

    wrapper = decode_strict_json_object((_FIXTURES_DIRECTORY / filename).read_bytes())
    envelope = wrapper.get("envelope")
    if not isinstance(envelope, Mapping):
        raise AssertionError(f"{filename} must contain an envelope object")
    mutable = _mutable_json(envelope)
    if not isinstance(mutable, dict):
        raise AssertionError(f"{filename} envelope did not copy as an object")
    return mutable


def _mutable_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _mutable_json(member) for key, member in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json(member) for member in value]
    return value


def _json_bytes(value: object) -> bytes:
    def json_default(member: object) -> object:
        if isinstance(member, Decimal):
            return float(member)
        raise TypeError(f"cannot encode {type(member).__name__}")

    return json.dumps(
        value,
        default=json_default,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _consumer_context(
    raw_context: object, envelope: Mapping[str, object]
) -> tuple[str, str, str]:
    if raw_context is None:
        return (
            _require_string(envelope.get("requestId"), "envelope.requestId"),
            _require_string(envelope.get("imageId"), "envelope.imageId"),
            "FIXTURE",
        )
    context = _require_exact_object(
        raw_context,
        allowed=_CONTEXT_MEMBERS,
        required=_CONTEXT_MEMBERS,
        label="consumerContext",
    )
    return (
        _require_string(context["expectedRequestId"], "expectedRequestId"),
        _require_string(context["expectedImageId"], "expectedImageId"),
        _require_string(context["mode"], "mode"),
    )


def _strict_object(raw_json: bytes, *, label: str) -> Mapping[str, object]:
    try:
        return decode_strict_json_object(raw_json)
    except ConformanceViolation as violation:
        raise AssertionError(
            f"{label} is not strict JSON: {violation.code} at {violation.path}"
        ) from violation


def _require_exact_object(
    value: object,
    *,
    allowed: set[str],
    required: set[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssertionError(f"{label} must be an object")
    keys = set(value)
    unknown = keys - allowed
    missing = required - keys
    if unknown:
        raise AssertionError(f"{label} has unknown members: {sorted(unknown)}")
    if missing:
        raise AssertionError(f"{label} is missing members: {sorted(missing)}")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{label} must be a nonempty string")
    return value


def _assert_safe_fixture_path(test: unittest.TestCase, path: str) -> None:
    posix = PurePosixPath(path)
    test.assertFalse(posix.is_absolute())
    test.assertEqual(path, posix.as_posix())
    test.assertGreater(len(posix.parts), 1)
    test.assertEqual("fixtures", posix.parts[0])
    test.assertNotIn("..", posix.parts)
    test.assertEqual(".json", posix.suffix)


if __name__ == "__main__":
    unittest.main()

