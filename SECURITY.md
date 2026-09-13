# Security and private data

Do not post private calendars or exploit details containing user data in public
issues. Prefer GitHub's private vulnerability reporting facility if it is
enabled for this repository. If it is unavailable, open a minimal issue asking
the maintainer for a private reporting channel; omit exploit details and files.

The supported boundary is the current browser profile, origin and deployment
directory. Workspaces share that browser's data; they are not account isolation.
Files and calendars remain in the browser, with no business backend or cloud API.

Reports are useful when they describe the affected version, reproduction steps,
impact, and a sanitized example. In particular, report traversal in archives,
untrusted code execution through templates or file content, exposure of private
source data, accidental network access during OCR, or corruption of existing
calendar data after a failed operation.

Backups contain personal data and should be stored accordingly. They have
integrity checks, not password encryption. A checksum detects accidental changes;
it does not establish that an untrusted file's author is trustworthy.

The web alpha's verification gaps are tracked in
[docs/verification-web.md](docs/verification-web.md). Clearing site data or browser
storage eviction can remove personal data; exported backups are the recovery path.
