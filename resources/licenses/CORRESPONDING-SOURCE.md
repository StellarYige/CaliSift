# Corresponding dependency sources

The offline installer includes `CaliSift-third-party-source-0.3.0-alpha.1.zip`
in `_internal/licenses/`. The same archive is a release asset. It contains the
complete, unmodified upstream source distributions for GEOS 3.13.1, Shapely
2.1.2, certifi 2026.7.22 and tqdm 4.70.0, including their build files and notices.
`manifest.json` records the download locations and SHA-256 checksums.

GEOS is licensed under LGPL-2.1-or-later. Its libraries are dynamically loaded
from `_internal/shapely.libs/`; this distribution does not prohibit replacing
them with compatible modified versions or reverse engineering for debugging
such modifications. Use the bundled source's CMake build instructions to build
shared libraries, preserving the ABI and filenames expected by the Shapely
wheel. Shapely itself uses BSD-3-Clause. Their source archives contain the full
license texts and instructions. No GEOS or Shapely changes were made by CaliSift.

certifi and the applicable portions of tqdm are covered by MPL-2.0 (tqdm also
contains MIT-licensed material). Their complete source distributions are
included without modification. These components keep their original licenses;
CaliSift's Apache-2.0 license does not replace them.

Sources: https://libgeos.org/usage/download/ ; https://pypi.org/project/shapely/2.1.2/ ;
https://pypi.org/project/certifi/2026.7.22/ ; https://pypi.org/project/tqdm/4.70.0/
