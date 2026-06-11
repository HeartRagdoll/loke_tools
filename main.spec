# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 资源外置，exe 同级目录可读写
打包命令: pyinstaller main.spec --clean

目录结构:
  dist/洛克工具/
  ├── 洛克工具.exe
  ├── config.json       ← 用户可编辑
  ├── models/           ← 用户导入 .pt
  ├── data/             ← 数据集
  └── logs/             ← 运行时日志
"""
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'icon.ico'), '.'),
    ],
    hiddenimports=[
        'torch',
        'numpy',
        'ultralytics.nn.tasks',
        'matplotlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'scipy',
        'pandas',
        'nvidia',
        'cupy',
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
    name='洛克工具',
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
    icon='icon.ico',
)
