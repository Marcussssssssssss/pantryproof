"""Private one-frame T13 PaddleOCR worker. Started only by the approved host."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

from scripts.gate_c_native_worker_host_v0 import (
    HostError, _Pipe, _Win32, _check_time, _local_path, _same_path,
)


def _array_matches(array, frame, np):
    binding = frame.binding
    return (
        type(array) is np.ndarray and array.dtype == np.dtype("uint8")
        and array.shape == (binding.height, binding.width, 3)
        and array.strides == (3 * binding.width, 3, 1)
        and array.nbytes == len(frame.packed_bgr8)
        and array.flags.c_contiguous and not array.flags.writeable
        and array.base is frame.packed_bgr8
        and sha256(memoryview(array)).hexdigest() == binding.bgr8_sha256
    )


def _convert_record(record, binding, np):
    from pipeline.native_local_image_executor_v0 import _recognized_payload
    from scripts import gate_c_ocr_b2_probe_v0 as probe

    if len(record) > len(probe._RESULT_FIELDS) or any(
        type(key) is not str or key not in probe._RESULT_FIELDS for key in record
    ):
        raise HostError("Unexpected native result fields.")
    texts, scores, polygons = (record.get(key) for key in ("rec_texts", "rec_scores", "rec_polys"))
    if not (
        all(type(values) is list for values in (texts, scores, polygons))
        and len(texts) == len(scores) == len(polygons) <= 128
    ):
        raise HostError("Native result arrays refused.")
    plain = []
    for polygon in polygons:
        if type(polygon) is np.ndarray:
            if (
                polygon.ndim != 2 or polygon.shape[1] != 2
                or polygon.dtype != np.dtype("int16") or not 3 <= polygon.shape[0] <= 8
            ):
                raise HostError("Native polygon shape refused.")
            plain.append(polygon.tolist())
        elif type(polygon) in (list, tuple) and 3 <= len(polygon) <= 8:
            plain.append(polygon)
        else:
            raise HostError("Native polygon refused.")

    return _recognized_payload(
        {"rec_texts": texts, "rec_scores": scores, "rec_polys": plain}, binding,
    )


def _recognize(frame, profile, scratch, deadline):
    from importlib.metadata import version
    from scripts import gate_c_ocr_b2_probe_v0 as probe
    from scripts import synthetic_receipt_backend_smoke_v0 as l05

    with l05._offline_scope(scratch):
        l05._runtime()
        pinned = {"numpy": "2.3.5", "opencv-contrib-python": "4.10.0.84", "PyYAML": "6.0.2"}
        if {name: version(name) for name in pinned} != pinned:
            raise HostError("Pinned native imports unavailable.")
        provider = iterator = official_models = original_resolver = None
        try:
            with l05._optional_ccache_probe():
                import numpy as np
                from paddlex.inference.utils.official_models import official_models

                original_resolver = official_models.get_model_path
                official_models.get_model_path = l05._deny
                _check_time(deadline)
                provider, result_type = probe._open_native(profile)

            b = frame.binding
            array = np.ndarray((b.height, b.width, 3), dtype=np.uint8, buffer=frame.packed_bgr8)
            if not _array_matches(array, frame, np):
                raise HostError("Native input association refused.")
            _check_time(deadline)
            iterator, result, failure = probe._record(provider, array, result_type)
            if failure is not None:
                raise HostError("Native recognition failed.")
            probe._association(result, array)
            if not _array_matches(array, frame, np):
                raise HostError("Native raster changed during inference.")
            payload = _convert_record(result, b, np)
        finally:
            resource_error = False
            for resource in (iterator, provider):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        resource_error = True
            if original_resolver is not None:
                official_models.get_model_path = original_resolver
            if resource_error:
                raise HostError("Worker resource closure failed.") from None

        if l05._guard_failure is not None:
            raise HostError("Worker offline guard refused.")
        _check_time(deadline)
        return payload


def _worker_main(args) -> int:
    if (
        sys.platform != "win32" or len(args) != 4 or args[0] != "--t13-worker"
        or not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode
    ):
        return 2
    handle, parent, deadline = map(int, args[1:])
    if handle <= 0 or parent <= 0 or not 0 < deadline < (1 << 63):
        return 2
    _check_time(deadline)
    win = _Win32()
    win.require_job(win.api.GetCurrentProcess())
    if win.pipe_pid(handle, server=True) != parent:
        return 2
    os.set_handle_inheritable(handle, False)

    from pipeline.native_local_image_executor_v0 import (
        NativeLocalImageBindingV0, NativeLocalImageInputV0, _binding, _validate_frame,
        _FRAME_VERSION, _MAX_METADATA_BYTES, _MAX_RASTER_BYTES, _MAX_TERMINAL_BYTES,
        _NONCE, _pack, _unpack,
    )
    from scripts import gate_c_ocr_b2_probe_v0 as probe

    pipe = _Pipe(win, handle, _MAX_RASTER_BYTES, Event())
    try:
        metadata = _unpack(pipe.receive(_MAX_METADATA_BYTES, deadline), _MAX_METADATA_BYTES)
        if (
            set(metadata) != {"version", "dispatch", "binding", "configuration", "detector", "recognizer", "scratch"}
            or metadata["version"] != _FRAME_VERSION or type(metadata["dispatch"]) is not str
            or _NONCE.fullmatch(metadata["dispatch"]) is None or type(metadata["binding"]) is not dict
            or not all(_local_path(metadata[key]) for key in ("configuration", "detector", "recognizer", "scratch"))
            or not _same_path(str(Path.cwd()), metadata["scratch"])
            or Path(metadata["detector"]).parent.name != probe._DETECTOR
            or Path(metadata["recognizer"]).parent.name != probe._RECOGNIZER
        ):
            return 2
        binding = NativeLocalImageBindingV0(**metadata["binding"])
        _binding(binding)
        raster = pipe.receive(3 * binding.width * binding.height, deadline)
        frame = _validate_frame(NativeLocalImageInputV0(binding, raster))
        del raster
        profile = SimpleNamespace(
            configuration=SimpleNamespace(path=metadata["configuration"]),
            detector=(SimpleNamespace(path=metadata["detector"]),),
            recognizer=(SimpleNamespace(path=metadata["recognizer"]),),
            cpu_threads=2,
        )
        status, payload = "FAILED", None
        try:
            payload = _recognize(frame, profile, Path(metadata["scratch"]), deadline)
            status = "COMPLETED"
        except Exception:
            pass

        # Release the raster before the terminal record. Teardown facts are
        # supplied only by the host after EOF, OS exit and scratch observation.
        del frame
        pipe.send(_pack({
            "version": _FRAME_VERSION, "dispatch": metadata["dispatch"],
            "binding": asdict(binding), "status": status, "payload": payload,
        }, _MAX_TERMINAL_BYTES), deadline)
        return 0
    finally:
        if not pipe.close(deadline):
            raise HostError("Worker pipe closure failed.")


if __name__ == "__main__":
    try:
        result = _worker_main(sys.argv[1:])
    except BaseException:
        result = 2
    os._exit(result)
