# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir / 无控制台窗口）。

- 只读资源（知识库、语言文件、embedding 种子缓存）随包分发
- .env 不打入包内，首次运行时在 exe 同级自动生成模板
- 日语模型（约420MB）不打入包内，首次运行时经 hf-mirror.com 下载到用户缓存
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = [
    ('knowledge_base.json', '.'),
    ('kb_embeddings.npz', '.'),
    ('locales', 'locales'),
]
# fugashi / unidic_lite 的词典与数据文件
datas += collect_data_files('unidic_lite')
datas += collect_data_files('fugashi')

# 动态导入较多的包，显式收集子模块防止运行期缺模块
hiddenimports = []
hiddenimports += collect_submodules('sentence_transformers')
hiddenimports += collect_submodules('transformers')
hiddenimports += collect_submodules('fugashi')
hiddenimports += collect_submodules('unidic_lite')
hiddenimports += collect_submodules('sklearn')
hiddenimports += collect_submodules('scipy')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 项目中未使用的重型包，减小体积
        'matplotlib', 'pandas', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'notebook', 'jupyter', 'IPython', 'pytest', 'tensorboard',
        'tensorflow', 'jax', 'flax',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BizJargonTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 应用，无控制台窗口
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='BizJargonTool',
)
