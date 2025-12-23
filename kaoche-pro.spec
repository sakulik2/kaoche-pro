# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# 收集 AI 引擎的依赖项
# 1. Sherpa-ONNX
datas_sherpa, binaries_sherpa, hiddenimports_sherpa = collect_all('sherpa_onnx')

# 2. WhisperX (包含 torch, torchaudio, transformers)
datas_whisperx, binaries_whisperx, hiddenimports_whisperx = collect_all('whisperx')

# 3. Faster-Whisper
datas_fw, binaries_fw, hiddenimports_fw = collect_all('faster_whisper')

# 4. Langdetect (有时需要 dat 文件)
datas_lang, binaries_lang, hiddenimports_lang = collect_all('langdetect')

# 列表合并辅助函数
def merge_libs(*args):
    result = []
    for arg in args:
        result.extend(arg)
    return result

# 合并所有
all_datas = merge_libs(datas_sherpa, datas_whisperx, datas_fw, datas_lang)
all_binaries = merge_libs(binaries_sherpa, binaries_whisperx, binaries_fw, binaries_lang)
all_hiddenimports = merge_libs(hiddenimports_sherpa, hiddenimports_whisperx, hiddenimports_fw, hiddenimports_lang)

# 添加自定义项目资源
all_datas.extend([
    ('config/prompts', 'config/prompts'),
    ('ui/assets', 'ui/assets'),
])

# 添加 hooks 未捕获的显式隐藏导入
all_hiddenimports.extend([
    'google.genai',
    'google.genai.types',
    'anthropic',
    'PyQt6.QtCore',
    'PyQt6.QtWidgets',
    'PyQt6.QtGui',
    'pysubs2',
    'openai',
    'cryptography',
    'charset_normalizer',
    'openpyxl',
    'soundfile', # librosa/torchaudio 常需此库
])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'lqa_tool', 'sample', 'notebooks'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [], # 排除二进制文件 (使用 ONEDIR 模式)
    exclude_binaries=True,
    name='kaoche-pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ui/assets/icon.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kaoche-pro',
)
