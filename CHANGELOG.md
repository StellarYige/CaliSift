# Changelog

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
