"""Shared helpers: paths, config, JSON state, and yt-dlp calls."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "campaigns.yaml"
DATA = ROOT / "data"
STATE = ROOT / "state"
WORK = Path(os.environ.get("CLIP_WORK_DIR", ROOT / "work"))
OUT = Path(os.environ.get("CLIP_OUT_DIR", ROOT / "out"))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_campaigns() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)["campaigns"]


def approved_campaign(key: str) -> dict:
    camps = load_campaigns()
    if key not in camps:
        sys.exit(f"Unknown campaign: {key}")
    camp = camps[key]
    if camp.get("status") != "approved":
        sys.exit(f"Campaign {key} is not approved (status={camp.get('status')}); refusing to process it.")
    return camp


def read_json(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def cookies_args() -> list[str]:
    """Use a cookies file if one was provided (GitHub secret YT_COOKIES), to get past YouTube bot checks."""
    path = os.environ.get("YT_COOKIES_FILE")
    if path and Path(path).exists() and Path(path).stat().st_size > 0:
        return ["--cookies", path]
    return []


def ytdlp(args: list[str], retries: int = 3, capture: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run yt-dlp with retries for temporary failures. Raises RuntimeError on final failure."""
    exe = shutil.which("yt-dlp") or "yt-dlp"
    cmd = [exe, "--retries", "5", "--fragment-retries", "10", *cookies_args(), *args]
    last = None
    for attempt in range(1, retries + 1):
        try:
            res = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"TIMEOUT: yt-dlp took longer than {timeout}s")
        if res.returncode == 0:
            return res
        last = res
        err = (res.stderr or "")[-600:]
        if "Sign in to confirm" in err or "not a bot" in err:
            raise RuntimeError("YOUTUBE_BOT_CHECK: YouTube asked to confirm we are not a bot. "
                               "Add a cookies file as the YT_COOKIES secret.\n" + err)
        if "Private video" in err or "members-only" in err or "This live event will begin" in err:
            raise RuntimeError("SOURCE_UNAVAILABLE: " + err)
        warn = [l for l in err.splitlines() if "WARNING" in l][-3:]
        log(f"yt-dlp failed (attempt {attempt}/{retries}): {err.strip().splitlines()[-1] if err.strip() else 'no output'}"
            + ("\n  " + "\n  ".join(w[:250] for w in warn) if warn else ""))
        time.sleep(5 * attempt)
    raise RuntimeError("YTDLP_FAILED: " + ((last.stderr or "")[-1500:] if last else ""))


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd[:4])} ...\n{res.stderr[-2000:]}")
    return res


def ffprobe(path: Path) -> dict:
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(res.stdout)
