# -*- mode: python ; coding: utf-8 -*-

import os

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

# 只打包运行时真正用到的 4 个资源：
#   nizi_clean_qt.png  —— Qt 版猫图·坐姿（512×512 高清源）
#   nizi_sleep_qt.png  —— Qt 版猫图·睡姿（暂停时显示，与坐姿底边对齐）
#   nizi_clean.png     —— 猫图与托盘图标的兜底（paths.MASCOT_PATH）
#   icon.ico           —— exe 与窗口图标
# 其余素材（nizi.png、nizi_user_source.jpg、_previews/ 设计稿）仅开发期使用，不进包。
datas = [
    ('assets/nizi_clean_qt.png', 'assets'),
    ('assets/nizi_sleep_qt.png', 'assets'),
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
    # ⚠️ 这里只能挡住 Python 层的绑定（*.pyd）；Qt 的 DLL 与插件不受它管辖，
    #    见下方 _drop_from_bundle() 的说明。
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
    # 2 = -OO：去掉 docstring（项目内无 assert，所以安全）。PYZ 1.54 → 1.27 MB。
    optimize=2,
)
pyz = PYZ(a.pure)

# -------------------------------------------------------------------- 体积裁剪
# 2026-09-17：以下裁剪把单文件 exe 从 36.92 MB 压到 22.72 MB（−38.4%），
# 剔除的全部是运行时用不到的文件，功能无任何变化（已真机启动验证：窗口正常上屏、
# 托盘/计时正常、日志零异常）。改动前 164 个打包条目，改动后 49 个。
#
# ⚠️ 关键：**别指望 excludes 能删掉 Qt 的 DLL**。
# PySide6 的打包 hook 是直接扫 Qt 安装目录把 DLL / plugins 当 binaries 收进来的，
# 它根本不看 excludes；excludes 只挡得住 Python 层的绑定（*.pyd）。
# 所以早就写进 excludes 的 QtNetwork，其 Qt6Network.dll 依旧在包里。
# 要真删，只能像下面这样过滤打包清单本身。
DROP_BASENAMES = {
    # Qt 自带的软件 OpenGL 渲染器（Mesa）。原始 19.7 MB，压缩后仍占 7.3 MB，
    # 是包里最大的一项。妮子只用 QPainter 画 2D 位图，走 Qt 的光栅引擎，
    # 不碰 OpenGL；若目标机器没有硬件 OpenGL，系统自带的 opengl32.dll 也能兜底。
    'opengl32sw.dll',
    # 应用全程不发起网络请求（这是设计约定），网络与加密库都用不到。
    'Qt6Network.dll',
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
    '_ssl.pyd',
    # 图标只用 .ico / .png，不需要 SVG 渲染。
    'Qt6Svg.dll',
}


def _drop_from_bundle(name):
    """判断某个打包条目是否应从包里剔除。"""
    n = str(name).replace('\\', '/')
    base = os.path.basename(n)
    if base in DROP_BASENAMES:
        return True
    if n.startswith('PySide6/translations/'):
        # Qt 多语言翻译（70+ 个 .qm，1.85 MB）。应用未使用 QTranslator，
        # 界面文案都是自己写的中文，这些文件从来不会被加载。
        return True
    if n.startswith('PySide6/plugins/imageformats/'):
        # 只留 ico（exe 图标 + 托盘图标）。qjpeg/qwebp/qtiff 等都没用到；
        # PNG 的支持是编进 QtGui.dll 的，不靠插件，所以删了也不影响猫图显示。
        return base != 'qico.dll'
    if n.startswith('PySide6/plugins/platforms/'):
        # 只留 Windows 平台插件。qdirect2d 是备选后端（默认不走），
        # qoffscreen / qminimal 只在无头环境（自动化测试）里用。
        return base != 'qwindows.dll'
    if n.startswith('PySide6/plugins/iconengines/'):
        return True     # SVG 图标引擎，随 Qt6Svg 一并去掉
    if n.startswith('PySide6/plugins/generic/'):
        return True     # 触摸板输入插件，桌面鼠标用不到
    return False
    # 注：plugins/styles/qmodernwindowsstyle.dll 必须保留，
    #     否则 Windows 11 上控件会退回旧样式，外观会变。


# PySide6 把 Qt 的 DLL 与 plugins 作为 binaries 收集，所以主要过滤 binaries；
# datas 一并过滤以防将来打包方式变化。
a.binaries = [e for e in a.binaries if not _drop_from_bundle(e[0])]
a.datas = [e for e in a.datas if not _drop_from_bundle(e[0])]

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
