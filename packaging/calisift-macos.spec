"""Native, single-architecture app with shared GUI, CLI and isolated worker."""
from pathlib import Path
import platform
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
ocr_data, binaries, hidden = collect_all('rapidocr')
data = [(str(root/'desktop/dist'), 'desktop-ui'), (str(root/'samples'), 'samples'),
        (str(root/'resources/licenses'), 'licenses'), (str(root/'LICENSE'), '.'),
        (str(root/'THIRD_PARTY_NOTICES.md'), '.')]
from xingcheng.modelpack import resources
for name in resources():
    data.append((str(root/'models/ocr'/name), 'models/ocr'))
for name in ('rapidocr','onnxruntime','pywebview'):
    data += copy_metadata(name)
for name in ('models.json','dependencies.json','corresponding-source.json'):
    data.append((str(root/'resources'/name), 'licenses'))
for path in (root/'artifacts/release').glob('CaliSift-third-party-source-*.zip'):
    data.append((str(path), 'licenses'))
entries = ('desktop_entry.py','worker_entry.py','cli_entry.py')
a = Analysis([str(root/'packaging'/entry) for entry in entries], pathex=[str(root/'src')],
             binaries=binaries, datas=data+ocr_data,
             hiddenimports=hidden+['webview.platforms.cocoa'],
             excludes=['tkinter','PyQt5','PyQt6','PySide2','PySide6','gi','cefpython3',
                       'fastapi','uvicorn','httpx','pytest','matplotlib','scipy','pandas'])
pyz = PYZ(a.pure)
executables = []
for script,name,console in [('desktop_entry','CaliSift',False),('worker_entry','calisift-worker',True),('cli_entry','calisift-cli',True)]:
    scripts=[s for s in a.scripts if s[0] not in ('desktop_entry','worker_entry','cli_entry') or s[0] == script]
    executables.append(EXE(pyz,scripts,[],exclude_binaries=True,name=name,console=console,
                           target_arch=platform.machine(),codesign_identity='-',strip=False,upx=False))
collection=COLLECT(*executables,a.binaries,a.datas,name='CaliSift')
app=BUNDLE(collection,name='CaliSift.app',bundle_identifier='io.github.StellarYige.CaliSift',
           info_plist={'CFBundleShortVersionString':'0.3.0','CFBundleVersion':'0.3.2',
                       'LSMinimumSystemVersion':'15.0','NSHighResolutionCapable':True})
