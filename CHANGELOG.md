# Changelog

## 0.4.0-alpha.1 — 2026-09-13

CaliSift now runs entirely in a browser. The Vue workbench uses local Web
Workers for Python parsing and real OCR, with IndexedDB for workspaces,
drafts, rules, preferences and source evidence.

- Reuse the calendar, name matching, overnight time and review domain with
  Pyodide 314.0.6 and a separate browser dependency lock.
- Run the pinned OCR models through ONNX Runtime Web 1.23.2, using sequential
  single-threaded WASM with cancellation and processing deadlines.
- Replace native dialogs and directories with browser selection, drag/drop,
  image paste and downloads. Keep old Windows and v1/v2 JSON backup imports.
- Check revisions inside IndexedDB transactions, recover interrupted imports,
  and retain recovery points when replacing a workspace from backup.
- Prepare and verify all offline resources locally. Service Worker updates
  wait for existing pages to close and preserve personal databases.
- Deliver static files, SHA-256 checksums, a complete ZIP and static-only
  Docker/Compose configuration. Deploy checked `main` builds through Pages.
- Replace native shell/build tests with domain, Vue, IndexedDB and real
  Chrome/Edge/Firefox browser coverage. See the [verification record](docs/verification-web.md)
  for results and the limits of the synthetic corpus.

The project no longer builds desktop or mobile applications. Historical
commits, tags and published installers remain available without modification.

## 0.3.0-alpha.1 — 2026-09-08

First CaliSift desktop developer preview. The existing 星程 extraction and
calendar core is retained; the default product is now a local Windows desktop
application with a Vue interface, native file dialogs and isolated file workers.

- Add SQLite workspaces, persisted drafts, transactional previews and idempotent
  commits, stable event identities, recovery points and portable backups.
- Add a desktop review workbench with spreadsheet paging, image crop/rotation,
  local OCR evidence, manual corrections and batch draft editing.
- Expose reusable source rules, course expansion, shareable declarative
  templates, source revision review, explicit cancellation choices and undo.
- Add ICS export profiles and history, stable revision handling and native save
  dialogs. Retain legacy WeChat backup and UID compatibility.
- Package the local OCR engine, pinned models, font, Python runtime and offline
  WebView2 installer. Add an offline model repair pack and dependency sources.
- Add CLI operations, optional API compatibility, bilingual documentation,
  Apache-2.0 licensing, dependency notices and verification/build workflows.

This is an alpha preview, not the stable 0.3.0 acceptance result. Independent
photo/layout accuracy, clean machines without WebView2, external calendar
clients and the full DPI matrix remain unverified. See
[verification status](docs/desktop-verification.md).
