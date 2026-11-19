"""Find new approved source videos and score them for clip-worthy moments.

Signals (combined, so silent visual moments are not missed when chat reacts):
  * live-chat replay rate and laugh/hype reactions (livestreams only)
  * audio loudness spikes relative to the surrounding minute
  * hype words in YouTube's auto-captions

Only small files are downloaded here: captions, chat replay and a low-bitrate audio track.
The video itself is never downloaded in full; render.py fetches just the chosen minutes.

Usage:
  python -m engine.scan --campaign tomo_gta6                 # discover and scan new sources
  python -m engine.scan --campaign tomo_gta6 --video <id|url> [--force]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from engine.common import (DATA, STATE, WORK, approved_campaign, log, read_json, run, write_json, ytdlp)

HYPE_WORDS = [
    "oh my god", "no way", "what the", "let's go", "lets go", "holy", "bro", "dude", "yo", "wait",
    "run", "help", "dead", "died", "crazy", "insane", "what", "why", "how", "nah", "stop", "go go",
    "laughter", "haha", "hahaha", "oh no", "omg", "wow", "yes",
]
CHAT_LAUGH = re.compile(r"(\blol\b|\blmao+\b|\blmfao\b|kekw|\blul\b|omegalul|😂|🤣|💀|\bw+\b|\bhaha+\b|\bclip it\b|\bclip\b)", re.I)

SOURCES_STATE = STATE / "processed_sources.json"


def vid_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s


# ---------------------------------------------------------------- discovery
def discover(camp: dict) -> list[dict]:
    src = camp["source"]
    pats = [re.compile(p, re.I) for p in src["title_patterns"]]
    after = src.get("published_after", "1970-01-01").replace("-", "")
    found: dict[str, dict] = {}
    for tab in src.get("tabs", ["streams"]):
        url = src["channel_url"].rstrip("/") + "/" + tab
        try:
            res = ytdlp(["--flat-playlist", "-J", "--playlist-end", "20", url])
        except RuntimeError as e:
            log(f"Could not list {url}: {str(e)[:300]}")
            if "YOUTUBE_BOT_CHECK" in str(e):
                raise
            continue
        for e in json.loads(res.stdout).get("entries") or []:
            title = e.get("title") or ""
            if e.get("id") and any(p.search(title) for p in pats):
                found.setdefault(e["id"], {"id": e["id"], "title": title, "tab": tab})
    out = []
    for v in found.values():
        try:
            meta = video_meta(v["id"])
        except RuntimeError as e:
            if "YOUTUBE_BOT_CHECK" in str(e):
                raise
            log(f"Skip {v['id']} ({v['title'][:50]}): {str(e).splitlines()[-1][:150]}")
            continue  # upcoming, private or members-only: not usable (yet)
        if meta.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            log(f"Skip {v['id']} ({meta.get('live_status')}): VOD not ready yet")
            continue
        if (meta.get("upload_date") or "0") < after:
            continue
        if meta.get("availability") not in (None, "public", "unlisted"):
            continue
        out.append({**v, **meta})
    out.sort(key=lambda m: m.get("upload_date") or "", reverse=True)
    return out


def video_meta(video: str) -> dict:
    res = ytdlp(["-J", "--skip-download", f"https://www.youtube.com/watch?v={vid_id(video)}"])
    j = json.loads(res.stdout)
    return {
        "id": j["id"], "title": j.get("title"), "url": j.get("webpage_url"),
        "channel": j.get("channel"), "channel_url": j.get("channel_url"),
        "duration": j.get("duration") or 0, "upload_date": j.get("upload_date"),
        "live_status": j.get("live_status"), "availability": j.get("availability"),
        "view_count": j.get("view_count"), "width": j.get("width"), "height": j.get("height"),
    }


# ---------------------------------------------------------------- signals
def fetch_signals(video_id: str, wd: Path) -> dict:
    wd.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    # captions (auto or manual, English) as json3
    try:
        ytdlp(["--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
               "--sub-format", "json3", "-o", str(wd / "cap"), url])
    except RuntimeError as e:
        log(f"No captions: {str(e)[:200]}")
    # live chat replay
    try:
        ytdlp(["--skip-download", "--write-subs", "--sub-langs", "live_chat", "-o", str(wd / "chat"), url], retries=2)
    except RuntimeError as e:
        log(f"No chat replay: {str(e)[:200]}")
    # low bitrate audio only
    ytdlp(["-f", "worstaudio[abr>=30]/worstaudio/bestaudio", "-o", str(wd / "audio.%(ext)s"), url])
    return {
        "captions": next(iter(sorted(wd.glob("cap*.json3"))), None),
        "chat": next(iter(sorted(wd.glob("chat*.live_chat.json"))), None),
        "audio": next(iter(sorted(p for p in wd.glob("audio.*") if not p.name.endswith(".part"))), None),
    }


def parse_captions(path: Path | None) -> tuple[list[dict], list[dict]]:
    """Return (words, cues). words: {t, text}; cues: {start, end, text}."""
    if not path:
        return [], []
    j = json.loads(path.read_text(encoding="utf-8"))
    words, cues = [], []
    for ev in j.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        cues.append({"start": t0, "end": t0 + dur, "text": text})
        for s in segs:
            w = s.get("utf8", "").strip()
            if w:
                words.append({"t": t0 + s.get("tOffsetMs", 0) / 1000, "text": w})
    return words, cues


def parse_chat(path: Path | None) -> list[dict]:
    if not path:
        return []
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            rep = j.get("replayChatItemAction", {})
            t = int(rep.get("videoOffsetTimeMsec", -1)) / 1000
            if t < 0:
                continue
            for act in rep.get("actions", []):
                item = act.get("addChatItemAction", {}).get("item", {})
                r = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if not r:
                    continue
                runs = r.get("message", {}).get("runs", [])
                text = "".join(x.get("text") or x.get("emoji", {}).get("shortcuts", [""])[0] for x in runs)
                msgs.append({"t": t, "text": text})
    return msgs


def audio_rms_per_second(path: Path, duration: int) -> list[float]:
    meta = path.with_suffix(".rms.txt")
    run(["ffmpeg", "-v", "error", "-i", str(path), "-af",
         "aresample=8000,asetnsamples=n=8000:p=0,astats=metadata=1:reset=1,"
         f"ametadata=print:key=lavfi.astats.Overall.RMS_level:file={meta}", "-f", "null", "-"])
    vals = []
    for line in meta.read_text().splitlines():
        if "RMS_level=" in line:
            v = line.split("=", 1)[1]
            vals.append(-90.0 if v in ("-inf", "inf", "nan") else max(-90.0, float(v)))
    if len(vals) < duration:
        vals += [-90.0] * (duration - len(vals))
    return vals[:duration]


# ---------------------------------------------------------------- scoring
SPAM = re.compile(r"(how do i clip|can i clip|shout ?out|hello|^hi\b|^hey\b|^yo+\b|first|subscribe|sub to)", re.I)


def dedupe_chat(chat: list[dict]) -> list[dict]:
    """Drop greetings/requests and the same message repeated within 30 seconds (spam)."""
    last: dict[str, float] = {}
    out = []
    for m in sorted(chat, key=lambda x: x["t"]):
        key = re.sub(r"\W+", "", m["text"].lower())[:40]
        if not key or SPAM.search(m["text"].strip()):
            continue
        if key in last and m["t"] - last[key] < 30:
            continue
        last[key] = m["t"]
        out.append(m)
    return out

def per_second(events: list[float], n: int) -> list[float]:
    arr = [0.0] * n
    for t in events:
        i = int(t)
        if 0 <= i < n:
            arr[i] += 1
    return arr


def smooth(a: list[float], w: int) -> list[float]:
    if w <= 1 or not a:
        return a[:]
    out, s, h = [], 0.0, w // 2
    pre = [0.0]
    for x in a:
        s += x
        pre.append(s)
    for i in range(len(a)):
        lo, hi = max(0, i - h), min(len(a), i + h + 1)
        out.append((pre[hi] - pre[lo]) / (hi - lo))
    return out


def robust_z(a: list[float]) -> list[float]:
    if not a:
        return a
    med = statistics.median(a)
    mad = statistics.median([abs(x - med) for x in a])
    # sparse series (mostly zeros) have MAD 0; fall back to the spread so one stray "lol" doesn't max out
    scale = max(1.4826 * mad, 0.5 * statistics.pstdev(a), 1e-3)
    return [max(-3.0, min(6.0, (x - med) / scale)) for x in a]


def local_spike(a: list[float], short: int = 3, long: int = 61) -> list[float]:
    """Loudness relative to the surrounding minute, so a loud streamer is not always 'exciting'."""
    s, l = smooth(a, short), smooth(a, long)
    return [x - y for x, y in zip(s, l)]


def score_video(duration: int, words: list[dict], chat: list[dict], rms: list[float]) -> tuple[list[float], dict]:
    n = max(1, int(duration))
    kw_times = []
    joined = [(w["t"], w["text"].lower()) for w in words]
    for i, (t, w) in enumerate(joined):
        tri = " ".join(x[1] for x in joined[i:i + 3])
        if any(tri.startswith(h) for h in HYPE_WORDS) or "[laughter]" in w or "[laughs]" in w:
            kw_times.append(t)
    kw = robust_z(smooth(per_second(kw_times, n), 7))
    aud = robust_z(local_spike(rms)) if rms else [0.0] * n
    # many speaker changes (">>") in a row usually means a story cutscene, not the streamer reacting
    turns = robust_z(smooth(per_second([w["t"] for w in words if w["text"].startswith(">>")], n), 21))
    chat = dedupe_chat(chat)
    have_chat = len(chat) > 50
    if have_chat:
        # chat reacts a few seconds after the moment happens, so move chat signals ~6s earlier
        lag = 6
        rate = robust_z(smooth(per_second([m["t"] - lag for m in chat], n), 7))
        laugh = robust_z(smooth(per_second([m["t"] - lag for m in chat if CHAT_LAUGH.search(m["text"])], n), 7))
        weights = {"chat": 0.15, "chat_laugh": 0.30, "audio": 0.35, "words": 0.20, "cutscene": -0.15}
        comb = [weights["chat"] * c + weights["chat_laugh"] * l + weights["audio"] * a + weights["words"] * k
                + weights["cutscene"] * max(0.0, t) for c, l, a, k, t in zip(rate, laugh, aud, kw, turns)]
    else:
        rate = laugh = [0.0] * n
        weights = {"audio": 0.55, "words": 0.45, "cutscene": -0.15}
        comb = [weights["audio"] * a + weights["words"] * k + weights["cutscene"] * max(0.0, t)
                for a, k, t in zip(aud, kw, turns)]
    return smooth(comb, 9), {"weights": weights, "have_chat": have_chat,
                              "series": {"chat": rate, "chat_laugh": laugh, "audio": aud, "words": kw, "cutscene": turns}}


def pick_windows(score: list[float], cues: list[dict], camp_clip: dict, duration: int) -> list[dict]:
    lo_bound = camp_clip.get("skip_start_seconds", 0)
    hi_bound = max(lo_bound + 60, duration - camp_clip.get("skip_end_seconds", 0))
    target = camp_clip.get("target_seconds", 32)
    mn, mx = camp_clip.get("min_seconds", 20), camp_clip.get("max_seconds", 45)
    gap = camp_clip.get("min_gap_seconds", 90)
    order = sorted(range(lo_bound, min(hi_bound, len(score))), key=lambda i: score[i], reverse=True)
    peaks: list[int] = []
    for i in order:
        if all(abs(i - p) >= gap for p in peaks):
            peaks.append(i)
        if len(peaks) >= camp_clip.get("candidates_per_source", 6):
            break
    starts = sorted(c["start"] for c in cues)
    ends = sorted(c["end"] for c in cues)

    def snap(t: float, arr: list[float], lo: float, hi: float) -> float:
        best = [x for x in arr if lo <= x <= hi]
        return min(best, key=lambda x: abs(x - t)) if best else t

    out = []
    for p in peaks:
        s = p - target * 0.65
        e = s + target
        s = snap(s, starts, s - 4, s + 3)
        e = snap(e, ends, e - 3, e + 6)
        s, e = max(lo_bound, s), min(hi_bound, e)
        if e - s < mn:
            e = min(hi_bound, s + mn)
        if e - s > mx:
            e = s + mx
        out.append({"peak": p, "start": round(s, 2), "end": round(e, 2), "score": round(score[p], 3)})
    return out


def describe(win: dict, words: list[dict], chat: list[dict], series: dict) -> dict:
    s, e = win["start"], win["end"]
    text = " ".join(w["text"] for w in words if s <= w["t"] <= e)
    ctx_before = " ".join(w["text"] for w in words if s - 20 <= w["t"] < s)
    msgs = [m["text"] for m in chat if s <= m["t"] <= e + 8 and m["text"].strip()]
    p = win["peak"]
    sig = {k: round(v[p], 2) for k, v in series.items() if v and p < len(v)}
    return {**win, "transcript": text, "context_before": ctx_before[-300:],
            "chat_sample": msgs[:25], "chat_messages": len(msgs), "signals_at_peak": sig}


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# ---------------------------------------------------------------- main
def scan_one(camp_key: str, camp: dict, meta: dict) -> Path:
    vid = meta["id"]
    wd = WORK / "scan" / vid
    t0 = time.time()
    log(f"Scanning {vid}: {meta.get('title')} ({fmt_ts(meta.get('duration', 0))})")
    files = fetch_signals(vid, wd)
    words, cues = parse_captions(files["captions"])
    chat = parse_chat(files["chat"])
    duration = int(meta.get("duration") or (cues[-1]["end"] if cues else 0))
    rms = audio_rms_per_second(files["audio"], duration) if files["audio"] else []
    score, extra = score_video(duration, words, chat, rms)
    wins = pick_windows(score, cues, camp["clip"], duration)
    cands = []
    for rank, w in enumerate(wins, 1):
        d = describe(w, words, chat, extra["series"])
        d["rank"] = rank
        d["candidate_id"] = f"{vid}_{int(d['start'])}"
        d["timestamp_url"] = f"https://www.youtube.com/watch?v={vid}&t={int(d['start'])}s"
        d["label"] = f"{fmt_ts(d['start'])}-{fmt_ts(d['end'])}"
        cands.append(d)
    result = {
        "campaign": camp_key, "source": meta, "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signals_used": {"captions": bool(words), "chat_replay": extra["have_chat"], "audio": bool(rms),
                         "visual_analysis": False},
        "weights": extra["weights"], "candidates": cands,
        "notes": "visual_analysis is false: moments are found from chat, audio and speech; frames are checked at render time.",
    }
    path = DATA / "candidates" / camp_key / f"{vid}.json"
    write_json(path, result)
    if cues:
        tpath = DATA / "transcripts" / camp_key / f"{vid}.txt"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        lines, cur_t, cur = [], None, []
        for c in cues:
            if cur_t is None:
                cur_t = c["start"]
            cur.append(c["text"].replace("\n", " "))
            if c["end"] - cur_t >= 10:
                lines.append(f"[{fmt_ts(cur_t)}] {' '.join(cur)}")
                cur_t, cur = None, []
        if cur:
            lines.append(f"[{fmt_ts(cur_t)}] {' '.join(cur)}")
        tpath.write_text(f"# {meta.get('title')} ({meta.get('url')})\n" + "\n".join(lines) + "\n", encoding="utf-8")
    shutil.rmtree(wd, ignore_errors=True)
    log(f"Wrote {len(cands)} candidates to {path.relative_to(path.parents[3])} in {time.time() - t0:.0f}s")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--video", help="scan this video id or URL instead of discovering")
    ap.add_argument("--force", action="store_true", help="rescan even if already processed")
    a = ap.parse_args()
    camp = approved_campaign(a.campaign)
    state = read_json(SOURCES_STATE, {})
    if a.video:
        metas = [video_meta(a.video)]
    else:
        metas = discover(camp)
        log(f"Found {len(metas)} matching sources: {[m['id'] for m in metas]}")
    done = 0
    for m in metas:
        key = f"{a.campaign}:{m['id']}"
        prev = state.get(key, {})
        if not a.force and (prev.get("status") == "scanned" or prev.get("attempts", 0) >= 3):
            continue  # already done, or failed 3 times (needs a manual look)
        if done >= camp["source"].get("max_sources_per_scan", 3):
            break
        try:
            path = scan_one(a.campaign, camp, m)
            state[key] = {"status": "scanned", "title": m.get("title"), "at": time.strftime("%Y-%m-%d %H:%M"),
                          "candidates_file": str(path.relative_to(DATA.parent))}
            done += 1
        except Exception as e:  # record and continue with the next source
            log(f"ERROR scanning {m['id']}: {e}")
            prev = state.get(key, {})
            state[key] = {"status": "error", "title": m.get("title"), "error": str(e)[:500],
                          "attempts": prev.get("attempts", 0) + 1, "at": time.strftime("%Y-%m-%d %H:%M")}
            if "YOUTUBE_BOT_CHECK" in str(e):
                write_json(SOURCES_STATE, state)
                raise
        write_json(SOURCES_STATE, state)
    log(f"Scanned {done} new source(s).")


if __name__ == "__main__":
    main()
