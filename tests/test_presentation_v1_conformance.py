"""Manifest-driven cross-language receipt-presentation-v1 conformance tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unittest
from collections import Counter
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any
from pipeline.presentation_v1 import conformance as v1

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
        _check_dto_inventory()
        actual_rows = []
        expected_rows = []
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

                expected_row, actual_row = _structured_fixture(relative_path, raw_fixture, expected)
                expected_rows.append(expected_row)
                actual_rows.append(actual_row)
                actual = actual_row.get("diagnostic", {}).get("code", "ACCEPT")
                self.assertEqual(expected, actual)
                if expected == "ACCEPT":
                    self.assertEqual([], _record_differences(expected_row, actual_row))
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
        if output := _evidence_dir():
            _write_rows(output / "expected.jsonl", expected_rows)
            _write_rows(output / "python.jsonl", actual_rows)

    def test_date_domain_and_raw_precedence(self) -> None:
        _run_structured_probes(self)

    def test_native_confidence_record_is_exact(self) -> None:
        for token, coefficient, exponent in (
            ("0.750", "75", "-2"), ("75e-2", "75", "-2"),
            ("-0.00", "0", "0"), ("0E+4", "0", "0"),
            ("0.75000000000000000001", "75000000000000000001", "-20"),
        ):
            with self.subTest(token=token):
                expected = {"coefficient": coefficient, "exponent": exponent}
                self.assertEqual(expected, _decimal_dto(Decimal(token)))
                self.assertEqual(expected, _wire_expected(_strict_wire(token.encode("ascii")), "nativeConfidence"))
        self.assertIsNone(_dto_record(None))



# Explicit DTO schema, independent of the generic fixture-input reader.
_DTO_MEMBERS = {
    v1.ReceiptPresentationV1: "schemaName schemaVersion sourceContractVersion requestId imageId source outcome sourceEvidence sourceGate automaticExtraction receipt".split(),
    v1.PresentationSource: "type provenance".split(),
    v1.PresentationProvenance: "sourceSystem sourceReference contentSha256".split(),
    v1.PresentationOutcome: "status failure".split(),
    v1.PresentationFailure: "stage code retryable".split(),
    v1.PresentationSourceEvidence: "sourceProcessingStatus tokenIds".split(),
    v1.PresentationSourceGate: "gateResultId decision reasons".split(),
    v1.PresentationAutomaticExtraction: "stage extractionStatus producer".split(),
    v1.PresentationProducer: "producerId producerVersion".split(),
    v1.PresentationReceipt: "receiptId currencyCode receiptFields itemRows".split(),
    v1.PresentationItemRow: "rowId fields".split(),
    v1.PresentationField: "fieldId role status originalAutomaticValue presentationValue absenceReason sourceTokenIds nativeConfidence".split(),
}
_DTO_ENUMS = {
    (v1.PresentationSource, "type"): set("LOCAL_IMAGE SYNTHETIC_FIXTURE".split()),
    (v1.PresentationOutcome, "status"): set("RESULT_AVAILABLE PROCESSING_UNAVAILABLE PROCESSING_FAILED SOURCE_EVIDENCE_INSUFFICIENT".split()),
    (v1.PresentationFailure, "stage"): set("AVAILABILITY OCR SOURCE_GATE EXTRACTION PRESENTATION_ADAPTER".split()),
    (v1.PresentationSourceEvidence, "sourceProcessingStatus"): set("RECEIVED OCR_COMPLETED OCR_PARTIAL OCR_FAILED".split()),
    (v1.PresentationSourceGate, "decision"): set("SUFFICIENT INSUFFICIENT".split()),
    (v1.PresentationAutomaticExtraction, "stage"): set("PRE_REVIEW_AUTOMATIC".split()),
    (v1.PresentationAutomaticExtraction, "extractionStatus"): set("EXTRACTED PARTIAL FAILED".split()),
    (v1.PresentationField, "role"): set("STORE_NAME PURCHASE_DATE ITEM_DESCRIPTION QUANTITY UNIT_PRICE LINE_TOTAL RECEIPT_TOTAL".split()),
    (v1.PresentationField, "status"): set("EXTRACTED MISSING UNRESOLVED".split()),
}
_ENVELOPE_38_SHA = "afbfa334ff2b9ec1b5a00bc6e9fed85b5074cc7413af966ef249189768a0614a"
_STRING_TOKEN = re.compile(rb'"(?:[^"\\\x00-\x1f]|\\[^\r\n])*"')
_PATH_REQUIREMENTS = {
    "08": "$.schemaVersion",
    "33": "$.receipt.receiptFields[1].presentationValue",
    "38": "$",
    "44": "$.requestId",
    "45": "$.imageId",
    "57": "$.receipt.itemRows[0].fields[0].sourceTokenIds[0]",
}


def _attribute(key: str) -> str:
    return re.sub(r"(?<!^)[A-Z]", lambda match: "_" + match[0].lower(), key)


def _check_dto_inventory() -> None:
    for dto, members in _DTO_MEMBERS.items():
        mapped = {_attribute(key) for key in members}
        if len(mapped) != len(members) or mapped != {field.name for field in fields(dto)}:
            raise AssertionError(f"DTO field inventory mismatch: {dto.__name__}")


def _strict_wire(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate member {key!r}")
            result[key] = value
        return result

    def invalid_constant(token: str) -> Any:
        raise ValueError(f"invalid JSON constant {token}")

    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=object_pairs,
                      parse_float=Decimal, parse_int=Decimal, parse_constant=invalid_constant)


def _envelope_span(raw: bytes) -> tuple[int, int]:
    if len(raw) > 1_048_576 or not raw.lstrip().startswith(b"{"):
        raise ValueError("fixture wrapper size or root")
    raw.decode("utf-8", errors="strict")
    stack: list[int] = []
    start = end = None
    index = 0
    while index < len(raw):
        token = raw[index]
        if token == ord('"'):
            match = _STRING_TOKEN.match(raw, index)
            if match is None:
                raise ValueError("unterminated string")
            if stack == [ord("{")] and json.loads(match[0]) == "envelope":
                tail = re.match(rb"\s*:\s*", raw[match.end():])
                if tail is not None:
                    candidate = match.end() + tail.end()
                    if start is not None or raw[candidate:candidate + 1] != b"{":
                        raise ValueError("duplicate or non-object envelope")
                    start = candidate
            index = match.end()
            continue
        if token in b"{[":
            stack.append(token)
            if len(stack) > 64:
                raise ValueError("fixture depth exceeds 64")
        elif token in b"}]":
            opening = ord("{") if token == ord("}") else ord("[")
            if not stack or stack.pop() != opening:
                raise ValueError("unbalanced fixture")
            if start is not None and end is None and len(stack) == 1 and token == ord("}"):
                end = index + 1
        index += 1
    if stack or start is None or end is None:
        raise ValueError("missing or incomplete envelope")
    return start, end


def _decimal_dto(value: Decimal) -> dict[str, str]:
    sign, digits, exponent = value.as_tuple()
    coefficient = "".join(map(str, digits)).lstrip("0")
    if not coefficient:
        return {"coefficient": "0", "exponent": "0"}
    trimmed = coefficient.rstrip("0")
    return {"coefficient": ("-" if sign else "") + trimmed,
            "exponent": str(exponent + len(coefficient) - len(trimmed))}


def _wire_expected(value: Any, member: str | None = None) -> Any:
    if isinstance(value, dict):
        return {key: _wire_expected(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_wire_expected(item) for item in value]
    if isinstance(value, Decimal):
        if member != "nativeConfidence":
            raise ValueError(f"unexpected numeric fixture member: {member}")
        # Independent conversion of the exact JSON number, without DTO inspection.
        if value.is_zero():
            return {"coefficient": "0", "exponent": "0"}
        whole, _, exponent = format(value, "e").partition("e")
        sign = "-" if whole.startswith("-") else ""
        integer, _, fraction = whole.lstrip("-").partition(".")
        digits = (integer + fraction).rstrip("0")
        removed = len(integer) + len(fraction) - len(digits)
        return {"coefficient": sign + digits, "exponent": str(int(exponent) - len(fraction) + removed)}
    return value


def _dto_record(value: Any) -> Any:
    if type(value) in (str, bool, type(None)):
        return value
    if isinstance(value, Decimal):
        return _decimal_dto(value)
    if isinstance(value, tuple):
        return [_dto_record(item) for item in value]
    dto = type(value)
    record = {}
    for key in _DTO_MEMBERS[dto]:
        member = getattr(value, _attribute(key))
        allowed = _DTO_ENUMS.get((dto, key))
        if allowed is not None and member not in allowed:
            raise ValueError(f"unexpected enum token: {dto.__name__}.{key}={member!r}")
        record[key] = _dto_record(member)
    return record


def _evidence_dir() -> Path | None:
    return Path(path) if (path := os.environ.get("PANTRYPROOF_M3E_PARITY_EVIDENCE_DIR")) else None


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def _fixture_input(path: str, raw: bytes, expected: str) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    start, end = _envelope_span(raw)
    envelope = raw[start:end]
    wrapper = _require_exact_object(
        _strict_wire(raw[:start] + b"{}" + raw[end:]),
        allowed=_WRAPPER_ALLOWED_MEMBERS, required=_WRAPPER_REQUIRED_MEMBERS, label="fixture wrapper",
    )
    if (wrapper["expectedResult"] != expected or wrapper["fixtureStatus"] != "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY"
            or type(wrapper["scenario"]) is not str or not wrapper["scenario"].strip()):
        raise AssertionError("fixture wrapper identity mismatch")
    digest = hashlib.sha256(envelope).hexdigest()
    if path.startswith("fixtures/38-"):
        if (start, end, digest) != (188, 947, _ENVELOPE_38_SHA):
            raise AssertionError("fixture 38 envelope span or hash changed")
        wire = {"requestId": "request-duplicate-json-key-001", "imageId": "image-duplicate-json-key-001"}
    else:
        wire = _strict_wire(envelope)
    request, image, mode = _consumer_context(wrapper.get("consumerContext"), wire)
    meta = {"fixtureId": path, "fixtureGitBlob": hashlib.sha1(
                f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest(),
            "fixtureSha256": hashlib.sha256(raw).hexdigest(), "envelopeSha256": digest,
            "context": {"expectedRequestId": request, "expectedImageId": image, "mode": mode}}
    return envelope, wire, meta


def _decode_record(raw: bytes, context: Mapping[str, str]) -> dict[str, Any]:
    try:
        dto = decode_and_validate_presentation_v1(
            raw, expected_request_id=context["expectedRequestId"],
            expected_image_id=context["expectedImageId"], consumer_mode=context["mode"],
        )
    except ConformanceViolation as issue:
        return {"verdict": "REJECT", "diagnostic": {
            "code": issue.code, "path": issue.path, "detail": issue.detail}}
    return {"verdict": "ACCEPT", "record": _dto_record(dto)}


def _structured_fixture(path: str, raw: bytes, expected: str) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope, wire, meta = _fixture_input(path, raw, expected)
    actual = meta | _decode_record(envelope, meta["context"])
    if expected == "ACCEPT":
        return meta | {"verdict": "ACCEPT", "record": _wire_expected(wire)}, actual
    required_path = _PATH_REQUIREMENTS.get(Path(path).name.split("-")[0])
    if required_path is not None and actual.get("diagnostic", {}).get("path") != required_path:
        raise AssertionError(f"{path}: unexpected diagnostic path: {actual}")
    if path.startswith("fixtures/38-") and (output := _evidence_dir()):
        with (output / "fixture-38-python.bin").open("xb") as stream:
            stream.write(envelope)
    return meta | {"verdict": "REJECT", "diagnostic": {"code": expected, "path": required_path}}, actual


def _record_differences(expected: Any, actual: Any, path: str = "") -> list[dict[str, Any]]:
    if type(expected) is type(actual):
        if isinstance(expected, dict):
            differences = []
            for key in sorted(expected.keys() | actual.keys()):
                pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in expected or key not in actual:
                    difference = {"pointer": pointer, "kind": "unexpected" if key in actual else "missing"}
                    if key in expected:
                        difference["expected"] = expected[key]
                    if key in actual:
                        difference["actual"] = actual[key]
                    differences.append(difference)
                else:
                    differences.extend(_record_differences(expected[key], actual[key], pointer))
            return differences
        if isinstance(expected, list):
            differences = [] if len(expected) == len(actual) else [
                {"pointer": path, "kind": "length", "expected": len(expected), "actual": len(actual)}]
            for index, (left, right) in enumerate(zip(expected, actual)):
                differences.extend(_record_differences(left, right, f"{path}/{index}"))
            return differences
        if expected == actual:
            return []
    return [{"pointer": path, "kind": "value" if type(expected) is type(actual) else "type",
             "expected": expected, "actual": actual}]


def compare_structured_evidence(run_directory: str) -> int:
    directory = Path(run_directory)
    report: dict[str, Any] = {"acceptCompared": 0, "rejectCompared": 0, "differences": [],
                              "diagnostics": [], "cases": []}
    try:
        manifest_bytes = _MANIFEST_PATH.read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != "4b1bcd3445d82852c7f4c3beb5f0e07f39853497e92713b81a063dcdf5350ee9":
            raise ValueError("comparator manifest hash mismatch")
        manifest = _strict_wire(manifest_bytes)["fixtures"]
        expected, python, kotlin = (
            [_strict_wire(line) for line in (directory / filename).read_bytes().splitlines()]
            for filename in ("expected.jsonl", "python.jsonl", "kotlin.jsonl")
        )
        paths = [entry["path"] for entry in manifest]
        for rows in (expected, python, kotlin):
            if [row["fixtureId"] for row in rows] != paths or len(paths) != 32 or len(set(paths)) != 32:
                raise ValueError("missing, duplicate, or out-of-order evidence rows")
        for entry, oracle, py, kt in zip(manifest, expected, python, kotlin):
            path, verdict = entry["path"], entry["expectedResult"]
            raw = (_FIXTURE_ROOT / path).read_bytes()
            envelope, wire, meta = _fixture_input(path, raw, verdict)
            if meta["fixtureSha256"] != entry["sha256"] or len(raw) != entry["byteLength"]:
                raise ValueError(f"comparator fixture identity mismatch: {path}")
            required_path = _PATH_REQUIREMENTS.get(Path(path).name.split("-")[0])
            if verdict == "ACCEPT":
                rebuilt = meta | {"verdict": "ACCEPT", "record": _wire_expected(wire)}
                comparisons = (("oracle integrity", rebuilt, oracle), ("expected/python", oracle, py),
                               ("expected/kotlin", oracle, kt), ("python/kotlin", py, kt))
                report["acceptCompared"] += 1
            else:
                rebuilt = meta | {"verdict": "REJECT", "diagnostic": {"code": verdict, "path": required_path}}
                comparisons = [("oracle integrity", rebuilt, oracle)]
                for label, actual in (("python", py), ("kotlin", kt)):
                    diagnostic = actual["diagnostic"]
                    if set(diagnostic) != {"code", "path", "detail"} or any(type(x) is not str for x in diagnostic.values()):
                        raise ValueError(f"invalid {label} diagnostic: {path}")
                    comparable = actual | {"diagnostic": {"code": diagnostic["code"],
                                                          "path": diagnostic["path"] if required_path else None}}
                    comparisons.append((label, rebuilt, comparable))
                report["diagnostics"].append({"fixtureId": path, "expectedCode": verdict,
                                              "requiredPath": required_path, "python": py["diagnostic"],
                                              "kotlin": kt["diagnostic"], "pathsMatch":
                                              py["diagnostic"]["path"] == kt["diagnostic"]["path"]})
                report["rejectCompared"] += 1
            checks = {}
            for label, left, right in comparisons:
                differences = [
                    {"fixtureId": path, "comparison": label} | diff
                    for diff in _record_differences(left, right)
                ]
                checks[label] = not differences
                report["differences"].extend(differences)
            report["cases"].append({"fixtureId": path, "expectedResult": verdict, "checks": checks})
            if path.startswith("fixtures/38-"):
                for language in ("python", "kotlin"):
                    if (directory / f"fixture-38-{language}.bin").read_bytes() != envelope:
                        raise ValueError(f"{language} fixture 38 input bytes differ")
                report["fixture38"] = {"offset": 188, "endExclusive": 947, "length": len(envelope),
                                       "sha256": _ENVELOPE_38_SHA, "byteIdentical": True}
        if (report["acceptCompared"], report["rejectCompared"]) != (17, 15):
            raise ValueError("comparison distribution mismatch")
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        report["error"] = str(error)
    report["passed"] = not report["differences"] and "error" not in report
    with (directory / "comparison.json").open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, default=str)
        output.write("\n")
    return 0 if report["passed"] else 1


def _run_structured_probes(case: unittest.TestCase) -> None:
    def encode(value: Any) -> str:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return "{" + ",".join(json.dumps(key) + ":" + encode(item) for key, item in value.items()) + "}"
        if isinstance(value, list):
            return "[" + ",".join(map(encode, value)) + "]"
        return json.dumps(value, allow_nan=False)

    def probe(label: str, envelope: dict[str, Any], code: str | None, path: str | None,
              raw: bytes | None = None) -> None:
        context = {"expectedRequestId": envelope["requestId"], "expectedImageId": envelope["imageId"], "mode": "FIXTURE"}
        with case.subTest(label=label):
            actual = _decode_record(raw if raw is not None else encode(envelope).encode("utf-8"), context)
            if code is None:
                case.assertEqual("ACCEPT", actual["verdict"])
                date = actual["record"]["receipt"]["receiptFields"][1]
                case.assertEqual(label, date["originalAutomaticValue"])
                case.assertEqual(label, date["presentationValue"])
            else:
                case.assertEqual(code, actual["diagnostic"]["code"])
                case.assertEqual(path, actual["diagnostic"]["path"])

    date_path = "$.receipt.receiptFields[1]"
    valid_dates = ("0001-01-01", "9999-12-31", "0004-02-29", "1582-10-10", "2000-02-29")
    invalid_dates = ("0000-01-01", "0000-02-29", "0001-02-29", "1900-02-29", "2100-02-29",
                     "2026-02-30", "10000-01-01", "2026-2-03")
    for date in valid_dates + invalid_dates:
        env = _mutable_envelope("01-complete-extracted-receipt.json")
        env["receipt"]["receiptFields"][1].update(originalAutomaticValue=date, presentationValue=date)
        probe(date, env, None if date in valid_dates else "REJECT_INVALID_DATE", date_path + ".presentationValue")
    env["receipt"]["receiptFields"][1].update(originalAutomaticValue="0001-01-01", presentationValue="0000-02-29")
    probe("date relationship first", env, "REJECT_VALUE_RELATIONSHIP", date_path)
    env = _mutable_envelope("01-complete-extracted-receipt.json")
    env["schemaVersion"] = "999"
    probe("duplicate before version", env, "REJECT_DUPLICATE_JSON_KEY", "$",
          b'{"schemaVersion":"1",' + encode(env).encode("utf-8")[1:])
    reason = "Reference evidence A12"
    env = _mutable_envelope("16-source-evidence-insufficient.json")
    env["sourceGate"]["reasons"] = [reason, reason]
    probe("duplicate gate reason", env, "REJECT_GATE_STATE", "$.sourceGate.reasons[1]")
    env["sourceGate"]["reasons"] = [reason]
    probe("unsafe gate reason", env, "REJECT_UNSAFE_PROVENANCE", "$.sourceGate.reasons[0]")
    for name, index in (("03-missing-required-store-name.json", 0), ("04-unresolved-purchase-date.json", 1)):
        env = _mutable_envelope(name)
        field = env["receipt"]["receiptFields"][index]
        field["absenceReason"] = reason
        path = f"$.receipt.receiptFields[{index}]"
        probe("unsafe absence reason " + name, env, "REJECT_UNSAFE_PROVENANCE", path + ".absenceReason")
        field["originalAutomaticValue"] = "unexpected"
        probe("contradiction before privacy " + name, env, "REJECT_CONTRADICTORY_FIELD_STATE", path)

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

