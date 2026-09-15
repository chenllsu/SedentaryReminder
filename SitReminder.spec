# -*- mode: python ; coding: utf-8 -*-

# 主程序拆成 sitreminder 包，UI 层在 sitreminder.qt 子包下。
#
# 这里只显式列出 Qt 侧模块，**不再用 collect_submodules 整包收集**：
# 那会把包里当时已归档的 Tk 模块（app / imagery / tray / ui）也当成隐藏导入
# 拖进分析，构建日志里随之出现 tkinter / PIL / pystray 缺失警告。
# PySide6 同理——交给 PyInstaller 自带的 hook 按实际 import 收集即可，
# 全量子模块收集连 QtQml、QtWebEngine 的边角都算了进来。
hiddenimports = [
    'sitreminder.qt.app',
    'sitreminder.qt.window',
    'sitreminder.qt.settings',
    'sitreminder.qt.choice',
    'sitreminder.qt.bubble',
    'sitreminder.qt.qtheme',
]

# 只打包运行时真正用到的 3 个资源：
#   nizi_clean_qt.png —— Qt 版猫图（512×512 高清源）
#   nizi_clean.png    —— 猫图与托盘图标的兜底（paths.MASCOT_PATH）
#   icon.ico          —— exe 与窗口图标
# 其余素材（nizi.png、nizi_user_source.jpg、_previews/ 设计稿）仅开发期使用，不进包。
datas = [
    ('assets/nizi_clean_qt.png', 'assets'),
    ('assets/nizi_clean.png', 'assets'),
    ('assets/icon.ico', 'assets'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 体积优化：排除明显用不到的 PySide6 子模块（仅 Essentials 子集）
    excludes=[
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
        'PySide6.QtBluetooth', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtLocation', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtNetwork', 'PySide6.QtNfc', 'PySide6.QtPdf',
        'PySide6.QtPositioning', 'PySide6.QtQml', 'PySide6.QtQuick',
        'PySide6.QtQuick3D', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml',
        'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSql',
        'PySide6.QtTest', 'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets', 'PySide6.QtXml',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SitReminder',
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
    icon=['assets\\icon.ico'],
)
