# SedentaryReminder 久坐提醒小工具

一款**完全本地运行**的久坐提醒桌面工具。一只名叫「妮子」的小猫常驻你的桌面，随时显示距下次提醒的倒计时；到点弹出一个气泡框，提醒你起来活动活动。

> 不联网、不吃资源、随时看到倒计时、到点弹个气泡让你起来动一动。
>
> **UI 已切换到 PySide6 (Qt6)**，享受真·半透明窗口 + QPainter 抗锯齿，猫与气泡边缘丝滑无毛边；形象素材升级为 512px 高清版并做了高 DPI 适配，在 125% / 150% 缩放的屏幕上同样锐利。

## 功能特性

- 🐱 **桌面宠物常驻** — 小猫「妮子」以透明浮窗形式停在桌面上，可鼠标拖动到任意位置
- 📍 **位置记忆** — 首次启动默认出现在屏幕右下角；之后拖到哪里，下次启动就回到哪里（换显示器 / 改分辨率后若原位置已不可见，自动回退到右下角）
- ⏱️ **悬停看倒计时** — 鼠标悬停在小猫上，弹出深色小胶囊显示距下次提醒的剩余时间（等宽数字，跳秒不抖）
- 💬 **到点气泡提醒** — 计时归零弹出白卡气泡，尾巴始终指向小猫本体，文案从内置诙谐文案库随机抽取，每次不重样
- ⚙️ **自定义间隔** — 提醒间隔支持分钟（1–600）与秒（5–36000）两种单位，保存到本地 `config.json`，重启不丢
- ⏸️ **暂停 / 跳过** — 开会吃饭可暂停计时；刚活动完可跳过本轮、立即重新计时
- 🧊 **开设置自动冻结计时** — 打开设置窗口时倒计时自动暂停；没改间隔就关窗，则从冻结点继续；改了间隔并保存，则按新间隔重新计时
- 🖥️ **系统托盘** — 最小化到托盘常驻，右键菜单含「设置 / 暂停继续 / 跳过本次 / 退出」，关掉设置窗不会误退出程序
- 🖼️ **高 DPI 友好** — 按屏幕缩放比例取物理像素渲染并标注 DPR，高分屏下不糊不锯齿

## 快速开始

### 方式一：运行打包版（推荐，无需 Python）

用下方「从源码打包」生成 `SitReminder.exe`，双击运行即可。

- 首次运行 Windows 可能弹出 SmartScreen 提示（无签名正常现象），点「仍要运行」
- `config.json` 会在 exe 同目录自动生成
- 想开机自启：把 exe 的快捷方式放进 `shell:startup` 文件夹（Win+R 输入 `shell:startup`）

### 方式二：从源码运行

```bash
# 依赖：Python 3.9+，PySide6（Qt6 GUI），Pillow（图像处理）
pip install PySide6 pillow
python main.py
```

## 使用说明

| 操作 | 效果 |
|------|------|
| 拖动小猫 | 移动位置；松手后自动记住，下次启动回到该位置 |
| 悬停小猫 | 显示剩余倒计时胶囊 |
| 单击小猫 | **无动作**（左键只用于拖动，避免误触弹出窗口） |
| 右键小猫 | 显示主窗口 / 设置 / 暂停计时·继续计时 / 跳过本次 / 关闭… |
| 右键托盘图标 | 显示 / 设置 / 暂停继续 / 跳过本次 / 退出 |
| 单击托盘图标 | 重新显示小猫浮窗 |
| 打开设置窗口 | 倒计时自动冻结；未改间隔 → 关窗后从冻结点继续；改了间隔并保存 → 按新间隔重新计时 |
| 提醒弹出后点「知道了」 | 关闭气泡，重新开始计时 |

## 从源码打包

```bash
pip install pyinstaller
pyinstaller SitReminder.spec
# 产物在 dist/SitReminder.exe
```

或不用 spec 手动指定参数：

```bash
pyinstaller --onefile --noconsole --name SitReminder \
  --icon assets/icon.ico \
  --add-data "assets;assets" main.py
```

## 项目结构

```
main.py                     # 入口：单实例保护、日志初始化、异常兜底
sitreminder/
  config.py                 # 配置读写（校验 + 旧字段迁移 + 原子写入 + 窗口位置解析）
  timer.py                  # 倒计时状态机（基于时间戳，不累积误差；支持暂停/恢复/跳过）
  quips.py                  # 内置文案库与随机选取（不连续重复）
  theme.py                  # 配色 / 字体 / 动画常量（样式只改这里；保留作参考）
  paths.py                  # 运行路径（源码运行 vs PyInstaller 打包）
  logging_setup.py          # 日志初始化（滚动文件，便于排查）
  single_instance.py        # 单实例保护（Win 互斥体 / Unix 文件锁）
  qt/                       # PySide6 (Qt6) UI 层 —— 当前主用
    app.py                  # QtController：浮窗 + 计时 + 托盘 + 位置记忆 + 交互编排
    window.py               # 主浮窗（真透明 + QPainter 抗锯齿 + 高 DPI 素材加载）
    bubble.py               # 到点提醒气泡（真阴影 + 真文字）
    settings.py             # 设置窗口（标准控件；关闭时通知控制器决定续算/重算）
    choice.py               # 关闭二选一（退出 / 最小化到托盘）
    qtheme.py               # Qt 主题色/字体常量
  app.py / imagery.py / tray.py / ui/  # 早期 Tkinter 实现（保留作参考与回退路径）
assets/
  nizi.png                  # 早期形象
  nizi_clean.png            # 抠图后的桌面形象（Tk 版使用，1920 原图）
  nizi_clean_qt.png         # Qt 版形象：512px 高清、边缘去色晕（高 DPI 适配）
  nizi_user_source.jpg      # 原始素材
  icon.ico                  # exe 图标
tests/
  test_core.py              # 核心逻辑单元测试（无 GUI）
  smoke_qt.py               # Qt 版 GUI 渲染冒烟（输出预览图到 assets/_previews/）
  smoke_gui.py              # Tk 版 GUI 冒烟（回退路径）
  smoke_main_entry.py       # 入口冒烟（单实例保护等）
clean_bg.py                 # 抠图脚本（早期）
clean_bg_cat.py             # 精细抠图脚本（flood-fill + defringe + 羽化）
SitReminder.spec            # PyInstaller 打包配置（Qt 版）
需求文档.md                  # 需求梳理文档
```

## 开发

```bash
# 建议先建虚拟环境并安装依赖（避免污染系统 Python）
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
pip install PySide6 pillow

# 核心逻辑测试（不弹窗口；框架无关，用解释器跑）
python -m unittest discover -s tests -v

# Qt 版 GUI 渲染冒烟（要求装了 PySide6 的解释器；会输出预览图到 assets/_previews/）
python tests/smoke_qt.py

# Tk 版 GUI 冒烟（回退路径；需装了 tkinter 的解释器）
python tests/smoke_gui.py

# 带调试日志启动
python main.py --debug
```

> 提示：源码里只有 Qt 版（`sitreminder/qt/`）是当前主用；Tk 版（`sitreminder/ui/`、`app.py` 等）是早期实现，保留作回退路径。若本机没有图形界面 / 未安装 tkinter，跳过 `smoke_gui.py` 即可。

日志写入用户数据目录（Windows：`%LOCALAPPDATA%\SitReminder\sitreminder.log`），
打包成无控制台版本后也能据此排查问题。

## 配置文件

`config.json` 与程序同目录（已加入 `.gitignore`，不会进仓库），字段：

| 字段 | 说明 |
|------|------|
| `interval_seconds` | 提醒间隔（秒）。旧版的 `interval_minutes` 会自动迁移 |
| `autostart` | 开机自启偏好（当前仅记录，未真正写入系统启动项） |
| `window_pos` | 浮窗最后位置 `[x, y]`；`null` 表示从未拖动过（首次启动走右下角） |

## 设计说明

- **真·半透明窗口**：PySide6 的 `WA_TranslucentBackground` + `WA_NoSystemBackground` 让整窗 alpha 通道生效，所有像素（含阴影、字体抗锯齿、PNG 边缘）都是真·渐变，**无 Tk 1-bit 色键的阶梯 / 毛边**
- **高清素材 + 高 DPI 适配**：Qt 版用 `assets/nizi_clean_qt.png`（512px）。加载时按「逻辑尺寸 × 屏幕缩放比」取物理像素并设置 `devicePixelRatio`，避免高分屏下位图被放大而发糊；窗口移动到不同缩放的屏幕时会自动重载
- **去色晕抠图**：对原抠图做「边缘像素用内核真实色替换」，彻底消除浅色毛边鬼影
- **形象朝向统一**：主浮窗与托盘图标共用同一素材加载函数，`window.py` 中一个 `MASCOT_MIRROR` 常量即可整体水平翻转，两处同步生效
- **动画**：气泡与倒计时胶囊均使用 easeOut 缓动的生长动画，弹出自然不生硬
- **防出屏**：气泡位置在屏幕边缘自动收拢，尾巴始终指向小猫

## 环境支持

- Windows（已完整测试并打包）
- Linux / macOS（理论可运行，未打包测试，欢迎反馈）

## License

MIT
