import os
import uvicorn
import yt_dlp
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Hybrid Video Downloader API")

# --- KONFIGURASI ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = os.getenv("RAPIDAPI_HOST")
RAPID_API_URL = "https://social-media-video-downloader.p.rapidapi.com/smvd/get/all"

class VideoRequest(BaseModel):
    url: str

# --- ENGINE 1: LOCAL (yt-dlp) ---
def get_local_link(url: str):
    """
    Mencoba mengambil link video menggunakan resource server sendiri.
    Gratis, tapi mungkin gagal jika diblokir platform.
    """
    print("⚙️  Mencoba Engine Lokal (yt-dlp)...")
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'noplaylist': True,
        # Emulasi Browser untuk menghindari deteksi ringan
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Kita hanya ekstrak info, TIDAK download filenya ke server (hemat storage)
            info = ydl.extract_info(url, download=False)
            return {
                "source": "Local Server",
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "download_url": info.get('url'), # Direct Link .mp4
                "platform": info.get('extractor')
            }
    except Exception as e:
        print(f"❌ Local Engine Gagal: {e}")
        return None

# --- ENGINE 2: EXTERNAL (RapidAPI) ---
def get_rapidapi_link(url: str):
    """
    Menggunakan API pihak ketiga. Lebih ampuh tembus blokir (YouTube),
    tapi berbayar/terbatas kuota.
    """
    print("🌍 Mengalihkan ke RapidAPI...")
    
    if not RAPID_API_KEY:
        print("⚠️ API Key belum disetting!")
        return None

    querystring = {"url": url}
    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST
    }

    try:
        response = requests.get(RAPID_API_URL, headers=headers, params=querystring)
        data = response.json()
        
        # Note: Struktur response tergantung API yang Anda pilih di RapidAPI
        # Ini contoh parsing umum untuk 'Social Media Video Downloader'
        if 'links' in data:
            # Ambil kualitas terbaik
            best_link = data['links'][0]['link'] 
            return {
                "source": "RapidAPI",
                "title": data.get('title', 'Video Download'),
                "thumbnail": data.get('picture', ''),
                "download_url": best_link,
                "platform": "External"
            }
        return None
    except Exception as e:
        print(f"❌ RapidAPI Error: {e}")
        return None

# --- ROUTE UTAMA ---
@app.post("/api/download")
async def download_video(request: VideoRequest):
    url = request.url
    
    # LOGIKA HYBRID (Routing Cerdas)
    
    # Kasus Khusus: YouTube
    # YouTube server-side blocking sangat kuat. Sebaiknya langsung lempar ke API
    # untuk menghemat waktu proses server kita.
    if "youtube.com" in url or "youtu.be" in url:
        result = get_rapidapi_link(url)
        if result: return result
        # Jika API habis kuota, baru coba local sebagai usaha terakhir
        result = get_local_link(url)
        if result: return result

    # Kasus Umum: TikTok, FB, IG, Twitter
    # Coba Local dulu (Gratis), kalau gagal baru API
    else:
        # Coba Local
        result = get_local_link(url)
        if result: return result
        
        # Jika Local gagal, panggil Bala Bantuan (API)
        result = get_rapidapi_link(url)
        if result: return result

    # Jika semua cara gagal
    raise HTTPException(status_code=400, detail="Gagal mengambil video. Link mungkin private atau server diblokir.")

@app.get("/")
def home():
    return {"message": "Video Downloader API is Running. Use POST /api/download"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
