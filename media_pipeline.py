#!/usr/bin/env python3
"""
media_pipeline.py
Automated Termux Video Ingestion & Streaming Pipeline with Live Real-time Logging.
Features:
- 100% Automated Tag & Description extraction:
  * Pulls video tags, categories, hashtags (#...), artist/album details from YouTube/Instagram.
  * Preserves full rich description automatically without manual typing.
  * Auto-recommends matching storage profile (e.g. Entertainment for music/songs, Tutorials for tech).
- Live real-time streaming logs for yt-dlp, FFmpeg, and upload processes.
- Dual persistent log saving to ~/.akash_media.log.
- Dual-database classification:
  * Shorts (<= 120s) -> Auto-creator verification/registration -> shorts.db -> Instagram Reels player
  * Long Videos (> 120s) -> Categorized Profile & Tag storage -> long_videos.db -> YouTube player
"""

import os
import sys
import re
import time
import json
import shutil
import subprocess
import datetime
import urllib.parse
from typing import Optional, Tuple, List, Dict, Any
import requests

# ─── Terminal Colors ─────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_GRAY = "\033[90m"

SERVER_BASE_URL = os.getenv("AKASH_SERVER_URL", os.getenv("DEVOS_SERVER_URL", "https://akashbox.duckdns.org"))
API_KEY = os.getenv("AKASH_API_KEY", os.getenv("DEVOS_API_KEY", "9c9cdbe35d8309877d3bbd4d568a03e2404c59675bccbe1d6d137c9f2f64f969"))

# 4 High-Secured Application Tokens
AKASH_UPLOAD_TOKEN = os.getenv("AKASH_UPLOAD_TOKEN", os.getenv("DEVOS_UPLOAD_TOKEN", "akash_sec_upload_74b53a981ae0b5bfea6b195668b43ee92ae574fd37754124"))
AKASH_RETRIEVE_TOKEN = os.getenv("AKASH_RETRIEVE_TOKEN", os.getenv("DEVOS_RETRIEVE_TOKEN", "akash_sec_retrieve_d7bec7b9a242cac702f89c2f9d1f1cc079e7add94580aead"))

# Dynamically load from ~/.akash_app_tokens.json or ~/.devos_app_tokens.json if present
for tok_cand in [os.path.expanduser("~/.akash_app_tokens.json"), os.path.expanduser("~/.devos_app_tokens.json")]:
    if os.path.exists(tok_cand):
        try:
            with open(tok_cand, "r") as tf:
                tok_map = json.load(tf).get("tokens", {})
                for t_val, t_meta in tok_map.items():
                    if t_meta.get("role") == "upload":
                        AKASH_UPLOAD_TOKEN = t_val
                    elif t_meta.get("role") == "retrieve":
                        AKASH_RETRIEVE_TOKEN = t_val
            break
        except Exception:
            pass

HEADERS = {
    "x-api-key": API_KEY,
    "X-App-Token": AKASH_UPLOAD_TOKEN,
    "Authorization": f"Bearer {AKASH_UPLOAD_TOKEN}"
}
HEADERS_RETRIEVE = {
    "x-api-key": API_KEY,
    "X-App-Token": AKASH_RETRIEVE_TOKEN,
    "Authorization": f"Bearer {AKASH_RETRIEVE_TOKEN}"
}

# Obfuscated Route Slugs
ROUTE_UPLOAD = "/_/9a4f2b"
ROUTE_RETRIEVE = "/_/3c7e1a"
ROUTE_STREAM = "/_/8b0d4f"
ROUTE_LIST = "/_/2b8e6c"
ROUTE_PLAYER = "/_/p7f1"
ROUTE_SHORTS_FEED = "/_/s7a1"
ROUTE_LONG_FEED = "/_/l3b9"
ROUTE_FEED = "/_/l3b9"

LOG_DIR = os.path.expanduser("~")
LOG_FILE = os.path.join(LOG_DIR, ".akash_media.log")


# ─── Live Logger & Log File Persistence ───────────────────────────────────────

class PipelineLogger:
    """Handles formatted console logs and writes plain timestamped logs to file."""

    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    @classmethod
    def log(cls, message: str, level: str = "INFO", color: str = C_RESET):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [{level}] "

        # Terminal colored output
        print(f"{color}{message}{C_RESET}", flush=True)

        # File output (strip ANSI escape sequences)
        try:
            clean_msg = cls.ANSI_ESCAPE.sub('', message)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{prefix}{clean_msg}\n")
        except Exception:
            pass

    @classmethod
    def info(cls, msg: str):
        cls.log(msg, level="INFO", color=C_RESET)

    @classmethod
    def success(cls, msg: str):
        cls.log(f"[OK] {msg}", level="SUCCESS", color=C_GREEN)

    @classmethod
    def warn(cls, msg: str):
        cls.log(f"[WARN] {msg}", level="WARN", color=C_YELLOW)

    @classmethod
    def error(cls, msg: str):
        cls.log(f"[ERROR] {msg}", level="ERROR", color=C_RED)

    @classmethod
    def live_exec(cls, cmd: List[str], desc: str = "") -> int:
        """
        Executes a command and streams its output live to terminal and log file.
        Used for yt-dlp downloads, ffmpeg transcoding, and shell tasks.
        """
        if desc:
            cls.log(f"\n{C_CYAN}> {desc}{C_RESET}", level="EXEC")

        cmd_str = " ".join(cmd)
        cls.log(f"[CMD] {cmd_str}", level="EXEC_START")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        for line in process.stdout:
            line_str = line.rstrip()
            if not line_str:
                continue

            # Check if it's a download percentage line (update in place or print)
            if "[download]" in line_str or "frame=" in line_str:
                # Live dynamic progress line
                sys.stdout.write(f"\r{C_GRAY}{line_str[:90]}{C_RESET}")
                sys.stdout.flush()
            else:
                print(f"{C_GRAY}  │ {line_str}{C_RESET}", flush=True)

            # Persist to log file
            clean_line = cls.ANSI_ESCAPE.sub('', line_str)
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {clean_line}\n")
            except Exception:
                pass

        process.wait()
        sys.stdout.write("\n")
        sys.stdout.flush()

        cls.log(f"[CMD_FINISH] Exit code: {process.returncode}", level="EXEC_END")
        return process.returncode


def print_banner():
    banner = f"""
{C_CYAN}╔════════════════════════════════════════════════════════════╗
║          AKASH SMART MEDIA STREAMING PIPELINE            ║
║       YouTube & Instagram -> Shorts & Long Video Hub       ║
╚════════════════════════════════════════════════════════════╝{C_RESET}
"""
    print(banner, flush=True)


def send_toast(message: str):
    """Triggers Android system toast notification if termux-api is available."""
    try:
        subprocess.run(["termux-toast", message], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower:
        return "instagram"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    return "web"


# ─── Clean Author & Classification Helpers ────────────────────────────────────

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50\u2b55\u2934\u2935]|[\ufe00-\ufe0f]|[\u200d]|[\u20a0-\u20cf]",
    re.UNICODE
)

def strip_emojis(text: Optional[str]) -> str:
    """Strips all emoji icons and supplementary unicode symbols from strings."""
    if not text:
        return ""
    cleaned = EMOJI_PATTERN.sub("", str(text))
    return re.sub(r"\s+", " ", cleaned).strip()

def extract_clean_author_handle(meta: dict, platform: str) -> Tuple[str, str]:
    """
    Extracts (clean_username_handle, display_name) with special handling for Instagram, YouTube, TikTok.
    Guarantees clean handles (e.g. mirmehdi.seyidzada) without bio titles or pipe characters or emojis.
    """
    title = strip_emojis(meta.get("title") or "")
    uploader_id = strip_emojis(meta.get("uploader_id") or "")
    uploader = strip_emojis(meta.get("uploader") or "")
    channel = strip_emojis(meta.get("channel") or "")

    clean_handle = ""
    # Clean display name: remove pipe/dash bio clutter
    raw_display = uploader or channel or uploader_id or "creator"
    display_name = strip_emojis(raw_display.split("|")[0].split(" - ")[0].strip())

    if platform == "instagram":
        # 1. Look for 'Video by <username>' in title
        m = re.search(r'Video by ([a-zA-Z0-9._]+)', title, re.IGNORECASE)
        if m:
            clean_handle = m.group(1).lower().strip()
        # 2. Check uploader_id if clean alphanumeric
        elif uploader_id and re.match(r'^[a-zA-Z0-9._]+$', uploader_id):
            clean_handle = uploader_id.lower().strip()
        # 3. Check channel if clean alphanumeric
        elif channel and re.match(r'^[a-zA-Z0-9._]+$', channel):
            clean_handle = channel.lower().strip()
        else:
            first_part = uploader.split("|")[0].split("-")[0].strip()
            clean_handle = re.sub(r'[^a-zA-Z0-9._]', '', first_part).lower()

    if not clean_handle:
        candidate = uploader_id or channel or uploader
        clean_handle = candidate.split("|")[0].split("-")[0].strip()
        clean_handle = clean_handle.lstrip("@").replace(" ", "_").lower()
        clean_handle = re.sub(r'[^a-zA-Z0-9._]', '', clean_handle)

    if not clean_handle:
        clean_handle = "creator"

    if not display_name:
        display_name = clean_handle

    display_name = strip_emojis(display_name) or clean_handle

    return clean_handle, display_name


def is_short_media(meta: dict, url: str, platform: str) -> Tuple[bool, str]:
    """
    Determines whether a media file is a Short / Reel or a Long Video.
    If duration is undetected or missing, checks platform:
    Instagram, TikTok, and YouTube Shorts URLs are ALWAYS auto-assigned as Shorts.
    """
    duration = float(meta.get("duration") or 0.0)
    url_lower = url.lower()

    # Rule 1: Instagram (always Short/Reel unless duration explicitly > 120s)
    # Instagram Reels have a hard 90s limit. If duration is undetected, auto-classify as Reel.
    if platform == "instagram" or "instagram.com" in url_lower:
        if duration <= 120.0:
            dur_text = f"duration {duration:.1f}s" if duration > 0 else "duration undetected on Instagram, auto-classified as Reel"
            return True, f"Instagram source ({dur_text})"

    # Rule 2: YouTube Shorts URL
    if "/shorts/" in url_lower:
        return True, "YouTube Shorts URL detected (/shorts/...)"

    # Rule 3: TikTok
    if platform == "tiktok" or "tiktok.com" in url_lower:
        return True, "TikTok short format detected"

    # Rule 4: Explicit valid duration <= 120s
    if 0.0 < duration <= 120.0:
        return True, f"Detected duration {duration:.1f}s <= 120s"

    # Rule 5: Missing or 0 duration on other sources
    if duration <= 0.0:
        # Check aspect ratio if available
        w = meta.get("width") or 0
        h = meta.get("height") or 0
        if h > w and w > 0:
            return True, f"Vertical aspect ratio ({w}x{h}) with undetected duration"
        if platform in ("instagram", "tiktok", "twitter"):
            return True, f"{platform.capitalize()} social video with undetected duration"

    # Otherwise Long Video
    return False, f"Standard video (duration {duration:.1f}s > 120s)"


def inspect_media_file(file_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rigorously verifies that a file is genuinely a valid image or video before uploading.
    Returns: (is_valid: bool, media_type: 'video' | 'image' | 'invalid', metadata: dict)
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False, "empty_or_missing", {}

    try:
        with open(file_path, "rb") as f:
            head = f.read(64)
    except Exception as e:
        return False, f"unreadable: {e}", {}

    is_known_magic = False
    tentative_type = "unknown"

    # 1. JPEG
    if head.startswith(b"\xff\xd8\xff"):
        is_known_magic = True
        tentative_type = "image"
    # 2. PNG
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        is_known_magic = True
        tentative_type = "image"
    # 3. WebP / AVI
    elif head.startswith(b"RIFF") and len(head) >= 12:
        riff_tag = head[8:12]
        if riff_tag == b"WEBP":
            is_known_magic = True
            tentative_type = "image"
        elif riff_tag in (b"AVI ", b"WAVE"):
            is_known_magic = True
            tentative_type = "video" if riff_tag == b"AVI " else "audio"
    # 4. GIF
    elif head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        is_known_magic = True
        tentative_type = "image"
    # 5. BMP
    elif head.startswith(b"BM"):
        is_known_magic = True
        tentative_type = "image"
    # 6. TIFF
    elif head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        is_known_magic = True
        tentative_type = "image"
    # 7. WebM / Matroska
    elif head.startswith(b"\x1a\x45\xdf\xa3"):
        is_known_magic = True
        tentative_type = "video"
    # 8. MPEG-TS
    elif head.startswith(b"\x47"):
        is_known_magic = True
        tentative_type = "video"
    # 9. FLV
    elif head.startswith(b"FLV\x01"):
        is_known_magic = True
        tentative_type = "video"
    # 10. ISO-BMFF (MP4, QuickTime, MOV, HEIC, AVIF)
    elif len(head) >= 12 and head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"skip"):
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"avif", b"avis"):
            is_known_magic = True
            tentative_type = "image"
        else:
            is_known_magic = True
            tentative_type = "video"

    if not is_known_magic:
        return False, "unsupported_magic_signature", {}

    # 11. Deep FFprobe analysis (Verifies container integrity and stream existence)
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,codec_type,width,height,duration",
        "-show_entries", "format=format_name,duration,size",
        "-of", "json",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode != 0:
            return False, "corrupted_or_invalid_stream", {}
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if not streams:
            return False, "no_visual_stream", {}

        v_stream = streams[0]
        fmt = data.get("format", {})
        fmt_name = fmt.get("format_name", "").lower()
        codec = v_stream.get("codec_name", "").lower()
        width = int(v_stream.get("width") or 0)
        height = int(v_stream.get("height") or 0)
        dur = float(fmt.get("duration") or v_stream.get("duration") or 0.0)

        image_formats = ("image2", "png_pipe", "jpeg_pipe", "webp_pipe", "gif", "bmp_pipe")
        image_codecs = ("mjpeg", "png", "webp", "bmp", "tiff", "gif", "heic", "avif")

        if (fmt_name in image_formats) or (codec in image_codecs and dur <= 0.0) or (tentative_type == "image" and dur <= 0.0):
            media_type = "image"
        else:
            media_type = "video"

        meta = {
            "media_type": media_type,
            "format": fmt_name,
            "codec": codec,
            "width": width,
            "height": height,
            "duration": dur,
            "size": int(fmt.get("size") or os.path.getsize(file_path))
        }
        return True, media_type, meta
    except Exception as e:
        return False, f"probe_failed: {e}", {}


def probe_media_duration(file_path: str) -> float:
    """Uses ffprobe to extract real duration in seconds from downloaded media file."""
    if not os.path.exists(file_path):
        return 0.0
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur = float(res.stdout.strip())
        return dur
    except Exception:
        return 0.0


# ─── Automated Tag & Description Extractor ────────────────────────────────────

def extract_automated_metadata(meta: dict, platform: str) -> Tuple[str, str, str]:
    """
    100% Automatically extracts tags, hashtags, categories, music info, and description.
    Returns: (full_tags_string, clean_description, recommended_profile)
    """
    title = meta.get("title") or "Untitled"
    author_clean, display_name = extract_clean_author_handle(meta, platform)

    tags_list = [f"author:@{author_clean}", f"platform:{platform}"]

    # 1. Official video tags from YouTube / source
    raw_tags = meta.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            t_str = str(t).strip()
            if t_str and t_str not in tags_list:
                tags_list.append(t_str)

    # 2. Categories
    categories = meta.get("categories") or []
    if isinstance(categories, list):
        for c in categories:
            c_str = str(c).strip()
            if c_str and f"category:{c_str}" not in tags_list:
                tags_list.append(f"category:{c_str}")

    # 3. Music, Artist, Album metadata
    for field in ("artist", "creator", "album", "track", "genre"):
        val = meta.get(field)
        if val and isinstance(val, str) and val.strip():
            tags_list.append(f"{field}:{val.strip()}")

    # 4. Extract hashtags from description & title
    desc = meta.get("description") or ""
    hashtags = re.findall(r"#([a-zA-Z0-9_\u0900-\u097F]+)", f"{title} {desc}")
    for h in hashtags:
        h_tag = f"#{h.strip()}"
        if h_tag not in tags_list:
            tags_list.append(h_tag)

    # Deduplicate while preserving order
    seen = set()
    deduped_tags = []
    for t in tags_list:
        norm = t.lower()
        if norm not in seen:
            seen.add(norm)
            deduped_tags.append(t)

    full_tags = ", ".join(deduped_tags[:30])

    # 5. Smart Profile Recommendation
    recommended_profile = "Default"
    categories_lower = [str(c).lower() for c in categories]
    text_corpus = f"{title} {desc}".lower()

    if any(m in categories_lower for m in ["music", "entertainment", "film & animation", "comedy", "movies"]):
        recommended_profile = "Entertainment"
    elif any(t in categories_lower for t in ["education", "science & technology", "howto & style"]):
        recommended_profile = "Tutorials"
    elif any(kw in text_corpus for kw in ["song", "remix", "music", "dance", "movie", "video song", "trailer", "soundtrack"]):
        recommended_profile = "Entertainment"
    elif any(kw in text_corpus for kw in ["tutorial", "course", "guide", "learn", "how to", "coding", "python", "javascript"]):
        recommended_profile = "Tutorials"

    return full_tags, desc, recommended_profile


def safe_input(prompt_text: str = "") -> str:
    """Reads user input safely, returning empty string on EOF or closed stdin."""
    try:
        return input(prompt_text).strip()
    except (EOFError, IOError):
        return ""


def prompt_on_error(error_msg: str, allow_retry: bool = True) -> str:
    """
    Never exits automatically on error.
    Displays error details and prompts user for action:
    [R] Retry, [L] View logs, [N] New URL, or [Enter] / [X] Exit.
    """
    PipelineLogger.error(error_msg)
    send_toast(f"Pipeline Error: {error_msg[:40]}")

    is_interactive = sys.stdin.isatty() or os.path.exists("/dev/tty")

    print(f"\n{C_RED}╔════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_RED}║                     AN ERROR OCCURRED                      ║{C_RESET}")
    print(f"{C_RED}╚════════════════════════════════════════════════════════════╝{C_RESET}")
    print(f"{C_BOLD}Details:{C_RESET} {C_RED}{error_msg}{C_RESET}")
    print(f"{C_GRAY}Log file: {LOG_FILE}{C_RESET}\n")

    if not is_interactive:
        print(f"{C_YELLOW}Non-interactive session. Pausing 5s before exit...{C_RESET}")
        time.sleep(5)
        return "exit"

    while True:
        print(f"{C_BOLD}Select an action:{C_RESET}")
        if allow_retry:
            print(f"  {C_GREEN}[R]{C_RESET} {C_BOLD}Retry{C_RESET} (Attempt this operation again)")
        print(f"  {C_CYAN}[L]{C_RESET} {C_BOLD}View Logs{C_RESET} (Inspect detailed execution logs)")
        print(f"  {C_YELLOW}[N]{C_RESET} {C_BOLD}New URL{C_RESET} (Try a different video link)")
        print(f"  {C_MAGENTA}[X]{C_RESET} {C_BOLD}Exit{C_RESET} (Press Enter to close window)\n")

        ans = safe_input(f"{C_YELLOW}Choose action (Default: Close): {C_RESET}").lower()

        if ans in ("r", "retry") and allow_retry:
            return "retry"
        elif ans in ("l", "logs", "log"):
            show_recent_logs(40)
            continue
        elif ans in ("n", "new"):
            return "new"
        elif ans in ("x", "exit", "q", "quit") or ans == "":
            return "exit"
        else:
            return "exit"


def normalize_canonical_url(url: Optional[str]) -> Optional[str]:
    """Extracts canonical form of URLs to detect duplicates regardless of tracking parameters."""
    if not url:
        return None
    url = url.strip()
    if not url or url.lower() in ("app_direct_upload", "direct_upload", "unknown", "none"):
        return None
    yt_match = re.search(r'(?:v=|youtu\.be/|/embed/|/shorts/|/v/|/live/|^)([A-Za-z0-9_-]{11})(?:[&/?#]|$)', url)
    if "youtube" in url.lower() or "youtu.be" in url.lower():
        if yt_match:
            return f"https://youtu.be/{yt_match.group(1)}"
    ig_match = re.search(r'instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)', url, re.I)
    if ig_match:
        return f"https://www.instagram.com/reel/{ig_match.group(1)}/"
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc:
            return None
        return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), '', '', ''))
    except Exception:
        return url


def clean_title_compare(title: Optional[str]) -> str:
    """Normalizes title for duplicate comparison."""
    if not title:
        return ""
    t = re.sub(r'[^\w\s]', '', title.lower())
    return " ".join(t.split())


def check_existing_vault_media(url: str, meta: Optional[dict] = None) -> Optional[dict]:
    """
    Queries Akash Media Vault to check if the target media is already published.
    Matches by canonical URL or (cleaned title + duration within 3 seconds).
    Returns the existing item dict if found, or None.
    """
    norm_input = normalize_canonical_url(url)
    target_title = None
    target_duration = 0.0

    if meta:
        target_title = clean_title_compare(meta.get("title"))
        target_duration = float(meta.get("duration") or 0.0)

    try:
        r = requests.get(f"{SERVER_BASE_URL}{ROUTE_LIST}?type=all&limit=100", headers=HEADERS_RETRIEVE, timeout=8)
        if r.status_code == 200:
            items = r.json().get("items", [])
            for item in items:
                # 1. Check raw source_url match
                item_source = item.get("source_url") or ""
                if item_source and url.strip() == item_source.strip():
                    return item

                # 2. Check canonical URL match
                if norm_input and item_source:
                    item_norm = normalize_canonical_url(item_source)
                    if item_norm and item_norm == norm_input:
                        return item

                # 3. Check title and duration match
                if target_title and len(target_title) > 3:
                    item_c_title = clean_title_compare(item.get("title"))
                    if item_c_title == target_title:
                        item_dur = float(item.get("duration") or 0.0)
                        if target_duration <= 0 or item_dur <= 0 or abs(target_duration - item_dur) <= 3.0:
                            return item
    except Exception as e:
        PipelineLogger.warn(f"Duplicate vault pre-check skipped due to network timeout: {e}")

    return None


def print_existing_vault_media(existing: dict):
    """Displays standard banner and stream link for an already vaulted media item."""
    title = existing.get("title") or "Untitled Media"
    author = existing.get("author") or "Vault Media"
    dur_raw = float(existing.get("duration") or 0.0)
    dur_str = f"{int(dur_raw//60)}m {int(dur_raw%60)}s" if dur_raw >= 60 else f"{dur_raw:.1f}s"
    m_type = existing.get("media_type", "video").upper()
    stream_url = existing.get("stream_url") or existing.get("playback", {}).get("full_stream_url") or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{existing.get('file_code')}"
    code = existing.get("file_code")

    send_toast(f"Media already in vault: {title[:20]}")
    PipelineLogger.success("DUPLICATE DETECTED: MEDIA ALREADY IN AKASH VAULT!")

    print(f"\n{C_CYAN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_CYAN}║     VIDEO ALREADY EXISTS IN AKASH SOVEREIGN VAULT!         ║{C_RESET}")
    print(f"{C_CYAN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
    print(f"{C_BOLD} Title:{C_RESET}       {C_WHITE}{title}{C_RESET}")
    print(f"{C_BOLD} Author:{C_RESET}      {C_YELLOW}{author}{C_RESET}")
    print(f"{C_BOLD} Duration:{C_RESET}    {dur_str}")
    print(f"{C_BOLD} Vault Code:{C_RESET}  {code}")
    print(f"{C_BOLD} Type:{C_RESET}        {m_type}")
    print(f"{C_BOLD} Stream URL:{C_RESET}  {C_GREEN}{stream_url}{C_RESET}")
    print(f"{C_GRAY} Preserved existing file - zero duplicate storage created.{C_RESET}\n")


def fetch_metadata(url: str) -> Optional[Tuple[dict, str]]:
    """
    Fetches video metadata using yt-dlp.
    Never exits abruptly on error: prompts user to retry or provide a new URL.
    Returns (meta_dict, final_url) or None if cancelled.
    """
    current_url = url
    while True:
        PipelineLogger.info(f"{C_YELLOW}> Analyzing media source and extracting metadata...{C_RESET}")
        cmd = ["yt-dlp", "--dump-single-json", "--no-download", current_url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                meta = json.loads(res.stdout)
                PipelineLogger.success(f"Metadata extracted: '{meta.get('title', 'Unknown')[:50]}'")
                return meta, current_url
            except json.JSONDecodeError as e:
                err_text = f"JSON decode failed: {e}"
        else:
            err_text = res.stderr.strip() if res.stderr else "yt-dlp failed to inspect URL"

        action = prompt_on_error(f"Failed to fetch video metadata: {err_text}")
        if action == "retry":
            continue
        elif action == "new":
            new_u = safe_input(f"{C_GREEN}Enter new video URL: {C_RESET}")
            if new_u:
                current_url = new_u
                continue
        return None


# ─── Upload with Live Progress ────────────────────────────────────────────────

class ProgressFileReader:
    """Wrapper that logs live upload progress."""
    def __init__(self, filename, total_size):
        self._file = open(filename, "rb")
        self.total_size = total_size
        self.bytes_read = 0
        self.last_percent = -1

    def read(self, size=-1):
        chunk = self._file.read(size)
        if chunk:
            self.bytes_read += len(chunk)
            percent = int((self.bytes_read / self.total_size) * 100) if self.total_size > 0 else 0
            if percent != self.last_percent and percent % 10 == 0:
                self.last_percent = percent
                mb_uploaded = self.bytes_read / (1024 * 1024)
                mb_total = self.total_size / (1024 * 1024)
                sys.stdout.write(f"\r{C_CYAN}Uploading: {percent}% ({mb_uploaded:.1f}/{mb_total:.1f} MB){C_RESET}")
                sys.stdout.flush()
        return chunk

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def ensure_colab_authenticated() -> bool:
    """Verifies that Google Colab CLI (colabcli) is authorized on this device."""
    token_file = os.path.expanduser("~/.config/colab-cli/token.json")
    if os.path.exists(token_file) and os.path.getsize(token_file) > 10:
        return True

    print(f"\n{C_YELLOW}╔════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_YELLOW}║   GOOGLE COLAB GPU AUTHORIZATION REQUIRED ON THIS DEVICE    ║{C_RESET}")
    print(f"{C_YELLOW}╚════════════════════════════════════════════════════════════╝{C_RESET}")
    print("Akash is configured to process all YouTube videos using Google Colab GPU (T4).")
    print("Please authorize colab-cli with your Google account.")
    print("Sign in and copy the authorization code to paste it below:\n")
    try:
        # Running colab sessions triggers the remote copy-paste OAuth flow directly in the terminal
        subprocess.run(["colab", "sessions"])
        if os.path.exists(token_file) and os.path.getsize(token_file) > 10:
            PipelineLogger.success("Google Colab CLI successfully authorized on this device!")
            return True
        else:
            PipelineLogger.error("Colab authorization was not completed.")
            return False
    except Exception as e:
        PipelineLogger.warn(f"Colab auth prompt error: {e}")
        return False


# ─── 1. Shorts Pipeline (<= 120s) ─────────────────────────────────────────────

def handle_short_pipeline(meta: dict, url: str, classification_reason: str = ""):
    title = strip_emojis(meta.get("title") or "Untitled Short")
    duration = float(meta.get("duration") or 0.0)
    platform = detect_platform(url)
    username, display_name = extract_clean_author_handle(meta, platform)

    auto_tags, auto_desc, _ = extract_automated_metadata(meta, platform)
    caption = strip_emojis(auto_desc if auto_desc else title)

    dur_info = f"{duration:.1f}s <= 120s" if duration > 0 else f"Auto-detected ({classification_reason})"

    PipelineLogger.info(f"\n{C_GREEN}────────────────────────────────────────────────────────────{C_RESET}")
    PipelineLogger.info(f"{C_BOLD} CLASSIFICATION: SHORTS / REEL ({dur_info}){C_RESET}")
    PipelineLogger.info(f"{C_CYAN}Creator Handle:{C_RESET} @{username}")
    PipelineLogger.info(f"{C_CYAN}Display Name:{C_RESET}   {display_name}")
    PipelineLogger.info(f"{C_CYAN}Platform:{C_RESET}       {platform.capitalize()}")
    PipelineLogger.info(f"{C_CYAN}Title:{C_RESET}          {title[:60]}")
    PipelineLogger.info(f"{C_CYAN}Auto-Tags:{C_RESET}      {auto_tags[:70]}...")
    PipelineLogger.info(f"{C_GREEN}────────────────────────────────────────────────────────────{C_RESET}\n")

    # 1. Creator Verification
    creator_id = None
    while True:
        PipelineLogger.info(f" Verifying creator account '@{username}' in database...")
        check_url = f"{SERVER_BASE_URL}/api/media/creator/check?username={username}"
        try:
            r = requests.get(check_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                c_data = r.json()
                if c_data.get("exists") and c_data.get("creator"):
                    creator = c_data["creator"]
                    creator_id = creator["id"]
                    PipelineLogger.success(f"Existing creator account found (ID: {creator_id}, Display: {creator.get('display_name')})")
                    break
                else:
                    PipelineLogger.info(f"Creator '@{username}' not in database. Auto-creating new account...")
                    create_url = f"{SERVER_BASE_URL}/api/media/creator/create"
                    payload = {
                        "username": username,
                        "platform": platform,
                        "display_name": display_name,
                        "avatar_url": None
                    }
                    cr_r = requests.post(create_url, json=payload, headers=HEADERS, timeout=10)
                    if cr_r.status_code == 200:
                        creator = cr_r.json().get("creator")
                        creator_id = creator["id"]
                        PipelineLogger.success(f"New creator account created successfully! (ID: {creator_id})")
                        break
                    else:
                        err = f"Failed to create creator: {cr_r.text}"
            else:
                err = f"Server returned HTTP {r.status_code} while checking creator"
        except Exception as e:
            err = f"Connection error to {SERVER_BASE_URL}: {e}"

        action = prompt_on_error(err)
        if action != "retry":
            return

    # If source is YouTube, offload processing directly to Google Colab GPU CLI on this device
    if platform == "youtube":
        PipelineLogger.info("YouTube Short Detected: Processing via Google Colab GPU CLI (T4) on this device...")
        if ensure_colab_authenticated():
            colab_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "colab_transcoder.py")
            if not os.path.exists(colab_script):
                colab_script = os.path.expanduser("~/colab_transcoder.py")

            cmd = [
                "colab", "run",
                "--gpu", "T4",
                "--timeout", "3600",
                colab_script,
                "--url", url,
                "--server", SERVER_BASE_URL,
                "--api-key", API_KEY,
                "--author", username,
                "--tags", auto_tags,
                "--is-short"
            ]
            PipelineLogger.info(f"Executing Colab GPU Short pipeline on this device...")
            try:
                ret = subprocess.run(cmd)
                if ret.returncode == 0:
                    send_toast(f"Short processed on Colab GPU! @{username}")
                    PipelineLogger.success("YOUTUBE SHORT PROCESSED ON GOOGLE COLAB GPU!")
                    print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
                    print(f"{C_GREEN}║     YOUTUBE SHORT PROCESSED ON GOOGLE COLAB GPU            ║{C_RESET}")
                    print(f"{C_GREEN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
                    print(f"{C_BOLD}Engine:{C_RESET}      Google Colab CLI (colabcli) on NVIDIA T4 GPU")
                    print(f"{C_BOLD}Creator:{C_RESET}     @{username}")
                    print(f"{C_BOLD}Feed Vault:{C_RESET}  {SERVER_BASE_URL}{ROUTE_FEED}")
                    print(f"{C_GRAY}Logs saved to: {LOG_FILE}{C_RESET}\n")
                    return
                else:
                    PipelineLogger.warn(f"Colab execution returned code {ret.returncode}. Falling back to local direct download...")
            except Exception as e:
                PipelineLogger.warn(f"Colab short execution error: {e}. Falling back to local download...")

    # 2. Download Short with Live Terminal Logs
    temp_dir = "/data/data/com.termux/files/usr/tmp/akash_media"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = os.path.join(temp_dir, "short.mp4")

    dl_cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", temp_file,
        url
    ]

    while True:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

        exit_code = PipelineLogger.live_exec(dl_cmd, desc="Downloading short video with yt-dlp...")
        if exit_code == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
            break

        action = prompt_on_error("Download failed or output file is empty.")
        if action == "retry":
            dl_cmd = ["yt-dlp", "-f", "best", "-o", temp_file, url]
            continue
        else:
            return

    # If duration was 0 or undetected, measure exact duration using ffprobe
    if duration <= 0.0:
        duration = probe_media_duration(temp_file)
        if duration > 0:
            PipelineLogger.info(f"Exact duration probed via ffprobe: {duration:.1f}s")

    # Pre-upload Media Verification: Verify that file is genuinely an image or video
    PipelineLogger.info(" Pre-upload verification: Verifying media integrity...")
    is_valid, media_type, meta_info = inspect_media_file(temp_file)
    if not is_valid:
        PipelineLogger.error(f"[ERROR] Upload rejected! '{temp_file}' is neither a valid image nor a video (Error: {media_type}).")
        prompt_on_error(f"Media validation failed: file is not a supported video or image ({media_type}).", allow_retry=False)
        return
    PipelineLogger.success(f"[VERIFIED] Verified Media: {media_type.upper()} ({meta_info.get('codec')}, {meta_info.get('width')}x{meta_info.get('height')}, {meta_info.get('duration', 0):.1f}s)")

    # 3. Upload to Server with Live Progress
    upload_url = f"{SERVER_BASE_URL}{ROUTE_UPLOAD}"
    data = {
        "author": username,
        "title": title,
        "caption": caption[:1500],
        "is_short": "true",
        "source_url": url
    }

    uploaded = False
    while not uploaded:
        PipelineLogger.info(f"Uploading via High-Security Obfuscated Tunnel ({SERVER_BASE_URL})...")
        try:
            file_size = os.path.getsize(temp_file)
            with ProgressFileReader(temp_file, file_size) as pr_file:
                files = {"file": ("media.mp4", pr_file, "video/mp4")}
                res = requests.post(upload_url, data=data, files=files, headers=HEADERS, timeout=180)

            sys.stdout.write("\n")
            if res.status_code == 200:
                resp = res.json()
                stream_url = resp.get("playback", {}).get("full_ott_stream_url") or resp.get("stream_url") or resp.get("playback", {}).get("full_stream_url") or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{resp.get('file_code')}"
                send_toast(f"Short Uploaded! @{username}")

                PipelineLogger.success("REEL / SHORT PUBLISHED LIVE!")
                print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
                print(f"{C_GREEN}║              REEL / SHORT PUBLISHED LIVE!                  ║{C_RESET}")
                print(f"{C_GREEN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
                print(f"{C_BOLD} Stream URL:{C_RESET}   {C_CYAN}{stream_url}{C_RESET}")
                print(f"{C_BOLD} Creator:{C_RESET}      @{username}")
                print(f"{C_BOLD} Duration:{C_RESET}     {duration:.1f}s")
                print(f"{C_GRAY} Logs saved to: {LOG_FILE}{C_RESET}\n")
                uploaded = True
            else:
                action = prompt_on_error(f"Upload failed (HTTP {res.status_code}): {res.text}")
                if action != "retry":
                    break
        except Exception as e:
            action = prompt_on_error(f"Network error during upload: {e}")
            if action != "retry":
                break

    if os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except Exception:
            pass


# ─── 2. Long Videos Pipeline (> 120s) ─────────────────────────────────────────

def handle_long_pipeline(meta: dict, url: str):
    title = strip_emojis(meta.get("title") or "Untitled Video")
    duration = float(meta.get("duration") or 0.0)
    platform = detect_platform(url)
    username, display_name = extract_clean_author_handle(meta, platform)
    uploader = strip_emojis(display_name)
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    # 1. Automatic Tag, Description & Profile Extraction
    auto_tags, auto_desc, recommended_profile = extract_automated_metadata(meta, platform)

    PipelineLogger.info(f"\n{C_YELLOW}╔════════════════════════════════════════════════════════════╗{C_RESET}")
    PipelineLogger.info(f"{C_YELLOW}║           LONG VIDEO DETECTED ({minutes}m {seconds}s > 2 minutes)          ║{C_RESET}")
    PipelineLogger.info(f"{C_YELLOW}╚════════════════════════════════════════════════════════════╝{C_RESET}")
    PipelineLogger.info(f"{C_BOLD}Title:{C_RESET}       {title}")
    PipelineLogger.info(f"{C_BOLD}Author:{C_RESET}      {uploader} {C_GRAY}(Saved as metadata tag, not account name){C_RESET}")
    PipelineLogger.info(f"{C_BOLD}Length:{C_RESET}      {minutes}m {seconds}s")
    PipelineLogger.info(f"{C_BOLD}Auto-Tags:{C_RESET}   {auto_tags[:90]}...")
    PipelineLogger.info(f"{C_BOLD}Description:{C_RESET} {auto_desc[:100]}...\n")

    # 2. Fetch Profiles from Server
    PipelineLogger.info(" Fetching storage profiles from server...")
    try:
        r = requests.get(f"{SERVER_BASE_URL}/api/media/profiles", headers=HEADERS, timeout=10)
        profiles = r.json().get("profiles", [])
    except Exception as e:
        PipelineLogger.error(f"Server error fetching profiles: {e}")
        profiles = [{"id": 1, "name": "Default", "description": "General uploaded long videos"}]

    # Determine recommended profile index
    rec_idx = 1
    for idx, p in enumerate(profiles, start=1):
        if p["name"].lower() == recommended_profile.lower():
            rec_idx = idx
            break

    print(f"{C_BOLD}Select Storage Profile:{C_RESET}")
    for idx, p in enumerate(profiles, start=1):
        highlight = f" {C_GREEN}[Recommended: {recommended_profile}]{C_RESET}" if idx == rec_idx else ""
        print(f"  {C_GREEN}[{idx}]{C_RESET} {C_BOLD}{p['name']}{C_RESET} - {C_GRAY}{p.get('description', '')}{C_RESET}{highlight}")
    print(f"  {C_MAGENTA}[N]{C_RESET} {C_BOLD}Create NEW Profile{C_RESET}\n")

    # Prompt user with automatic recommended default
    choice = safe_input(f"{C_YELLOW}Choose profile [1-{len(profiles)}, N] (Auto-detected: [{rec_idx}] {profiles[rec_idx-1]['name']}): {C_RESET}")

    selected_profile_id = profiles[rec_idx - 1]["id"]
    selected_profile_name = profiles[rec_idx - 1]["name"]

    if choice.upper() == "N":
        new_name = safe_input(f"{C_CYAN}Enter new profile name: {C_RESET}")
        new_desc = safe_input(f"{C_CYAN}Enter profile description (optional): {C_RESET}")
        if not new_name:
            new_name = "Custom Collection"

        try:
            r = requests.post(f"{SERVER_BASE_URL}/api/media/profiles", json={"name": new_name, "description": new_desc}, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                created = r.json().get("profile")
                selected_profile_id = created["id"]
                selected_profile_name = created["name"]
                PipelineLogger.success(f"Created profile '{selected_profile_name}' (ID: {selected_profile_id})")
        except Exception as e:
            PipelineLogger.error(f"Error creating profile: {e}")
    elif choice:
        try:
            idx = int(choice)
            if 1 <= idx <= len(profiles):
                selected_profile_id = profiles[idx - 1]["id"]
                selected_profile_name = profiles[idx - 1]["name"]
        except ValueError:
            pass

    PipelineLogger.success(f"Assigned Storage Profile: '{selected_profile_name}'")

    # 3. Processing Engine Selection
    print(f"\n{C_BOLD}Choose Processing & Quality Mode:{C_RESET}")
    print(f"  {C_GREEN}[1]{C_RESET} {C_BOLD}Direct Download & Upload{C_RESET} {C_CYAN}(Recommended: Instant streamable MP4 in Termux, ~15-30s, zero transcoding){C_RESET}")
    print(f"  {C_YELLOW}[2]{C_RESET} {C_BOLD}Google Colab GPU Transcode{C_RESET} {C_GRAY}(8-tier HLS adaptive package 144p to 4K, takes ~5-8m){C_RESET}\n")

    mode = safe_input(f"{C_YELLOW}Select mode [1/2] (Default: [1] Direct Download): {C_RESET}")
    if not mode or mode.strip() == "1":
        mode = "1"
    else:
        mode = "2"

    if mode == "2":
        # Processed on this device via Google Colab GPU CLI
        PipelineLogger.info("Offloading video transcoding to Google Colab GPU CLI (colabcli) on this device...")
        if not ensure_colab_authenticated():
            PipelineLogger.warn("Colab authorization incomplete or cancelled. Falling back to local direct download...")
        else:
            colab_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "colab_transcoder.py")
            if not os.path.exists(colab_script):
                colab_script = os.path.expanduser("~/colab_transcoder.py")

            import secrets
            transcode_file_code = f"v_{secrets.token_hex(4)}"

            # Pre-register transcoding state on server so it appears in vault listings immediately
            try:
                target_res = "4K (2160p)" if int(meta.get("height") or 0) >= 2160 else "1080p"
                requests.post(
                    f"{SERVER_BASE_URL}/api/media/long/transcode-start",
                    headers=HEADERS,
                    data={
                        "file_code": transcode_file_code,
                        "profile_id": str(selected_profile_id),
                        "title": title,
                        "author": uploader,
                        "duration": str(duration),
                        "source_url": url,
                        "tags": auto_tags,
                        "description": auto_desc[:3000],
                        "target_resolution": target_res
                    },
                    timeout=10
                )
                PipelineLogger.info(f"Registered video in vault catalog: '{title[:40]}' [Status: Transcoding]")
            except Exception as e:
                PipelineLogger.warn(f"Failed to pre-register transcoding status on server: {e}")

            cmd = [
                "colab", "run",
                "--gpu", "T4",
                "--timeout", "7200",
                colab_script,
                "--url", url,
                "--server", SERVER_BASE_URL,
                "--api-key", API_KEY,
                "--profile-id", str(selected_profile_id),
                "--profile-name", selected_profile_name,
                "--author", uploader,
                "--tags", auto_tags,
                "--file-code", transcode_file_code
            ]
            PipelineLogger.info("Executing Colab GPU Full-Spectrum Transcode on this device...")
            try:
                ret = subprocess.run(cmd)
                if ret.returncode == 0:
                    send_toast("Transcoding complete on Colab GPU!")
                    PipelineLogger.success("TRANSCODING COMPLETE VIA GOOGLE COLAB GPU!")
                    print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
                    print(f"{C_GREEN}║     TRANSCODING COMPLETE ON GOOGLE COLAB GPU               ║{C_RESET}")
                    print(f"{C_GREEN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
                    print(f"{C_BOLD}Engine:{C_RESET}      Google Colab CLI (colabcli) on NVIDIA T4 GPU")
                    print(f"{C_BOLD}Task:{C_RESET}        Multi-bitrate HLS adaptive package (144p to 4K 2160p)")
                    print(f"{C_BOLD}Profile:{C_RESET}     {selected_profile_name}")
                    print(f"{C_BOLD}Author:{C_RESET}      {uploader}")
                    print(f"{C_BOLD}Watch / Feed:{C_RESET} {SERVER_BASE_URL}{ROUTE_LONG_FEED}")
                    print(f"{C_GRAY}Logs saved to: {LOG_FILE}{C_RESET}\n")
                    return
                else:
                    PipelineLogger.warn(f"Colab run exited with code {ret.returncode}. Canceling pending transcode status...")
                    try:
                        requests.post(f"{SERVER_BASE_URL}/api/media/long/transcode-cancel", headers=HEADERS, data={"file_code": transcode_file_code}, timeout=5)
                    except Exception:
                        pass
            except Exception as e:
                PipelineLogger.warn(f"Colab execution error: {e}. Canceling pending transcode status...")
                try:
                    requests.post(f"{SERVER_BASE_URL}/api/media/long/transcode-cancel", headers=HEADERS, data={"file_code": transcode_file_code}, timeout=5)
                except Exception:
                    pass

    # Fallback / Direct Mode: Download and upload with Live Logs
    temp_dir = "/data/data/com.termux/files/usr/tmp/akash_media"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = os.path.join(temp_dir, "long_video.mp4")

    dl_cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=visionos,android",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", temp_file,
        url
    ]

    while True:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

        exit_code = PipelineLogger.live_exec(dl_cmd, desc="Downloading video locally with yt-dlp...")
        if exit_code == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
            break

        action = prompt_on_error("Download failed or output file is empty.")
        if action == "retry":
            dl_cmd = ["yt-dlp", "-f", "best", "-o", temp_file, url]
            continue
        else:
            return

    if duration <= 0.0:
        duration = probe_media_duration(temp_file)
        if duration > 0:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            PipelineLogger.info(f"Exact duration probed via ffprobe: {minutes}m {seconds}s")

    # Pre-upload Media Verification: Ensure file is genuine image or video
    PipelineLogger.info(" Pre-upload verification: Verifying media integrity...")
    is_valid, media_type, meta_info = inspect_media_file(temp_file)
    if not is_valid:
        PipelineLogger.error(f"[ERROR] Upload rejected! '{temp_file}' is neither a valid image nor a video (Error: {media_type}).")
        prompt_on_error(f"Media validation failed: file is not a supported video or image ({media_type}).", allow_retry=False)
        return
    PipelineLogger.success(f"[VERIFIED] Verified Media: {media_type.upper()} ({meta_info.get('codec')}, {meta_info.get('width')}x{meta_info.get('height')}, {meta_info.get('duration', 0):.1f}s)")

    upload_url = f"{SERVER_BASE_URL}{ROUTE_UPLOAD}"
    data = {
        "profile_name": selected_profile_name,
        "title": title,
        "caption": auto_desc[:3000],
        "tags": auto_tags,
        "author": uploader,
        "is_short": "false",
        "source_url": url
    }

    uploaded = False
    while not uploaded:
        PipelineLogger.info(f"Uploading via High-Security Obfuscated Tunnel ({SERVER_BASE_URL})...")
        try:
            file_size = os.path.getsize(temp_file)
            with ProgressFileReader(temp_file, file_size) as pr_file:
                files = {"file": ("media.mp4", pr_file, "video/mp4")}
                res = requests.post(upload_url, data=data, files=files, headers=HEADERS, timeout=360)

            sys.stdout.write("\n")
            if res.status_code == 200:
                resp = res.json()
                stream_url = resp.get("playback", {}).get("full_ott_stream_url") or resp.get("stream_url") or resp.get("playback", {}).get("full_stream_url") or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{resp.get('file_code')}"
                send_toast(f"Video Uploaded: {title[:20]}...")

                PipelineLogger.success("LONG VIDEO PUBLISHED SUCCESSFULLY!")
                print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
                print(f"{C_GREEN}║              VIDEO PUBLISHED SUCCESSFULLY!                 ║{C_RESET}")
                print(f"{C_GREEN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
                print(f"{C_BOLD} Stream URL:{C_RESET}   {C_CYAN}{stream_url}{C_RESET}")
                print(f"{C_BOLD} Profile:{C_RESET}      {selected_profile_name}")
                print(f"{C_BOLD} Auto-Tags:{C_RESET}    {auto_tags}")
                print(f"{C_BOLD} Duration:{C_RESET}     {minutes}m {seconds}s")
                print(f"{C_GRAY} Logs saved to: {LOG_FILE}{C_RESET}\n")
                uploaded = True
            else:
                action = prompt_on_error(f"Upload failed (HTTP {res.status_code}): {res.text}")
                if action != "retry":
                    break
        except Exception as e:
            action = prompt_on_error(f"Network error during upload: {e}")
            if action != "retry":
                break

    if os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except Exception:
            pass


# ─── Helper Functions & Log Viewer ────────────────────────────────────────────

def show_recent_logs(lines: int = 50):
    if not os.path.exists(LOG_FILE):
        print(f"{C_YELLOW}No logs found at {LOG_FILE}{C_RESET}")
        return
    print(f"\n{C_CYAN} Last {lines} log entries from {LOG_FILE}:{C_RESET}\n")
    try:
        subprocess.run(["tail", f"-n{lines}", LOG_FILE], check=True)
    except Exception:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            for l in all_lines[-lines:]:
                print(l.rstrip())


def show_uploaded_media(filter_type: str = "all"):
    """Fetches and displays all uploaded Shorts and Long Videos from server via secure opaque route."""
    print(f"\n{C_CYAN} Fetching uploaded media catalog from {SERVER_BASE_URL}...{C_RESET}\n")

    shorts = []
    videos = []

    try:
        r = requests.get(f"{SERVER_BASE_URL}{ROUTE_LIST}?type={filter_type}&limit=50", headers=HEADERS_RETRIEVE, timeout=12)
        if r.status_code == 200:
            all_items = r.json().get("items", [])
            shorts = [i for i in all_items if i.get("media_type") == "short"]
            videos = [i for i in all_items if i.get("media_type") == "long_video"]
        else:
            PipelineLogger.warn(f"Catalog query returned HTTP {r.status_code}")
    except Exception as e:
        PipelineLogger.error(f"Failed to fetch media catalog: {e}")

    if filter_type in ("all", "shorts"):
        print(f"{C_BOLD}{C_GREEN} SHORTS & REELS ({len(shorts)}){C_RESET} {C_GRAY}- Vault: {SERVER_BASE_URL}{ROUTE_FEED}{C_RESET}")
        print(f"{C_GRAY}──────────────────────────────────────────────────────────────────────────{C_RESET}")
        if not shorts:
            print(f"  {C_GRAY}(No shorts uploaded yet){C_RESET}")
        else:
            for s in shorts:
                title = (s.get('title') or 'Untitled')[:42]
                creator = s.get('author') or '@creator'
                dur = f"{float(s.get('duration') or 0):.1f}s"
                views = s.get('views', 0)
                stream_url = s.get('stream_url') or s.get('playback', {}).get('full_stream_url') or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{s['file_code']}"
                print(f"  {C_CYAN}*{C_RESET} {C_BOLD}{title:<42}{C_RESET} {C_YELLOW}{creator:<18}{C_RESET} {C_GRAY}{dur:<8}{C_RESET} {C_BLUE}{views} views{C_RESET}")
                print(f"    {C_CYAN} Stream:{C_RESET} {stream_url}\n")

    if filter_type in ("all", "videos", "long"):
        print(f"{C_BOLD}{C_YELLOW} LONG VIDEOS ({len(videos)}){C_RESET} {C_GRAY}- Vault: {SERVER_BASE_URL}{ROUTE_FEED}{C_RESET}")
        print(f"{C_GRAY}──────────────────────────────────────────────────────────────────────────{C_RESET}")
        if not videos:
            print(f"  {C_GRAY}(No long videos uploaded yet){C_RESET}")
        else:
            for v in videos:
                title = (v.get('title') or 'Untitled')[:42]
                profile = f"[{v.get('profile') or 'Default'}]"
                author = (v.get('author') or 'Author')[:20]
                dur_raw = float(v.get('duration') or 0)
                dur = f"{int(dur_raw//60)}m {int(dur_raw%60)}s"
                views = v.get('views', 0)
                stream_url = v.get('stream_url') or v.get('playback', {}).get('full_stream_url') or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{v['file_code']}"
                v_status = v.get('status') or 'ready'
                v_progress = v.get('progress') or ''

                if v_status == "transcoding":
                    print(f"  {C_MAGENTA}*{C_RESET} {C_BOLD}{title:<42}{C_RESET} {C_YELLOW}[Transcoding]{C_RESET} {C_GRAY}{author:<22} {dur:<8}{C_RESET}")
                    print(f"    {C_CYAN} Status:{C_RESET} {v_progress or 'In progress on Google Colab GPU (4K Multi-Bitrate HLS)'}\n")
                else:
                    print(f"  {C_YELLOW}*{C_RESET} {C_BOLD}{title:<42}{C_RESET} {C_GREEN}{profile:<14}{C_RESET} {C_GRAY}{author:<22} {dur:<8}{C_RESET}")
                    print(f"    {C_YELLOW} Stream:{C_RESET} {stream_url}\n")

    print(f"{C_CYAN} Global Web Portals:{C_RESET}")
    print(f"   Continuous Media Vault & Player: {C_BOLD}{SERVER_BASE_URL}{ROUTE_FEED}{C_RESET}\n")


def print_help():
    print(f"{C_CYAN}Usage:{C_RESET} dl [URL | --list | --shorts | --videos | --logs | --tail | --help]")
    print("\nOptions:")
    print("  dl <URL>     Process YouTube/Instagram video (Auto-tags & classification)")
    print("  dl --list    View all uploaded Shorts & Long Videos (or 'dl ls')")
    print("  dl --shorts  View only uploaded Shorts & Instagram Reels")
    print("  dl --videos  View only uploaded Long Videos")
    print("  dl --logs    View recent execution logs")
    print("  dl --tail    Live-stream log entries (tail -f)")
    print("  dl --help    Show this guide\n")
    print("Android Quick Share:")
    print("  Click 'Share' in YouTube/Instagram -> Select 'Termux'.")
    print(f"  Execution logs are saved automatically to: {LOG_FILE}\n")


def handle_local_file_upload(file_path: str, media_type: str, meta_info: dict):
    title = os.path.splitext(os.path.basename(file_path))[0].replace("_", " ").title()
    duration = float(meta_info.get("duration") or 0.0)
    is_short = (duration <= 120.0) if media_type == "video" else True

    upload_url = f"{SERVER_BASE_URL}{ROUTE_UPLOAD}"
    data = {
        "author": "LocalUser",
        "title": title,
        "is_short": "true" if is_short else "false"
    }
    file_size = os.path.getsize(file_path)
    mime_type = "image/jpeg" if media_type == "image" else "video/mp4"

    PipelineLogger.info(f"Uploading verified {media_type} to Akash Sovereign Vault...")
    try:
        with ProgressFileReader(file_path, file_size) as pr_file:
            files = {"file": (os.path.basename(file_path), pr_file, mime_type)}
            res = requests.post(upload_url, data=data, files=files, headers=HEADERS, timeout=360)

        sys.stdout.write("\n")
        if res.status_code == 200:
            resp = res.json()
            stream_url = resp.get("stream_url") or resp.get("playback", {}).get("full_stream_url") or f"{SERVER_BASE_URL}{ROUTE_STREAM}/{resp.get('file_code')}"
            send_toast(f"Media Uploaded: {title[:20]}")
            PipelineLogger.success(f"{media_type.upper()} PUBLISHED SUCCESSFULLY!")
            print(f"\n{C_GREEN}╔════════════════════════════════════════════════════════════╗{C_RESET}")
            print(f"{C_GREEN}║              MEDIA PUBLISHED LIVE!                       ║{C_RESET}")
            print(f"{C_GREEN}╚════════════════════════════════════════════════════════════╝{C_RESET}")
            print(f"{C_BOLD} Stream / View URL:{C_RESET} {C_CYAN}{stream_url}{C_RESET}")
            print(f"{C_BOLD} Code:{C_RESET}              {resp.get('file_code')}")
            print(f"{C_BOLD} Type:{C_RESET}              {media_type.upper()} ({meta_info.get('format')})")
            print(f"{C_GRAY} Logs saved to: {LOG_FILE}{C_RESET}\n")
        else:
            prompt_on_error(f"Upload failed (HTTP {res.status_code}): {res.text}", allow_retry=False)
    except Exception as e:
        prompt_on_error(f"Network error during upload: {e}", allow_retry=False)


def run_pipeline():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ("-h", "--help", "help"):
            print_help()
            return
        elif arg in ("--list", "-l", "list", "ls", "--all"):
            show_uploaded_media(filter_type="all")
            return
        elif arg in ("--shorts", "shorts", "-s"):
            show_uploaded_media(filter_type="shorts")
            return
        elif arg in ("--videos", "videos", "-v", "--long"):
            show_uploaded_media(filter_type="videos")
            return
        elif arg in ("--logs", "logs"):
            show_recent_logs()
            return
        elif arg in ("--tail", "-f", "tail"):
            print(f"{C_CYAN}Streaming live logs from {LOG_FILE} (Ctrl+C to stop)...{C_RESET}")
            subprocess.run(["tail", "-f", LOG_FILE])
            return
        url = arg
    else:
        url = safe_input(f"{C_GREEN}Enter YouTube or Instagram Video URL (or local file path): {C_RESET}")

    if not url:
        prompt_on_error("No input URL or file provided.", allow_retry=False)
        return

    # Direct local file upload with pre-upload verification
    if os.path.isfile(url):
        PipelineLogger.info(f"Local file detected: {url}")
        PipelineLogger.info(" Pre-upload verification: Verifying media integrity...")
        is_valid, media_type, meta_info = inspect_media_file(url)
        if not is_valid:
            PipelineLogger.error(f"[ERROR] Upload rejected! '{url}' is neither a valid image nor a video (Error: {media_type}).")
            prompt_on_error(f"Verification failed: '{os.path.basename(url)}' is not an image or video.", allow_retry=False)
            return

        PipelineLogger.success(f"[VERIFIED] Verified Media: {media_type.upper()} ({meta_info.get('codec')}, {meta_info.get('width')}x{meta_info.get('height')}, {meta_info.get('duration', 0):.1f}s)")
        handle_local_file_upload(url, media_type, meta_info)
        return

    while url:
        PipelineLogger.info(f"Target URL: {url}")

        # 1. Early canonical URL deduplication check
        existing_early = check_existing_vault_media(url)
        if existing_early:
            print_existing_vault_media(existing_early)
            choice = safe_input(f"{C_YELLOW}Media already in vault. Force re-process/re-upload? (y/N): {C_RESET}").strip().lower()
            if choice not in ("y", "yes"):
                return

        meta_res = fetch_metadata(url)
        if not meta_res:
            return
        meta, active_url = meta_res

        # 2. Comprehensive metadata deduplication check (title + duration match)
        existing_meta = check_existing_vault_media(active_url, meta=meta)
        if existing_meta:
            print_existing_vault_media(existing_meta)
            choice = safe_input(f"{C_YELLOW}Media already in vault. Force re-process/re-upload? (y/N): {C_RESET}").strip().lower()
            if choice not in ("y", "yes"):
                return

        platform = detect_platform(active_url)
        is_short, reason = is_short_media(meta, active_url, platform)

        if is_short:
            handle_short_pipeline(meta, active_url, classification_reason=reason)
        else:
            handle_long_pipeline(meta, active_url)
        break


def main():
    print_banner()
    try:
        run_pipeline()
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Process cancelled by user.{C_RESET}")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        PipelineLogger.error(f"Fatal error: {e}\n{tb}")
        prompt_on_error(f"Unexpected error: {e}\n\n{tb}", allow_retry=False)
    finally:
        # Prompt user to press enter before exiting so results and stream URLs remain visible
        if not os.getenv("TERMUX_URL_OPENER_HANDLES_PAUSE"):
            try:
                if sys.stdin.isatty() or os.path.exists("/dev/tty"):
                    print(f"\n{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")
                    safe_input(f"{C_BOLD}{C_GREEN}Press [Enter] to exit...{C_RESET}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
