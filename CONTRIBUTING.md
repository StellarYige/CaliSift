# Contributing to CaliSift

Thank you for helping make personal schedules easier to verify.

Start with [development instructions](docs/development.md), the
[desktop plan](docs/desktop-open-source-plan.md), and the
[verification status](docs/desktop-verification.md). Small, focused pull requests
with a reproducible before/after example are easiest to review.

## Reproduction data

Do not upload private rosters, personal names, workplace details, phone numbers,
or screenshots containing someone else's information to a public issue. Use the
fictional example name **星辰奕歌** and remove other identifying content. State
whether you have permission to share the file and which license applies.

Describe the expected events, the actual result, file type, layout and software
version. Include exact cell coordinates where useful. An image's OCR score is
not evidence of event accuracy. Label synthetic screenshots and real photographs
separately; rotated or recolored variants are not independent layouts.

## Changes and verification

- Keep parsing and calendar business rules in Python. The frontend does not own
  the authoritative calendar and must not directly replace a stored snapshot.
- Preserve event IDs, source contributions, personal overrides and export UIDs.
  Include migration handling when changing stored schemas.
- Use declarative templates. Do not execute imported code, infer a similar name,
  or silently infer school holiday adjustments.
- Run tests appropriate to the change. The full Windows gate includes real
  local OCR and at least 90% Python branch-aware coverage.
- Test native dialogs and the frozen worker when changing desktop boundaries.
  Browser-only tests do not prove installation or native interaction.
- Update documentation and verification records. Clearly mark unsupported
  platforms, incomplete data sets and untested calendar clients.

Contributions are accepted under Apache-2.0 for project source. Keep third-party
attributions and do not include secrets, personal data, model binaries, virtual
environments or local build output in Git commits. Model changes require an
explicit provenance, checksum and redistribution review.
