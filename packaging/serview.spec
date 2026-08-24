# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for SER Viewer (macOS .app and Windows folder/exe)."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))
ICON_DIR = os.path.join(ROOT, "packaging", "icons")
VERSION = "1.0.0"

datas = [(os.path.join(ROOT, "serview", "resources"), "serview/resources")]

# Qt modules SER Viewer never touches; leaving them out roughly halves the bundle.
excluded_qt = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
]

analysis = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["serview"],
    hookspath=[os.path.join(ROOT, "packaging", "pyinstaller_hooks")],
    runtime_hooks=[],
    # Optional dependencies of astropy and OpenCV that SER Viewer never uses.
    # Without these the bundle grows by several hundred megabytes.
    excludes=excluded_qt + [
        "tkinter", "matplotlib", "IPython", "pytest", "scipy", "pandas", "pyarrow",
        "h5py", "dask", "sqlalchemy", "numexpr", "bottleneck", "notebook", "jupyter",
        "sphinx", "PyQt5", "PyQt6", "PySide2",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

icon = None
if sys.platform == "darwin" and os.path.exists(os.path.join(ICON_DIR, "serview.icns")):
    icon = os.path.join(ICON_DIR, "serview.icns")
elif sys.platform == "win32" and os.path.exists(os.path.join(ICON_DIR, "serview.ico")):
    icon = os.path.join(ICON_DIR, "serview.ico")

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SER Viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == "darwin",
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SER Viewer",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="SER Viewer.app",
        icon=icon,
        bundle_identifier="org.serviewer.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "SER Viewer",
            "CFBundleDisplayName": "SER Viewer",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "MIT licensed",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "SER video",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Owner",
                    "CFBundleTypeExtensions": ["ser", "SER"],
                    "LSItemContentTypes": ["public.data"],
                }
            ],
        },
    )
