# SedentaryReminder 久坐提醒小工具

一款**完全本地运行**的久坐提醒桌面工具。一只名叫「妮子」的小猫常驻你的桌面，随时显示距下次提醒的倒计时；到点弹出一个气泡框，提醒你起来活动活动。

> 不联网、不吃资源、随时看到倒计时、到点弹个气泡让你起来动一动。

## 功能特性

- 🐱 **桌面宠物常驻** — 小猫「妮子」以透明浮窗形式停在桌面上，可鼠标拖动到任意位置
- ⏱️ **悬停看倒计时** — 鼠标悬停在小猫上，弹出深色小胶囊显示距下次提醒的剩余时间（等宽数字，跳秒不抖）
- 💬 **到点气泡提醒** — 计时归零弹出白卡气泡，尾巴始终指向小猫本体，文案从内置诙谐文案库随机抽取，每次不重样
- ⚙️ **自定义间隔** — 提醒间隔 1–600 分钟自由设置，保存到本地 `config.json`，重启不丢
- ⏸️ **暂停 / 跳过** — 开会吃饭可暂停计时；刚活动完可跳过本轮、立即重新计时
- 🖥️ **系统托盘** — 最小化到托盘常驻，右键菜单快捷操作，关闭不误触

## 快速开始

### 方式一：直接运行打包版（推荐，无需 Python）

下载 `SitReminder.exe`，双击运行即可。

- 首次运行 Windows 可能弹出 SmartScreen 提示（无签名正常现象），点「仍要运行」
- `config.json` 会在 exe 同目录自动生成
- 想开机自启：把 exe 的快捷方式放进 `shell:startup` 文件夹（Win+R 输入 `shell:startup`）

### 方式二：从源码运行

```bash
# 依赖：Python 3.8+，Pillow（可选，缺失时自动降级为基础样式）
pip install pillow
python main.py
```

## 使用说明

| 操作 | 效果 |
|------|------|
| 拖动小猫 | 移动位置 |
| 悬停小猫 | 显示倒计时胶囊 |
| 单击小猫 | 打开设置窗口 |
| 右键小猫 | 暂停 / 跳过 / 设置 / 退出 |
| 提醒弹出后点「知道了」 | 关闭气泡，重新开始计时 |

## 从源码打包

```bash
pip install pyinstaller
pyinstaller SitReminder.spec
# 产物在 dist/SitReminder.exe
```

或直接使用 spec：

```bash
pyinstaller --onefile --noconsole --name SitReminder \
  --icon assets/icon.ico \
  --add-data "assets;assets" main.py
```

## 项目结构

```
main.py                  # 主程序（Tkinter 单文件实现）
assets/
  nizi.png               # 早期形象
  nizi_clean.png         # 精细抠图后的桌面形象
  nizi_user_source.jpg   # 原始素材
  icon.ico               # exe 图标
clean_bg.py              # 抠图脚本（早期）
clean_bg_cat.py          # 精细抠图脚本（flood-fill + defringe + 羽化）
需求文档.md               # 需求梳理文档
SitReminder.spec         # PyInstaller 打包配置
```

## 设计说明

- **透明色键窗口**：Tkinter 的 `transparentcolor` 为 1-bit 透明，选用淡粉色 `#f0e5e7` 作为色键，与猫毛及绘制色零撞色，使阴影可以做真正的羽化渐变
- **动画**：气泡与倒计时胶囊均使用 easeOutBack 缓动的生长动画（15 帧 × 14ms），弹出自然不生硬
- **防出屏**：气泡位置在屏幕边缘自动收拢，尾巴始终指向小猫

## 环境支持

- Windows（已完整测试并打包）
- Linux / macOS（基于 Tkinter 理论可运行，未打包测试，欢迎反馈）

## License

MIT
