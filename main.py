import os
import uvicorn
import yt_dlp
import requests
import json
import re  # <--- Tambahan untuk Regex
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Hybrid Video Downloader (Fix YouTube API)")

templates = Jinja2Templates(directory="templates")

# --- KONFIGURASI API ---
RAPID_API_KEY = os.getenv("RAPIDAPI_KEY")
RAPID_API_HOST = "social-media-video-downloader.p.rapidapi.com" # Host sesuai snippet Anda

class VideoRequest(BaseModel):
    url: str

# --- HELPER: Ekstrak ID YouTube ---
def extract_youtube_id(url: str):
    """
    Mengambil ID video dari URL Youtube (Shorts/Watch/Mobile)
    Contoh: https://youtu.be/z9oV-6-eP3Y -> z9oV-6-eP3Y
    """
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
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        print(f"❌ [Local Engine] Gagal: {error_msg}...")
        return None

# --- ENGINE 2: EXTERNAL (RapidAPI - Modified) ---
def get_rapidapi_link(url: str):
    print("🌍 [API Engine] Mengalihkan ke RapidAPI...")
    
    if not RAPID_API_KEY:
        print("⚠️  API Key belum disetting!")
        return None

    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST
    }

    # --- LOGIKA KHUSUS BERDASARKAN URL ---
    
    # KASUS 1: YOUTUBE (Sesuai snippet Anda)
    if "youtube.com" in url or "youtu.be" in url:
        video_id = extract_youtube_id(url)
        if not video_id:
            print("❌ Gagal mengekstrak Video ID YouTube")
            return None

        # Endpoint baru sesuai snippet user
        api_url = f"https://{RAPID_API_HOST}/youtube/v3/video/details"
        querystring = {
            "videoId": video_id,
            "renderableFormats": "720p,highres", # Meminta kualitas HD
            "urlAccess": "proxied",
            "getTranscript": "false"
        }
    
    # KASUS 2: TIKTOK/LAINNYA (Fallback ke endpoint umum jika ada)
    else:
        # Kita coba endpoint umum, jika gagal nanti user harus beri snippet TikTok juga
        api_url = f"https://{RAPID_API_HOST}/smvd/get/all" 
        querystring = {"url": url}

    try:
        print(f"   ➡️ Requesting: {api_url}")
        if "youtube" in url: print(f"   ➡️ Params: {querystring}")
        
        response = requests.get(api_url, headers=headers, params=querystring)
        data = response.json()
        
        # --- DEBUG LOG (PENTING: Cek log ini nanti) ---
        print(f"   📩 RAW RESPONSE: {json.dumps(data)}") 
        # ----------------------------------------------

        # LOGIKA PARSING (Mencoba menebak struktur respon baru)
        
        # Pola 1: Langsung ada link (Umum)
        if 'links' in data and len(data['links']) > 0:
            return {
                "source": "RapidAPI",
                "title": data.get('title', 'Video Downloaded'),
                "thumbnail": data.get('picture', ''),
                "download_url": data['links'][0]['link'],
                "platform": "RapidAPI"
            }
            
        # Pola 2: Struktur YouTube Details (Biasanya ada di streamingData atau formats)
        # Karena kita belum tahu pasti output JSON-nya, kita coba cari key umum 'url'
        # atau kita kembalikan raw data URL jika ada di root.
        
        # Coba cari URL di dalam dictionary (Deep Search sederhana)
        # Ini langkah darurat: mencari string "http" pertama di JSON respon
        if "youtube" in url:
            # Biasanya respon API youtube wrapper mengembalikan list format
            if 'formats' in data:
                 return {
                    "source": "RapidAPI YouTube",
                    "title": data.get('title', 'YouTube Video'),
                    "thumbnail": data.get('thumbnail', {}).get('url', ''),
                    "download_url": data['formats'][0]['url'], # Ambil format pertama
                    "platform": "YouTube API"
                }
            # Jika responnya single object dengan key 'url'
            elif 'url' in data:
                 return {
                    "source": "RapidAPI YouTube",
                    "title": data.get('title', 'YouTube Video'),
                    "thumbnail": data.get('thumbnail', ''),
                    "download_url": data['url'],
                    "platform": "YouTube API"
                }

        print("   ❌ Gagal mengenali struktur JSON respon (Cek log RAW RESPONSE).")
        return None

    except Exception as e:
        print(f"❌ [API Engine] Error: {e}")
        return None

# --- ROUTES ---
@app.post("/api/download")
async def download_video_api(request: VideoRequest):
    url = request.url
    print(f"\n📥 New Request: {url}")
    
    result = None

    # Routing
    if "youtube.com" in url or "youtu.be" in url:
        # YouTube: API Wajib (Local gagal di Heroku)
        result = get_rapidapi_link(url)
    else:
        # Lainnya: Coba Local dulu
        result = get_local_link(url)
        if not result:
            result = get_rapidapi_link(url)

    if result:
        return result
    else:
        raise HTTPException(status_code=400, detail="Gagal. Cek log server untuk melihat respons API.")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
