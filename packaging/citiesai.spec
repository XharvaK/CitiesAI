# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CitiesAI desktop app."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None
_spec = Path(SPECPATH).resolve()
packaging_dir = _spec.parent if _spec.suffix == ".spec" else _spec
repo = packaging_dir.parent
icon_path = packaging_dir / "assets" / "CitiesAI.ico"

datas = [
    (str(repo / "citiesai" / "gui" / "static"), "citiesai/gui/static"),
    (str(repo / "pyproject.toml"), "."),
]
hiddenimports = [
    "cities2_mcp",
    "cities2_mcp.game_encyclopedia",
    "citiesai.gui.hud_app",
    "citiesai.gui.hud_window",
    "citiesai.gui.hud_client",
    "citiesai.gui.hud_process",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
]
binaries: list = []

_mcp_datas, _mcp_binaries, _mcp_hidden = collect_all("cities2_mcp")
datas += _mcp_datas
binaries += _mcp_binaries
hiddenimports += _mcp_hidden

_wv_datas, _wv_binaries, _wv_hidden = collect_all("webview")
datas += _wv_datas
binaries += _wv_binaries
hiddenimports += _wv_hidden

_ps_datas, _ps_binaries, _ps_hidden = collect_all("pystray")
datas += _ps_datas
binaries += _ps_binaries
hiddenimports += _ps_hidden

# PySide6 Essentials — avoid collect_all (pulls broken support submodule scans).
# Skip translations (unused by Co-Mayor; onefile extract often fails on *.qm under UPX).
datas += collect_data_files(
    "PySide6",
    includes=[
        "plugins/platforms/**",
        "plugins/styles/**",
        "plugins/imageformats/**",
        "plugins/iconengines/**",
        "plugins/generic/**",
    ],
)
binaries += collect_dynamic_libs("PySide6")
binaries += collect_dynamic_libs("shiboken6")

bundled_dir = repo / "packaging" / "bundled"
bundled_mod = bundled_dir / "CS2DataExport"
if bundled_mod.is_dir():
    datas.append((str(bundled_mod), "citiesai/bundled/CS2DataExport"))

webhook_bundle = bundled_dir / "feedback_webhook.url"
if webhook_bundle.is_file():
    datas.append((str(webhook_bundle), "citiesai/bundled"))

logo_png = packaging_dir / "assets" / "logo.png"
if logo_png.is_file():
    datas.append((str(logo_png), "packaging/assets"))

a = Analysis(
    [str(repo / "citiesai" / "app.py")],
    pathex=[str(repo)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtPdf",
        "PySide6.QtTest",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtUiTools",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CitiesAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.is_file() else None,
)
