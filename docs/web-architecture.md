# Browser architecture

`web/` is the only UI. Vue sends typed local commands to a module Web Worker, which runs the existing Python parsing/calendar domain under Pyodide 314.0.6. Browser Pydantic is 2.12.5. No HTTP business API, native shell, subprocess, local directory service or remote inference remains.

`runtime.ts` serializes commands within a tab. Every command reads the current IndexedDB snapshot, passes an isolated copy to Python, then rechecks the global revision in the **same read/write transaction** that stores the result. A failed transaction never returns success. Calendar previews verify calendar versions, draft revisions and dependency hashes. Settings use their own revisions. This is a conservative whole-state store: large workspaces incur serialization cost; it intentionally prioritizes atomicity over fine-grained concurrent writes.

Import files remain base64 inside the persisted unfinished job. A second Worker processes files sequentially. A Web Lock owns each active job across tabs. Cancelling terminates the computation Worker; generation checks reject late results. On refresh, orphaned jobs become retryable without discarding their bytes or completed file reports. Files have a 90-second processing deadline including first runtime initialization. The UI never treats OCR failure as a successful table-only import.

OCR reuses `ocr.py` decoding, crop/rotation, deskew, automatic orientation scoring, layout reconstruction, confidence thresholds and evidence extraction. `browser_ocr.py` runs Det/Cls/Rec with ONNX Runtime Web 1.23.2 using WASM, `numThreads = 1`, sequential recognition and no WebGPU. The DB detector postprocessor is extracted from RapidOCR 3.4.2 under Apache-2.0. The recognition dictionary is extracted from the pinned recognition model's metadata, rather than guessed from a different model release.

Downloads use Blob URLs. Browsers do not reliably report that the user kept the file; UI messages say a download was requested and ask users to check the browser's download list. ICS is a snapshot, and no external calendar synchronization or system reminder service is claimed.

The build includes every executable asset, wheel, model, dictionary and required license notice. A generated Service Worker embeds a versioned resource manifest. Resource reads and explicit preparation verify SHA-256; preparation is complete only after every resource is valid. A waiting worker never calls `skipWaiting`. Caches and IndexedDB are separate; upgrading or repairing resource caches never deletes personal data.

Limits: desktop Chrome/Edge/Firefox are the acceptance matrix. Mobile gets the existing responsive layout only. Real anonymized samples remain absent from the corpus and are not inferred from synthetic success. Browser storage is finite and subject to browser retention rules; users need portable backups.
