# CaliSift

A browser-only, local calendar workspace for rosters, spreadsheets and printed screenshots.

**[Open the website](https://stellaryige.github.io/CaliSift/)** · [Complete static ZIP](https://stellaryige.github.io/CaliSift/downloads/CaliSift-web-0.4.0-alpha.1.zip) · [中文](README.md) · [Self-hosting](docs/self-hosting.md) · [Verification](docs/verification-web.md)

Vue runs the review interface. A Web Worker runs the existing Python calendar domain using Pyodide 314.0.6 and Pydantic 2.12.5. Fixed OCR models run under ONNX Runtime Web 1.23.2, with single-thread WASM and no WebGPU. Files are processed locally; there is no account, synchronization service, business backend or runtime CDN dependency.

Select or drop XLSX/XLS/CSV/PNG/JPEG files, or paste an image. Review original cells, uncertainty and overnight/conflicting events before saving. Download ICS snapshots, reports and portable backups. Old Windows ZIP and mini-program v1/v2 JSON backups remain importable.

Use **Prepare offline use** in settings. The app reports resource size, progress and SHA-256 verification; offline readiness requires all resources. Updates do not force-reload a review page or delete its database. HTTPS or localhost is required for full offline support.

Data belongs to the current browser profile, origin and deployment directory. The same profile shares it. Changing browsers, sites or paths, clearing site data, or browser storage eviction requires a downloaded backup to recover. Workspaces are organizational, not account isolation. ICS is a snapshot; changes do not synchronize to external calendars. Import each version into a dedicated calendar and verify it.

Only the web product is maintained from 0.4.0-alpha.1. No new phone or desktop applications/installers are built. Historical commits, tags and published installers remain untouched. Desktop Chrome, Edge and Firefox form the acceptance matrix; mobile retains basic responsive layout without dedicated device acceptance. Synthetic tests are not a real-world accuracy benchmark.

```sh
npm ci --prefix web
npm run build
python scripts/serve-web.py --port 8080
```

The complete static ZIP contains the same app, runtime, models, dictionary, checksums and Docker/Compose setup. GitHub Actions validates `main` before Pages deployment, without a release branch. See the linked deployment and verification documents for exact commands and limitations.
