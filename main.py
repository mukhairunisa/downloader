import os
import uvicorn
import yt_dlp
import requests
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()

app = FastAPI(title="All-in-One Video Downloader (Debug Mode)")

# 2. Setup Folder Templates
templates = Jinja2Templates(directory="templates")

# --- KONFIGURASI API EKSTERNAL ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = os.getenv("RAPIDAPI_HOST")
# URL Default (Social Media Video Downloader)
RAPID_API_URL = "https://social-media-video-downloader.p.rapidapi.com/smvd/get/all"

class VideoRequest(BaseModel):
    url: str

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
                "source": "Local Server (yt-dlp)",
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "download_url": info.get('url'),
                "platform": info.get('extractor')
            }
    except Exception as e:
        # Kita hanya print error pendek agar log tidak penuh sampah
        error_msg = str(e).split('\n')[0] 
        print(f"❌ [Local Engine] Gagal: {error_msg}...")
        return None

# --- ENGINE 2: EXTERNAL (RapidAPI) ---
# FUNGSI INI SUDAH DITAMBAHKAN DEBUG LOG
def get_rapidapi_link(url: str):
    print("🌍 [API Engine] Mengalihkan ke RapidAPI...")
    
    if not RAPID_API_KEY:
        print("⚠️  CRITICAL: API Key belum disetting di Heroku Config Vars!")
        return None

    querystring = {"url": url}
    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST
    }

    try:
        print(f"   ➡️ Requesting to URL: {RAPID_API_URL}")
        response = requests.get(RAPID_API_URL, headers=headers, params=querystring)
        
        # --- DEBUGGING AREA (Cek Log Heroku Bagian Ini) ---
        try:
            data = response.json()
            print(f"   📩 RAW RESPONSE API: {json.dumps(data)}") # Ini akan mencetak jawaban asli API
        except:
            print(f"   ❌ Gagal parsing JSON. Status Code: {response.status_code}")
            print(f"   ❌ Isi Response: {response.text}")
            return None
        # --------------------------------------------------

        # Cek Error dari API (Biasanya kalau salah key ada field 'message')
        if "message" in data and not "links" in data:
            print(f"   ⚠️ API Error Message: {data['message']}")
            return None

        # Logika Parsing (Sesuaikan dengan Social Media Video Downloader)
        if 'links' in data and len(data['links']) > 0:
            best_link = data['links'][0]['link']
            return {
                "source": "RapidAPI",
                "title": data.get('title', 'Video Downloaded'),
                "thumbnail": data.get('picture', ''),
                "download_url": best_link,
                "platform": "External API"
            }
        
        print("   ❌ Key 'links' tidak ditemukan atau kosong.")
        return None

    except Exception as e:
        print(f"❌ [API Engine] Connection Error: {e}")
        return None

# --- ROUTES ---

@app.post("/api/download")
async def download_video_api(request: VideoRequest):
    url = request.url
    result = None

    print(f"\n📥 New Request: {url}")

    # LOGIKA PRIORITAS
    # 1. Jika YouTube, Pakai API Dulu (Karena Local pasti gagal di Heroku)
    if "youtube.com" in url or "youtu.be" in url:
        result = get_rapidapi_link(url)
        if not result:
            print("   ↪️ API gagal, mencoba fallback ke Local...")
            result = get_local_link(url)
            
    # 2. Jika TikTok/Lainnya, Coba Local Dulu (Lebih Cepat & Gratis)
    else:
        result = get_local_link(url)
        if not result:
            print("   ↪️ Local gagal, mencoba fallback ke API...")
            result = get_rapidapi_link(url)

    if result:
        print("✅ Success!")
        return result
    else:
        print("❌ All engines failed.")
        raise HTTPException(status_code=400, detail="Gagal mengambil video. Cek Log Server untuk detail debug.")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
