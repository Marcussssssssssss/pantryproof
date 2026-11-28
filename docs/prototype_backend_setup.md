# Windows prototype backend setup

Use Windows AMD64 CPython 3.13.7 and the repository-local virtual environment at .venv. The supervisor verifies the base interpreter and the virtual environment launcher separately. The [runtime specification](prototype_runtime.md) and [review contract](review_contract.md) define the supervision and wire contracts.

## Install and acquire assets

Use the approved base interpreter to create .venv for a fresh installation. Install requirements-app.txt with that environment's Python. Use requirements-app-test.txt when running the synthetic tests. The declarations pin the dependency closure measured on Windows AMD64. For an already approved installation, preserve its environment and recheck its exact pins.

Before opening an offline session, acquire PaddleX's official PP-OCRv6_medium_det and PP-OCRv6_medium_rec models from the official model distribution. Use one directory per exact model name. Retain inference.json, inference.pdiparams and inference.yml from the same distribution. Record provenance and hashes locally. Keep packages, interpreters, and model files outside Git.

~~~powershell
& .\.venv\Scripts\python.exe -B -m pytest -q tests/test_prototype_receipt_backend.py tests/test_real_receipt_http_service_v1.py tests/test_native_local_image_executor_v0.py
~~~

## Prepare a private launch manifest

Copy [the example](../config/prototype_manifest.example.json) to private local storage. Empty lists, null profile entries and the relative resource path require operator preparation. Each file pin has absolute path, positive byte length, and lowercase SHA-256. Use PowerShell Get-Item and Get-FileHash -Algorithm SHA256 to measure the actual installed files. Git checkout line-ending conversion can affect these measurements.

- Pin the reviewed source closure, including all paths listed in _PROTOTYPE_SOURCES in scripts/dev_local_image_backend_v0.py. Pin scripts/native_local_image_worker_v0.py as the worker.
- Set the launch executable to the base Python associated with .venv, and pin the .venv launcher separately. Set import_paths to the repository and .venv/Lib/site-packages, in that order. Set SystemRoot to the actual Windows system path.
- Include the base executable, .venv/pyvenv.cfg, pipeline/native_local_image_executor_v0.py, pipeline/native_local_image_dev_controls_v0.py, scripts/gate_c_native_worker_host_v0.py, scripts/gate_c_ocr_b2_probe_v0.py and scripts/synthetic_receipt_backend_smoke_v0.py in runtime, along with the reviewed dependency pins. Pin the installed paddlex/configs/pipelines/OCR.yaml and all three files in each model directory.
- Use private, initially absent scratch outside the checkout and separate from pinned files. Provision the reviewed memory, scratch, minimum work and teardown budgets. Keep the two-thread native worker setting.
- Bind the resource snapshot to its absolute path. The default integration uses NOT_READY with verification and price_rule both null.

The PriceCatcher extract credits the Ministry of Domestic Trade (KPDN) and Department of Statistics Malaysia (DOSM) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). PantryProof selected and joined dated prices and lookup entries, added exact outlet aliases and pantry mappings, and encoded the subset as JSON. Source, rights, and extract provenance accompany the [snapshot](../resources/receipt_pricecatcher_kl_v1.json). [Transactional records](https://data.gov.my/data-catalogue/pricecatcher) · [Item lookup](https://data.gov.my/data-catalogue/lookup_item) · [Premise lookup](https://data.gov.my/data-catalogue/lookup_premise)

## Authorize and run locally

After confirming the approved physical offline condition, prepare private controls evidence with scope LOCAL_GROCERY_RECEIPTS_V1, network_observation WINDOWS_LINK_AND_ROUTE_V0, physical_disconnection_confirmed_unix_s, and expires_unix_s. Use actual UTC Unix seconds and the earliest approved expiry, at most four hours after confirmation. Pin this file and obtain joint authorization for the final manifest digest, exact Android build and receipt-use scope.

Generate one fresh cryptographically random 32-byte token only for the authorized session. Provision its lowercase 64-character hexadecimal encoding into the Android t09Live in-memory debug configuration and into PANTRYPROOF_RECEIPT_TOKEN in the backend launcher environment. Keep it out of manifests, command arguments, logs and persistent settings.

~~~powershell
try {
    & .\.venv\Scripts\python.exe -B -m scripts.dev_local_image_backend_v0 serve-prototype --manifest $approvedManifestPath --approval-sha256 $approvedManifestSha256
} finally {
    Remove-Item Env:PANTRYPROOF_RECEIPT_TOKEN -ErrorAction SilentlyContinue
}
~~~

The backend binds to 127.0.0.1:8765. Android connects through http://10.0.2.2:8765 and sends POST /v1/receipts/process with X-Response-Schema set to receipt-review-v1. After cancellation, allow cleanup before retrying. Stop with Ctrl+C, verify the worker and listener exited, and check scratch is absent. Quarantine or residue requires independent cleanup confirmation before renewal. Renew with fresh host evidence and a fresh token.
