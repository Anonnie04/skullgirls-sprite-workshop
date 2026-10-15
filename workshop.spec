# PyInstaller portable Windows build; invoked by scripts/build_release.py.
a = Analysis(['app.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='Skullgirls Sprite Workshop', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
