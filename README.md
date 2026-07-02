# Douyin to Text

本项目是一个本地抖音视频转文字工具：

- 输入抖音分享链接
- 用 `yt-dlp` 拉取视频或音频
- 用 `openai-whisper` 转写
- 输出文本和 JSON

## 项目结构

- `work/douyin_to_text.py`：命令行转写核心
- `work/ui_server.py`：本地网页界面
- `start_ui.bat`：Windows 一键启动入口

## 本地启动

双击 `start_ui.bat`，它会：

1. 启动本地服务
2. 等待 `127.0.0.1:8765`
3. 自动打开页面

## 安装依赖

需要：

- Python 3.12+
- `ffmpeg` 已安装并可直接调用

安装命令：

```powershell
python -m pip install -r requirements.txt
```

## 命令行用法

```powershell
python .\work\douyin_to_text.py "https://v.douyin.com/xxxx/" --model large-v3 --cookies auto
```

默认输出目录：

- `C:\Users\<你的用户名>\Documents\DouyinTranscripts`

输出内容：

- `<slug>.txt`：纯文本
- `<slug>.json`：结构化结果

## 说明

- 这套方案提取的是视频里的口播，不是 OCR 字幕识别。
- 如果抖音反爬、跳验证或链接失效，`yt-dlp` 仍然可能失败。
- 如果你想做成可发布版本，下一步建议把默认输出目录改成仓库外的用户目录，避免硬编码 `D:\`。
