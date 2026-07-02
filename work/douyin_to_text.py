from __future__ import annotations

import argparse
import json
import re
import subprocess
from threading import Lock
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "DouyinTranscripts"
DEFAULT_DOWNLOAD_DIR = DEFAULT_OUTPUT_DIR / "videos"
DEFAULT_MODEL = "turbo"
_MODEL_CACHE = {}
_MODEL_LOCK = Lock()


def ensure_command(name: str) -> None:
    if subprocess.run(["where", name], capture_output=True, text=True).returncode != 0:
        raise SystemExit(f"Missing required command: {name}")


def slugify(text: str) -> str:
    text = re.sub(r"^https?://", "", text.strip())
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:80] or "video"


def first_url(text: str) -> str:
    match = re.search(r"https?://\S+", text.strip())
    if not match:
        return text.strip()
    return match.group(0).rstrip("，,。)）]")


def to_simplified_chinese(text: str) -> str:
    if not text:
        return text
    try:
        from opencc import OpenCC
    except ImportError:
        return text
    return OpenCC("t2s").convert(text)


def punctuate_chinese_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text
    punctuation_count = len(re.findall(r"[，。！？；：,.!?;:]", text))
    if punctuation_count >= max(3, len(text) // 90):
        return normalize_chinese_punctuation(text)

    text = re.sub(r"(好|对|嗯|是的|没错|然后|所以|但是|那|其实|比如说)(?=[\u4e00-\u9fff])", r"\1，", text)
    text = re.sub(r"(对吧|是不是|为什么|怎么办)(?=[\u4e00-\u9fff])", r"\1，", text)
    text = re.sub(r"([，,]){2,}", "，", text)

    pieces = []
    current = ""
    for part in re.split(r"(，)", text):
        current += part
        if len(current) >= 55 and current.endswith("，"):
            pieces.append(current[:-1] + "。")
            current = ""
    if current.strip():
        pieces.append(current.strip())
    text = "".join(pieces)
    if text and text[-1] not in "。！？.!?":
        text += "。"
    return normalize_chinese_punctuation(text)


def normalize_chinese_punctuation(text: str) -> str:
    replacements = {
        ",": "，",
        ".": "。",
        "?": "？",
        "!": "！",
        ";": "；",
        ":": "：",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s*([，。！？；：])\s*", r"\1", text)
    text = re.sub(r"([，。！？；：]){2,}", r"\1", text)
    return text.strip()


def postprocess_text(text: str) -> str:
    text = to_simplified_chinese(text)
    text = punctuate_chinese_text(text)
    return text


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', "", text)


def extract_audio_only(media_path: Path) -> Path:
    """Strip video stream from file, keep only audio. Uses ffmpeg.
    If already audio-only, ffmpeg copies in <100ms."""
    if media_path.suffix.lower() in {".m4a", ".mp3", ".aac", ".opus", ".wav", ".flac"}:
        return media_path
    audio_path = media_path.with_suffix(".m4a")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(media_path), "-vn", "-acodec", "copy", str(audio_path)],
        capture_output=True, timeout=180,
    )
    if not audio_path.exists():
        raise RuntimeError(f"提取音频失败: {media_path}")
    media_path.unlink(missing_ok=True)
    return audio_path


def _download_once(url: str, out_dir: Path, cookie_browser: str | None, on_progress=None) -> Path:
    import yt_dlp

    ydl_opts = {
        "format": "bestaudio/bestaudio*/worstvideo+bestaudio/worst*",
        "outtmpl": str(out_dir / "%(title).80s-%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if cookie_browser:
        ydl_opts["cookiesfrombrowser"] = (cookie_browser,)
    else:
        # Auto-detect cookies.txt (yt-dlp native format, no browser dependency)
        for _cf in [DEFAULT_OUTPUT_DIR / "cookies.txt", Path("cookies.txt")]:
            if _cf.exists():
                ydl_opts["cookiefile"] = str(_cf)
                break

    if on_progress:
        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                if total > 0:
                    pct = min(99, int(done * 100 / total))
                    speed = d.get("speed", 0)
                    label = f"下载中 {pct}%"
                    if speed:
                        label += f" ({speed/1024/1024:.1f}MB/s)"
                    on_progress(pct, label)
        ydl_opts["progress_hooks"] = [hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "requested_downloads" in info and info["requested_downloads"]:
            filepath = info["requested_downloads"][0].get("filepath")
            if filepath:
                return Path(filepath)
        filename = ydl.prepare_filename(info)
        if filename.endswith(".webm") or filename.endswith(".mkv"):
            merged = Path(filename).with_suffix(".mp4")
            if merged.exists():
                return merged
        return Path(filename)


def _download_from_mobile_share_page(url: str, out_dir: Path, on_progress=None) -> Path:
    import requests
    import warnings as _warnings
    _warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

    clean_url = first_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Referer": "https://www.iesdouyin.com/",
    }
    page = requests.get(clean_url, headers=headers, timeout=30)
    page.raise_for_status()

    video_id = ""
    parsed_path = urlparse(page.url).path
    id_match = re.search(r"/(?:video|share/video)/(\d+)", parsed_path)
    if id_match:
        video_id = id_match.group(1)
    if not video_id:
        id_match = re.search(r'"aweme_id":"(\d+)"', page.text)
        video_id = id_match.group(1) if id_match else "douyin_video"

    play_match = re.search(r'"play_addr":\{"uri":"[^"]+","url_list":\["([^"]+)"', page.text)
    if not play_match:
        raise RuntimeError("Mobile share page did not contain a playable video URL")

    play_url = json.loads(f'"{play_match.group(1)}"')
    # Non-watermarked version
    play_url = play_url.replace("/playwm/", "/play/")

    if on_progress:
        on_progress(0, "下载中 0%")

    # Disable SSL verification — aweme.snssdk.com cert chain is not trusted by certifi
    media = requests.get(play_url, headers=headers, stream=True, timeout=120, verify=False)
    media.raise_for_status()

    total = int(media.headers.get("Content-Length", "0"))
    media_path = out_dir / f"{video_id}.mp4"
    downloaded = 0
    with media_path.open("wb") as fh:
        for chunk in media.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)
                downloaded += len(chunk)
                if on_progress and total > 0:
                    pct = min(99, int(downloaded * 100 / total))
                    on_progress(pct, f"下载中 {pct}%")
    if on_progress:
        on_progress(100, "下载完成")
    return media_path


def download_video(url: str, out_dir: Path, cookie_browser: str = "auto", on_progress=None) -> Path:
    url = first_url(url)
    out_dir.mkdir(parents=True, exist_ok=True)
    if cookie_browser == "auto":
        candidates: list[str | None] = [None, "edge", "chrome"]
    elif cookie_browser == "none":
        candidates = [None]
    elif cookie_browser == "edge":
        candidates = ["edge", "chrome"]
    elif cookie_browser == "chrome":
        candidates = ["chrome", "edge"]
    else:
        candidates = [cookie_browser]

    errors: list[str] = []
    for candidate in candidates:
        try:
            return _download_once(url, out_dir, candidate, on_progress)
        except Exception as exc:
            label = candidate or "no cookies"
            errors.append(f"{label}: {exc}")

    try:
        return _download_from_mobile_share_page(url, out_dir, on_progress)
    except Exception as exc:
        errors.append(f"mobile share page fallback: {exc}")

    raise RuntimeError("下载失败。\n" + "\n".join(errors))


def preload_model(model_name: str = DEFAULT_MODEL) -> None:
    """Pre-load a Whisper model into the cache (call at startup)."""
    import whisper
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    key = (model_name, device)
    with _MODEL_LOCK:
        if key not in _MODEL_CACHE:
            _MODEL_CACHE[key] = whisper.load_model(model_name, device=device)


def transcribe(media_path: Path, model_name: str, language: str = "zh", on_progress=None) -> dict:
    import whisper
    import torch

    if on_progress:
        on_progress(0, "加载模型…")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    cache_key = (model_name, device)
    with _MODEL_LOCK:
        if cache_key not in _MODEL_CACHE:
            _MODEL_CACHE[cache_key] = whisper.load_model(model_name, device=device)
    model = _MODEL_CACHE[cache_key]

    if on_progress:
        on_progress(15, "开始转写…")

    result = model.transcribe(
        str(media_path),
        fp16=(device == "cuda"),
        language=language,
        task="transcribe",
        condition_on_previous_text=True,
        initial_prompt="以下是普通话口播内容，请输出简体中文，并保留自然的中文标点符号。",
    )

    if on_progress:
        on_progress(100, "转写完成")

    result["text"] = postprocess_text(result.get("text", ""))
    return result


def write_outputs(base_dir: Path, url: str, media_path: Path, result: dict) -> tuple[Path, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(url)
    text_path = base_dir / f"{stem}.txt"
    json_path = base_dir / f"{stem}.json"

    text = result.get("text", "").strip()
    segments = result.get("segments", [])
    payload = {
        "source_url": url,
        "media_path": str(media_path),
        "text": text,
        "segments": segments,
    }
    text_path.write_text(text + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return text_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a Douyin video and transcribe it to text.")
    parser.add_argument("url", help="Douyin video URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Whisper model name, default: {DEFAULT_MODEL}")
    parser.add_argument("--language", default="zh", help="Whisper language code, default: zh")
    parser.add_argument("--cookies", default="auto", choices=["auto", "none", "edge", "chrome"], help="Browser cookies for yt-dlp")
    parser.add_argument("--workdir", default=str(DEFAULT_DOWNLOAD_DIR))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    ensure_command("ffmpeg")

    workdir = Path(args.workdir)
    outdir = Path(args.outdir)

    print(f"[1/3] downloading: {args.url}")
    media_path = download_video(args.url, workdir, args.cookies)
    print(f"  extracting audio...")
    media_path = extract_audio_only(media_path)
    print(f"[2/3] transcribing: {media_path.name} with model={args.model}")
    result = transcribe(media_path, args.model, args.language)
    print("[3/3] writing outputs")
    text_path, json_path = write_outputs(outdir, args.url, media_path, result)
    print(str(text_path))
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
