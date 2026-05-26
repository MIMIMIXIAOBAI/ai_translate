# AI Translate

桌面翻译工具：按下热键，框选屏幕任意区域，自动识别文字并在原位显示翻译结果。支持英文、中文、日文 OCR 识别。

## 功能

- **框选翻译** — `Ctrl+Shift+T` 或系统托盘图标，拖拽选择屏幕区域
- **多语言 OCR** — 支持英文、中文、日文识别，语言包首次运行自动下载
- **原位叠加** — 翻译结果以半透明浮层覆盖在原文字位置，点击关闭
- **多翻译引擎** — 优先使用百度翻译 API，自动回退到 MyMemory → Google → LibreTranslate
- **系统托盘** — 最小化到托盘，右键菜单操作

## 安装

### 1. 安装 Python 3.10+

从 [python.org](https://www.python.org/downloads/) 下载安装，安装时勾选「Add Python to PATH」。

### 2. 安装 Tesseract OCR

**Windows：**
```powershell
winget install tesseract
```
或从 [GitHub Releases](https://github.com/UB-Mannheim/tesseract/wiki) 下载安装包。安装时勾选 **Chinese (Simplified)** 语言包。

**macOS：**
```bash
brew install tesseract tesseract-lang
```

**Linux：**
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置百度翻译（可选）

编辑 `config.json`，填入百度翻译 API 凭据即可获得更高质量的翻译。不配置也可以使用免费翻译引擎。

## 使用

```bash
python main.py
```

Windows 也可双击 `run.bat` 一键启动。

1. 系统托盘出现「译」字图标
2. 按 `Ctrl+Shift+T` 或右键托盘 →「框选翻译」
3. 拖拽鼠标框选屏幕上的文字区域
4. 翻译结果以浮层形式显示在原位
5. 点击浮层关闭，框选时按 `Esc` 取消

## 配置

编辑 `config.json`：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `target_language` | 目标翻译语言 | `zh-CN` |
| `hotkey` | 全局热键 | `ctrl+shift+t` |
| `translation_service` | 翻译服务（`auto` / `baidu`） | `auto` |
| `overlay.background_color` | 浮层背景色 | `#ffffff` |
| `overlay.background_opacity` | 浮层背景不透明度 | `0.85` |
| `overlay.text_color` | 浮层文字颜色 | `#000000` |
| `overlay.min_font_size` | 最小字号 | `10` |
| `overlay.padding` | 文字内边距 | `12` |
| `overlay.border_radius` | 浮层圆角 | `8` |

## 依赖

- [PySide6](https://pypi.org/project/PySide6/) — Qt GUI 框架
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — 文字识别引擎
- [pytesseract](https://pypi.org/project/pytesseract/) — Tesseract Python 封装
- [mss](https://pypi.org/project/mss/) — 屏幕截图（物理像素精度）
- [deep-translator](https://pypi.org/project/deep-translator/) — 多引擎翻译封装
- [keyboard](https://pypi.org/project/keyboard/) — 全局热键注册

## License

MIT
