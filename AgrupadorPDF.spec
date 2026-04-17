# -*- mode: python ; coding: utf-8 -*-
#
# AgrupadorPDF.spec  -  PyInstaller build spec  (v1.6.0)
#

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("tkinterdnd2")

hiddenimports = (
    collect_submodules("pypdf")
    + collect_submodules("pdfplumber")
    + collect_submodules("PIL")
    + collect_submodules("tkinterdnd2")
    + collect_submodules("pypdfium2")
    + collect_submodules("brutils")
    + [
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.colorchooser",
        "tkinter.font",
        "hashlib",
        "json",
        "shutil",
        "threading",
        "zipfile",
        "sqlite3",
        "pickle",
        "unidecode",
        "cleanco",
        "re",
        "os",
        "unicodedata",
        "pathlib",
        "collections",
        "itertools",
        "pdfplumber",
        "pdfplumber.page",
        "pdfplumber.pdf",
        "agrupador",
        "agrupador.config",
        "agrupador.models",
        "agrupador.extractor",
        "agrupador.matcher",
        "agrupador.grouper",
        "agrupador.merger",
        "agrupador.scorer",
        "agrupador.classifier",
        "agrupador.cnpj_cache",
        "agrupador.feedback_store",
        "agrupador.graph_resolver",
        "agrupador.ui",
        "agrupador.ui.app",
        "agrupador.ui.widgets",
        "sklearn",
        "sklearn.feature_extraction.text",
        "sklearn.svm",
        "sklearn.pipeline",
        "sklearn.calibration",
        "rapidfuzz",
        "rapidfuzz.fuzz",
        "networkx",
        "networkx.algorithms",
    ]
)

a = Analysis(
    ["AgrupadorPDF.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy",
        "PyQt5", "PyQt6", "wx",
        "IPython", "jupyter",
        "unittest", "doctest",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgrupadorPDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="AgrupadorPDF.ico",
    onefile=True,
)
