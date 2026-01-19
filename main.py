import os
import uvicorn
import yt_dlp
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# 1. Load Environment Variables (API Key, dll)
load_dotenv()

app = FastAPI(title="All-in-One Video Downloader")

# 2. Setup Folder Templates (Untuk Frontend HTML)
# Pastikan Anda sudah membuat folder 'templates' dan file 'index.html' di dalamnya
templates = Jinja2Templates(directory="templates")

# --- KONFIGURASI API EKSTERNAL ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = os.getenv("RAPIDAPI_HOST")
# URL ini bisa berubah tergantung provider API yang Anda pilih di RapidAPI
RAPID_API_URL = "https://social-media-video-downloader.p.rapidapi.com"

# Model Data Input
class VideoRequest(BaseModel):
    url: str

# --- ENGINE 1: LOCAL (yt-dlp) ---
# Gratis, menggunakan resources server sendiri.
def get_local_link(url: str):
    print(f"⚙️  [Local Engine] Memproses: {url}")
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'noplaylist': True,
        # Menyamar sebagai Browser Chrome agar tidak diblokir ringan
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Ekstrak info tanpa download file (hemat storage server)
            info = ydl.extract_info(url, download=False)
            return {
                "source": "Local Server",
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "download_url": info.get('url'), # Direct link ke file video
                "platform": info.get('extractor')
            }
    except Exception as e:
        print(f"❌ [Local Engine] Gagal: {e}")
        return None

# --- ENGINE 2: EXTERNAL (RapidAPI) ---
# Berbayar/Terbatas, tapi lebih ampuh tembus blokir (terutama YouTube).
def get_rapidapi_link(url: str):
    print("🌍 [API Engine] Mengalihkan ke RapidAPI...")
    
    if not RAPID_API_KEY:
        print("⚠️  API Key belum disetting di .env atau Config Vars!")
        return None

    querystring = {"url": url}
    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST
    }

    try:
        response = requests.get(RAPID_API_URL, headers=headers, params=querystring)
        data = response.json()
        
        # Parsing JSON response (Sesuaikan dengan dokumentasi API yang Anda pakai)
        if 'links' in data:
            # Mengambil link kualitas terbaik (biasanya index pertama)
            best_link = data['links'][0]['link']
            return {
                "source": "RapidAPI",
                "title": data.get('title', 'Video Downloaded'),
                "thumbnail": data.get('picture', ''),
                "download_url": best_link,
                "platform": "External API"
            }
        return None
    except Exception as e:
        print(f"❌ [API Engine] Error: {e}")
        return None

# --- ROUTES ---

# 1. Route API (Logic Download)
@app.post("/api/download")
async def download_video_api(request: VideoRequest):
    url = request.url
    result = None

    # LOGIKA ROUTING CERDAS
    
    # KASUS A: YouTube (Sering memblokir server datacenter/Heroku)
    # Langsung lempar ke API eksternal untuk hemat waktu dan menghindari error
    if "youtube.com" in url or "youtu.be" in url:
        result = get_rapidapi_link(url)
        # Jika API gagal/habis kuota, baru coba cara lokal sebagai cadangan
        if not result:
            result = get_local_link(url)

    # KASUS B: TikTok, Facebook, Instagram, Twitter
    # Coba cara Lokal dulu (Gratis & Cepat)
    else:
        result = get_local_link(url)
        # Jika cara lokal gagal (kena blokir/captcha), baru minta bantuan API
        if not result:
            result = get_rapidapi_link(url)

    # HASIL AKHIR
    if result:
        return result
    else:
        # Jika kedua cara gagal
        raise HTTPException(status_code=400, detail="Gagal mengambil video. Link mungkin private, dihapus, atau server sedang sibuk.")

# 2. Route Frontend (Menampilkan HTML)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Render file index.html yang ada di folder templates
    return templates.TemplateResponse("index.html", {"request": request})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Konfigurasi Port untuk Heroku
    # Heroku akan menyuntikkan variable PORT ke environment
    port = int(os.environ.get("PORT", 8000))
    
    # Jalankan Server
    uvicorn.run(app, host="0.0.0.0", port=port)
