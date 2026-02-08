import io
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
import magic
import yt_dlp
from bs4 import BeautifulSoup
from PIL import Image

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
            size_str = str(content_length)
            metadata = f"[IMAGE] {im.format} | {im.size[0]}x{im.size[1]} | Size: {size_str}"
            fp.close()
        except Exception:
            metadata = "[IMAGE] Unknown Format"
    else:
        filetype = magic.from_buffer(content)
        metadata = f"[FILE] {filetype}"

    return metadata


def get_page_text(*, content: bytes, content_type: str, content_length: int) -> str:
    if content_type and content_type.startswith("text/plain"):
        return content.decode("utf-8", errors="ignore")
    return ""


async def print_url_metadata(url: str, callback: Callable) -> None:
    content, content_type, content_length = await get_url_data(url=url)
    metadata = get_page_metadata(
        content=content,
        content_type=content_type,
        content_length=content_length,
    )
    if metadata:
        callback(metadata)


async def get_url_text(url: str) -> str:
    content, content_type, content_length = await get_url_data(url=url)
    return get_page_text(content=content, content_type=content_type, content_length=content_length)


# --- YOUTUBE CORE LOGIC ---


def get_url_youtube_info(url: str, proxy: str = "") -> dict:
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
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
    for entry in entries:
        if not entry:
            continue

        if "formats" in entry:
            return entry

        video_id = entry.get("id") or entry.get("videoId")
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            return get_url_youtube_info(url)

    raise Exception("No compatible YouTube video found in results.")


def get_audio_format(info: dict[str, Any]) -> str:
    formats = info.get("formats", [])
    for fmt in formats:
        if fmt.get("vcodec") == "none" and fmt.get("url"):
            return fmt["url"]

    if formats:
        return formats[0]["url"]

    raise Exception("No compatible audio format found.")


def get_first_youtube_result(query: str, proxy: str = "") -> dict[str, Any]:
    query_clean = query.strip()

    if query_clean.startswith(("http://", "https://")):
        search_target = query_clean
    else:
        search_target = f"ytsearch1:{query_clean}"

    info = get_url_youtube_info(search_target, proxy=proxy)

    if "entries" in info:
        return get_first_valid_entry(info["entries"])

    return info


def get_url_real_time(url: str) -> int:
    for sep in ("&t=", "?t=", "#t="):
        if sep in url:
            try:
                time_str = url.split(sep)[1].split("&")[0].split("?")[0].split("#")[0]
                return int(time_str.replace("s", ""))
            except (ValueError, IndexError):
                continue
    return 0
    