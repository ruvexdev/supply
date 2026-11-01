# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller Pull.spec
from PyInstaller.utils.hooks import collect_all

datas = [('fonts', 'fonts'), ('pull.ico', '.')]
binaries = []
hiddenimports = []
# yt-dlp loads its extractors dynamically; yt_dlp_ejs is the JS challenge solver.
for pkg in ('yt_dlp', 'yt_dlp_ejs'):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['ytdlp-plus.pyw'],
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
    name='Pull',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX makes antivirus false-positives more likely
    runtime_tmpdir=None,
    console=False,      # no black console window
    icon='pull.ico',
)
