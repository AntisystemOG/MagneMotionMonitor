# PyInstaller spec for MagneMotion Monitor.
# Build:  python -m PyInstaller --noconfirm MagneMotionMonitor.spec
# Output: dist/MagneMotionMonitor.exe  (single-file, windowed)
from PyInstaller.utils.hooks import collect_submodules

# pycomm3 imports some drivers dynamically; pull them all in so the EXE never
# fails at runtime with a missing-module error.
hiddenimports = collect_submodules("pycomm3")

# Bundle the runtime data (TrackFile.mmtrk is read by track_geometry; the rest is
# kept alongside it to match the source layout). track_photo.png is the real
# Live Track background (see track_photo.py) — without it, the app falls back
# to the schematic automatically, but it should always be present in a release build.
datas = [("mm_monitor/data/TrackFile.mmtrk",        "mm_monitor/data"),
         ("mm_monitor/data/node_configuration.xml", "mm_monitor/data"),
         ("mm_monitor/data/track_photo.png",        "mm_monitor/data"),
         ("assets/app_icon.ico",                    "assets")]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MagneMotionMonitor",
    icon="dist/app_icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
