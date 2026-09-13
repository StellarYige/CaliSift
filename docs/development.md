# Development

The only frontend is `web/`. Python modules under `src/xingcheng/` contain parsing, rules, review, calendar and portable backup logic. Browser state and command boundaries are described in [web architecture](web-architecture.md).

Use Python 3.11+ and Node 24. Install `requirements-lock.txt`, then `python -m pip install --no-deps -e .`, and `npm ci --prefix web`. The native Python dependencies are regression tools; browser packages are independently pinned in `resources/web-runtime-lock.json`.

Run `python -m pytest`, `npm test`, `npm run build`, then `npm run test:browser`. Browser tests use real Chrome, Edge and Playwright Firefox, real Pyodide, real ONNX models, IndexedDB and Service Workers. Install the test browsers with `node web/node_modules/playwright/cli.js install chrome msedge firefox`.

`npm run build` downloads only locked assets, verifies their hashes, bundles the Python source and pure wheels, builds Vue, and emits a versioned offline manifest and checksums. `npm run package` packages those exact bytes and deployment instructions. `npm run dev` is a UI development server; production/offline acceptance uses the built files and `scripts/serve-web.py`.

The 15-file spreadsheet baseline is checked in at `tests/fixtures/browser-expected.json`. Regenerate it deliberately with `python scripts/generate-browser-expected.py` after reviewing a domain change. CSV fixtures use LF line endings to match Git checkouts: file evidence IDs intentionally fingerprint the original bytes, so changing fixture newlines changes those IDs. `tests/fixtures/table-corpus.json` and `ocr/regression-manifest.json` track provenance. Do not describe synthetic pass rates as real-world accuracy. The old portable Windows fixture is retained unchanged; it must not be regenerated with the new web implementation.

No native installers, desktop shell, mini-program build, backend API or system reminder service is maintained. Earlier desktop verification documents remain historical. CI checks `main` before static Pages deployment; see [self-hosting](self-hosting.md).
