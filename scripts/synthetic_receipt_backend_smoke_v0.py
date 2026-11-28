"""Fixed generated-image, offline OCR -> accepted S02 -> V1 smoke execution.

Run with the pinned interpreter: ``python -B -m
scripts.synthetic_receipt_backend_smoke_v0 [--insufficient]``. No image, model,
output or network argument is accepted. Unit tests mock the engine separately;
the CLI loads the installed PaddleOCR engine. Only a safe summary is returned.
This single-process developer runner is synthetic-only, not a service or gate
policy. Observed model hashes are reproducibility evidence, not authentication.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
import io
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
import tempfile
import unicodedata
from types import FunctionType, ModuleType

from pipeline import backend_synthetic_coordinator_v0 as coordinator
from pipeline.contracts import SourceEvidenceDecision, SourceEvidenceGateResult, SourceProcessingStatus
from pipeline.ocr_adapter import adapt_paddleocr_result
from pipeline.presentation_v1.conformance import decode_and_validate_presentation_v1
from pipeline.presentation_v1.synthetic_failure_projection_v0 import SyntheticFailureContextV0


_VERSIONS = {"paddlepaddle": "3.3.1", "paddleocr": "3.7.0", "paddlex": "3.7.2", "Pillow": "12.3.0"}
_MODEL_NAMES = ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec")
_MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")
_REQUEST = "request-l05-synthetic-1"
_IMAGE = "image-l05-synthetic-1"
_NAMESPACE = "0123456789abcdef0123456789abcdef"
_REASON = "Synthetic source structure was unavailable."
_EVIDENCE_DIRECTORY = Path(__file__).resolve().parents[1] / "reports/private/l05-real-ocr-v1-2026-11-18"
_write_root: Path | None = None
_audit_installed = False
_resolver_restore = None
_guard_failure = None
# CPython v3.13.7 os/pty/subprocess audit vocabulary. POSIX-only events are
# denied defensively but no unavailable POSIX API is invoked on Windows.
# Retain CPython v3.13.7's native _winapi.CreateProcess audit-event denial
# together with the scoped defensive Windows entry-point wrapper below.
_PROCESS_EVENTS = frozenset((
    "subprocess.Popen", "os.system", "os.spawn", "os.posix_spawn", "os.exec",
    "os.fork", "os.forkpty", "os.startfile", "os.startfile/2", "pty.spawn",
    "_winapi.CreateProcess",
))
_STAGE_CODES = {
    adapt_paddleocr_result.__code__: "adapter",
    coordinator.coordinate_synthetic_receipt_v0.__code__: "coordinator",
    coordinator.attach_gate_result.__code__: "attachment",
    coordinator.extract_b2.__code__: "b2",
    coordinator.project_retained_b2_fixture_presentation_v1.__code__: "projection",
}


@contextmanager
def _stage_counts():
    """Observe genuine Python calls without replacing accepted stage functions."""
    previous = sys.getprofile()
    if previous is not None:
        raise RuntimeError("Exclusive call observation unavailable.")
    counts = dict.fromkeys(_STAGE_CODES.values(), 0)

    def observe(frame, event, arg):
        if event == "call" and frame.f_code in _STAGE_CODES:
            counts[_STAGE_CODES[frame.f_code]] += 1

    try:
        sys.setprofile(observe)
        yield counts
    finally:
        sys.setprofile(previous)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def sha256_stream(stream) -> str:
    digest = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _runtime() -> dict:
    packages = {name: version(name) for name in _VERSIONS}
    if (platform.python_implementation() != "CPython" or sys.version_info[:3] != (3, 13, 7)
            or unicodedata.unidata_version != "15.1.0" or packages != _VERSIONS):
        raise RuntimeError("Pinned runtime unavailable.")
    return {"python": platform.python_version(), "implementation": "CPython",
            "unicode": unicodedata.unidata_version, "packages": packages}


def _model_preflight(directories: tuple[Path, Path]) -> tuple[list[dict], tuple[Path, ...]]:
    """Read all required bytes before OCR imports; never fetch or repair files."""
    import yaml

    if type(directories) is not tuple or len(directories) != 2:
        raise ValueError("Invalid local model configuration.")
    records, resolved = [], []
    for name, directory in zip(_MODEL_NAMES, directories):
        directory = directory.resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("Invalid local model configuration.")
        files = []
        for filename in _MODEL_FILES:
            path = directory / filename
            if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
                raise ValueError("Invalid local model artifact.")
            size = path.stat().st_size
            with path.open("rb") as stream:
                prefix = stream.read(128)
            if size == 0 or prefix.startswith(b"version https://git-lfs.github.com/spec/"):
                raise ValueError("Invalid local model artifact.")
            files.append({"file": filename, "bytes": size, "sha256": _digest(path)})
        graph = json.loads((directory / "inference.json").read_bytes())
        config = yaml.safe_load((directory / "inference.yml").read_text(encoding="utf-8"))
        if not isinstance(graph, dict) or not graph or config.get("Global", {}).get("model_name") != name:
            raise ValueError("Invalid local model configuration.")
        records.append({"model": name, "files": files, "verification": "LOCAL_READABLE_HASHED_NOT_AUTHENTICATED"})
        resolved.append(directory)
    return records, tuple(resolved)


def _deny(*args, **kwargs):
    global _guard_failure
    _guard_failure = "NETWORK_DOWNLOAD_OR_SUBPROCESS_BLOCKED"
    raise RuntimeError("Offline operation blocked.")


def _audit(event, args):
    """Deny Python-observable writes outside this invocation's temporary root.

    Not an OS sandbox or native-memory/time bound. The hook becomes inert after
    the scope exits; its process-global installation is never advertised as a
    general-purpose concurrency-safe library boundary.
    """
    global _guard_failure
    root = _write_root
    if root is None:
        return
    if event in _PROCESS_EVENTS or event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
        _deny()
    paths = ()
    if event == "open":
        path, mode, flags = args
        writing = (mode is not None and any(c in mode for c in "wax+")) or bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            paths = (path,)
    elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"):
        paths = args[:1]
    elif event in ("os.rename", "os.link", "os.symlink"):
        paths = args[:2]
    for path in paths:
        if isinstance(path, int) or os.fspath(path) == os.devnull:
            continue
        # Paddle's dataset import calls makedirs on its already existing cache,
        # then catches EEXIST. Permit that no-op, not creation of a new location.
        if event == "os.mkdir" and Path(path).is_dir():
            continue
        if not Path(path).resolve().is_relative_to(root):
            _guard_failure = "NON_TEMPORARY_WRITE_BLOCKED"
            raise RuntimeError("Non-temporary write blocked.")


@contextmanager
def _offline_scope(root: Path):
    """Set cache roots before optional imports; deny Python network/process use."""
    global _write_root, _audit_installed, _resolver_restore, _guard_failure
    if _write_root is not None:
        raise RuntimeError("Concurrent smoke scope rejected.")
    settings = {name: str(root / name.lower()) for name in (
        "PADDLE_PDX_CACHE_HOME", "PADDLE_EXTENSION_DIR", "HF_HOME", "MODELSCOPE_CACHE",
        "MPLCONFIGDIR", "XDG_CACHE_HOME", "CCACHE_DIR", "AISTUDIO_CACHE_HOME",
    )}
    settings.update(PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True", HF_HUB_OFFLINE="1",
                    TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                    PYTHONDONTWRITEBYTECODE="1", TEMP=str(root), TMP=str(root))
    previous = {key: os.environ.get(key) for key in settings}
    targets = [(socket.socket, name) for name in ("connect", "connect_ex", "sendto")]
    targets += [(socket, "create_connection"), (socket, "getaddrinfo")]
    if sys.platform == "win32":
        import _winapi
        targets.append((_winapi, "CreateProcess"))
    originals = [(owner, name, getattr(owner, name)) for owner, name in targets]
    old_bytecode = sys.dont_write_bytecode
    old_tempdir = tempfile.tempdir
    if not _audit_installed:
        sys.addaudithook(_audit)
        _audit_installed = True
    try:
        _write_root = root.resolve()
        _guard_failure = None
        sys.dont_write_bytecode = True
        # gettempdir() is cached before this scope creates TEMP/TMP overrides.
        tempfile.tempdir = str(root)
        os.environ.update(settings)
        for owner, name, _ in originals:
            setattr(owner, name, _deny)
        yield
    finally:
        if _resolver_restore is not None:
            owner, original = _resolver_restore
            owner.get_model_path = original
            _resolver_restore = None
        for owner, name, original in originals:
            setattr(owner, name, original)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.dont_write_bytecode = old_bytecode
        tempfile.tempdir = old_tempdir
        _write_root = None


@contextmanager
def _quiet():
    """Discard third-party Python/native output; never persist transcripts."""
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "w") as sink:
        copies = [os.dup(fd) for fd in (1, 2)]
        try:
            for fd in (1, 2):
                os.dup2(sink.fileno(), fd)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
        finally:
            for fd, copy in zip((1, 2), copies):
                os.dup2(copy, fd)
                os.close(copy)


def _verified_ccache_caller(caller) -> bool:
    """Require the loaded Paddle function's exact code and module globals."""
    module = sys.modules.get("paddle.utils.cpp_extension.extension_utils")
    if type(module) is not ModuleType:
        return False
    discovery = module.__dict__.get("find_ccache_home")
    return (type(discovery) is FunctionType
            and discovery.__globals__ is module.__dict__
            and caller.f_globals is module.__dict__
            and caller.f_code is discovery.__code__)


def _verified_nvcc_stderr(stream, caller) -> bool:
    """Check Paddle-owned writable NUL, without coercing arbitrary objects."""
    module = sys.modules.get("paddle.utils.cpp_extension.extension_utils")
    if type(module) is not ModuleType:
        return False
    discovery = module.__dict__.get("find_cuda_home")
    if (type(discovery) is not FunctionType or caller.f_code is not discovery.__code__
            or caller.f_locals.get("devnull") is not stream):
        return False
    if (type(stream) is not io.TextIOWrapper or stream.closed
            or type(stream.name) is not str or stream.name != os.devnull
            or stream.mode != "w" or not stream.writable()
            or type(stream.buffer) is not io.BufferedWriter
            or type(stream.buffer.raw) is not io.FileIO):
        return False
    try:
        import _winapi
        import msvcrt
        descriptor = stream.fileno()
        return (stat.S_ISCHR(os.fstat(descriptor).st_mode)
                and _winapi.GetFileType(msvcrt.get_osfhandle(descriptor)) == 2)
    except (OSError, ValueError):
        return False


@contextmanager
def _optional_ccache_probe():
    """Preempt only verified Paddle ccache and nvcc lookups.

    This invocation-local wrapper exists only around import/initialization.
    No successful path is invented and no discovery function is replaced.
    Every other call keeps the original check_output and strict offline guard.
    The runner remains intentionally single-process and not concurrency-safe.
    """
    original = subprocess.check_output
    observation = {
        "optional_ccache_probe": "DISABLED_FOR_SYNTHETIC_CPU_INFERENCE",
        "optional_ccache_probe_count": 0,
        "optional_nvcc_probe": "DISABLED_FOR_SYNTHETIC_CPU_INFERENCE",
        "optional_nvcc_probe_count": 0,
    }
    pinned_windows = (
        sys.platform == "win32" and sys.version_info[:3] == (3, 13, 7)
        and platform.python_implementation() == "CPython"
        and version("paddlepaddle") == "3.3.1"
    )

    def check_output(*args, **kwargs):
        if (pinned_windows and len(args) == 1 and not kwargs
                and type(args[0]) is list and len(args[0]) == 2
                and all(type(part) is str for part in args[0])
                and args[0] == ["where", "ccache"]
                and _verified_ccache_caller(sys._getframe(1))):
            observation["optional_ccache_probe_count"] += 1
            # Paddle catches this normal unavailable-tool result and leaves
            # ccache_path as None. No Popen/audit event or guard reset occurs.
            raise subprocess.CalledProcessError(1, ["where", "ccache"])
        if (pinned_windows and len(args) == 1 and type(args[0]) is list
                and len(args[0]) == 2 and all(type(part) is str for part in args[0])
                and args[0] == ["where", "nvcc"] and len(kwargs) == 1
                and all(type(key) is str and key == "stderr" for key in kwargs)
                and _verified_nvcc_stderr(kwargs["stderr"], sys._getframe(1))):
            observation["optional_nvcc_probe_count"] += 1
            raise subprocess.CalledProcessError(1, ["where", "nvcc"])
        return original(*args, **kwargs)

    try:
        subprocess.check_output = check_output
        yield observation
    finally:
        subprocess.check_output = original


def _load_engine(directories):
    global _resolver_restore
    from paddleocr import PaddleOCR
    from paddlex.inference.utils.official_models import official_models

    # Explicit paths bypass this installed resolver. Deny any accidental attempt
    # to fall back to the official cache/download path, including optional models.
    if _write_root is None or _resolver_restore is not None:
        raise RuntimeError("Offline scope required.")
    _resolver_restore = (official_models, official_models.get_model_path)
    official_models.get_model_path = _deny
    return PaddleOCR(
        text_detection_model_name=_MODEL_NAMES[0], text_detection_model_dir=str(directories[0]),
        text_recognition_model_name=_MODEL_NAMES[1], text_recognition_model_dir=str(directories[1]),
        device="cpu", enable_mkldnn=False, use_doc_orientation_classify=False,
        use_doc_unwarping=False, use_textline_orientation=False,
    )


def _create_image(path):
    # Reuse the original fixed content/layout, not its transcript-writing main().
    from scripts.ocr_smoke_test import create_synthetic_receipt
    from PIL import Image

    create_synthetic_receipt(path)
    with Image.open(path) as image:
        dimensions = list(image.size)
    if dimensions != [1100, 700]:
        raise ValueError("Unexpected synthetic image shape.")
    return {"sha256": _digest(path), "dimensions": dimensions}


def _project_result(result, image_path: Path, insufficient: bool, retained_payloads=None) -> dict:
    source = adapt_paddleocr_result(
        result, receipt_id="receipt-l05-synthetic-1", image_id=_IMAGE,
        source_system="I2B_L05_GENERATED_SYNTHETIC", source_reference="generated-l05-fixed-1",
        processing_status=SourceProcessingStatus.OCR_COMPLETED, source_image_path=image_path,
    )
    gate_calls = 0
    gate = None

    def synthetic_fixture_gate(actual):
        nonlocal gate_calls, gate
        gate_calls += 1
        if actual is not source or gate_calls != 1:
            raise ValueError("Invalid synthetic invocation.")
        gate = SourceEvidenceGateResult(
            "gate-l05-synthetic-1", source.receipt_id,
            SourceEvidenceDecision.INSUFFICIENT if insufficient else SourceEvidenceDecision.SUFFICIENT,
            (_REASON,) if insufficient else (),
        )
        return gate

    executed = coordinator.coordinate_synthetic_receipt_v0(
        adapted_source=source, gate_evaluator=synthetic_fixture_gate,
        context=SyntheticFailureContextV0(_REQUEST, _IMAGE, _NAMESPACE, "FIXTURE"),
        producer_id="I2B_SYNTHETIC_L05", expected_synthetic_failure=None,
    )
    if type(executed) is not coordinator.SyntheticCoordinatorResultV0:
        raise ValueError("Invalid coordinator result.")
    if type(executed.result) is coordinator.SyntheticCoordinatorRejectionV0:
        # Never stringify a caller-controlled reason or hidden source object.
        return {"adapter": "PASS", "regions": len(source.tokens), "gate_calls": gate_calls,
                "coordinator": "LOCAL_REJECTION", "v1_outcome": None}
    payload, trace = executed.result, executed.trace
    evidence, b2 = trace.source_evidence, trace.b2_result
    if (type(payload) is not bytes or gate_calls != 1 or trace.adapted_source is not source
            or trace.gate_result is not gate or evidence is None or b2 is None
            or evidence.tokens is not source.tokens or evidence.provenance is not source.provenance
            or evidence.gate_result is not gate):
        raise ValueError("Invalid execution continuity.")
    dto = decode_and_validate_presentation_v1(
        payload, expected_request_id=_REQUEST, expected_image_id=_IMAGE, consumer_mode="FIXTURE",
    )
    expected = "SOURCE_EVIDENCE_INSUFFICIENT" if insufficient else "RESULT_AVAILABLE"
    if (dto.outcome.status != expected or dto.outcome.failure is not None
            or dto.source.type != "SYNTHETIC_FIXTURE"
            or dto.source.provenance.source_system != "I2B_SYNTHETIC_B2_V0"
            or dto.source.provenance.source_reference != f"src-v1-{_NAMESPACE}-1"
            or dto.source.provenance.content_sha256 is not None
            or dto.source_evidence.source_processing_status != "OCR_COMPLETED"
            or dto.source_evidence.token_ids != tuple(f"tok-v1-{_NAMESPACE}-{i}" for i in range(1, len(source.tokens) + 1))
            or dto.source_gate.decision != gate.decision.value or dto.source_gate.reasons != gate.reasons):
        raise ValueError("Invalid presentation continuity.")
    if insufficient:
        valid = (b2.receipt_output is None and b2.pre_resolution_disposition.gate_result is gate
                 and dto.receipt is dto.automatic_extraction is None)
    else:
        valid = (b2.receipt_output is not None and b2.receipt_output.source_evidence is evidence
                 and dto.automatic_extraction.extraction_status == b2.receipt_output.extraction_status.value)
    if not valid:
        raise ValueError("Invalid B2 continuity.")
    if retained_payloads is not None:
        retained_payloads.append(payload)
    return {"adapter": "PASS", "regions": len(source.tokens), "gate_calls": gate_calls,
            "coordinator": "PASS", "v1_outcome": dto.outcome.status,
            "extraction_status": None if dto.automatic_extraction is None else dto.automatic_extraction.extraction_status,
            "payload_bytes": len(payload), "payload_sha256": sha256(payload).hexdigest(),
            "original_record_continuity": True}


def run_smoke(*, insufficient: bool = False, _retained_payloads=None) -> dict:
    """Execute only the fixed generated receipt; publish no records or bytes."""
    global _guard_failure
    _guard_failure = None
    summary = {"status": "INCOMPLETE", "device": "cpu", "mkldnn": False,
               "synthetic_gate": "INSUFFICIENT" if insufficient else "SUFFICIENT",
               "ocr_completed": False, "adapter": "NOT_RUN", "coordinator": "NOT_RUN",
               "v1_outcome": None, "cleanup": False, "engine_cleanup": "NOT_CREATED"}
    stage, engine, workspace = "RUNTIME_PREFLIGHT", None, None
    if type(insufficient) is not bool:
        return {**summary, "status": "INVALID_CONFIGURATION", "cleanup": True}
    try:
        summary["runtime"] = _runtime()
        stage = "OFFLINE_MODEL_PREFLIGHT"
        model_root = Path.home() / ".paddlex" / "official_models"
        summary["models"], directories = _model_preflight(tuple(model_root / name for name in _MODEL_NAMES))
        stage = "TEMPORARY_STORAGE"
        with tempfile.TemporaryDirectory(prefix="pantryproof-l05-") as temporary:
            workspace = Path(temporary)
            if workspace.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
                raise ValueError("Temporary storage must be outside the repository.")
            with _offline_scope(workspace), _quiet():
                try:
                    stage = "OCR_INITIALIZATION"
                    with _optional_ccache_probe() as probe:
                        try:
                            engine = _load_engine(directories)
                        finally:
                            summary.update(probe)
                    summary["engine_cleanup"] = "PENDING"
                    stage = "SYNTHETIC_IMAGE"
                    image_path = workspace / "synthetic_receipt.png"
                    summary["image"] = _create_image(image_path)
                    stage = "OCR_INFERENCE"
                    results = engine.predict(str(image_path))
                    summary["ocr_completed"] = True
                    stage = "OCR_RESULT_SHAPE"
                    if not isinstance(results, (list, tuple)) or len(results) != 1 or not isinstance(results[0], Mapping):
                        raise ValueError("Unsupported OCR result shape.")
                    original = results[0]
                    summary["result_structure"] = "MAPPING"
                    summary["confidence_supplied"] = original.get("rec_scores") is not None
                    summary["geometry_supplied"] = any(original.get(key) is not None for key in ("rec_polys", "dt_polys", "rec_boxes"))
                    stage = "ADAPTER_OR_PRESENTATION"
                    with _stage_counts() as counts:
                        summary["stage_calls"] = counts
                        summary.update(_project_result(original, image_path, insufficient, _retained_payloads))
                    if summary["coordinator"] == "PASS" and any(count != 1 for count in counts.values()):
                        raise ValueError("Invalid stage invocation count.")
                    summary["status"] = "PASS" if summary["coordinator"] == "PASS" else "SAFE_LOCAL_REJECTION"
                finally:
                    if engine is not None:
                        # A cleanup failure invalidates a successful run too.
                        previous_stage = stage
                        stage = "ENGINE_CLEANUP"
                        summary["engine_cleanup"] = "FAILED"
                        engine.close()
                        engine = None
                        summary["engine_cleanup"] = "PASS"
                        stage = previous_stage
        summary["cleanup"] = not workspace.exists()
    except KeyboardInterrupt:
        summary["status"] = "INTERRUPTED"
    except Exception:
        summary["status"] = "BLOCKED_OFFLINE_MODEL_PREFLIGHT" if stage == "OFFLINE_MODEL_PREFLIGHT" else "FAILED_" + stage
    if workspace is None or not workspace.exists():
        summary["temporary_cleanup"] = True
        summary["cleanup"] = summary["engine_cleanup"] in ("PASS", "NOT_CREATED")
    else:
        summary["status"] = "CLEANUP_FAILED"
    # A library may catch the safe guard exception and continue. Retain its
    # violation through cleanup and reject an otherwise successful/local run.
    # Specific failures, interruption and cleanup failures keep their precedence.
    if _guard_failure is not None:
        summary["guard_block"] = _guard_failure
        if summary["status"] in ("PASS", "SAFE_LOCAL_REJECTION"):
            summary["status"] = "BLOCKED_OFFLINE_GUARD"
    if summary["status"] != "PASS" and _retained_payloads is not None:
        _retained_payloads.clear()
    return summary


def _export_evidence(summary, retained_payloads, *, insufficient, command, started):
    """Export original coordinator bytes only after the fixed run has cleaned up.

    Called solely by the explicit CLI switch. Existing payloads are never
    replaced; the manifest collects at most the two fixed synthetic executions.
    """
    if (summary["status"] != "PASS" or not summary["cleanup"]
            or summary.get("guard_block") is not None or _guard_failure is not None
            or summary.get("engine_cleanup") != "PASS"
            or summary.get("temporary_cleanup") is not True
            or len(retained_payloads) != 1):
        raise ValueError("Synthetic evidence is unavailable.")
    payload = retained_payloads[0]
    dto = decode_and_validate_presentation_v1(
        payload, expected_request_id=_REQUEST, expected_image_id=_IMAGE, consumer_mode="FIXTURE",
    )
    expected = "SOURCE_EVIDENCE_INSUFFICIENT" if insufficient else "RESULT_AVAILABLE"
    if (type(payload) is not bytes or dto.outcome.status != expected
            or dto.source.type != "SYNTHETIC_FIXTURE"
            or dto.source.provenance.source_system != "I2B_SYNTHETIC_B2_V0"
            or dto.source.provenance.source_reference != f"src-v1-{_NAMESPACE}-1"
            or dto.source_evidence.source_processing_status != "OCR_COMPLETED"
            or dto.source_gate.decision != summary["synthetic_gate"]
            or len(payload) != summary["payload_bytes"]
            or sha256(payload).hexdigest() != summary["payload_sha256"]
            or (insufficient and (dto.receipt is not None or dto.automatic_extraction is not None))):
        raise ValueError("Invalid synthetic evidence binding.")
    directory = _EVIDENCE_DIRECTORY
    # The CLI accepts no output path. Reject redirected components, even when
    # they would resolve to another location within the checkout.
    for component in (directory, *directory.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError("Redirected evidence storage.")
    directory.mkdir(parents=True, exist_ok=True)
    filename = "l05-real-ocr-insufficient-v1.json" if insufficient else "l05-real-ocr-sufficient-v1.json"
    destination = directory / filename
    manifest_path = directory / "l05-real-ocr-payload-manifest.json"
    if destination.exists() or manifest_path.is_symlink():
        raise ValueError("Evidence already exists or is redirected.")
    manifest = {"schema": "L05_SYNTHETIC_OCR_EVIDENCE_1", "executions": {}}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_bytes())
        if (manifest.get("schema") != "L05_SYNTHETIC_OCR_EVIDENCE_1"
                or type(manifest.get("executions")) is not dict
                or not set(manifest["executions"]).issubset({"l05-real-ocr-sufficient-v1.json", "l05-real-ocr-insufficient-v1.json"})
                or filename in manifest["executions"]):
            raise ValueError("Invalid evidence manifest.")
        for name, prior in manifest["executions"].items():
            previous_payload = directory / name
            if previous_payload.is_symlink() or _digest(previous_payload) != prior["sha256"]:
                raise ValueError("Existing evidence changed.")
    record = {
        "filename": filename, "bytes": len(payload), "sha256": sha256(payload).hexdigest(),
        "expected_request_id": _REQUEST, "expected_image_id": _IMAGE, "consumer_mode": "FIXTURE",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "command": command, "exit_code": 0, "runner_sha256": _digest(Path(__file__)),
        "offline_guard": "PASS", "execution_summary": summary,
    }
    with destination.open("xb") as stream:
        stream.write(payload)
    if destination.read_bytes() != payload:
        raise ValueError("Evidence bytes changed during export.")
    manifest["executions"][filename] = record
    raw_manifest = json.dumps(manifest, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2).encode("utf-8") + b"\n"
    # A single-process developer export; stage a complete manifest before
    # replacement so an interrupted write cannot truncate the previous record.
    staged = directory / ".l05-manifest.pending"
    try:
        with staged.open("xb") as stream:
            stream.write(raw_manifest)
        staged.replace(manifest_path)
        if manifest_path.read_bytes() != raw_manifest:
            raise ValueError("Evidence manifest changed during export.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        staged.unlink(missing_ok=True)
    return {"filename": filename, "bytes": len(payload), "sha256": record["sha256"]}


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--insufficient"], ["--export-evidence"], ["--insufficient", "--export-evidence"]):
        print('{"status":"INVALID_ARGUMENTS"}')
        return 2
    insufficient = "--insufficient" in arguments
    exporting = "--export-evidence" in arguments
    retained = []
    started = datetime.now(timezone.utc).isoformat()
    if exporting:
        summary = run_smoke(insufficient=insufficient, _retained_payloads=retained)
        if summary["status"] == "PASS":
            try:
                summary["evidence_export"] = _export_evidence(
                    dict(summary), retained, insufficient=insufficient,
                    command=[sys.executable, "-B", "-m", "scripts.synthetic_receipt_backend_smoke_v0", *arguments],
                    started=started,
                )
            except Exception:
                summary["status"] = "FAILED_EVIDENCE_EXPORT"
        retained.clear()
    else:
        summary = run_smoke(insufficient=insufficient)
    print(json.dumps(summary, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if (summary["status"] == "PASS" and summary["cleanup"]
                 and summary.get("guard_block") is None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
