"""Render approved clip requests into 1080x1920 MP4s with real-speech subtitles, a hook and a call to action.

A request file (requests/<request_id>.json) looks like:
{
  "request_id": "2026-11-19-01",
  "campaign": "tomo_gta6",
  "clips": [
    {"clip_id": "tomo_abc123XYZ00_1234", "video_id": "abc123XYZ00", "start": 1234.0, "end": 1266.5,
     "hook": "Tomo's first police chase in GTA 6", "layout": "blur"}
  ]
}

Only the requested minutes are downloaded. Subtitles come from Whisper run on the clip's own audio;
nothing is invented. Usage:
  python -m engine.render requests/2026-11-19-01.json [--release-base URL] [--words-json test.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path

from engine.common import DATA, OUT, WORK, approved_campaign, ffprobe, log, read_json, run, write_json, ytdlp

W, H = 1080, 1920
RENDER_INDEX = DATA / "rendered_index.json"
FONT = os.environ.get("CLIP_FONT", "DejaVu Sans")


# ---------------------------------------------------------------- source
def download_section(video_id: str, start: float, end: float, wd: Path) -> Path:
    wd.mkdir(parents=True, exist_ok=True)
    for p in wd.glob("src.*"):
        p.unlink()
    ytdlp(["-f", "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
           "--download-sections", f"*{start:.2f}-{end:.2f}", "--force-keyframes-at-cuts",
           "--merge-output-format", "mp4", "-o", str(wd / "src.%(ext)s"),
           f"https://www.youtube.com/watch?v={video_id}"])
    files = [p for p in wd.glob("src.*") if p.suffix in (".mp4", ".mkv", ".webm")]
    if not files:
        raise RuntimeError("MISSING_SOURCE: section download produced no file")
    return files[0]


# ---------------------------------------------------------------- speech
def transcribe(src: Path, wd: Path) -> tuple[list[dict], str]:
    wav = wd / "audio16k.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)])
    from faster_whisper import WhisperModel  # imported here so tests can run without it
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav), language="en", word_timestamps=True, vad_filter=True,
                                       condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            txt = w.word.strip()
            if txt:
                words.append({"start": float(w.start), "end": float(w.end), "text": txt, "p": float(w.probability)})
    return words, " ".join(w["text"] for w in words)


# ---------------------------------------------------------------- subtitles
def ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass_text(s: str) -> str:
    return s.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def chunk_words(words: list[dict], max_words: int = 3, max_len: float = 1.4) -> list[dict]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["end"] - cur[0]["start"] > max_len
                    or re.search(r"[.!?,]$", cur[-1]["text"])):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        start = c[0]["start"]
        end = c[-1]["end"] + 0.15
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0]["start"])
        end = max(end, start + 0.35)
        text = " ".join(x["text"] for x in c)
        text = re.sub(r"[,.]+$", "", text)
        out.append({"start": start, "end": end, "text": text.upper()})
    return out


def build_ass(words: list[dict], duration: float, hook: str, cta_lines: list[str], tag: str,
              fg_bottom: int) -> str:
    sub_y = min(H - 260, fg_bottom + 230)
    hook_end = min(3.6, duration * 0.4)
    cta_start = max(hook_end + 1.0, duration - 3.2)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{FONT},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,18,0,5,70,70,0,1
Style: Sub,{FONT},82,&H00FFFFFF,&H0000E6FF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,7,3,5,60,60,0,1
Style: Tag,{FONT},44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,1,0,1,4,0,5,60,60,0,1
Style: CTA,{FONT},66,&H0000E6FF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,18,0,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    top_y = 330
    if hook:
        ev.append(f"Dialogue: 2,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{{\\pos({W // 2},{top_y})\\fad(0,200)}}{ass_text(hook)}")
    ev.append(f"Dialogue: 1,{ass_time(hook_end)},{ass_time(cta_start)},Tag,,0,0,0,,{{\\pos({W // 2},{top_y + 120})\\fad(250,150)}}{ass_text(tag)}")
    cta = "\\N".join(ass_text(x) for x in cta_lines)
    ev.append(f"Dialogue: 2,{ass_time(cta_start)},{ass_time(duration)},CTA,,0,0,0,,{{\\pos({W // 2},{top_y})\\fad(200,0)}}{cta}")
    for c in chunk_words(words):
        if c["start"] >= duration:
            continue
        ev.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(min(c['end'], duration))},Sub,,0,0,0,,"
                  f"{{\\pos({W // 2},{sub_y})\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}}{ass_text(c['text'])}")
    return head + "\n".join(ev) + "\n"


def write_srt(words: list[dict], path: Path) -> None:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"
    lines = []
    for i, c in enumerate(chunk_words(words, max_words=6, max_len=2.5), 1):
        lines += [str(i), f"{ts(c['start'])} --> {ts(c['end'])}", c["text"].capitalize(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- video
def layout_filter(layout: str, src_w: int, src_h: int) -> tuple[str, int]:
    """Return (filter for the foreground, bottom y of the foreground). Never stretches."""
    if layout == "zoom":   # crop the middle 4:3 of a 16:9 frame -> bigger action, loses the far edges
        fg = "crop=ih*4/3:ih,scale=1080:-2:flags=lanczos"
        fg_h = 810
    else:                  # full frame, nothing lost
        fg = "scale=1080:-2:flags=lanczos"
        fg_h = int(round(1080 * src_h / max(1, src_w) / 2) * 2)
    return fg, (H + fg_h) // 2


def render_clip(src: Path, ass: Path, layout: str, out: Path) -> None:
    info = ffprobe(src)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    fg, _ = layout_filter(layout, int(v["width"]), int(v["height"]))
    fontsdir = os.environ.get("CLIP_FONTS_DIR", "/usr/share/fonts")
    graph = (f"[0:v]split=2[a][b];"
             f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,"
             f"eq=brightness=-0.12:saturation=1.1[bg];"
             f"[b]{fg}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
             f"ass={ass}:fontsdir={fontsdir},format=yuv420p[v]")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", graph, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "veryfast"), "-crf", "20",
            "-r", "30", "-movflags", "+faststart", str(out)]
    run(cmd)


def qc(path: Path, min_s: float, max_s: float, words: list[dict]) -> dict:
    info = ffprobe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    vol = run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"]).stderr
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", vol)
    mean_db = float(m.group(1)) if m else -99.0
    problems = []
    if (v.get("width"), v.get("height")) != (W, H):
        problems.append(f"size {v.get('width')}x{v.get('height')}")
    if not a:
        problems.append("no audio")
    elif mean_db < -40:
        problems.append(f"very quiet audio ({mean_db} dB)")
    if not (min_s - 1 <= dur <= max_s + 1):
        problems.append(f"duration {dur:.1f}s outside {min_s}-{max_s}s")
    if len(words) < 4:
        problems.append("little or no speech: subtitles are sparse, check the clip still reads without sound")
    return {"pass": not [p for p in problems if not p.startswith("little")], "problems": problems,
            "duration": round(dur, 2), "width": v.get("width"), "height": v.get("height"),
            "mean_volume_db": mean_db, "size_mb": round(path.stat().st_size / 1e6, 2), "subtitle_words": len(words)}


# ---------------------------------------------------------------- main
def overlaps(index: dict, video_id: str, s: float, e: float) -> str | None:
    for cid, r in index.items():
        if r.get("video_id") == video_id and r.get("status") == "rendered":
            o = min(e, r["end"]) - max(s, r["start"])
            if o > 0.5 * min(e - s, r["end"] - r["start"]):
                return cid
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("request")
    ap.add_argument("--release-base", default="", help="URL prefix where output files will be published")
    ap.add_argument("--words-json", help="TEST ONLY: use these words instead of running Whisper")
    ap.add_argument("--source-file", help="TEST ONLY: use this local file instead of downloading")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    req = json.loads(Path(a.request).read_text(encoding="utf-8"))
    camp = approved_campaign(req["campaign"])
    pk, cc = camp["packaging"], camp["clip"]
    index = read_json(RENDER_INDEX, {})
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for c in req["clips"]:
        cid = c["clip_id"]
        res = {"clip_id": cid, "video_id": c["video_id"], "start": c["start"], "end": c["end"],
               "hook": c.get("hook", ""), "layout": c.get("layout", "blur")}
        try:
            if not a.force:
                if index.get(cid, {}).get("status") == "rendered":
                    raise RuntimeError("DUPLICATE: clip_id already rendered")
                dup = overlaps(index, c["video_id"], c["start"], c["end"])
                if dup:
                    raise RuntimeError(f"DUPLICATE: overlaps already rendered clip {dup}")
            length = c["end"] - c["start"]
            if not (cc["min_seconds"] - 1 <= length <= cc["max_seconds"] + 1):
                raise RuntimeError(f"BAD_LENGTH: {length:.1f}s")
            t0 = time.time()
            wd = WORK / "render" / cid
            wd.mkdir(parents=True, exist_ok=True)
            src = Path(a.source_file) if a.source_file else download_section(c["video_id"], c["start"], c["end"], wd)
            info = ffprobe(src)
            dur = float(info["format"]["duration"])
            if a.words_json:
                words = json.loads(Path(a.words_json).read_text())
                text = " ".join(w["text"] for w in words)
            else:
                words, text = transcribe(src, wd)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            _, fg_bottom = layout_filter(res["layout"], int(v["width"]), int(v["height"]))
            tag = f"{pk['creator_name'].upper()}  |  {pk['creator_handle']}"
            ass = wd / "clip.ass"
            ass.write_text(build_ass(words, dur, c.get("hook", ""), pk["cta_lines"], tag, fg_bottom), encoding="utf-8")
            mp4 = OUT / f"{cid}.mp4"
            render_clip(src, ass, res["layout"], mp4)
            cover = OUT / f"{cid}.jpg"
            run(["ffmpeg", "-y", "-v", "error", "-ss", "1.2", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(cover)])
            srt = OUT / f"{cid}.srt"
            write_srt(words, srt)
            q = qc(mp4, cc["min_seconds"], cc["max_seconds"], words)
            base = a.release_base.rstrip("/") + "/" if a.release_base else ""
            res.update({"status": "rendered" if q["pass"] else "failed_qc", "qc": q, "transcript": text,
                        "files": {k: base + p.name for k, p in (("video", mp4), ("cover", cover), ("srt", srt))},
                        "source_url": f"https://www.youtube.com/watch?v={c['video_id']}&t={int(c['start'])}s",
                        "render_seconds": round(time.time() - t0, 1),
                        "rendered_at": time.strftime("%Y-%m-%d %H:%M:%S")})
            if not a.source_file:
                shutil.rmtree(wd, ignore_errors=True)
            log(f"{cid}: {res['status']} {q}")
        except Exception as e:
            res.update({"status": "error", "error": str(e)[:800]})
            log(f"{cid}: ERROR {e}")
        results.append(res)
        if res["status"] in ("rendered", "failed_qc"):
            index[cid] = {k: res[k] for k in ("video_id", "start", "end", "status")} | {"request_id": req["request_id"]}
    write_json(RENDER_INDEX, index)
    summary = {"request_id": req["request_id"], "campaign": req["campaign"], "results": results,
               "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    write_json(DATA / "rendered" / f"{req['request_id']}.json", summary)
    log(f"Done: {sum(r['status'] == 'rendered' for r in results)}/{len(results)} rendered")


if __name__ == "__main__":
    main()
