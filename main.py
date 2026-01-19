import os
import uvicorn
import yt_dlp
import requests
import json
import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Hybrid Video Downloader (Final Fix)")

templates = Jinja2Templates(directory="templates")

# --- KONFIGURASI API ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = "social-media-video-downloader.p.rapidapi.com"

class VideoRequest(BaseModel):
    url: str

# --- HELPER: Ekstrak ID YouTube ---
def extract_youtube_id(url: str):
    # Pola untuk berbagai jenis link YouTube (Shorts, Watch, youtu.be)
    regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(regex, url)
    return match.group(1) if match else None

# --- ENGINE 1: LOCAL (yt-dlp) ---
def get_local_link(url: str):
    print(f"⚙️  [Local Engine] Memproses: {url}")
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "source": "Local Server",
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "download_url": info.get('url'),
                "platform": info.get('extractor')
            }
    except Exception:
        return None

# --- ENGINE 2: EXTERNAL (RapidAPI) ---
def get_rapidapi_link(url: str):
    print("🌍 [API Engine] Mengalihkan ke RapidAPI...")
    
    if not RAPID_API_KEY:
        print("⚠️  API Key belum disetting!")
        return None

    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST
    }

    # --- LOGIKA REQUEST ---
    # API Anda memiliki endpoint khusus untuk YouTube
    if "youtube.com" in url or "youtu.be" in url:
        video_id = extract_youtube_id(url)
        if not video_id: return None
        
        api_url = f"https://{RAPID_API_HOST}/youtube/v3/video/details"
        querystring = {
            "videoId": video_id,
            "renderableFormats": "720p,highres", 
            "urlAccess": "proxied", 
            "getTranscript": "false"
        }
    else:
        # Fallback untuk TikTok/IG (Menggunakan endpoint umum)
        api_url = f"https://{RAPID_API_HOST}/smvd/get/all"
        querystring = {"url": url}

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        data = response.json()
        
        # --- LOGIKA PARSING BARU (SESUAI LOG JSON ANDA) ---
        
        # 1. Ambil Metadata (Judul & Gambar)
        metadata = data.get('metadata', {})
        title = metadata.get('title', 'Video Download')
        thumbnail = metadata.get('thumbnailUrl', '')

        # 2. Ambil Link Video
        # Struktur JSON Anda: data['contents'][0]['videos'][0]['url']
        download_url = None
        
        if 'contents' in data and len(data['contents']) > 0:
            content_item = data['contents'][0]
            if 'videos' in content_item and len(content_item['videos']) > 0:
                # Ambil video pertama (biasanya kualitas tertinggi/1080p sesuai urutan JSON)
                download_url = content_item['videos'][0]['url']
        
        # Cek apakah berhasil mendapatkan URL
        if download_url:
            return {
                "source": "RapidAPI",
                "title": title,
                "thumbnail": thumbnail,
                "download_url": download_url,
                "platform": "YouTube (API)"
            }
        
        print("❌ Gagal Parsing: Tidak ada link video di dalam 'contents'")
        return None

    except Exception as e:
        print(f"❌ [API Engine] Error: {e}")
        return None

# --- ROUTES ---
@app.post("/api/download")
async def download_video_api(request: VideoRequest):
    url = request.url
    result = None

    # Routing Cerdas
    if "youtube.com" in url or "youtu.be" in url:
        # YouTube wajib pakai API (Local diblokir Heroku)
        result = get_rapidapi_link(url)
    else:
        # TikTok/Lainnya coba Local dulu (Gratis)
        result = get_local_link(url)
        if not result:
            result = get_rapidapi_link(url)

    if result:
        return result
    else:
        raise HTTPException(status_code=400, detail="Gagal mengambil video. Pastikan link valid.")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
