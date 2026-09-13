# Third-party notices — web edition

CaliSift code is Apache-2.0. Third-party components retain their own licenses. The static distribution includes license files under `licenses/`, with the runtime wheel and NPM version locks. Original `@xingcheng.local` ICS UIDs remain unchanged for backup compatibility.

| Component | Use and source | License |
| --- | --- | --- |
| Pyodide 314.0.6 | Unmodified browser runtime, [corresponding source](https://github.com/pyodide/pyodide/tree/314.0.6) | MPL-2.0 |
| CPython 3.14.2 | Pyodide's embedded Python, [source](https://github.com/python/cpython/tree/v3.14.2) | PSF |
| Vue 3.5.42 | Review interface, [source](https://github.com/vuejs/core) | MIT |
| ONNX Runtime Web 1.23.2 | Single-thread WASM inference, [source](https://github.com/microsoft/onnxruntime/tree/v1.23.2) | MIT |
| RapidOCR 3.4.2 | Extracted DB preprocessing/postprocessing in `src/xingcheng/vendor/db.py`, [source](https://github.com/RapidAI/RapidOCR/tree/v3.4.2) | Apache-2.0 |
| PP-OCRv5 mobile detection/recognition; PP-OCR mobile v2 classification | Fixed ONNX models and metadata dictionary, [publisher](https://www.modelscope.cn/models/RapidAI/RapidOCR), [upstream](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 publisher metadata |
| Pydantic 2.12.5 and pydantic-core 2.41.5 | Browser validation | MIT |
| OpenPyXL / xlrd / defusedxml | Spreadsheet reading | MIT / BSD / PSF |
| NumPy / OpenCV / Pillow / pyclipper | Local image geometry and arrays | BSD / Apache-2.0 / HPND / MIT |
| Shapely 2.1.2 / GEOS 3.12.1 | DB polygon expansion, [Shapely source](https://github.com/shapely/shapely/tree/2.1.2), [Pyodide recipe and rebuild environment](https://github.com/pyodide/pyodide-recipes/tree/314-20260815/packages/shapely) | BSD-3-Clause / LGPL-2.1-or-later |
| Noto Sans SC | Synthetic test fixture font, not required at runtime | OFL-1.1 |

`resources/web-runtime-lock.json` specifies every downloaded runtime asset and its SHA-256. `web/package-lock.json` separately locks JavaScript packages. Runtime wheels retain their distribution license metadata, and the build extracts those notices into the static bundle. `licenses/Pyodide-MPL-2.0.txt` and `licenses/Python-PSF.txt` accompany the runtime. Original upstream copyright notices apply to the extracted detector and model metadata dictionary.

Pyodide and the Shapely/GEOS binaries are unmodified. Their linked source releases and Pyodide recipes provide source and rebuilding instructions; users can substitute rebuilt wheels at the same static paths and regenerate the resource lock/manifest. Dependency source archives required for redistribution are included under `licenses/sources/` by the asset preparation script. No desktop bridge, .NET, WebView2, native OCR runtime or installer builder is included in this web distribution. Historical native license records in the repository remain historical.

Synthetic images and examples in this repository are test fixtures, not real personal schedules or independently reviewed accuracy evidence.
