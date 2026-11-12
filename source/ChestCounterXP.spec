from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files,collect_submodules
source=Path(SPECPATH)
datas=collect_data_files('rapidocr',includes=['**/*.yaml','**/*.txt'])+[(str(source/'models'),'models'),(str(source/'fixtures'),'fixtures'),(str(source/'assets'),'assets')]
hidden=collect_submodules('rapidocr')+['onnxruntime']
a=Analysis([str(source/'launcher_xp.py')],pathex=[str(source)],binaries=[],datas=datas,hiddenimports=hidden,
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['pyaudiowpatch','soundcard','torch','tensorflow','paddle','openvino','tensorrt','matplotlib','pytest'],noarchive=False,optimize=0)
foreign_icu={'icuuc.dll','icuin.dll','icuio.dll','icudt78.dll'}
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in foreign_icu]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ChestCounterXP',icon=str(source/'assets'/'logo.ico'),debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ChestCounter-XP-Fast')
