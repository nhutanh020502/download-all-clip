import os
import sys
import json
import time
import uuid
import shutil
import asyncio
import threading
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Any, Optional

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as e:
    pass

import yt_dlp
from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DOWNLOADS_DIR = Path("/tmp/downloads") if IS_VERCEL else (BASE_DIR / "downloads")
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="YouTube Ultimate Downloader", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-cleanup files older than 30 minutes
def cleanup_old_files():
    try:
        now = time.time()
        for p in DOWNLOADS_DIR.iterdir():
            if p.is_file() and p.name != ".gitkeep":
                if now - p.stat().st_mtime > 1800:
                    p.unlink(missing_ok=True)
    except Exception:
        pass

tasks: Dict[str, Dict[str, Any]] = {}
task_locks: Dict[str, threading.Lock] = {}

class VideoInfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_type: str = "video"
    resolution: str = "best"
    container: str = "mp4"
    audio_format: str = "mp3"
    audio_quality: str = "320"
    download_subs: bool = False
    download_thumbnail: bool = False

class OpenFileRequest(BaseModel):
    filename: str

class DeleteFileRequest(BaseModel):
    filename: str

def format_bytes(num_bytes: Optional[int]) -> str:
    if not num_bytes:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

router = APIRouter()

@router.post("/info")
async def get_video_info(req: VideoInfoRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đường dẫn YouTube!")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }

    try:
        loop = asyncio.get_event_loop()
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, extract)
        if not info:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông tin video.")

        formats = info.get('formats', [])
        resolutions_map = {}
        res_labels = {
            4320: "8K Ultra HD",
            2160: "4K Ultra HD",
            1440: "2K Quad HD",
            1080: "Full HD 1080p",
            720: "HD 720p",
            480: "SD 480p",
            360: "360p",
            240: "240p",
            144: "144p"
        }

        for f in formats:
            h = f.get('height')
            if not h or f.get('vcodec') == 'none':
                continue
            
            fps = f.get('fps') or 30
            filesize = f.get('filesize') or f.get('filesize_approx') or 0

            if h not in resolutions_map or fps > resolutions_map[h]['fps']:
                label = res_labels.get(h, f"{h}p")
                resolutions_map[h] = {
                    'height': h,
                    'label': label,
                    'fps': fps,
                    'filesize': filesize,
                    'filesize_str': format_bytes(filesize) if filesize else "Ước tính tự động",
                    'vcodec': f.get('vcodec', 'unknown'),
                    'dynamic_range': f.get('dynamic_range', 'SDR')
                }

        sorted_res = sorted(resolutions_map.values(), key=lambda x: x['height'], reverse=True)

        direct_formats = []
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
                direct_formats.append({
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext', 'mp4'),
                    'label': f"{f.get('height')}p (Tải trực tiếp)",
                    'height': f.get('height') or 0,
                    'url': f.get('url'),
                    'filesize_str': format_bytes(f.get('filesize') or f.get('filesize_approx'))
                })
        direct_formats.sort(key=lambda x: x['height'], reverse=True)

        subtitles_available = []
        if 'subtitles' in info and info['subtitles']:
            subtitles_available.extend(list(info['subtitles'].keys()))
        if 'automatic_captions' in info and info['automatic_captions']:
            subtitles_available.extend([f"{k} (auto)" for k in info['automatic_captions'].keys() if k in ['vi', 'en', 'ja', 'ko']])

        data = {
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "duration_str": format_duration(info.get("duration")),
            "thumbnail": info.get("thumbnail"),
            "view_count": f"{info.get('view_count', 0):,}" if info.get('view_count') else "N/A",
            "upload_date": info.get("upload_date"),
            "webpage_url": info.get("webpage_url", url),
            "resolutions": sorted_res,
            "direct_formats": direct_formats[:3],
            "subtitles": subtitles_available[:10]
        }
        return JSONResponse(content=data)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi phân tích video: {str(e)}")

def progress_hook(d: dict, task_id: str):
    task = tasks.get(task_id)
    if not task:
        return

    status = d.get('status')
    if status == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes') or 0
        percent = 0.0
        if total > 0:
            percent = round((downloaded / total) * 100, 1)

        speed = d.get('speed')
        speed_str = f"{format_bytes(speed)}/s" if speed else "Đang tính..."

        eta = d.get('eta')
        eta_str = f"{eta}s" if eta else "..."

        filename = os.path.basename(d.get('filename', ''))

        task.update({
            "status": "downloading",
            "percent": percent,
            "downloaded": format_bytes(downloaded),
            "total": format_bytes(total) if total > 0 else "...",
            "speed": speed_str,
            "eta": eta_str,
            "filename": filename,
            "stage": "Đang tải luồng dữ liệu..."
        })
    elif status == 'finished':
        task.update({
            "status": "processing",
            "percent": 99.0,
            "stage": "Đang xử lý & ghép nối bằng FFmpeg..."
        })

def postprocessor_hook(d: dict, task_id: str):
    task = tasks.get(task_id)
    if not task:
        return
    postprocessor = d.get('postprocessor', '')
    status = d.get('status')
    if status == 'started':
        task.update({
            "status": "processing",
            "stage": f"FFmpeg đang xử lý: {postprocessor}..."
        })
    elif status == 'finished':
        task.update({
            "status": "processing",
            "stage": "Đang hoàn tất lưu file..."
        })

def run_download_thread(task_id: str, req: DownloadRequest):
    task = tasks[task_id]
    url = req.url
    outtmpl = str(DOWNLOADS_DIR / "%(title).200B [%(id)s].%(ext)s")

    ydl_opts: Dict[str, Any] = {
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'postprocessor_hooks': [lambda d: postprocessor_hook(d, task_id)],
        'writethumbnail': req.download_thumbnail,
    }

    if req.download_subs:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['subtitleslangs'] = ['vi', 'en']

    if req.format_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': req.audio_format,
            'preferredquality': req.audio_quality,
        }]
    else:
        res = req.resolution
        if res == "best":
            format_str = f"bestvideo+bestaudio/best"
        else:
            try:
                h = int(res)
                format_str = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            except ValueError:
                format_str = "bestvideo+bestaudio/best"

        ydl_opts['format'] = format_str
        container = req.container.lower()
        if container not in ['mp4', 'mkv', 'webm']:
            container = 'mp4'
        ydl_opts['merge_output_format'] = container

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res_info = ydl.extract_info(url, download=True)
            saved_filename = ""
            if res_info:
                expected_filename = ydl.prepare_filename(res_info)
                if req.format_type == "audio":
                    expected_filename = os.path.splitext(expected_filename)[0] + f".{req.audio_format}"
                else:
                    expected_filename = os.path.splitext(expected_filename)[0] + f".{req.container}"
                saved_filename = os.path.basename(expected_filename)

            task.update({
                "status": "completed",
                "percent": 100.0,
                "stage": "Tải xuống thành công!",
                "filename": saved_filename or task.get("filename", "video"),
                "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
    except Exception as e:
        task.update({
            "status": "error",
            "error_msg": str(e),
            "stage": f"Lỗi: {str(e)}"
        })

@router.post("/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    cleanup_old_files()
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "task_id": task_id,
        "url": req.url,
        "status": "starting",
        "percent": 0.0,
        "downloaded": "0 B",
        "total": "...",
        "speed": "0 KB/s",
        "eta": "...",
        "filename": "",
        "stage": "Đang khởi tạo trình tải...",
        "created_at": time.time()
    }

    thread = threading.Thread(target=run_download_thread, args=(task_id, req), daemon=True)
    thread.start()

    return {"task_id": task_id}

@router.get("/progress/{task_id}")
async def stream_progress(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ.")

    async def event_generator():
        while True:
            task = tasks.get(task_id)
            if not task:
                break

            data_str = json.dumps(task, ensure_ascii=False)
            yield f"data: {data_str}\n\n"

            if task.get("status") in ["completed", "error"]:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/history")
async def get_download_history():
    files = []
    if DOWNLOADS_DIR.exists():
        for p in DOWNLOADS_DIR.iterdir():
            if p.is_file() and p.name != ".gitkeep":
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "size": stat.st_size,
                    "size_str": format_bytes(stat.st_size),
                    "modified": stat.st_mtime,
                    "modified_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "ext": p.suffix.lower().replace(".", "")
                })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return JSONResponse(content={"files": files, "download_dir": str(DOWNLOADS_DIR)})

@router.post("/open-folder")
async def open_downloads_folder():
    try:
        if sys.platform == "win32" and not IS_VERCEL:
            os.startfile(DOWNLOADS_DIR)
            return {"status": "ok", "message": "Đã mở thư mục downloads!"}
        return {"status": "info", "message": "Ứng dụng đang chạy trên Cloud. Hãy tải file trực tiếp về trình duyệt!"}
    except Exception as e:
        return {"status": "info", "message": str(e)}

@router.post("/open-file")
async def open_file(req: OpenFileRequest):
    file_path = DOWNLOADS_DIR / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã hết hạn!")
    try:
        if sys.platform == "win32" and not IS_VERCEL:
            os.startfile(file_path)
            return {"status": "ok", "message": f"Đã mở file {req.filename}"}
        return {"status": "info", "message": "Đang chạy trên Cloud. Vui lòng tải file qua trình duyệt!"}
    except Exception as e:
        return {"status": "info", "message": str(e)}

@router.delete("/delete-file")
async def delete_file(req: DeleteFileRequest):
    file_path = DOWNLOADS_DIR / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại!")
    try:
        file_path.unlink()
        return {"status": "ok", "message": "Đã xóa file"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download-file/{filename}")
async def download_file_browser(filename: str):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã hết hạn!")
    
    encoded_name = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "Access-Control-Expose-Headers": "Content-Disposition"
    }
    return FileResponse(
        path=file_path, 
        filename=filename, 
        media_type="application/octet-stream",
        headers=headers
    )

# Include router under both /api and root paths so it NEVER 404s
app.include_router(router, prefix="/api")
app.include_router(router)

@app.get("/")
async def serve_index():
    for p in [BASE_DIR / "public" / "index.html", BASE_DIR / "static" / "index.html"]:
        if p.exists():
            return HTMLResponse(content=p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>YouTube Ultimate Downloader is running</h1>")
