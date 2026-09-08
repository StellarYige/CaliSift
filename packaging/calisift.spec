# Windows x64 onedir: three entrypoints share the same Python runtime/resources.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
ocr_data, ocr_binary, ocr_hidden = collect_all('rapidocr')
data = [(str(root / 'desktop/dist'), 'desktop-ui'),
        (str(root / 'samples'), 'samples'),
        (str(root / 'resources/licenses'), 'licenses'),
        (str(root / 'LICENSE'), '.'),
        (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
from xingcheng.modelpack import resources
for filename in resources():
    data.append((str(root / 'models/ocr' / filename), 'models/ocr'))
data += copy_metadata('rapidocr') + copy_metadata('onnxruntime') + copy_metadata('pywebview')
data.append((str(root/'artifacts/release/CaliSift-third-party-source-0.3.0-alpha.2.zip'), 'licenses'))
for manifest in ('models.json','dependencies.json','dotnet-dependencies.json','corresponding-source.json','windows-toolchain.json'):
    data.append((str(root/'resources'/manifest), 'licenses'))
a = Analysis([str(root / 'packaging' / entry) for entry in ('desktop_entry.py','worker_entry.py','cli_entry.py')],
             pathex=[str(root/'src')], binaries=ocr_binary, datas=data+ocr_data,
             hiddenimports=ocr_hidden + ['webview.platforms.edgechromium', 'webview.platforms.winforms'],
             excludes=['tkinter','PyQt5','PyQt6','PySide2','PySide6','gi','cefpython3','fastapi','uvicorn','httpx','pytest','matplotlib','scipy','pandas'])
pyz = PYZ(a.pure)
executables = []
for script, name, console in [('desktop_entry','CaliSift',False),('worker_entry','calisift-worker',True),('cli_entry','calisift-cli',True)]:
    entries = [s for s in a.scripts if s[0] not in ('desktop_entry','worker_entry','cli_entry') or s[0] == script]
    exe = EXE(pyz, entries, [], exclude_binaries=True, name=name, debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, console=console, icon=str(root/'resources/calisift.ico'),
              version=str(root/'packaging/version.txt'))
    executables.append(exe)
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name='CaliSift')
