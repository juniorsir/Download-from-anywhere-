#!/usr/bin/env python3
"""
colab_transcoder.py
Autonomous GPU-accelerated video transcoder for Google Colab CLI.
Usage with colab CLI:
  colab run --gpu T4 colab_transcoder.py --url "https://..." --server "https://akashbox.duckdns.org" --api-key "..." --profile-id 1

Workflow:
1. Installs/verifies nodejs (for yt-dlp JS engine), ffmpeg, and yt-dlp on Colab VM.
2. Extracts metadata and downloads highest quality source (up to 4K / 2160p 60fps HDR).
3. Transcodes to multi-bitrate HLS (2160p, 1440p, 1080p, 720p, 480p, 360p, 240p, 144p) using NVIDIA NVENC GPU encoder (or CPU fallback).
4. Generates master.m3u8 playlist.
5. Packages HLS stream bundle into zip and uploads to Akash server /api/media/long/upload.
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
    packages_to_install = []
    try:
        subprocess.run(["node", "-v"], check=True, capture_output=True)
    except Exception:
        packages_to_install.append("nodejs")

    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except Exception:
        packages_to_install.append("ffmpeg")

    if packages_to_install:
        print(f">>> Installing system packages: {packages_to_install}...")
        subprocess.run(["apt-get", "update", "-qq"], check=False)
        subprocess.run(["apt-get", "install", "-y", "-qq"] + packages_to_install, check=True)

    print(">>> Upgrading yt-dlp and requests to latest versions...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "-q", "yt-dlp", "requests"], check=True)


def check_gpu_nvenc():
    """Checks if h264_nvenc encoder is available on current system."""
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        return "h264_nvenc" in res.stdout
    except Exception:
        return False


def run_ffmpeg_with_progress(cmd, label):
    """Executes FFmpeg with real-time progress streaming."""
    import time
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )
    buf = ""
    error_lines = []
    last_print_time = time.time()
    while True:
        ch = proc.stderr.read(1)
        if not ch and proc.poll() is not None:
            break
        if ch in ("\r", "\n"):
            line = buf.strip()
            if line:
                if "frame=" in line or "time=" in line or "fps=" in line:
                    now = time.time()
                    if now - last_print_time >= 2.0:
                        sys.stdout.write(f"  [{label}] {line}\n")
                        sys.stdout.flush()
                        last_print_time = now
                else:
                    error_lines.append(line)
            buf = ""
        else:
            buf += ch

    proc.wait()
    sys.stdout.flush()
    return proc.returncode, "\n".join(error_lines[-10:])


def probe_metadata(url, default_author=""):
    print(">>> Probing video metadata...")
    commands = [
        [sys.executable, "-m", "yt_dlp", "--extractor-args", "youtube:player_client=tv_embedded", "--dump-single-json", "--no-download", url],
        [sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "--remote-components", "ejs:github", "--dump-single-json", "--no-download", url],
        [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--no-download", url]
    ]
    last_err = ""
    for cmd in commands:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                return json.loads(res.stdout)
            except Exception as e:
                last_err = str(e)
        else:
            last_err = res.stderr.strip() if res.stderr else "Unknown error"

    print(f"[WARN] Metadata probe warning: {last_err[:200]}")
    return {"title": "Uploaded Video", "uploader": default_author, "duration": 0.0}


def download_source_video(url, output_path):
    print("\n>>> Downloading highest resolution source video...")
    commands = [
        [
            sys.executable, "-m", "yt_dlp",
            "--extractor-args", "youtube:player_client=tv_embedded",
            "-f", "bestvideo[protocol^=http]+bestaudio[protocol^=http]/bestvideo+bestaudio/best",
            "--format-sort", "res,fps,proto:https",
            "--merge-output-format", "mp4",
            "--newline",
            "--progress",
            "-o", output_path,
            url
        ],
        [
            sys.executable, "-m", "yt_dlp",
            "--extractor-args", "youtube:player_client=tv_embedded",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--newline",
            "--progress",
            "-o", output_path,
            url
        ],
        [
            sys.executable, "-m", "yt_dlp",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            "-f", "bestvideo[protocol^=http]+bestaudio[protocol^=http]/bestvideo+bestaudio/best",
            "--format-sort", "res,fps,proto:https",
            "--merge-output-format", "mp4",
            "--newline",
            "--progress",
            "-o", output_path,
            url
        ],
        [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--newline",
            "--progress",
            "-o", output_path,
            url
        ]
    ]
    for idx, cmd in enumerate(commands, 1):
        print(f">>> Download attempt {idx}/{len(commands)}...")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait()

        if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"\n>>> Download succeeded on attempt {idx} (Size: {os.path.getsize(output_path) / (1024*1024):.1f} MB)")
            return True
        else:
            print(f"\n>>> Download attempt {idx} failed with exit code {proc.returncode}. Trying next method...")

    return False


def probe_video_height(video_file, fallback_h=1080):
    try:
        p_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=height",
            "-of", "csv=p=0", video_file
        ]
        p_res = subprocess.run(p_cmd, capture_output=True, text=True)
        out_h = p_res.stdout.strip()
        if out_h.isdigit() and int(out_h) > 0:
            return int(out_h)
    except Exception as e:
        print(f">>> Height probe warning: {e}")
    return fallback_h


def notify_server_progress(server_url, api_key, file_code, progress_msg):
    if not file_code:
        return
    try:
        import requests
        requests.post(
            f"{server_url.rstrip('/')}/api/media/long/transcode-progress",
            headers={"x-api-key": api_key},
            data={"file_code": file_code, "progress": progress_msg},
            timeout=5
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Akash Colab GPU Video Transcoder")
    parser.add_argument("--url", required=True, help="Video source URL")
    parser.add_argument("--server", default="https://akashbox.duckdns.org", help="Akash Server URL")
    parser.add_argument("--api-key", default="9c9cdbe35d8309877d3bbd4d568a03e2404c59675bccbe1d6d137c9f2f64f969", help="Server API Key")
    parser.add_argument("--profile-id", type=int, default=1, help="Target Profile ID")
    parser.add_argument("--profile-name", default="Default", help="Target Profile Name")
    parser.add_argument("--author", default="", help="Original Author / Channel")
    parser.add_argument("--tags", default="", help="Metadata tags")
    parser.add_argument("--is-short", action="store_true", help="Process as vertical Short Reel instead of HLS package")
    parser.add_argument("--file-code", default="", help="Pre-registered Vault File Code")
    args = parser.parse_args()

    ensure_dependencies()

    work_dir = os.path.abspath("colab_work")
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir, exist_ok=True)
    os.chdir(work_dir)

    print("\n=======================================================")
    print("AKASH GPU TRANSCODER STARTED")
    print(f"URL: {args.url}")
    print(f"Server: {args.server}")
    print("=======================================================\n")

    # 1. Probe video info via yt-dlp
    meta = probe_metadata(args.url, default_author=args.author)

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
    success = download_source_video(args.url, source_file)
    if not success or not os.path.exists(source_file):
        raise RuntimeError("Source file download failed on Colab")

    # 3. Extract Thumbnail
    thumb_file = os.path.join(work_dir, "thumb.jpg")
    print(">>> Generating video poster thumbnail...")
    subprocess.run([
        "ffmpeg", "-y", "-ss", "00:00:03", "-i", source_file,
        "-vframes", "1", "-q:v", "2", thumb_file
    ], check=False)

    use_nvenc = check_gpu_nvenc()
    v_codec = "h264_nvenc" if use_nvenc else "libx264"
    preset = "p1" if use_nvenc else "veryfast"
    print(f">>> Selected FFmpeg Video Codec: {v_codec} (GPU NVENC: {use_nvenc})")

    # If processed as a Short / Reel
    if args.is_short:
        print(">>> Processing Short / Reel on Colab GPU...")
        short_out = os.path.join(work_dir, "short_opt.mp4")
        short_cmd = [
            "ffmpeg", "-y", "-i", source_file,
            "-vf", "format=yuv420p",
            "-c:v", v_codec,
            "-pix_fmt", "yuv420p",
            "-preset", preset,
            "-b:v", "3500k", "-maxrate", "4000k", "-bufsize", "7000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            short_out
        ]
        rc, err = run_ffmpeg_with_progress(short_cmd, "Short")
        if rc != 0:
            print(f">>> GPU NVENC short transcode failed (Code {rc}). Retrying with CPU libx264...")
            fb_short_cmd = [
                "ffmpeg", "-y", "-i", source_file,
                "-vf", "format=yuv420p",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-b:v", "3500k", "-maxrate", "4000k", "-bufsize", "7000k",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                short_out
            ]
            fb_rc, fb_err = run_ffmpeg_with_progress(fb_short_cmd, "Short (CPU)")
            if fb_rc != 0:
                raise RuntimeError(f"FFmpeg failed to transcode Short: {fb_err}")

        upload_url = f"{args.server.rstrip('/')}/api/media/shorts/upload"
        import requests
        headers = {"x-api-key": args.api_key}
        data = {
            "username": uploader,
            "platform": "youtube",
            "title": title,
            "caption": description[:1500] if description else title,
            "duration": duration,
            "source_url": args.url
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
            print("\n=======================================================")
            print("SHORT / REEL TRANSCODING COMPLETE & PUBLISHED LIVE!")
            print("=======================================================\n")
        else:
            print("[ERROR] Upload failed:", resp.text)
            sys.exit(1)
        return

    # 4. Transcode to Multi-Bitrate HLS (Up to 4K / 2160p)
    hls_dir = os.path.join(work_dir, "hls")
    os.makedirs(hls_dir, exist_ok=True)

    # Probe source resolution directly from source file
    source_h = probe_video_height(source_file, fallback_h=int(meta.get("height") or 2160))
    print(f">>> Probed Source Video Height: {source_h}p")

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

    base_1080p_file = None
    if source_h > 1080:
        base_1080p_file = os.path.join(work_dir, "base_1080p.mp4")

    for idx, q in enumerate(qualities, 1):
        q_dir = os.path.join(hls_dir, q["name"])
        os.makedirs(q_dir, exist_ok=True)
        playlist_path = os.path.join(q_dir, "prog.m3u8")
        segment_pattern = os.path.join(q_dir, "seg_%03d.ts")

        progress_text = f"Transcoding {q['name']} stream ({idx}/{len(qualities)})..."
        print(f">>> {progress_text}")
        notify_server_progress(args.server, args.api_key, args.file_code, progress_text)

        scale_filter = f"scale=w={q['w']}:h={q['h']}:force_original_aspect_ratio=decrease,pad={q['w']}:{q['h']}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"

        if q["name"] == "1080p" and base_1080p_file:
            print(">>> Generating optimized 1080p master for rapid multi-tier downscaling...")
            gen_base_cmd = [
                "ffmpeg", "-y", "-i", source_file,
                "-vf", scale_filter,
                "-c:v", v_codec,
                "-pix_fmt", "yuv420p",
                "-preset", preset,
                "-b:v", q["bitrate"],
                "-maxrate", q["maxrate"],
                "-bufsize", q["buf"],
                "-c:a", "aac",
                "-b:a", q["audio"],
                "-ar", "44100",
                base_1080p_file
            ]
            rc, err = run_ffmpeg_with_progress(gen_base_cmd, "1080p Master")
            if rc != 0:
                print(f">>> GPU NVENC 1080p base failed (Code {rc}). Retrying with CPU libx264...")
                fb_gen_cmd = [
                    "ffmpeg", "-y", "-i", source_file,
                    "-vf", scale_filter,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-b:v", q["bitrate"],
                    "-maxrate", q["maxrate"],
                    "-bufsize", q["buf"],
                    "-c:a", "aac",
                    "-b:a", q["audio"],
                    "-ar", "44100",
                    base_1080p_file
                ]
                fb_rc, fb_err = run_ffmpeg_with_progress(fb_gen_cmd, "1080p Master (CPU)")
                if fb_rc != 0:
                    raise RuntimeError(f"FFmpeg failed to generate 1080p master: {fb_err}")

            # Instant HLS segmentation using copy (takes ~1-2 seconds)
            hls_pack_cmd = [
                "ffmpeg", "-y", "-i", base_1080p_file,
                "-c", "copy",
                "-f", "hls",
                "-hls_time", "4",
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", segment_pattern,
                playlist_path
            ]
            subprocess.run(hls_pack_cmd, check=True)
        else:
            # 2160p, 1440p (from source) or sub-HD <= 720p (from fast 1080p master)
            input_file = source_file
            if q["h"] <= 720 and base_1080p_file and os.path.exists(base_1080p_file):
                input_file = base_1080p_file

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_file,
                "-vf", scale_filter,
                "-c:v", v_codec,
                "-pix_fmt", "yuv420p",
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
            rc, err = run_ffmpeg_with_progress(ffmpeg_cmd, q["name"])
            if rc != 0:
                print(f">>> GPU NVENC failed for {q['name']} (Code {rc}). Retrying with CPU libx264...")
                fallback_cmd = [
                    "ffmpeg", "-y", "-i", input_file,
                    "-vf", scale_filter,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-b:v", q["bitrate"],
                    "-maxrate", q["maxrate"],
                    "-bufsize", q["buf"],
                    "-c:a", "aac",
                    "-b:a", q["audio"],
                    "-ar", "44100",
                    "-f", "hls",
                    "-hls_time", "4",
                    "-hls_playlist_type", "vod",
                    "-hls_segment_filename", segment_pattern,
                    playlist_path
                ]
                fb_rc, fb_err = run_ffmpeg_with_progress(fallback_cmd, f"{q['name']} (CPU)")
                if fb_rc != 0:
                    print(f"Error on {q['name']}: {fb_err[-400:]}")
                    raise RuntimeError(f"FFmpeg failed to transcode tier {q['name']}")

        bandwidth = int(q["bitrate"].replace("k", "")) * 1000 + int(q["audio"].replace("k", "")) * 1000
        master_content.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={q["w"]}x{q["h"]},NAME="{q["name"]}"')
        master_content.append(f'{q["name"]}/prog.m3u8')

    # Write master.m3u8
    master_file = os.path.join(hls_dir, "master.m3u8")
    with open(master_file, "w") as f:
        f.write("\n".join(master_content) + "\n")

    print(">>> Multi-bitrate HLS package created successfully!")

    # 5. Compress HLS package to ZIP (using fast ZIP_STORED)
    notify_server_progress(args.server, args.api_key, args.file_code, "Packaging multi-bitrate HLS bundle...")
    print(">>> Packaging HLS bundle (fast archive mode)...")
    zip_path = os.path.join(work_dir, "hls_bundle.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for root, dirs, files in os.walk(hls_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, hls_dir)
                zf.write(abs_path, rel_path)

    # 6. Upload bundle to Akash Server
    notify_server_progress(args.server, args.api_key, args.file_code, "Uploading HLS package to Akash Vault...")
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
        "is_hls_package": "true",
        "file_code": args.file_code
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
        print("TRANSCODING COMPLETE & STREAM LIVE")
        print(f"Watch URL: {watch_url}")
        print("=======================================================\n")
    else:
        print("[ERROR] Upload failed:", resp.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
