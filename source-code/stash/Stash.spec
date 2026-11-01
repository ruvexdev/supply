# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller Stash.spec
datas = [('fonts', 'fonts'), ('stash.ico', '.')]
binaries = []
hiddenimports = []

a = Analysis(
    ['stash.pyw'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Stash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX makes antivirus false-positives more likely
    runtime_tmpdir=None,
    console=False,      # no black console window
    icon='stash.ico',
)
