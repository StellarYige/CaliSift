# CaliSift

[简体中文](README.md) · [Developer guide](docs/development.md) · [Verification status](docs/desktop-verification.md)

**Turn rosters, timetables, and screenshots into a calendar you can verify.**

CaliSift is a local desktop organizer for personal schedules. Import spreadsheets
or clear printed-table screenshots, compare each event with its source, keep
personal corrections, review revised schedules, and export an ICS calendar.
No account, cloud server, WeChat installation, or LLM API key is required.

The current release is **0.3.0-alpha.2**, a Windows 11 x64 and macOS 15+ desktop
preview with a Simplified Chinese interface and an explicit Asia/Shanghai time zone.

![Review extracted events beside the original table](docs/images/workbench-alpha2.png)

## Get started

Windows installers are distributed through
[Releases](https://github.com/StellarYige/CaliSift/releases). The installer bundles Python,
the local OCR engine, pinned model files and Microsoft's offline WebView2
installer. WebView2 is installed only when missing. Consult the release notes
for checksums, signing status and tested environments.

macOS has separate arm64 and x86_64 DMGs, built natively with ad-hoc signing.
Both architectures passed packaged UI and OCR checks on macOS 15 and 26 in CI.
Browser-download Gatekeeper, native file dialogs and Apple Calendar still need
physical-device verification. Linux currently receives core tests only.

Create a named workspace, choose files, review the extracted events and confirm
the import. A built-in fictional example uses the name **星辰奕歌**. Export ICS
to import into a calendar application you already use for reminders.

## Features

- XLSX / XLS / CSV parsing and local PNG / JPEG OCR with RapidOCR and ONNX Runtime CPU.
- Full paginated spreadsheet preview, cell references, image crop/rotation,
  OCR text correction, relevant image evidence and batch draft edits.
- Reusable source-specific shift rules, semester periods, odd/even weeks,
  batch course entry, semester reuse and editable/copyable/exportable templates.
- System/light/dark themes, three font sizes, spacing, week start and custom categories.
- Persistent SQLite workspaces, stable event identities, source contributions,
  explicit update/cancellation matching, correction choices and update undo.
- Restartable drafts, transactional preview/commit, hide/restore, archiving,
  portable backups and legacy WeChat v1/v2 backup migration.
- ICS export profiles and history, stable UIDs, revisions, time zones, all-day,
  overnight and start-only events, and selectable alarms.
- A reusable Python core, CLI and optional FastAPI adapter. The desktop does not
  expose the business API over HTTP; its loopback asset server serves bundled UI only.

ICS files are snapshots. Importing a new file does not guarantee automatic
updates, removals or reminders in every calendar client. The real Thunderbird
155.0 importer passed initial import, but re-import does not update or remove old
events. Mobile calendar clients remain unverified. See [client results](docs/calendar-compatibility.md).

OCR targets clear printed tables with borders or simple aligned layouts. It does
not promise arbitrary tables, handwriting, poor photographs, severe perspective,
PDF input or automatic interpretation of every recurring timetable. Names match
exactly. Uncertain information requires review.

The independent 20-layout / 20-image acceptance set and remaining calendar-client
checks are still outstanding. Synthetic regression fixtures do **not** establish real
photograph accuracy. See [verification](docs/desktop-verification.md).

## Develop

Python 3.11 and Node.js 24 are used for the desktop build. From the repository:

```sh
python -m venv .venv
# Activate the virtual environment for your shell.
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
npm ci --prefix desktop
npm run build:desktop
python -m scripts.install_ocr
python -m xingcheng.desktop
```

For the spreadsheet core only, `pip install -e .` installs no desktop, OCR or API
framework. Existing `xingcheng` imports and calendar UIDs remain compatible.

```sh
calisift parse samples/九月排班.csv --name 星辰奕歌 --year 2026 --output report.json
```

The shipped Windows CLI is named `calisift-cli.exe` to avoid a case-insensitive
filename collision with `CaliSift.exe`. Detailed build, test and SDK instructions
are in [docs/development.md](docs/development.md).

## Data and licensing

Data lives under `%LOCALAPPDATA%\CaliSift` on Windows or
`~/Library/Application Support/CaliSift` on macOS; `CALISIFT_DATA_DIR` overrides the
location. Import drafts retain local temporary originals until confirmation or
discard. Saved calendars retain extracted structure, corrections and relevant
cropped evidence. Backups exclude unfinished original files and models.

CaliSift has no telemetry, cloud sync or background reminder service. Microsoft's
shared Evergreen WebView2 runtime has its own update behavior and license.

Source: [Apache-2.0](LICENSE). Third-party dependencies, models and fonts retain
their own terms; see [notices](THIRD_PARTY_NOTICES.md). Contributions and sanitized
reproduction cases are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).

## alpha.2

Four sections (Import, Events, Templates, Settings), independent appearance preferences, editable/copyable templates, batch course entry and semester reuse. Windows 11 x64 has native installation checks. macOS 15+ arm64 and x86_64 builds use Cocoa/WKWebView and ad-hoc signing; see [verification](docs/desktop-verification.md) for CI evidence and outstanding physical-device checks. No Linux desktop release, cloud service or paid signing requirement. The UI remains Chinese.

[Architecture](docs/alpha2-architecture.md) · [Recognition corpus](docs/accuracy-corpus.md) · [Real Thunderbird importer results](docs/calendar-compatibility.md). Re-importing a static ICS file is not automatic synchronization.
