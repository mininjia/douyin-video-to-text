from __future__ import annotations

import argparse
import json
import sys
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from douyin_to_text import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    _strip_ansi,
    download_video,
    ensure_command,
    extract_audio_only,
    first_url,
    preload_model,
    transcribe,
    write_outputs,
)


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>抖音视频转文字</title>
  <style>
    :root {
      --paper: #f6f4ee;
      --ink: #22201c;
      --muted: #6f6a60;
      --line: #d8d0c2;
      --field: #fffdf8;
      --green: #157a5a;
      --green-dark: #0f5c44;
      --red: #b64230;
      --shadow: 0 18px 45px rgba(54, 45, 28, .13);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(34,32,28,.055) 1px, transparent 1px) 0 0 / 38px 38px,
        linear-gradient(0deg, rgba(34,32,28,.04) 1px, transparent 1px) 0 0 / 38px 38px,
        var(--paper);
      color: var(--ink);
      font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    }

    main {
      width: min(980px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 44px 0;
    }

    .mast {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 24px;
      align-items: end;
      border-bottom: 2px solid var(--ink);
      padding-bottom: 22px;
      margin-bottom: 28px;
    }

    h1 {
      margin: 0;
      font-size: clamp(30px, 5vw, 54px);
      line-height: 1;
      font-weight: 900;
      letter-spacing: 0;
    }

    .stamp {
      border: 2px solid var(--ink);
      padding: 10px 12px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 13px;
      transform: rotate(2deg);
      background: #f0e5d0;
    }

    .panel {
      background: rgba(255, 253, 248, .86);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 22px;
    }

    label {
      display: block;
      font-size: 15px;
      font-weight: 800;
      margin-bottom: 8px;
    }

    textarea, select, .dir-row input {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--field);
      color: var(--ink);
      font: inherit;
      outline: none;
    }

    textarea {
      min-height: 116px;
      resize: vertical;
      padding: 14px;
      line-height: 1.6;
    }

    select, .dir-row input {
      height: 44px;
      padding: 0 12px;
    }

    textarea:focus, select:focus, .dir-row input:focus, button:focus-visible {
      border-color: var(--green);
      box-shadow: 0 0 0 3px rgba(21, 122, 90, .17);
    }

    .row {
      display: grid;
      grid-template-columns: minmax(110px, 150px) minmax(120px, 170px) 1fr;
      gap: 14px;
      align-items: end;
      margin-top: 16px;
    }

    button {
      height: 44px;
      border: 0;
      background: var(--green);
      color: white;
      font: inherit;
      font-weight: 900;
      cursor: pointer;
    }

    button:hover { background: var(--green-dark); }
    button:disabled { cursor: not-allowed; opacity: .62; }
    btn-full { width: 100%; margin-top: 16px; }
    btn-sm { height: 34px; padding: 0 12px; font-size: 13px; }

    .status {
      min-height: 24px;
      margin: 16px 0 0;
      color: var(--muted);
      font-size: 14px;
    }
    .status.error { color: var(--red); }

    /* progress list */
    .progress-wrap { margin-top: 16px; }
    .progress-title { font-size: 15px; font-weight: 800; margin-bottom: 8px; }
    .progress-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 0;
      font-size: 14px;
      border-bottom: 1px solid var(--line);
      line-height: 1.5;
    }
    .progress-item:last-child { border-bottom: none; }
    .pi-status { width: 20px; text-align: center; font-size: 16px; flex-shrink: 0; }
    .pi-url  { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
    .pi-bar  { flex: 0 0 90px; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
    .pi-bar-fill { height: 100%; background: var(--green); border-radius: 3px; transition: width .25s ease; min-width: 0; }
    .pi-msg  { color: var(--muted); font-size: 12px; white-space: nowrap; flex-shrink: 0; min-width: 85px; text-align: right; }
    .pi-done  .pi-status { color: var(--green); }
    .pi-error .pi-status { color: var(--red); }
    .pi-active .pi-status { color: var(--green-dark); }

    /* results */
    .results-wrap { margin-top: 18px; }
    .result-section {
      padding: 16px 0;
      border-bottom: 1px solid var(--line);
    }
    .result-section:last-child { border-bottom: none; }
    .result-section:first-child { padding-top: 0; }
    .result-url {
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
      word-break: break-all;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .result-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
    .result-actions button {
      height: 32px; padding: 0 10px; font-size: 13px; width: auto;
      background: var(--ink);
    }
    .result-actions button:hover { background: #3a3632; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      min-height: 60px;
      max-height: 30vh;
      overflow: auto;
      padding: 14px;
      border: 1px solid var(--line);
      background: #fffaf0;
      line-height: 1.75;
      font-size: 14px;
    }
    .result-files {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
      margin-top: 8px;
      word-break: break-all;
    }
    .badge {
      display: inline-block;
      background: var(--green);
      color: #fff;
      font-size: 12px;
      font-weight: 800;
      padding: 1px 7px;
      border-radius: 3px;
    }

    .empty-state {
      color: var(--muted);
      font-size: 14px;
      font-style: italic;
    }

    @media (max-width: 680px) {
      main { padding-top: 24px; }
      .mast, .row { grid-template-columns: 1fr; }
      .stamp { width: fit-content; }
    }
  </style>
</head>
<body>
  <main>
    <section class="mast">
      <h1>抖音视频转文字</h1>
      <div class="stamp">local / whisper</div>
    </section>

    <section class="panel">
      <label for="url">分享链接（每行一个，支持批量处理）</label>
      <textarea id="url" placeholder="https://v.douyin.com/xxxx/&#10;https://v.douyin.com/yyyy/"></textarea>

      <div class="row">
        <div>
          <label for="cookies">cookie 来源</label>
          <select id="cookies">
            <option value="auto" selected>自动：推荐</option>
            <option value="edge">Edge</option>
            <option value="chrome">Chrome</option>
            <option value="none">不用 cookie</option>
          </select>
        </div>
        <div>
          <label for="output_dir">保存到</label>
          <div class="dir-row"><input id="output_dir" value="D:\DouyinTranscripts" /></div>
        </div>
      </div>

      <button id="run" class="btn-full">开始转文字</button>

      <p id="status" class="status"></p>

      <!-- progress list -->
      <div id="progressWrap" class="progress-wrap" style="display:none">
        <div class="progress-title">处理进度</div>
        <div id="progressList"></div>
      </div>

      <!-- results -->
      <div id="resultsWrap" class="results-wrap" style="display:none">
        <div class="progress-title">识别结果</div>
        <div id="results"></div>
      </div>
    </section>
  </main>

  <script>
    const run = document.getElementById("run");
    const urlIn = document.getElementById("url");
    const cookies = document.getElementById("cookies");
    const status = document.getElementById("status");
    const outputDir = document.getElementById("output_dir");
    const progressWrap = document.getElementById("progressWrap");
    const progressList = document.getElementById("progressList");
    const resultsWrap = document.getElementById("resultsWrap");
    const resultsDiv = document.getElementById("results");

    let results = [];
    let aborted = false;

    function setStatus(message, isError) {
      status.textContent = message;
      status.classList.toggle("error", !!isError);
    }

    function h(s) {
      const d = document.createElement("div");
      d.textContent = s;
      return d.innerHTML;
    }

    function extractUrl(s) {
      var m = s.match(/https?:\/\/\S+/);
      return m ? m[0].replace(/[，,。)）]+$/, "") : s;
    }

    function trunc(s, n) {
      if (s.length <= n) return s;
      return s.substring(0, n - 3) + "...";
    }

    function buildProgressItems(urls) {
      progressList.innerHTML = "";
      urls.forEach((u, i) => {
        const el = document.createElement("div");
        el.className = "progress-item";
        el.id = "pi-" + i;
        el.innerHTML =
          '<span class="pi-status">&#9675;</span>' +
          '<span class="pi-url">' + h(trunc(u, 70)) + '</span>' +
          '<div class="pi-bar"><div class="pi-bar-fill" id="pbf-' + i + '" style="width:0%"></div></div>' +
          '<span class="pi-msg" id="pim-' + i + '">等待中</span>';
        progressList.appendChild(el);
      });
    }

    function pi(idx) { return document.getElementById("pi-" + idx); }

    function piStatus(idx, icon, cls, msg, pct) {
      const el = pi(idx);
      if (!el) return;
      el.className = "progress-item " + cls;
      el.querySelector(".pi-status").textContent = icon;
      el.querySelector(".pi-msg").textContent = msg || "";
      const bar = document.getElementById("pbf-" + idx);
      if (bar && pct !== undefined) bar.style.width = Math.min(pct, 100) + "%";
    }

    function escPre(s) {
      return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function addResultSection(msg) {
      const idx = results.length;
      results.push(msg);
      resultsWrap.style.display = "block";

      const sec = document.createElement("div");
      sec.className = "result-section";
      sec.id = "rs-" + idx;

      const text = msg.text || "";

      sec.innerHTML =
        '<div class="result-url"><span class="badge">#' + (msg.url_index + 1) + '</span> ' + h(trunc(msg.url, 90)) + '</div>' +
        '<div class="result-actions">' +
          '<button onclick="copyText(' + idx + ')">📋 复制文字</button>' +
        '</div>' +
        '<pre>' + escPre(text) + '</pre>';

      resultsDiv.appendChild(sec);
    }

    function copyText(idx) {
      const r = results[idx];
      if (!r || !r.text) return;
      navigator.clipboard.writeText(r.text).then(function () {
        setStatus("已复制文字。");
      });
    }

    function handleSSEMessage(msg) {
      switch (msg.type) {
        case "progress":
          piStatus(msg.url_index, "▶", "pi-active", msg.message || "", msg.pct);
          break;
        case "url_done":
          piStatus(msg.url_index, "✓", "pi-done", "完成", 100);
          addResultSection(msg);
          break;
        case "url_error":
          piStatus(msg.url_index, "✗", "pi-error", msg.error ? trunc(msg.error, 60) : "失败");
          resultsWrap.style.display = "block";
          results.push(msg);
          break;
        case "done":
          setStatus("完成。共处理 " + (msg.results ? msg.results.length : 0) + " 个视频。");
          break;
        case "error":
          setStatus(msg.error || "处理失败", true);
          break;
      }
    }

    run.addEventListener("click", async function () {
      const raw = urlIn.value.trim();
      if (!raw) { setStatus("先粘贴抖音链接。", true); return; }

      const urls = raw.split("\n").map(function (u) { return extractUrl(u.trim()); }).filter(function (u) { return u; });
      if (!urls.length) { setStatus("先粘贴抖音链接。", true); return; }

      run.disabled = true;
      results = [];
      resultsDiv.innerHTML = "";
      resultsWrap.style.display = "none";
      progressWrap.style.display = "block";
      buildProgressItems(urls);
      setStatus("处理中…");

      try {
        const response = await fetch("/api/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            urls: urls,
            cookies: cookies.value,
            output_dir: outputDir.value.trim() || "D:\\DouyinTranscripts"
          })
        });

        if (!response.ok) {
          const errData = await response.json().catch(function () { return {}; });
          setStatus(errData.error || "请求失败 (" + response.status + ")", true);
          run.disabled = false;
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buf += decoder.decode(chunk.value, { stream: true });

          var parts = buf.split("\n\n");
          buf = parts.pop() || "";

          for (var j = 0; j < parts.length; j++) {
            var match = parts[j].match(/^data: (.+)$/m);
            if (!match) continue;
            try { handleSSEMessage(JSON.parse(match[1])); } catch (e) {}
          }
        }

        if (buf.trim()) {
          var match = buf.match(/^data: (.+)$/m);
          if (match) {
            try { handleSSEMessage(JSON.parse(match[1])); } catch (e) {}
          }
        }

        if (results.length === 0) {
          setStatus("处理完成，但没有返回结果。请检查输出目录。");
        }
      } catch (error) {
        setStatus(error.message || "网络错误", true);
      } finally {
        run.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/transcribe":
            self.send_error(404)
            return

        # parse request
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            self.send_json(400, {"error": f"无效请求: {exc}"})
            return

        raw_urls = data.get("urls", data.get("url", ""))
        if isinstance(raw_urls, str):
            urls = [first_url(u.strip()) for u in raw_urls.strip().split("\n") if u.strip()]
        elif isinstance(raw_urls, list):
            urls = [first_url(u.strip()) for u in raw_urls if u.strip()]
        else:
            urls = []

        cookie_val = str(data.get("cookies", "auto")).strip() or "auto"
        output_dir_raw = str(data.get("output_dir", "")).strip() or str(DEFAULT_OUTPUT_DIR)

        if not urls:
            self.send_json(400, {"error": "链接不能为空"})
            return

        # --- SSE stream ---
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def sse(type_: str, **kw: object) -> None:
            try:
                payload = {"type": type_, **kw}
                raw = json.dumps(payload, ensure_ascii=False)
                self.wfile.write(f"data: {raw}\n\n".encode("utf-8"))
                self.wfile.flush()
            except BrokenPipeError:
                pass  # client disconnected

        try:
            ensure_command("ffmpeg")
            output_dir_path = Path(output_dir_raw)
            download_dir = output_dir_path / "videos"

            results: list[dict] = []

            # Phase 1: parallel download (I/O bound, up to 3 concurrent)
            dl_results: dict[int, Path | Exception] = {}
            with ThreadPoolExecutor(max_workers=3) as pool:
                fut_to_idx: dict = {}
                for i, url in enumerate(urls):
                    def _cb(pct, msg, idx=i):
                        sse("progress", url_index=idx, pct=pct, message=msg, step="download", url=urls[idx])
                    f = pool.submit(download_video, url, download_dir, cookie_val, on_progress=_cb)
                    fut_to_idx[f] = i
                    sse("progress", url_index=i, pct=0, message="排队下载…", step="download", url=url)

                for f in as_completed(fut_to_idx):
                    i = fut_to_idx[f]
                    try:
                        dl_results[i] = f.result()
                    except Exception as exc:
                        dl_results[i] = exc
                        sse("url_error", url_index=i, url=urls[i],
                            error=_strip_ansi(str(exc)))

            # Phase 2: transcribe (GPU-bound, serial)
            for i, url in enumerate(urls):
                dl_result = dl_results.get(i)
                if dl_result is None or isinstance(dl_result, Exception):
                    continue  # already errored above

                try:
                    def _tr_cb(pct, msg, idx=i):
                        sse("progress", url_index=idx, pct=pct, message=msg, step="transcribe", url=urls[idx])

                    media_path: Path = dl_result
                    sse("progress", url_index=i, pct=0, message="提取音频…", step="transcribe", url=url)
                    media_path = extract_audio_only(media_path)

                    sse("progress", url_index=i, pct=0, message="准备转写…", step="transcribe", url=url)
                    result = transcribe(media_path, DEFAULT_MODEL, "zh", on_progress=_tr_cb)

                    sse("progress", url_index=i, url_total=len(urls),
                        step="save", message="正在保存…", url=url)
                    text_path, json_path = write_outputs(
                        output_dir_path, url, media_path, result
                    )

                    result_data: dict = {
                        "url": url,
                        "url_index": i,
                        "text": result.get("text", "").strip(),
                        "text_path": str(text_path),
                        "json_path": str(json_path),
                    }
                    results.append(result_data)
                    sse("url_done", **result_data)

                except Exception as exc:
                    traceback.print_exc()
                    sse("url_error", url_index=i, url=url,
                        error=_strip_ansi(str(exc)))

            sse("done", results=results)

        except Exception as exc:
            traceback.print_exc()
            try:
                sse("error", error=_strip_ansi(str(exc)))
            except Exception:
                pass

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Douyin transcription UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print(f"Loading {DEFAULT_MODEL} model...")
    preload_model(DEFAULT_MODEL)
    print("Model ready.")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Open {url}")
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
