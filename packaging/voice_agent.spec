# PyInstaller spec. Build from the repository root:
#   pyinstaller packaging/voice_agent.spec
# Output: dist/VoiceAgent/VoiceAgent.exe
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

a = Analysis(
    ["../voice_agent/main.py"],
    pathex=[".."],
    binaries=collect_dynamic_libs("sounddevice"),
    datas=[],
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceAgent",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="VoiceAgent")
