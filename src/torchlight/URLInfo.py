import asyncio
import io
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
import magic
import yt_dlp
from bs4 import BeautifulSoup
from PIL import Image

from torchlight.Utils import Utils

logger = logging.getLogger(__name__)

async def get_url_data(url: str) -> tuple[bytes, str, int]:
    async with aiohttp.ClientSession() as session:
        resp = await asyncio.wait_for(session.get(url), 5)
        content_type: str = resp.headers.get("Content-Type", "")
        content_length_raw: str = resp.headers.get("Content-Length", "")
        content = await asyncio.wait_for(resp.content.read(65536), 5)

        content_length = int(content_length_raw) if content_length_raw else -1
        resp.close()
    return content, content_type, content_length


def get_page_metadata(*, content: bytes, content_type: str, content_length: int) -> str:
    metadata = ""
    if content_type and content_type.startswith("text"):
        if not content_type.startswith("text/plain"):
            soup = BeautifulSoup(content.decode("utf-8", errors="ignore"), "lxml")
            if soup.title:
                metadata = f"[URL] {soup.title.string}"
    elif content_type and content_type.startswith("image"):
        fp = io.BytesIO(content)
        im = Image.open(fp)
        metadata = (
            f"[IMAGE] {im.format} | Width: {im.size[0]} | Height: {im.size[1]}"
            f" | Size: {Utils.HumanSize(content_length)}"
        )
        fp.close()
    else:
        filetype = magic.from_buffer(bytes(content))
        metadata = f"[FILE] {filetype} | Size: {Utils.HumanSize(content_length)}"
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


def get_url_real_time(url: str) -> int:
    temp_pos: int = -1
    for sep in ("&t=", "?t=", "#t="):
        temp_pos = url.find(sep)
        if temp_pos != -1:
            time_str = url[temp_pos + 3 :].split("&")[0].split("?")[0].split("#")[0]
            if time_str:
                return Utils.ParseTime(time_str)
    return 0

def get_url_youtube_info(url: str, proxy: str = "") -> dict:
    ydl_opts = {
        "format": "m4a/bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
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
        ydl.add_default_info_extractors()
        return ydl.extract_info(url.strip(), download=False)


def get_first_valid_entry(entries: list[Any], proxy: str = "") -> dict[str, Any]:
    for entry in entries:
        video_id = str(entry.get("id") or entry.get("videoId") or "")
        if not video_id:
            logger.warning(f"Skipping entry without valid id: {entry}")
            continue

        input_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            info = get_url_youtube_info(url=input_url, proxy=proxy)
            logger.info(f"Successfully extracted: {input_url}")
            return info
        except yt_dlp.utils.DownloadError as e:
            logger.warning(f"Failed to extract <{input_url}>: {e}")
            continue

    raise Exception("No compatible YouTube video found, try another query or URL")


def get_audio_format(info: dict[str, Any]) -> str:
    for fmt in info.get("formats", []):
        if "audio_channels" in fmt:
            logger.debug(json.dumps(fmt, indent=2))
            return fmt["url"]
    raise Exception("No compatible audio format found, try something else")
