"""Source-defined acceptance cases for the jointly ratified S01 policy."""

from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from pipeline import gate_c_source_gate_v0 as gate
from pipeline.contracts import (
    OcrSourceToken,
    Point,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.ocr_adapter import AdaptedOcrSource


_RECEIPT = "rct-" + "1" * 32
_IMAGE = "img-" + "2" * 32
_GATE_ID = "gat-" + "3" * 32
_POLICY = gate.GATE_C_SOURCE_GATE_V0
_REASON = "Synthetic source structure was unavailable."
_ITEM_TEXT = "MILK 2 X 3.00 6.00"
_TOTAL_TEXT = "TOTAL 6.00"


def _polygon(left, top, right, bottom):
    return (
        Point(left, top),
        Point(right, top),
        Point(right, bottom),
        Point(left, bottom),
    )


_ITEM_BOX = _polygon(10, 10, 90, 30)
_TOTAL_BOX = _polygon(20, 40, 100, 60)


def _source(regions=(), *, status=SourceProcessingStatus.OCR_COMPLETED):
    return AdaptedOcrSource(
        receipt_id=_RECEIPT,
        image_id=_IMAGE,
        provenance=SourceProvenance("GATE_C_TEST", "generated-source"),
        processing_status=status,
        tokens=tuple(
            OcrSourceToken(_RECEIPT, f"{_RECEIPT}:paddleocr:{index:06d}", text, polygon, score)
            for index, (text, polygon, score) in enumerate(regions)
        ),
    )


def _repeated_source(texts, polygon=_ITEM_BOX):
    return _source((text, polygon, None) for text in texts)


def _positive(*, item_text=_ITEM_TEXT, total_text=_TOTAL_TEXT, item_box=_ITEM_BOX, total_box=_TOTAL_BOX):
    return _source(((item_text, item_box, None), (total_text, total_box, None)))


class GateCSourceGateTests(unittest.TestCase):
    def evaluate(self, source, *, policy=_POLICY, gate_id=_GATE_ID):
        return gate.evaluate_gate_c_source_v0(source=source, gate_result_id=gate_id, policy=policy)

    def assert_refusal(self, code, source, **context):
        with self.assertRaises(gate.GateCSourceGateRefusal) as raised:
            self.evaluate(source, **context)
        error = raised.exception
        self.assertEqual(error.code, code)
        self.assertEqual(error.args, (code,))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertFalse(getattr(error, "__notes__", ()))

    def assert_decision(self, source, expected, reasons):
        result = self.evaluate(source)
        self.assertIs(type(result), SourceEvidenceGateResult)
        self.assertIs(result.receipt_id, source.receipt_id)
        self.assertIs(result.gate_result_id, _GATE_ID)
        self.assertIs(result.decision, expected)
        self.assertEqual(result.reasons, reasons)
        return result

    def test_ratified_policy_identity_is_immutable(self):
        self.assertEqual(_POLICY.policy_id, "GATE_C_SOURCE_GATE_V0")
        self.assertEqual(_POLICY.revision, "S01")
        self.assertEqual(
            _POLICY.canonical_sha256,
            "488F962428AEFA098DCFA73D435A9711A73E90EEC74FCAA88DB4ECED0C98C72A",
        )
        self.assertEqual(_POLICY.reason_map, (
            ("NO_RECOGNITION_EVIDENCE", _REASON), ("NO_RECEIPT_STRUCTURE", _REASON),
        ))
        with self.assertRaises(FrozenInstanceError):
            _POLICY.revision = "S02"

    def test_whole_region_item_plus_total_returns_one_original_gate(self):
        source = _positive()
        original_gates = []

        def build(*args, **kwargs):
            result = SourceEvidenceGateResult(*args, **kwargs)
            original_gates.append(result)
            return result

        with patch.object(gate, "SourceEvidenceGateResult", side_effect=build) as construct:
            result = self.assert_decision(source, SourceEvidenceDecision.SUFFICIENT, ())
        construct.assert_called_once()
        self.assertIs(result, original_gates[0])

    def test_ascii_comparison_normalization_and_exact_lexical_cues(self):
        for item, summary in (
            ("\tMilk  Powder \t 0.750 \tx RM 3.00 MYR 6.00\t", "\tgrand\t total:\t MYR 6.00 "),
            ("MILK 000.00 X 0.00 1234.50", "TOTAL RM 0.00"),
        ):
            with self.subTest(item=item, summary=summary):
                self.assert_decision(
                    _positive(item_text=item, total_text=summary), SourceEvidenceDecision.SUFFICIENT, ()
                )

    def test_near_miss_lexical_cues_are_ambiguous(self):
        for item_text in (
            "MILK 2 × 3.00 6.00",
            "MILK 2 X RM3.00 6.00",
            "MILK 2 X 03.00 6.00",
            "MILK 2 X $3.00 6.00",
            "MILK 2 X 3.0 6.00",
            "MILK 2 X 3.00 6.00 EXTRA",
            "MILK\u00a02 X 3.00 6.00",
            "MILK ٢ X 3.00 6.00",
            "MILK 2. X 3.00 6.00",
            "CASH 2 X 3.00 6.00",
        ):
            with self.subTest(item=item_text):
                self.assert_refusal("AMBIGUOUS_EVIDENCE", _positive(item_text=item_text))
        for total_text in ("TOTAL:6.00", "TOTAL : 6.00", "TOTAL 6.000", "TOTAL 1,000.00", "TOTALS 6.00"):
            with self.subTest(total=total_text):
                self.assert_refusal("AMBIGUOUS_EVIDENCE", _positive(total_text=total_text))

    def test_geometry_controls_order_and_vertical_edge_contact_passes(self):
        forward = (
            (_ITEM_TEXT, _polygon(0, 0, 90, 40), None),
            (_TOTAL_TEXT, _polygon(20, 40, 1100, 700), None),
        )
        for order in (forward, forward[::-1]):
            self.assert_decision(_source(order), SourceEvidenceDecision.SUFFICIENT, ())

    def test_geometry_refuses_horizontal_touch_crossing_and_each_incoherent_item(self):
        for item_box in (
            _polygon(0, 0, 20, 30),
            _polygon(0, 0, 90, 40.5),
            _polygon(0, 61, 90, 80),
            _polygon(10, 10, 10, 30),
        ):
            self.assert_refusal("AMBIGUOUS_EVIDENCE", _positive(item_box=item_box))
        second = ("TEA 1 X 2.00 2.00", _polygon(100, 0, 170, 30), None)
        self.assert_refusal(
            "AMBIGUOUS_EVIDENCE",
            _source(((_ITEM_TEXT, _ITEM_BOX, None), second, (_TOTAL_TEXT, _TOTAL_BOX, None))),
        )

    def test_all_summary_heads_count_including_incomplete_ones(self):
        for conflicting in ("TOTAL", "TOTAL:6.00", "TOTAL 2.00", "GRAND TOTAL:"):
            self.assert_refusal(
                "AMBIGUOUS_EVIDENCE",
                _source((
                    (_ITEM_TEXT, _ITEM_BOX, None),
                    (_TOTAL_TEXT, _TOTAL_BOX, None),
                    (conflicting, _polygon(20, 80, 100, 100), None),
                )),
            )

    def test_partial_fragmented_numeric_and_control_evidence_is_ambiguous(self):
        for texts in (
            ("TOTAL 6.00",),
            (_ITEM_TEXT,),
            ("TOTAL",),
            ("6.00",),
            ("MILK 6.00", _TOTAL_TEXT),
            ("MILK", "2 X 3.00 6.00", _TOTAL_TEXT),
            (_ITEM_TEXT, "TOTAL", "6.00"),
            ("THANK YOU", "ITEMS"),
            ("apple grape!",),
        ):
            with self.subTest(texts=texts):
                self.assert_refusal("AMBIGUOUS_EVIDENCE", _repeated_source(texts))

    def test_completed_empty_and_plain_words_share_exact_singleton_reason(self):
        for source in (_source(), _repeated_source((" \t THANK  YOU. ", "apple\t grape"))):
            self.assert_decision(source, SourceEvidenceDecision.INSUFFICIENT, (_REASON,))

    def test_degenerate_plain_word_box_is_ambiguous(self):
        self.assert_refusal(
            "AMBIGUOUS_EVIDENCE", _repeated_source(("HELLO",), _polygon(0, 0, 20, 0))
        )

    def test_reason_collision_uses_exact_original_text_and_returns_no_gate(self):
        with patch.object(gate, "SourceEvidenceGateResult") as construct:
            self.assert_refusal("GATE_REASON_CONFLICT", _repeated_source((_REASON,)))
        construct.assert_not_called()

        for text in (" " + _REASON, _REASON.upper(), "NOTE " + _REASON):
            self.assert_decision(_repeated_source((text,)), SourceEvidenceDecision.INSUFFICIENT, (_REASON,))

    def test_unsupported_statuses_are_distinct_from_malformed_status(self):
        for status in (
            SourceProcessingStatus.RECEIVED, SourceProcessingStatus.OCR_PARTIAL, SourceProcessingStatus.OCR_FAILED,
        ):
            with self.subTest(status=status):
                self.assert_refusal("UNSUPPORTED_EVIDENCE_STATUS", _source(status=status))
        self.assert_refusal("MALFORMED_SOURCE", _source(status="OCR_COMPLETED"))

    def test_source_receipt_and_ordinal_identity_checks(self):
        source = _positive()
        token, second = source.tokens
        foreign = replace(token, receipt_id="rct-" + "4" * 32)
        duplicate = replace(second, token_id=token.token_id)
        wrong_order = replace(second, token_id=f"{_RECEIPT}:paddleocr:000002")
        for tokens in ((foreign, second), (token, duplicate), (second, token), (token, wrong_order)):
            corrupted = _positive()
            object.__setattr__(corrupted, "tokens", tokens)
            self.assert_refusal("SOURCE_BINDING_MISMATCH", corrupted)

        self.assert_refusal("SOURCE_BINDING_MISMATCH", replace(source, image_id="unbound"))
        self.assert_refusal("MALFORMED_SOURCE", object())

    def test_bad_gate_id_syntax_has_no_result(self):
        for gate_id in ("", "gat-" + "f" * 31, "gat-" + "A" * 32, "id-" + "f" * 32, None):
            self.assert_refusal("INVALID_GATE_ID", _source(), gate_id=gate_id)

    def test_unapproved_policy_and_incomplete_reason_map_have_precedence(self):
        self.assert_refusal("POLICY_UNAPPROVED", _source(), policy=replace(_POLICY))
        self.assert_refusal("POLICY_UNAPPROVED", _source(), policy=replace(_POLICY, revision="S02"))
        changed = replace(_POLICY, canonical_sha256="0" * 64)
        with patch.object(gate, "GATE_C_SOURCE_GATE_V0", changed):
            self.assert_refusal("POLICY_UNAPPROVED", _source(), policy=changed)
        a, b = _POLICY.reason_map
        for reasons in ((), (a,), (a, a), (b, a), (a, (b[0], "Unapproved reason."))):
            changed = replace(_POLICY, reason_map=reasons)
            with patch.object(gate, "GATE_C_SOURCE_GATE_V0", changed):
                self.assert_refusal("POLICY_INCOMPLETE", _source(), policy=changed, gate_id="")
        self.assert_refusal("INVALID_GATE_ID", object(), gate_id="wrong")

    def test_malformed_source_geometry_text_and_score_refuse(self):
        source = _positive()
        object.__setattr__(source, "tokens", list(source.tokens))
        self.assert_refusal("MALFORMED_SOURCE", source)
        for text in ("", " \t ", "\ud800"):
            source = _repeated_source(("HELLO",))
            object.__setattr__(source.tokens[0], "original_text", text)
            self.assert_refusal("MALFORMED_SOURCE", source)
        for polygon in (
            (Point(0, 0), Point(1, 1)),
            (Point(0, 0), Point(1, 1), (1, 2)),
            (Point(0, 0), Point(float("inf"), 1), Point(1, 2)),
            (Point(0, 0), Point(True, 1), Point(1, 2)),
            _polygon(-1, 0, 20, 30),
            _polygon(0, 0, 1101, 70),
            _polygon(0, 0, 20, 701),
        ):
            source = _repeated_source(("HELLO",))
            object.__setattr__(source.tokens[0], "polygon", polygon)
            self.assert_refusal("MALFORMED_SOURCE", source)
        for score in (False, "0.9", float("inf"), float("nan")):
            source = _repeated_source(("HELLO",))
            object.__setattr__(source.tokens[0], "raw_confidence", score)
            self.assert_refusal("MALFORMED_SOURCE", source)

    def test_exact_and_one_over_region_and_polygon_bounds(self):
        eight = _polygon(0, 0, 1100, 700) * 2
        exact = _repeated_source(("WORD",) * 128, eight)
        self.assert_decision(exact, SourceEvidenceDecision.INSUFFICIENT, (_REASON,))
        self.assert_refusal("EVIDENCE_LIMIT_EXCEEDED", _repeated_source(("WORD",) * 129, eight))

        # With at most 128 regions the first additional point must also exceed
        # the per-region vertex cap. The admitted population is 1,024 points.
        object.__setattr__(exact.tokens[-1], "polygon", eight + (Point(1, 1),))
        self.assert_refusal("EVIDENCE_LIMIT_EXCEEDED", exact)

    def test_exact_and_one_over_text_and_utf8_budgets(self):
        for texts in (("A" * 256,), ("A" * 256,) * 64):
            self.assert_decision(_repeated_source(texts), SourceEvidenceDecision.INSUFFICIENT, (_REASON,))
        astral = "\U0001f600" * 256
        for texts in ((astral,), (astral,) * 48):
            self.assert_refusal("AMBIGUOUS_EVIDENCE", _repeated_source(texts))
        for texts in (
            ("A" * 257,),
            ("A" * 256,) * 64 + ("A",),
            (astral,) * 48 + ("A",),
        ):
            self.assert_refusal("EVIDENCE_LIMIT_EXCEEDED", _repeated_source(texts))

    def test_native_confidence_never_changes_classification_or_records(self):
        for score in (None, -0.0, 0.0, 0.95, 1.0, 1.5):
            source = _source(((_ITEM_TEXT, _ITEM_BOX, score), (_TOTAL_TEXT, _TOTAL_BOX, None)))
            self.assert_decision(source, SourceEvidenceDecision.SUFFICIENT, ())
            self.assertIs(source.tokens[0].raw_confidence, score)

    def test_evaluation_keeps_original_source_token_polygon_and_provenance(self):
        source = _positive(item_text=" MILK   2 \tX 3.00 6.00\t")
        tokens = source.tokens
        provenance = source.provenance
        original = [(token, token.original_text, token.polygon, tuple(token.polygon)) for token in tokens]
        self.assert_decision(source, SourceEvidenceDecision.SUFFICIENT, ())
        self.assertIs(source.tokens, tokens)
        self.assertIs(source.provenance, provenance)
        self.assertIs(source.processing_status, SourceProcessingStatus.OCR_COMPLETED)
        for actual, (token, literal, polygon, points) in zip(source.tokens, original):
            self.assertIs(actual, token)
            self.assertIs(actual.original_text, literal)
            self.assertIs(actual.polygon, polygon)
            for point, expected in zip(actual.polygon, points):
                self.assertIs(point, expected)

    def test_unexpected_exception_is_sanitized_and_never_constructs_a_gate(self):
        def fail(*args):
            try:
                raise RuntimeError("private diagnostic")
            except RuntimeError as cause:
                error = ValueError("private source value")
                error.add_note("private note")
                raise error from cause

        with (
            patch.object(gate, "_classify_nonempty", side_effect=fail),
            patch.object(gate, "SourceEvidenceGateResult") as construct,
        ):
            self.assert_refusal("GATE_EXECUTION_FAILED", _positive())
        construct.assert_not_called()

    def test_unrecognized_refusal_metadata_cannot_escape(self):
        with patch.object(
            gate, "_classify_nonempty", side_effect=gate.GateCSourceGateRefusal("private text")
        ):
            self.assert_refusal("GATE_EXECUTION_FAILED", _positive())

    def test_evaluation_has_no_external_or_downstream_dispatch(self):
        source = _positive()
        prohibited = AssertionError("External operation")
        with (
            patch("builtins.open", side_effect=prohibited) as open_file,
            patch("io.open", side_effect=prohibited) as io_open,
            patch("socket.socket", side_effect=prohibited) as socket_open,
            patch("pipeline.ocr_adapter.adapt_paddleocr_result", side_effect=prohibited) as adapt,
            patch("pipeline.ocr_adapter.attach_gate_result", side_effect=prohibited) as attach,
            patch("builtins.__import__", side_effect=prohibited) as dynamic_import,
        ):
            self.assert_decision(source, SourceEvidenceDecision.SUFFICIENT, ())
        for operation in (open_file, io_open, socket_open, adapt, attach, dynamic_import):
            operation.assert_not_called()
