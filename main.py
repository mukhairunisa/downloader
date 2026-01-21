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
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="Multi-Format Video Downloader")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- KONFIGURASI API ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = "social-media-video-downloader.p.rapidapi.com"

class VideoRequest(BaseModel):
    url: str

# --- HELPER ---
def extract_youtube_id(url: str):
    regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(regex, url)
    return match.group(1) if match else None

# --- ENGINE 1: LOCAL (yt-dlp) ---
# Kita sesuaikan agar outputnya format LIST juga, biar frontend tidak bingung
def get_local_link(url: str):
    print(f"⚙️  [Local Engine] Memproses: {url}")
    ydl_opts = {
        'format': 'best', # Default ambil yang terbaik saja
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
                "downloads": [
                    {
                        "label": "Best Quality",
                        "size": "Auto",
                        "ext": info.get('ext', 'mp4'),
                        "url": info.get('url'),
                        "type": "video"
                    }
                ]
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

    # Request Logic
    if "youtube.com" in url or "youtu.be" in url:
        video_id = extract_youtube_id(url)
        if not video_id: return None
        
        api_url = f"https://{RAPID_API_HOST}/youtube/v3/video/details"
        querystring = {
            "videoId": video_id,
            "renderableFormats": "720p,1080p", # Request format HD
            "urlAccess": "proxied", 
            "getTranscript": "false"
        }
    else:
        # Fallback TikTok/IG
        api_url = f"https://{RAPID_API_HOST}/smvd/get/all"
        querystring = {"url": url}

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        data = response.json()
        
        # --- PARSING MULTI-FORMAT ---
        
        metadata = data.get('metadata', {})
        title = metadata.get('title', 'Video Download')
        thumbnail = metadata.get('thumbnailUrl', '')
        
        downloads_list = []

        # 1. PARSING VIDEO (Cari 1080p, 720p, 480p, 360p)
        if 'contents' in data and len(data['contents']) > 0:
            content = data['contents'][0]
            
            # Loop semua video yang tersedia
            if 'videos' in content:
                for v in content['videos']:
                    label = v.get('label', 'Video') # Contoh: "1080p", "720p"
                    
                    # Filter: Hanya ambil kualitas yang diinginkan
                    if label in ['1080p', '720p', '480p', '360p']:
                        downloads_list.append({
                            "label": label,
                            "size": v.get('metadata', {}).get('content_length_text', 'N/A'),
                            "ext": "mp4",
                            "url": v['url'],
                            "type": "video"
                        })

            # 2. PARSING AUDIO (Audio Only)
            if 'audios' in content:
                for a in content['audios']:
                    # Biasanya kita ambil yang kualitas Medium/High saja
                    quality = a.get('metadata', {}).get('audio_quality', 'AUDIO')
                    if quality != "AUDIO_QUALITY_LOW": # Filter low quality audio
                        downloads_list.append({
                            "label": "Audio Only",
                            "size": a.get('metadata', {}).get('content_length_text', 'N/A'),
                            "ext": "mp3",
                            "url": a['url'],
                            "type": "audio"
                        })

        if len(downloads_list) > 0:
            return {
                "source": "RapidAPI",
                "title": title,
                "thumbnail": thumbnail,
                "downloads": downloads_list # Mengembalikan list, bukan single url
            }
        
        return None

    except Exception as e:
        print(f"❌ [API Engine] Error: {e}")
        return None

# --- ROUTES ---
@app.post("/api/download")
async def download_video_api(request: VideoRequest):
    url = request.url
    result = None

    if "youtube.com" in url or "youtu.be" in url:
        result = get_rapidapi_link(url)
    else:
        result = get_local_link(url)
        if not result:
            result = get_rapidapi_link(url)

    if result:
        return result
    else:
        raise HTTPException(status_code=400, detail="Gagal mengambil video.")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
