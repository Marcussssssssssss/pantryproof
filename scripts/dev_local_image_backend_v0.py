"""One approved generated receipt through the existing loopback backend.

Supply the manifest SHA-256 from the separate execution authorization.
The digest identifies reviewed data. Creating a manifest or hashing it does
not grant authority. No manifest, token, runtime or listener is enabled by
importing this module.

The measure manifest contains scope, original and transmitted. The two file
records use FilePin fields (path, length, sha256). The approved transmitted
pin must come from Android's actual pre-upload bytes, with recorded custody
linking it to the approved generated original.

The serve manifest contains scope, original, transmitted, raster,
gate_policy_sha256 and profile. Raster is {bgr8_sha256, width, height}.
The separately approved seven-field serve manifest adds receipt_method.
Profile uses NativeLocalImageRuntimeProfileV0 field names, its LaunchSpec
field names, and FilePin records. Represent tuples as JSON arrays and launch
environment entries as pairs. Keep the bearer token out of both manifests.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from threading import Event, Lock
from time import monotonic, monotonic_ns
from typing import TYPE_CHECKING

from pipeline import backend_local_image_receipt_v0 as t10
from pipeline import gate_c_live_source_gate_v0 as gate
from pipeline import native_local_image_executor_v0 as t13
from pipeline import real_receipt_http_service_v1 as http
from pipeline.native_local_image_dev_controls_v0 import (
    DEVELOPMENT_SCOPE, DevelopmentLocalImageHostControlsV0, DevelopmentLocalImageRuntimeApprovalV0,
    PROTOTYPE_SCOPE, PrototypeLocalImageHostControlsV1, PrototypeSessionV1,
)
from pipeline.native_local_image_provider_v0 import (
    NativeLocalImageBindingV0, NativeLocalImageProviderV0, _prepare_frame,
)
from pipeline.presentation_v1.conformance import (
    ConformanceViolation, decode_and_validate_presentation_v1,
)
from pipeline.presentation_v1.local_image_projection_v0 import (
    LOCAL_IMAGE_SOURCE_SYSTEM, LiveGateApprovalV0, LocalImagePresentationContextV0,
)
from scripts.gate_c_native_worker_host_v0 import LaunchSpec, _same_path, _verify_file
from scripts.gate_c_ocr_b2_probe_v0 import FilePin, _absolute, _file_pin

if TYPE_CHECKING:
    from pipeline.operational_receipt_method_v1 import OperationalReceiptMethodV1


RATIFIED_POLICY_SHA256 = "bc478fd4544e96e64dfe4ac3fa960c5aa68f2dec490c29fea75594472293cdba"
_PORT = 8765
_MANIFEST_LIMIT = 65536
_RESEARCH_EVIDENCE_LIMIT = 2 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(rb"[0-9a-f]{64}")
_STARTUP = Lock()
_IDENTITY_FIELDS = {"scope", "original", "transmitted"}
_SERVE_FIELDS = _IDENTITY_FIELDS | {"raster", "gate_policy_sha256", "profile"}


class DevelopmentBootstrapRefusal(RuntimeError):
    """A fixed startup or shutdown diagnostic."""


def _digest(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _record(value, expected: set[str]) -> dict:
    if type(value) is not dict or value.keys() != expected:
        raise DevelopmentBootstrapRefusal("Development manifest fields refused.")
    return value


def _read_manifest(path: str, approved_sha256: str, *, scope: str = DEVELOPMENT_SCOPE) -> dict:
    if not _absolute(path) or not _digest(approved_sha256):
        raise DevelopmentBootstrapRefusal("An approved local manifest and its reviewed digest are required.")
    with Path(path).open("rb") as stream:
        raw = stream.read(_MANIFEST_LIMIT + 1)
    if not 0 < len(raw) <= _MANIFEST_LIMIT or sha256(raw).hexdigest() != approved_sha256:
        raise DevelopmentBootstrapRefusal("Development manifest identity refused.")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=t13._unique_pairs,
            parse_constant=t13._invalid_constant,
        )
    except (ValueError, RecursionError, t13.HostError):
        raise DevelopmentBootstrapRefusal("Development manifest syntax refused.") from None
    if type(value) is not dict or value.get("scope") != scope:
        raise DevelopmentBootstrapRefusal(
            "Generated-receipt development scope required." if scope == DEVELOPMENT_SCOPE
            else "Ordinary grocery prototype scope required."
        )
    return value


def _parse_pin(value) -> FilePin:
    pin = FilePin(**_record(value, {"path", "length", "sha256"}))
    if not _file_pin(pin):
        raise DevelopmentBootstrapRefusal("Development file pin refused.")
    return pin


def _parse_profile(value) -> t13.NativeLocalImageRuntimeProfileV0:
    profile_type = t13.NativeLocalImageRuntimeProfileV0
    parts = dict(_record(value, {field.name for field in fields(profile_type)}))
    launch = dict(_record(parts["launch"], {field.name for field in fields(LaunchSpec)}))
    if (
        type(launch["import_paths"]) is not list or type(launch["environment"]) is not list
        or any(type(pair) is not list or len(pair) != 2 for pair in launch["environment"])
    ):
        raise DevelopmentBootstrapRefusal("Development launch fields refused.")
    launch["import_paths"] = tuple(launch["import_paths"])
    launch["environment"] = tuple(tuple(pair) for pair in launch["environment"])
    parts["launch"] = LaunchSpec(**launch)
    for name in ("launcher", "worker", "configuration", "controls_manifest"):
        parts[name] = _parse_pin(parts[name])
    for name in ("runtime", "detector", "recognizer"):
        if type(parts[name]) is not list or not 1 <= len(parts[name]) <= 64:
            raise DevelopmentBootstrapRefusal("Development runtime pin list refused.")
        parts[name] = tuple(_parse_pin(pin) for pin in parts[name])
    return profile_type(**parts)


def _preflight_deadline() -> int:
    return monotonic_ns() + int(http.Deadlines().processing * 1_000_000_000)


def _measure_generated_export(
    original: FilePin, transmitted: FilePin, deadline: int,
) -> NativeLocalImageBindingV0:
    if transmitted.length > http.MAX_IMAGE_BYTES:
        raise DevelopmentBootstrapRefusal("Generated Android PNG exceeds T09 admission limits.")
    _verify_file(original, deadline)
    _verify_file(transmitted, deadline)
    with Path(transmitted.path).open("rb") as stream:
        encoded = stream.read(transmitted.length + 1)
    if len(encoded) != transmitted.length or sha256(encoded).hexdigest() != transmitted.sha256:
        raise DevelopmentBootstrapRefusal("Generated Android PNG identity refused.")
    presentation = LocalImagePresentationContextV0(
        "req-t15-preflight", "img-t15-preflight", "rct-t15-preflight", "t15-preflight",
    )
    request = t10.LocalImageOcrRequestV0(
        presentation, http.CONTENT_TYPE, encoded, transmitted.sha256, "gat-t15-preflight",
    )
    context = t10.LocalImageProcessingContextV0(deadline / 1_000_000_000, Event())
    frame, _, _ = _prepare_frame(request, context)
    return frame.binding


def _policy(expected_digest: object) -> LiveGateApprovalV0:
    policy = gate.PROPOSED_LIVE_GATE_V0
    if (
        expected_digest != RATIFIED_POLICY_SHA256 or type(policy) is not LiveGateApprovalV0
        or policy.policy_id != "GATE_C_LIVE_SOURCE_GATE_V0" or policy.revision != "T10-P01"
        or policy.policy_sha256 != RATIFIED_POLICY_SHA256
        or sha256(gate.LIVE_POLICY_CANONICAL_BYTES).hexdigest() != RATIFIED_POLICY_SHA256
        or policy.public_reasons != (gate.PUBLIC_INSUFFICIENCY_REASON,)
    ):
        raise DevelopmentBootstrapRefusal("Ratified T10-P01 policy identity refused.")
    return policy


@dataclass(frozen=True, slots=True, repr=False)
class _ApprovedLaunch:
    approval: DevelopmentLocalImageRuntimeApprovalV0
    policy: LiveGateApprovalV0
    proposed_method: OperationalReceiptMethodV1 | None = None


def _load_proposed_method(value) -> OperationalReceiptMethodV1:
    from pipeline.operational_receipt_method_v1 import (
        METHOD_ID, OperationalReceiptMethodV1, decode_frozen_receipt_verification,
    )
    from pipeline.proposed.receipt_correction_v1 import ReceiptMethodConfig
    from pipeline.proposed.receipt_resources_v1 import PriceDiscrepancyRule, decode_receipt_resources

    try:
        raw = _record(value, {"method_id", "region", "resource_snapshot", "price_rule",
                              "correction_config", "verification"})
        if raw["method_id"] != METHOD_ID:
            raise ValueError("Unknown receipt method id.")
        pin = _parse_pin(raw["resource_snapshot"])
        with Path(pin.path).open("rb") as stream:
            payload = stream.read(pin.length + 1)
        if len(payload) != pin.length or sha256(payload).hexdigest() != pin.sha256:
            raise ValueError("Resource snapshot pin refused.")
        rule = None
        if raw["price_rule"] is not None:
            rule_raw = _record(raw["price_rule"], {"rule_id", "relative_tolerance"})
            if type(rule_raw["relative_tolerance"]) is not str:
                raise ValueError("Price tolerance requires an exact decimal string.")
            rule = PriceDiscrepancyRule(rule_raw["rule_id"], Decimal(rule_raw["relative_tolerance"]))
        config = _record(raw["correction_config"], {"candidate_limit", "proposal_limit", "confidence_floor"})
        if type(config["confidence_floor"]) is not str:
            raise ValueError("The correction confidence floor requires an exact decimal string.")
        correction_config = ReceiptMethodConfig(
            **{**config, "confidence_floor": Decimal(config["confidence_floor"])},
        )
        verification = (None if raw["verification"] is None
                        else decode_frozen_receipt_verification(raw["verification"]))
        config_digest = sha256(json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return OperationalReceiptMethodV1(
            config_digest, decode_receipt_resources(payload, discrepancy_rule=rule),
            raw["region"], correction_config, verification,
        )
    except (ArithmeticError, AttributeError, OSError, TypeError, ValueError, KeyError):
        raise DevelopmentBootstrapRefusal("Approved proposed receipt method configuration refused.") from None


def _prepare_launch(manifest: dict, deadline: int) -> _ApprovedLaunch:
    has_proposed = "receipt_method" in manifest
    _record(manifest, _SERVE_FIELDS | {"receipt_method"} if has_proposed else _SERVE_FIELDS)
    if manifest["scope"] != DEVELOPMENT_SCOPE:
        raise DevelopmentBootstrapRefusal("Generated-receipt development scope required.")
    policy = _policy(manifest["gate_policy_sha256"])
    profile = _parse_profile(manifest["profile"])
    proposed_method = _load_proposed_method(manifest["receipt_method"]) if has_proposed else None
    raster = _record(manifest["raster"], {"bgr8_sha256", "width", "height"})
    if (
        not _digest(raster["bgr8_sha256"])
        or any(type(raster[axis]) is not int for axis in ("width", "height"))
    ):
        raise DevelopmentBootstrapRefusal("Approved BGR8 identity refused.")
    observed = _measure_generated_export(
        _parse_pin(manifest["original"]), _parse_pin(manifest["transmitted"]), deadline,
    )
    if (
        observed.bgr8_sha256 != raster["bgr8_sha256"]
        or (observed.width, observed.height) != (raster["width"], raster["height"])
    ):
        raise DevelopmentBootstrapRefusal("Approved BGR8 identity differs from the Android export.")
    approval = DevelopmentLocalImageRuntimeApprovalV0(
        profile, observed.encoded_sha256, observed.bgr8_sha256,
        observed.width, observed.height, manifest["scope"],
    )
    return _ApprovedLaunch(approval, policy, proposed_method)


def _scratch_absent(profile: t13.NativeLocalImageRuntimeProfileV0) -> bool:
    try:
        Path(profile.launch.working_directory).lstat()
    except FileNotFoundError:
        return True
    return False


def _check_runtime(
    profile: t13.NativeLocalImageRuntimeProfileV0,
    controls: DevelopmentLocalImageHostControlsV0 | None,
    deadline: int,
) -> None:
    pins = t13._profile_pins(profile)
    if (
        sys.platform != "win32" or sys.implementation.name != "cpython"
        or sys.version_info[:3] != (3, 13, 7)
        or not _same_path(sys.executable, profile.launcher.path)
        or not _scratch_absent(profile)
        or any(name.upper() == http.TOKEN_ENV for name, _ in profile.launch.environment)
        or profile.minimum_work_ns + profile.teardown_reserve_ns
        >= int(http.Deadlines().processing * 1_000_000_000)
    ):
        raise DevelopmentBootstrapRefusal("Development interpreter, scratch, environment or budget refused.")
    for pin in pins:
        _verify_file(pin, deadline)
    if controls is not None and controls.approve(profile, deadline) is not True:
        raise DevelopmentBootstrapRefusal("T14 development controls did not admit the runtime profile.")


_PROTOTYPE_SOURCES = (
    "scripts/dev_local_image_backend_v0.py",
    "pipeline/real_receipt_http_service_v1.py",
    "pipeline/backend_local_image_receipt_v0.py",
    "pipeline/gate_c_live_source_gate_v0.py",
    "pipeline/native_local_image_dev_controls_v0.py",
    "pipeline/native_local_image_executor_v0.py",
    "pipeline/native_local_image_provider_v0.py",
    "pipeline/operational_receipt_method_v1.py",
    "pipeline/presentation_v1/conformance.py",
    "pipeline/presentation_v1/local_image_projection_v0.py",
    "pipeline/presentation_v1/review_conformance.py",
    "pipeline/presentation_v1/review_projection.py",
    "pipeline/proposed/receipt_research_v1.py",
    "pipeline/proposed/receipt_correction_v1.py",
    "pipeline/proposed/receipt_resources_v1.py",
    "pipeline/layout_b2.py",
    "pipeline/ocr_adapter.py",
    "pipeline/contracts.py",
    "evaluation/research_policy_v0.py",
)


@dataclass(frozen=True, slots=True, repr=False)
class _ApprovedPrototype:
    profile: t13.NativeLocalImageRuntimeProfileV0
    method: OperationalReceiptMethodV1
    source_pins: tuple[FilePin, ...]


def _prepare_prototype_launch(manifest: dict) -> _ApprovedPrototype:
    _record(manifest, {"scope", "source_pins", "gate_policy_sha256", "profile", "receipt_method"})
    if (manifest["scope"] != PROTOTYPE_SCOPE
            or manifest["gate_policy_sha256"] != gate.GROCERY_LIVE_GATE_V1.policy_sha256):
        raise DevelopmentBootstrapRefusal("Ordinary grocery gate approval refused.")
    records = manifest["source_pins"]
    if type(records) is not list or not records:
        raise DevelopmentBootstrapRefusal("Reviewed prototype source pins required.")
    pins = tuple(map(_parse_pin, records))
    root = Path(__file__).absolute().parents[1]
    paths = {os.path.normcase(os.path.abspath(pin.path)) for pin in pins}
    required = {os.path.normcase(os.path.abspath(root / name)) for name in _PROTOTYPE_SOURCES}
    if len(paths) != len(pins) or not required.issubset(paths):
        raise DevelopmentBootstrapRefusal("Required prototype source pins are missing or duplicated.")
    return _ApprovedPrototype(_parse_profile(manifest["profile"]), _load_proposed_method(manifest["receipt_method"]), pins)


def _serve_prototype(launch: _ApprovedPrototype, token: bytes) -> None:
    if type(launch) is not _ApprovedPrototype or type(token) is not bytes or not _TOKEN.fullmatch(token):
        raise DevelopmentBootstrapRefusal("Prototype requires a reviewed manifest and a fresh session token.")
    if not _STARTUP.acquire(blocking=False):
        raise DevelopmentBootstrapRefusal("A local receipt session is already active.")
    try:
        if any(value is not None for value in (
            t13._AUTHORIZED_RUNTIME, t13._DEVELOPMENT_RUNTIME, t13._PROTOTYPE_RUNTIME, t13._QUARANTINED,
            t10._APPROVED_RUNTIME, t10._APPROVED_PROTOTYPE_RUNTIME,
            gate._APPROVED_POLICY_SHA256, gate._APPROVED_GROCERY_POLICY_SHA256,
        )):
            raise DevelopmentBootstrapRefusal("Start with unset approvals and confirmed prior cleanup.")
        profile = launch.profile
        preflight = _preflight_deadline()
        for pin in launch.source_pins:
            _verify_file(pin, preflight)
        _check_runtime(profile, None, preflight)
        session = PrototypeSessionV1(profile)
        controls = PrototypeLocalImageHostControlsV1(session)
        if (not session.permits(monotonic() + http.Deadlines().overall)
                or not controls.approve(profile, preflight)):
            raise DevelopmentBootstrapRefusal("Prototype host controls or remaining session budget refused.")
        executor = t13.SupervisedNativeLocalImageExecutorV0(profile, controls, prototype=True)
        provider = NativeLocalImageProviderV0(executor)
        session.observe_runtime(lambda: t13._QUARANTINED is not None,
                                lambda: provider.quarantined, lambda: controls.violation_seen(profile))
        runtime = t10.LocalImageRuntimeApprovalV0(provider, LOCAL_IMAGE_SOURCE_SYSTEM)
        coordinator = t10.LocalImageReceiptProcessorV0(
            gate_policy=gate.GROCERY_LIVE_GATE_V1, runtime=runtime, proposed_method=launch.method,
        )
        service = http.ReceiptHttpService(
            token, processor=t10.as_t09_receipt_processor_v0(coordinator), review_enabled=True, session=session,
        )
        try:
            t13._PROTOTYPE_RUNTIME = (profile, controls)
            t10._APPROVED_PROTOTYPE_RUNTIME = runtime
            gate._APPROVED_GROCERY_POLICY_SHA256 = gate.GROCERY_LIVE_GATE_V1.policy_sha256
            gate.require_approved_live_policy_v0(gate.GROCERY_LIVE_GATE_V1)
            http.serve_development(service, port=_PORT)
        finally:
            session.revoke()
            service.stop()
            try:
                cleaned = (service.drain(http.Deadlines().overall) and t13._QUARANTINED is None
                           and not provider.quarantined and _scratch_absent(profile))
            finally:
                t13._PROTOTYPE_RUNTIME = None
                t10._APPROVED_PROTOTYPE_RUNTIME = None
                gate._APPROVED_GROCERY_POLICY_SHA256 = None
            if not cleaned:
                raise DevelopmentBootstrapRefusal("Prototype shutdown cleanup remains unconfirmed.")
    finally:
        _STARTUP.release()


def _evidence_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)
                if not field.name.startswith("_")}
    raise TypeError("Unsupported generated evidence value.")


def _receipt_evidence(output):
    if output is None:
        return None
    return {field.name: getattr(output, field.name) for field in fields(output)
            if field.name != "source_evidence"}


def _correction_evidence(result):
    if result is None:
        return None
    baseline = result.baseline.receipt_output
    discovery, suspicion, features = result.discovery, result.suspicion, result.features
    recommendation = result.recommendation
    return {
        "original_b2": _receipt_evidence(baseline),
        "c0": None if baseline is None else baseline.purchase_date,
        "c0_candidate": None if discovery is None else discovery.existing_c0,
        "suspicion_reasons": None if suspicion is None else suspicion.reasons,
        "discovery": None if discovery is None else {
            "status": discovery.status, "observations": discovery.observations,
            "derivations": discovery.derivations, "proposals": discovery.proposals,
            "diagnostics": discovery.diagnostics,
        },
        "candidate_alternatives": [] if features is None else [
            constraint.candidate for constraint in features.constraint_results
            if constraint.candidate.candidate_id != constraint.c0_candidate.candidate_id
        ],
        "features": [] if features is None else [
            {"candidate_id": vector.candidate.candidate_id, "slots": vector.slot_values}
            for vector in features.candidate_features
        ],
        "hard_constraints": [] if features is None else [
            {"candidate_id": constraint.candidate.candidate_id, "state": constraint.aggregate_state,
             "reason": constraint.aggregate_reason, "rules": constraint.rule_outcomes}
            for constraint in features.constraint_results
        ],
        "diagnostic_scores": [
            {"candidate_id": score.feature_vector.candidate.candidate_id, "raw_score": score.raw_score,
             "artifact_sha256": score.artifact_sha256}
            for score in result.scores
        ],
        "decision": result.outcome,
        "reason": result.reason,
        "recommendation": None if recommendation is None else recommendation.status,
        "preferred_candidate_id": (
            None if recommendation is None or recommendation.preferred is None
            else recommendation.preferred.candidate_id
        ),
        "final_output": _receipt_evidence(result.final_output),
    }


def _proposed_evidence(method, attempt):
    result = None if attempt is None else attempt.proposed
    b2 = None if attempt is None else attempt.b2_result
    original = None if b2 is None else b2.receipt_output
    selected = None if result is None else result.receipt_output
    verification = method.verification
    correction = None if result is None else result.correction
    source = None if attempt is None else attempt.source_evidence or attempt.adapted_source
    fallback = None if b2 is None else b2.pre_resolution_disposition
    failure = None if attempt is None else attempt.failure
    review_draft = original if result is not None and result.state.value == "NOT_READY" else None
    return {
        "configuration_sha256": method.configuration_sha256,
        "correction_configuration": method.correction_config,
        "region": method.region,
        "scorer_sha256": None if verification is None else verification.scorer.sha256,
        "calibration_sha256": None if verification is None else verification.calibration.sha256,
        "method_state": (result.state.value if result is not None else
                         "FALLBACK_NO_UPDATE" if fallback is not None else "NOT_COMPLETED"),
        "source": source,
        "original_b2": _receipt_evidence(original),
        "fallback": fallback,
        "correction_fields": () if correction is None else correction.fields,
        "candidate_scoring_inputs": () if correction is None else correction.scoring_inputs(),
        "resource_references": () if correction is None else correction.resource_references,
        "verification_audits": () if result is None else result.audits,
        "policy_disposition": None if result is None or result.output is None else result.output.disposition,
        "final_pre_review_automatic": _receipt_evidence(selected),
        "unverified_v1_review_draft": _receipt_evidence(review_draft),
        "pantry_semantic_candidates": _pantry_semantic_evidence(method.resources, selected or review_draft),
        "application_confirmation_required": True,
        "failure": None if failure is None else failure.name,
        "proposed_failure": None if attempt is None else attempt.proposed_failure,
        "refusal_code": None if attempt is None else attempt.refusal_code,
    }


def _pantry_semantic_evidence(resources, output):
    terminology = resources.terminology
    if output is None or terminology is None:
        return ()
    retailer = terminology.retailer_id(output.store_name.value)
    return tuple({
        "row_id": row.row_id,
        "description_field_id": row.description.field_id,
        "terminology_reference": terminology.reference,
        "matches": terminology.pantry_matches(row.description.value, retailer),
    } for row in output.items if row.description.value is not None)


class _GeneratedResearchEvidence:
    """Single admitted generated receipt. Serialize only after the service drains."""

    def __init__(self, path: Path, proposed_method: OperationalReceiptMethodV1 | None = None) -> None:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise DevelopmentBootstrapRefusal("Generated research evidence path already exists.")
        self.path = path
        self.ids = None
        self.encoded_sha256 = None
        self.recognition = None
        self.provider_elapsed_ns = None
        self.correction = None
        self.response = None
        self.proposed_method = proposed_method
        self.attempt = None

    def recognize(self, provider, request, context):
        started = monotonic_ns()
        try:
            result = provider(request, context)
            self.recognition = result.payload
            return result
        finally:
            self.provider_elapsed_ns = monotonic_ns() - started

    def observe_correction(self, result) -> None:
        self.correction = result

    def observe_attempt(self, attempt) -> None:
        self.attempt = attempt

    def write(self, *, cleanup_confirmed: bool) -> None:
        if self.ids is None:
            return
        response = self.response
        presentation = None
        if type(response) is bytes and 0 < len(response) <= http.MAX_RESPONSE_BYTES:
            try:
                decode_and_validate_presentation_v1(
                    response, expected_request_id=self.ids[0], expected_image_id=self.ids[1],
                    consumer_mode="LIVE",
                )
            except (ConformanceViolation, RecursionError):
                pass
            else:
                envelope = json.loads(response)
                presentation = {key: envelope[key] for key in (
                    "outcome", "sourceEvidence", "sourceGate", "automaticExtraction", "receipt",
                )}
        record = {
            "evidence_version": "t15-generated-research-v0",
            "scope": DEVELOPMENT_SCOPE,
            "request_id": self.ids[0],
            "image_id": self.ids[1],
            "encoded_sha256": self.encoded_sha256,
            "ocr_state": ("COMPLETED" if self.recognition is not None else
                          "NOT_COMPLETED" if self.provider_elapsed_ns is not None else "NOT_ATTEMPTED"),
            "provider_elapsed_ns": self.provider_elapsed_ns,
            "recognition": self.recognition,
            "validated_processor_presentation": presentation,
            "processor_refusal": response.name if type(response) is http.ProcessingRefusal else None,
            "purchase_date_correction": _correction_evidence(self.correction),
            "score_scope": "Diagnostic raw margins. Source agreement and eligibility govern correction.",
            "cleanup_confirmed": cleanup_confirmed,
        }
        if self.proposed_method is not None:
            del record["purchase_date_correction"]
            record["evidence_version"] = "generated-proposed-receipt-research-v1"
            record["score_scope"] = "Operational receipt processing with explicit application confirmation."
            record["proposed_receipt"] = _proposed_evidence(self.proposed_method, self.attempt)
        encoder = json.JSONEncoder(default=_evidence_value, ensure_ascii=False, allow_nan=False)
        bounded = bytearray()
        for chunk in encoder.iterencode(record):
            raw = chunk.encode("utf-8")
            if len(bounded) + len(raw) >= _RESEARCH_EVIDENCE_LIMIT:
                raise DevelopmentBootstrapRefusal("Generated research evidence exceeded the byte limit.")
            bounded.extend(raw)
        with self.path.open("xb") as stream:
            stream.write(bounded + b"\n")


class _OneGeneratedReceipt:
    """Restrict T09 dispatch to the approved PNG and one processing attempt."""

    def __init__(
        self, encoded_sha256: str, processor: http.ReceiptProcessor,
        evidence: _GeneratedResearchEvidence | None = None,
    ) -> None:
        self._encoded_sha256 = encoded_sha256
        self._processor = processor
        self._evidence = evidence
        self._lock = Lock()
        self._idle = Event()
        self._idle.set()
        self._closed = self._used = False

    def __call__(self, request: http.ReceiptRequest, context: http.ProcessingContext, /):
        encoded = request.encoded_image
        if (
            request.content_type != http.CONTENT_TYPE or type(encoded) is not bytes
            or not 0 < len(encoded) <= http.MAX_IMAGE_BYTES
            or sha256(encoded).hexdigest() != self._encoded_sha256
        ):
            return http.ProcessingRefusal.UNAVAILABLE
        with self._lock:
            if self._closed or self._used:
                return http.ProcessingRefusal.UNAVAILABLE
            self._used = True
            self._idle.clear()
        try:
            if self._evidence is not None:
                self._evidence.ids = (request.request_id, request.image_id)
                self._evidence.encoded_sha256 = self._encoded_sha256
            response = self._processor(request, context)
            if self._evidence is not None:
                if type(response) is http.ProcessingRefusal or (
                    type(response) is bytes and len(response) <= http.MAX_RESPONSE_BYTES
                ):
                    self._evidence.response = response
            return response
        finally:
            self._idle.set()

    def close(self) -> bool:
        with self._lock:
            self._closed = True
        return self._idle.wait(http.Deadlines().overall)


def _serve_approved(
    launch: _ApprovedLaunch, token: bytes, *, evidence_path: Path | None = None,
) -> None:
    """Activate only the checked manifest in a dedicated, approved process."""
    if (
        type(launch) is not _ApprovedLaunch
        or type(launch.approval) is not DevelopmentLocalImageRuntimeApprovalV0
        or launch.approval.scope != DEVELOPMENT_SCOPE
        or launch.policy is not _policy(RATIFIED_POLICY_SHA256)
    ):
        raise DevelopmentBootstrapRefusal("Development launch approval required.")
    if type(token) is not bytes or not _TOKEN.fullmatch(token):
        raise DevelopmentBootstrapRefusal("A one-run 256-bit hexadecimal bearer token is required.")
    if not _STARTUP.acquire(blocking=False):
        raise DevelopmentBootstrapRefusal("Development bootstrap is already active.")
    try:
        if any(value is not None for value in (
            t13._AUTHORIZED_RUNTIME, t13._DEVELOPMENT_RUNTIME, t13._QUARANTINED,
            t10._APPROVED_RUNTIME, gate._APPROVED_POLICY_SHA256,
            t13._PROTOTYPE_RUNTIME, t10._APPROVED_PROTOTYPE_RUNTIME, gate._APPROVED_GROCERY_POLICY_SHA256,
        )):
            raise DevelopmentBootstrapRefusal("Start with unset approvals and no native quarantine.")
        profile = launch.approval.profile
        controls = DevelopmentLocalImageHostControlsV0(launch.approval)
        _check_runtime(profile, controls, _preflight_deadline())
        executor = t13.SupervisedNativeLocalImageExecutorV0(profile, controls, development=True)
        provider = NativeLocalImageProviderV0(executor)
        proposed_method = launch.proposed_method
        evidence = (_GeneratedResearchEvidence(evidence_path, proposed_method)
                    if evidence_path is not None else None)

        def recognize(request, context):
            return evidence.recognize(provider, request, context)

        runtime = t10.LocalImageRuntimeApprovalV0(
            provider if evidence is None else recognize, LOCAL_IMAGE_SOURCE_SYSTEM,
        )
        coordinator = t10.LocalImageReceiptProcessorV0(
            gate_policy=launch.policy, runtime=runtime, enable_purchase_date_correction=proposed_method is None,
            correction_observer=None if evidence is None or proposed_method is not None else evidence.observe_correction,
            proposed_method=proposed_method,
            attempt_observer=evidence.observe_attempt if evidence is not None and proposed_method is not None else None,
        )
        guarded = _OneGeneratedReceipt(
            launch.approval.encoded_sha256, t10.as_t09_receipt_processor_v0(coordinator), evidence,
        )
        service = http.ReceiptHttpService(token, processor=guarded)
        try:
            t13._DEVELOPMENT_RUNTIME = (profile, controls)
            t10._APPROVED_RUNTIME = runtime
            gate._APPROVED_POLICY_SHA256 = RATIFIED_POLICY_SHA256
            gate.require_approved_live_policy_v0(launch.policy)
            http.serve_development(service, port=_PORT)
        finally:
            try:
                service.stop()
                drained = guarded.close()
                clean = drained and t13._QUARANTINED is None and _scratch_absent(profile)
            finally:
                gate._APPROVED_POLICY_SHA256 = None
                t10._APPROVED_RUNTIME = None
                t13._DEVELOPMENT_RUNTIME = None
            if drained and evidence is not None:
                evidence.write(cleanup_confirmed=clean)
            if not clean:
                raise DevelopmentBootstrapRefusal("Native shutdown or scratch cleanup remains unconfirmed.")
    finally:
        _STARTUP.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approved loopback LOCAL_IMAGE backend.")
    parser.add_argument("mode", choices=("measure", "serve", "serve-prototype"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--approval-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "serve-prototype":
            manifest = _read_manifest(args.manifest, args.approval_sha256, scope=PROTOTYPE_SCOPE)
            token = os.environ.pop(http.TOKEN_ENV, "").encode("ascii")
            _serve_prototype(_prepare_prototype_launch(manifest), token)
            return 0
        manifest = _read_manifest(args.manifest, args.approval_sha256)
        deadline = _preflight_deadline()
        if args.mode == "measure":
            _record(manifest, _IDENTITY_FIELDS)
            binding = _measure_generated_export(
                _parse_pin(manifest["original"]), _parse_pin(manifest["transmitted"]), deadline,
            )
            print(json.dumps({
                "encoded_sha256": binding.encoded_sha256, "bgr8_sha256": binding.bgr8_sha256,
                "width": binding.width, "height": binding.height,
            }, sort_keys=True))
        else:
            launch = _prepare_launch(manifest, deadline)
            token = os.environ.pop(http.TOKEN_ENV, "").encode("ascii")
            evidence_name = ("generated-proposed-research-evidence.json" if "receipt_method" in manifest
                             else "generated-research-evidence.json")
            evidence_path = Path(args.manifest).with_name(evidence_name)
            _serve_approved(launch, token, evidence_path=evidence_path)
    except DevelopmentBootstrapRefusal as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("Development preflight or listener failed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
