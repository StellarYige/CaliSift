# Third-party notices

CaliSift source is Apache-2.0. Third-party components keep their own licenses.
The desktop distribution includes unmodified components and the accompanying
license texts under `licenses/`. The original Python module name and existing
`@xingcheng.local` calendar UIDs are retained for data compatibility.

| Component | Use | License / primary source |
| --- | --- | --- |
| CPython 3.11 | Bundled runtime | PSF License; Python distribution LICENSE |
| pywebview 6.2.1 | Native desktop bridge | BSD-3-Clause; https://github.com/r0x0r/pywebview |
| Vue 3 | Local desktop interface | MIT; https://github.com/vuejs/core |
| SQLite | Local data file | Public domain; https://sqlite.org/copyright.html |
| RapidOCR 3.4.2 | OCR pipeline | Apache-2.0; https://github.com/RapidAI/RapidOCR/tree/v3.4.2 |
| ONNX Runtime 1.23.2 | CPU inference | MIT; https://github.com/microsoft/onnxruntime |
| PP-OCRv5 mobile det/rec, PP-OCR mobile v2 cls | OCR weights converted to ONNX | Apache-2.0 publisher metadata; https://www.modelscope.cn/models/RapidAI/RapidOCR ; upstream https://github.com/PaddlePaddle/PaddleOCR |
| OpenCV 4.11 | Image geometry | Apache-2.0; https://opencv.org/license/ |
| Noto Sans SC | Chinese font used by local OCR | SIL OFL 1.1; pinned Google Fonts revision in `resources/models.json` |
| Microsoft WebView2 | System web renderer | Microsoft redistribution terms; separate runtime, not relicensed under Apache-2.0 |
| PyInstaller | Build tool | GPL-2.0-or-later with bootloader exception; https://pyinstaller.org/en/stable/license.html |
| Inno Setup 6.7.3 | Installer builder | Inno Setup license; https://jrsoftware.org/files/is/license.txt |
| Shapely / GEOS | OCR geometry | BSD-3-Clause / LGPL-2.1-or-later; https://libgeos.org/usage/download/ |
| .NET libraries bundled with pythonnet | Native bridge support | .NET Foundation MIT license and third-party notices; exact NuGet package list in `resources/dotnet-dependencies.json` |
| certifi / tqdm | Dependency support | MPL-2.0 / MPL-2.0 and MIT; complete corresponding sources bundled |

Exact dependency versions and dependency license texts are generated from the
locked build environment by `scripts/collect_licenses.py`. Build tools and test
dependencies are not represented as code authored by CaliSift. Generated test
images in `tests/fixtures/ocr` are regression fixtures, not photographs or an
independent accuracy benchmark. The star mark and example CSV files are original
CaliSift project assets, distributed under Apache-2.0.

Corresponding source archives for the unmodified GEOS, Shapely, certifi and tqdm
components are included in the installer and as a separate release asset.
See [source and rebuilding notes](resources/licenses/CORRESPONDING-SOURCE.md).

The WebView2 standalone installer may be redistributed only under Microsoft's
terms. It installs the shared Evergreen runtime and its update service; this is
separate from CaliSift's local file processing. CaliSift sends no event, image,
name, or document to a cloud API and does not install a reminder service.
