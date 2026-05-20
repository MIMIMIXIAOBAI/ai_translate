# AI Translate

桌面翻译工具：框选屏幕任意区域，自动识别文字并翻译替换显示。

## 功能

- **框选区域**：按 `Ctrl+Shift+T` 或点击托盘图标，拖动鼠标框选屏幕上任意区域
- **OCR 识别**：自动识别框选区域内的文字（支持中英文）
- **即时翻译**：自动翻译为中文，结果显示在半透明浮窗中覆盖原文
- **点击关闭**：点击翻译浮窗即可关闭

## 安装

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装 Tesseract OCR

**Windows:**
```powershell
winget install tesseract
```
或从 [GitHub Releases](https://github.com/UB-Mannheim/tesseract/wiki) 下载安装包。

安装时确保勾选 **Chinese (Simplified)** 语言包。

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Linux:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim
```

## 使用

```bash
python main.py
```

程序启动后会在系统托盘显示"译"图标。

1. 按下 **Ctrl+Shift+T** 或点击托盘图标 → 选择"Select Region"
2. 屏幕变暗，鼠标变为十字准星 → 拖动框选要翻译的区域
3. 松开鼠标 → 自动识别文字并翻译
4. 翻译结果显示在半透明浮窗中，覆盖在原文位置
5. 点击浮窗关闭，或按 **Esc** 取消框选

## 配置

编辑 `config.json`：

| 字段 | 说明 | 默认值 |
|---|---|---|
| `target_language` | 翻译目标语言 | `zh-CN` |
| `hotkey` | 全局快捷键 | `ctrl+shift+t` |
| `overlay.font_size` | 翻译文字大小 | `14` |
| `overlay.background_opacity` | 浮窗背景不透明度 | `0.88` |

支持的语言代码：`en`、`zh-CN`、`ja`、`ko`、`fr`、`de` 等。

## 依赖

- [PySide6](https://pypi.org/project/PySide6/) — Qt GUI
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — 文字识别引擎
- [pytesseract](https://pypi.org/project/pytesseract/) — Tesseract Python 封装
- [mss](https://pypi.org/project/mss/) — 屏幕截图
- [deep-translator](https://pypi.org/project/deep-translator/) — Google 翻译（无需 API Key）
- [keyboard](https://pypi.org/project/keyboard/) — 全局快捷键
