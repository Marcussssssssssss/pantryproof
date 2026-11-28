"""In-memory HTTP composition with generated OCR and test-only policy artifacts."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from unittest.mock import Mock

import pytest

from evaluation.research_policy_v0 import FitConfiguration, FrozenCalibration, FrozenScorer
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed import purchase_date_correction_v0, receipt_correction_v1, receipt_research_v1
from scripts import dev_local_image_backend_v0 as bootstrap
from tests.test_backend_local_image_receipt_v0 import _payload, _provider
from tests.test_dev_local_image_backend_v0 import _TOKEN, _write_pin, approved_export
from tests.test_receipt_correction_v1 import resources as synthetic_resources


def _verification_record():
    fit = FitConfiguration(iterations=1, learning_rate=0.1, l2=0.1)
    scorer = FrozenScorer("2" * 64, "3" * 64, fit, (4.0, 0.0, 0.0, -4.0, *(0.0,) * 11))
    calibration = FrozenCalibration(scorer.sha256, "4" * 64, fit, 0.0, 1.0, 0.0, 1.0)
    return {
        "scorer": asdict(scorer),
        "scorer_sha256": scorer.sha256,
        "calibration": asdict(calibration),
        "calibration_sha256": calibration.sha256,
        "field_settings": {name.value: {
            "pantry_relevant": True,
            "policy": {"acceptance_threshold": 0.5, "force_review": name is ReceiptFieldName.ITEM_DESCRIPTION},
            "replacement_margin": 0.0,
            "unresolved_conflict": False,
        } for name in ReceiptFieldName},
    }


def _select_proposed(manifest, *, verified):
    snapshot = Path(__file__).resolve().parents[1] / "resources" / "receipt_pricecatcher_kl_v1.json"
    raw = snapshot.read_bytes()
    manifest["receipt_method"] = json.loads(json.dumps({
        "method_id": "PROPOSED_RECEIPT_V1",
        "region": "W.P. Kuala Lumpur",
        "resource_snapshot": {"path": str(snapshot), "length": len(raw), "sha256": sha256(raw).hexdigest()},
        "price_rule": {"rule_id": "synthetic-test-only", "relative_tolerance": "0"},
        "correction_config": {"candidate_limit": 4, "proposal_limit": 24, "confidence_floor": "0.50"},
        "verification": _verification_record() if verified else None,
    }))


@pytest.mark.parametrize("mode", ("policy", "not-ready", "fallback", "method-failure"))
def test_operational_proposed_mode_through_existing_http_processor(
    approved_export, monkeypatch, tmp_path, mode,
):
    manifest, encoded = approved_export
    original_pin = _write_pin(tmp_path / "legacy-serve.json", json.dumps(manifest).encode("utf-8"))
    _select_proposed(manifest, verified=mode == "policy")
    serve_pin = _write_pin(tmp_path / "proposed-serve.json", json.dumps(manifest).encode("utf-8"))
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal, match="manifest identity"):
        bootstrap._read_manifest(serve_pin.path, original_pin.sha256)
    launch = bootstrap._prepare_launch(
        bootstrap._read_manifest(serve_pin.path, serve_pin.sha256), bootstrap._preflight_deadline(),
    )
    assert len(launch.proposed_method.resources.prices.entries) == 16
    launch = replace(launch, proposed_method=replace(launch.proposed_method, resources=synthetic_resources()))
    evidence = tmp_path / "generated-proposed-research-evidence.json"

    payload = {"rec_texts": []}
    if mode != "fallback":
        payload = _payload("PANTRYPROOF TEST MART", split=True)
        item = payload["rec_texts"].index("MILK")
        payload["rec_texts"][item] = "MLK"
        payload["rec_scores"] = [0.91] * len(payload["rec_texts"])
        payload["rec_scores"][item] = 0.20
    provider = Mock(side_effect=_provider(payload))
    gate = Mock(wraps=bootstrap.t10.evaluate_live_source_gate_v0)
    extract = Mock(wraps=bootstrap.t10.extract_b2)
    legacy = Mock(side_effect=AssertionError("legacy path used"))
    date_graph = Mock(wraps=receipt_correction_v1.correct_purchase_date_v0)
    run = Mock(wraps=receipt_research_v1.run_proposed_receipt_v1)
    if mode == "method-failure":
        run.side_effect = ValueError("private failure detail")
    monkeypatch.setattr(bootstrap, "_check_runtime", Mock())
    monkeypatch.setattr(bootstrap, "NativeLocalImageProviderV0", lambda _: provider)
    monkeypatch.setattr(bootstrap.t10, "evaluate_live_source_gate_v0", gate)
    monkeypatch.setattr(bootstrap.t10, "extract_b2", extract)
    monkeypatch.setattr(receipt_research_v1, "run_proposed_receipt_v1", run)
    monkeypatch.setattr(purchase_date_correction_v0, "correct_purchase_date_v0", legacy)
    monkeypatch.setattr(receipt_correction_v1, "correct_purchase_date_v0", date_graph)

    def serve(service, *, port):
        request = bootstrap.http.ReceiptRequest("req-proposed", "img-proposed", "image/png", encoded)
        context = bootstrap.http.ProcessingContext(monotonic() + 100)
        response = bootstrap.http._processor_response(service._processor, request, context)
        assert response.status == 200
        assert not evidence.exists()
        presentation = json.loads(response.body)
        if mode in ("policy", "not-ready"):
            assert presentation["outcome"]["status"] == "RESULT_AVAILABLE"
            producer = "PROPOSED_RECEIPT_V1" if mode == "policy" else "PROPOSED_UNVERIFIED_REVIEW_V1"
            assert presentation["automaticExtraction"]["producer"]["producerId"] == producer
            fields = presentation["receipt"]["itemRows"][0]["fields"]
            assert len(fields) + len(presentation["receipt"]["receiptFields"]) == 7
            expected = "MILK" if mode == "policy" else "MLK"
            assert fields[0]["originalAutomaticValue"] == fields[0]["presentationValue"] == expected
            assert fields[0]["sourceTokenIds"]
            assert fields[0]["nativeConfidence"] is None
        elif mode == "fallback":
            assert presentation["outcome"]["status"] == "SOURCE_EVIDENCE_INSUFFICIENT"
        else:
            assert presentation["outcome"]["failure"]["code"] == "PRESENTATION_PROJECTION_FAILURE"
            assert presentation["receipt"] is None

    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    bootstrap._serve_approved(launch, _TOKEN, evidence_path=evidence)
    provider.assert_called_once()
    gate.assert_called_once()
    extract.assert_called_once()
    legacy.assert_not_called()
    if mode == "fallback":
        run.assert_not_called()
    else:
        run.assert_called_once()
    if mode in ("policy", "not-ready"):
        assert date_graph.call_args.kwargs == {"include_diagnostic_scores": False}
    body = evidence.read_text(encoding="utf-8")
    assert _TOKEN.decode("ascii") not in body and "private failure detail" not in body
    generated = json.loads(body)
    record = generated["proposed_receipt"]
    assert generated["evidence_version"] == "generated-proposed-receipt-research-v1"
    assert record["application_confirmation_required"]
    assert bool(record["source"]["tokens"]) is (mode != "fallback")
    if mode in ("policy", "not-ready"):
        item = next(row for row in record["correction_fields"] if row["original"]["field_name"] == "ITEM_DESCRIPTION")
        assert item["candidates"][0]["value"] == "MLK"
        assert item["candidates"][1]["value"] == "MILK" and item["candidates"][1]["provenance"]
        assert any(len(candidate["missing_mask"]) == 7 for candidate in record["candidate_scoring_inputs"])
        assert record["original_b2"]["items"][0]["description"]["value"] == "MLK"
        if mode == "policy":
            assert record["method_state"] == "POLICY_APPLIED"
            assert record["scorer_sha256"] == manifest["receipt_method"]["verification"]["scorer_sha256"]
            assert record["policy_disposition"]["state"] == "REVIEW_REQUIRED"
            assert record["final_pre_review_automatic"]["items"][0]["description"]["value"] == "MILK"
        else:
            assert record["method_state"] == "NOT_READY"
            assert record["scorer_sha256"] is record["policy_disposition"] is record["final_pre_review_automatic"] is None
            assert record["verification_audits"] == []
    elif mode == "fallback":
        assert record["method_state"] == "FALLBACK_NO_UPDATE"
    else:
        assert record["proposed_failure"] == "PROPOSED_METHOD_FAILURE"
        assert record["original_b2"] and record["final_pre_review_automatic"] is None


@pytest.mark.parametrize("defect", ("snapshot", "scorer", "calibration", "field-settings"))
def test_proposed_preflight_refuses_invalid_artifacts(approved_export, defect):
    manifest, _ = approved_export
    _select_proposed(manifest, verified=True)
    method = manifest["receipt_method"]
    if defect == "snapshot":
        method["resource_snapshot"]["sha256"] = "0" * 64
    elif defect == "scorer":
        method["verification"]["scorer"]["weights"][0] = 1.0
    elif defect == "calibration":
        method["verification"]["calibration"]["scale"] = 0.0
    else:
        del method["verification"]["field_settings"]["QUANTITY"]
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal):
        bootstrap._prepare_launch(manifest, bootstrap._preflight_deadline())
