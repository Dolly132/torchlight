import asyncio
import io
import json
import logging
from typing import Any, Callable

import aiohttp
import magic
import yt_dlp
from bs4 import BeautifulSoup
from PIL import Image

# Assuming your existing Utils class is available
# from torchlight.Utils import Utils

logger = logging.getLogger(__name__)

# --- URL DATA HELPERS ---

async def get_url_data(url: str) -> tuple[bytes, str, int]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=5) as resp:
                content_type: str = resp.headers.get("Content-Type", "")
                content_length_raw: str = resp.headers.get("Content-Length", "")
                content = await resp.content.read(65536)
                content_length = int(content_length_raw) if content_length_raw else -1
                return content, content_type, content_length
        except Exception as e:
            logger.error(f"Error fetching URL data: {e}")
            return b"", "", -1


def get_page_metadata(*, content: bytes, content_type: str, content_length: int) -> str:
    if not content:
        return ""
    
    metadata = ""
    if content_type and content_type.startswith("text"):
        if not content_type.startswith("text/plain"):
            soup = BeautifulSoup(content.decode("utf-8", errors="ignore"), "lxml")
            if soup.title:
                metadata = f"[URL] {soup.title.string.strip()}"
    elif content_type and content_type.startswith("image"):
        try:
            fp = io.BytesIO(content)
            im = Image.open(fp)
            # Replace Utils.HumanSize with local logic if Utils is missing
            size_str = str(content_length) 
            metadata = f"[IMAGE] {im.format} | {im.size[0]}x{im.size[1]} | Size: {size_str}"
            fp.close()
        except Exception:
            metadata = "[IMAGE] Unknown Format"
    else:
        filetype = magic.from_buffer(content)
        metadata = f"[FILE] {filetype}"
    
    return metadata

# --- YOUTUBE CORE LOGIC ---

def get_url_youtube_info(url: str, proxy: str = "") -> dict:
    """
    Extract info from a YouTube URL or search query.
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        # KEY FIX: extract_flat=False ensures it fetches video details during search
        "extract_flat": False, 
        "cookies": "/app/config/cookies.txt",
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if proxy:
        ydl_opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url.strip(), download=False)


def get_first_valid_entry(entries: list[Any]) -> dict[str, Any]:
    """
    Loop through search results and return the first valid video.
    """
    for entry in entries:
        if not entry:
            continue
        
        # If entry has formats, it's already a fully extracted video object
        if "formats" in entry:
            return entry
            
        # Fallback: if it's just a reference, we might need to extract it (rare with extract_flat: False)
        video_id = entry.get("id") or entry.get("videoId")
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            return get_url_youtube_info(url)

    raise Exception("No compatible YouTube video found in results.")


def get_audio_format(info: dict[str, Any]) -> str:
    """
    Get first playable audio URL from info dict.
    """
    # Look for the best audio-only stream
    formats = info.get("formats", [])
    for fmt in formats:
        # Check for audio streams (typically have no video_ext or specific acodec)
        if fmt.get('vcodec') == 'none' and fmt.get('url'):
            return fmt["url"]
    
    # Fallback to any URL if no audio-only found
    if formats:
        return formats[0]["url"]
        
    raise Exception("No compatible audio format found.")


def get_first_youtube_result(query: str, proxy: str = "") -> dict[str, Any]:
    """
    High-level helper to get video info from a search or a direct URL.
    """
    query_clean = query.strip()
    
    # Check if input is already a URL
    if query_clean.startswith(("http://", "https://")):
        search_target = query_clean
    else:
        search_target = f"ytsearch1:{query_clean}"

    info = get_url_youtube_info(search_target, proxy=proxy)

    # Handle search/playlist result
    if "entries" in info:
        return get_first_valid_entry(info["entries"])
    
    # Handle direct video URL result
    return info

# --- UTILITY / MISC ---

def get_url_real_time(url: str) -> int:
    for sep in ("&t=", "?t=", "#t="):
        if sep in url:
            try:
                time_str = url.split(sep)[1].split("&")[0].split("?")[0].split("#")[0]
                # Assuming Utils.ParseTime exists or use simple int conversion
                return int(time_str.replace('s', '')) 
            except (ValueError, IndexError):
                continue
    return 0