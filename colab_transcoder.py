#!/usr/bin/env python3
"""
colab_transcoder.py
Autonomous GPU-accelerated video transcoder for Google Colab CLI.
Usage with colab CLI:
  colab run --gpu T4 colab_transcoder.py --url "https://..." --server "https://akashbox.duckdns.org" --api-key "..." --profile-id 1

Workflow:
1. Installs/verifies yt-dlp on Colab VM.
2. Extracts metadata and downloads highest quality source.
3. Transcodes to multi-bitrate HLS (1080p, 720p, 480p, 360p) using NVIDIA NVENC GPU encoder (or CPU fallback).
4. Generates master.m3u8 playlist.
5. Packages HLS stream bundle into zip and uploads to server /api/media/long/upload.
"""

import os
import sys
import json
import shutil
import zipfile
import subprocess
import argparse
import urllib.request
import urllib.parse


def run_cmd(cmd, check=True):
    print(f"[RUN] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, shell=isinstance(cmd, str), check=check, text=True, capture_output=True)
    return res


def ensure_dependencies():
    print(">>> Verifying dependencies on Colab...")
    try:
        subprocess.run(["yt-dlp", "--version"], check=True, capture_output=True)
    except Exception:
        print(">>> Installing yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], check=True)

    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except Exception:
        print(">>> Installing ffmpeg...")
        subprocess.run(["apt-get", "update", "-qq"], check=False)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)


def check_gpu_nvenc():
    """Checks if h264_nvenc encoder is available on current system."""
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        return "h264_nvenc" in res.stdout
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Colab Remote Video Transcoder")
    parser.add_argument("--url", required=True, help="Video source URL")
    parser.add_argument("--server", default="https://akashbox.duckdns.org", help="Akash Server URL")
    parser.add_argument("--api-key", default="9c9cdbe35d8309877d3bbd4d568a03e2404c59675bccbe1d6d137c9f2f64f969", help="Server API Key")
    parser.add_argument("--profile-id", type=int, default=1, help="Target Profile ID")
    parser.add_argument("--profile-name", default="Default", help="Target Profile Name")
    parser.add_argument("--author", default="", help="Original Author / Channel")
    parser.add_argument("--tags", default="", help="Metadata tags")
    parser.add_argument("--is-short", action="store_true", help="Process as vertical Short Reel instead of HLS package")
    args = parser.parse_args()

    ensure_dependencies()

    work_dir = os.path.abspath("colab_work")
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir, exist_ok=True)
    os.chdir(work_dir)

    print(f"\n=======================================================")
    print(f"AKASH GPU TRANSCODER STARTED")
    print(f"URL: {args.url}")
    print(f"Server: {args.server}")
    print(f"=======================================================\n")

    # 1. Probe video info via yt-dlp
    print(">>> Probing video metadata...")
    probe_cmd = ["yt-dlp", "--dump-single-json", "--no-download", args.url]
    probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    meta = json.loads(probe_res.stdout)

    title = meta.get("title", "Untitled Video")
    duration = float(meta.get("duration", 0.0) or 0.0)
    uploader = meta.get("uploader") or meta.get("uploader_id") or args.author or "unknown"
    description = meta.get("description", "")

    # Build tags
    tags_list = []
    if uploader:
        tags_list.append(f"author:@{uploader}")
    if "instagram.com" in args.url:
        tags_list.append("platform:instagram")
    elif "youtube.com" in args.url or "youtu.be" in args.url:
        tags_list.append("platform:youtube")
    if args.tags:
        tags_list.extend([t.strip() for t in args.tags.split(",") if t.strip()])
    full_tags = ", ".join(tags_list)

    print(f"Title: {title}")
    print(f"Author: {uploader}")
    print(f"Duration: {duration}s")
    print(f"Tags: {full_tags}")

    # 2. Download source file
    source_file = os.path.join(work_dir, "source.mp4")
    print("\n>>> Downloading source video...")
    dl_cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", source_file,
        args.url
    ]
    subprocess.run(dl_cmd, check=True)

    if not os.path.exists(source_file):
        raise RuntimeError("Source file download failed")

    # 3. Extract Thumbnail
    thumb_file = os.path.join(work_dir, "thumb.jpg")
    print(">>> Generating video poster thumbnail...")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "00:00:03", "-i", source_file,
        "-vframes", "1", "-q:v", "2", thumb_file
    ], check=False)

    use_nvenc = check_gpu_nvenc()
    v_codec = "h264_nvenc" if use_nvenc else "libx264"
    preset = "p4" if use_nvenc else "veryfast"
    print(f">>> Selected FFmpeg Video Codec: {v_codec} (GPU NVENC: {use_nvenc})")

    # If processed as a Short / Reel
    if args.is_short:
        print(">>> Processing Short / Reel on Colab GPU...")
        short_out = os.path.join(work_dir, "short_opt.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", source_file,
            "-c:v", v_codec, "-preset", preset,
            "-b:v", "3500k", "-maxrate", "4000k", "-bufsize", "7000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            short_out
        ], check=True)

        upload_url = f"{args.server.rstrip('/')}/api/media/shorts/upload"
        import requests
        headers = {"x-api-key": args.api_key}
        data = {
            "username": uploader,
            "platform": "youtube",
            "title": title,
            "caption": description[:1500] if description else title
        }
        files = {}
        with open(short_out, "rb") as sf:
            files["file"] = ("short.mp4", sf, "video/mp4")
            if os.path.exists(thumb_file):
                with open(thumb_file, "rb") as tf:
                    files["thumbnail"] = ("thumb.jpg", tf, "image/jpeg")
                    resp = requests.post(upload_url, data=data, files=files, headers=headers)
            else:
                resp = requests.post(upload_url, data=data, files=files, headers=headers)

        print(f"Short Upload Response Code: {resp.status_code}")
        if resp.status_code == 200:
            print("\n =======================================================")
            print(" SHORT / REEL TRANSCODING COMPLETE & PUBLISHED LIVE!")
            print(" =======================================================\n")
        else:
            print("❌ Upload failed:", resp.text)
            sys.exit(1)
        return

    # 4. Transcode to Multi-Bitrate HLS (Up to 4K / 2160p)
    hls_dir = os.path.join(work_dir, "hls")
    os.makedirs(hls_dir, exist_ok=True)

    # Probe source resolution using ffprobe
    source_h = 1080
    try:
        p_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=height",
            "-of", "csv=p=0", source_file
        ]
        p_res = subprocess.run(p_cmd, capture_output=True, text=True)
        out_h = p_res.stdout.strip()
        if out_h.isdigit():
            source_h = int(out_h)
            print(f">>> Probed Source Video Height: {source_h}p")
    except Exception as e:
        print(f">>> Height probe warning: {e}")

    ALL_QUALITIES = [
        {"name": "2160p", "w": 3840, "h": 2160, "bitrate": "16000k", "maxrate": "18000k", "buf": "32000k", "audio": "256k"},
        {"name": "1440p", "w": 2560, "h": 1440, "bitrate": "8000k",  "maxrate": "9500k",  "buf": "16000k", "audio": "192k"},
        {"name": "1080p", "w": 1920, "h": 1080, "bitrate": "4200k",  "maxrate": "5000k",  "buf": "8500k",  "audio": "192k"},
        {"name": "720p",  "w": 1280, "h": 720,  "bitrate": "2200k",  "maxrate": "2600k",  "buf": "4500k",  "audio": "128k"},
        {"name": "480p",  "w": 854,  "h": 480,  "bitrate": "1000k",  "maxrate": "1200k",  "buf": "2000k",  "audio": "96k"},
        {"name": "360p",  "w": 640,  "h": 360,  "bitrate": "600k",   "maxrate": "750k",   "buf": "1200k",  "audio": "64k"},
        {"name": "240p",  "w": 426,  "h": 240,  "bitrate": "350k",   "maxrate": "450k",   "buf": "700k",   "audio": "64k"},
        {"name": "144p",  "w": 256,  "h": 144,  "bitrate": "180k",   "maxrate": "240k",   "buf": "400k",   "audio": "48k"}
    ]

    # Generate all qualities supported by source video (up to 4K / 2160p)
    qualities = [q for q in ALL_QUALITIES if q["h"] <= source_h]
    if not qualities:
        qualities = [ALL_QUALITIES[-1]]
    available_qualities_str = ", ".join([q["name"] for q in qualities])
    print(f">>> Target Multi-Bitrate Tiers ({len(qualities)} levels): {available_qualities_str}")

    master_content = ["#EXTM3U", "#EXT-X-VERSION:3"]

    for q in qualities:
        q_dir = os.path.join(hls_dir, q["name"])
        os.makedirs(q_dir, exist_ok=True)
        playlist_path = os.path.join(q_dir, "prog.m3u8")
        segment_pattern = os.path.join(q_dir, "seg_%03d.ts")

        print(f">>> Transcoding {q['name']} stream...")
        scale_filter = f"scale=w={q['w']}:h={q['h']}:force_original_aspect_ratio=decrease,pad={q['w']}:{q['h']}:(ow-iw)/2:(oh-ih)/2"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", source_file,
            "-vf", scale_filter,
            "-c:v", v_codec,
            "-b:v", q["bitrate"],
            "-maxrate", q["maxrate"],
            "-bufsize", q["buf"],
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", q["audio"],
            "-ar", "44100",
            "-f", "hls",
            "-hls_time", "4",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", segment_pattern,
            playlist_path
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        bandwidth = int(q["bitrate"].replace("k", "")) * 1000 + int(q["audio"].replace("k", "")) * 1000
        master_content.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={q["w"]}x{q["h"]},NAME="{q["name"]}"')
        master_content.append(f'{q["name"]}/prog.m3u8')

    # Write master.m3u8
    master_file = os.path.join(hls_dir, "master.m3u8")
    with open(master_file, "w") as f:
        f.write("\n".join(master_content) + "\n")

    print(">>> Multi-bitrate HLS package created successfully!")

    # 5. Compress HLS package to ZIP
    print(">>> Compressing HLS package...")
    zip_path = os.path.join(work_dir, "hls_bundle.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(hls_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, hls_dir)
                zf.write(abs_path, rel_path)

    # 6. Upload bundle to DevOS Server
    print(">>> Uploading HLS bundle to Akash Server...")
    upload_url = f"{args.server.rstrip('/')}/api/media/long/upload"

    import requests
    headers = {"x-api-key": args.api_key}
    data = {
        "profile_id": args.profile_id,
        "profile_name": args.profile_name,
        "title": title,
        "description": description,
        "tags": full_tags,
        "original_author": uploader,
        "duration": duration,
        "available_qualities": available_qualities_str,
        "source_url": args.url,
        "is_hls_package": "true"
    }

    files = {}
    with open(zip_path, "rb") as zf:
        files["file"] = ("bundle.zip", zf, "application/zip")
        if os.path.exists(thumb_file):
            with open(thumb_file, "rb") as tf:
                files["thumbnail"] = ("thumb.jpg", tf, "image/jpeg")
                resp = requests.post(upload_url, data=data, files=files, headers=headers)
        else:
            resp = requests.post(upload_url, data=data, files=files, headers=headers)

    print(f"Server Response Code: {resp.status_code}")
    res_json = resp.json()
    print("Response:", json.dumps(res_json, indent=2))

    if resp.status_code == 200:
        watch_url = f"{args.server.rstrip('/')}{res_json.get('watch_url')}"
        print("\n=======================================================")
        print(f"TRANSCODING COMPLETE & STREAM LIVE")
        print(f"Watch URL: {watch_url}")
        print("=======================================================\n")
    else:
        print("[ERROR] Upload failed:", resp.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
