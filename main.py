#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import base64
import html
import io
import json
import logging
import os
import platform
import re
import sys
import tempfile
import time
import urllib.parse
import uuid
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import yt_dlp

BOT_START_TIME = time.time()

# ================= CẤU HÌNH TOKEN & MÔI TRƯỜNG =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98").strip()
ALLOWED_USERS: list[int] = []

FB_COOKIE = os.getenv("FB_COOKIE", "").strip()
raw_fb_token = os.getenv("FB_TOKEN", "").strip()
FB_TOKENS = [raw_fb_token] if raw_fb_token else [
    "EAAAAUaZA8jlABSv6yeD3uBWPS8HcBca2YO6LIUlPo3pIGqLJ5dy5VAurXzOqYIdbWOMv4bDVbvqmFZAWhbhERAvRPusDXFNw4Y1pYN1jVcDCYFSr52BZBrCTNLWLt1ELZChCghXrYcpGvx4EeMMZBGdSpEa4unkYiyyoDgBpI0bMgQQS8MOCYYTHVe2G4KTmpHLtZAItDCcdVRPZCZA8nKFvogZDZD"
]

YT_COOKIES_ENV = os.getenv("YT_COOKIES", "").strip()
COOKIE_FILE_PATH: str | None = None

if YT_COOKIES_ENV:
    try:
        cookie_tmp = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
        try:
            decoded = base64.b64decode(YT_COOKIES_ENV).decode("utf-8")
            with open(cookie_tmp, "w", encoding="utf-8") as f:
                f.write(decoded)
        except Exception:
            with open(cookie_tmp, "w", encoding="utf-8") as f:
                f.write(YT_COOKIES_ENV)
        COOKIE_FILE_PATH = cookie_tmp
        logging.info("Đã nạp thành công YouTube cookies từ biến môi trường.")
    except Exception as e:
        logging.warning(f"Không thể tạo file cookie: {e}")

ANIME_MAX_ITEMS = 6

TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

# Banner Images
IMG_WELCOME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"
IMG_MUSIC = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_GETINFO = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"
IMG_DOWN = "https://cdn.phototourl.com/free/2026-09-20-8f7cee5e-79ee-4e36-8bd6-1eb5d315635e.png"
IMG_FB = "https://cdn.phototourl.com/member/2026-09-20-9afea8db-8a1c-4ffb-9f41-68c26a82f2f5.jpg"
IMG_SING = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_ANIME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MultiToolBot")

HTTP_SESSION: aiohttp.ClientSession | None = None
_EP_CACHE: dict = {}


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


async def get_http_session() -> aiohttp.ClientSession:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = aiohttp.ClientSession(headers=COMMON_HEADERS)
    return HTTP_SESSION


async def close_http_session(application: Application = None):
    global HTTP_SESSION
    if HTTP_SESSION and not HTTP_SESSION.closed:
        await HTTP_SESSION.close()
        logger.info("Đã đóng an toàn kết nối aiohttp session.")


def truncate_text(text: str, max_len: int = 1000) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def ensure_full_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.tikwm.com{url}"
    return url


# ================= HỖ TRỢ STREAM / TẢI TỆP =================
async def download_file_to_temp(url: str, max_size_mb: int = 50, suffix: str = ".mp4") -> str | None:
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                return None

            content_len = resp.headers.get("Content-Length")
            if content_len and int(content_len) > max_size_mb * 1024 * 1024:
                return None

            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            total_downloaded = 0
            max_bytes = max_size_mb * 1024 * 1024

            with open(fd, "wb") as f:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    total_downloaded += len(chunk)
                    if total_downloaded > max_bytes:
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                        return None
                    f.write(chunk)

            return tmp_path
    except Exception as e:
        logger.error(f"Lỗi tải file tạm: {e}")
    return None


# ================= ANILIST GRAPHQL ENGINE (KHÔNG BAO GIỜ BỊ CHẶN) =================
ANILIST_GRAPHQL_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 6) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id
      title {
        romaji
        english
        native
      }
      episodes
      coverImage {
        large
      }
    }
  }
}
"""

async def ani_search(session: aiohttp.ClientSession, query: str) -> list[dict]:
    # 1. Quét AniList GraphQL (Ưu tiên số 1 - 100% không bị Cloudflare cản)
    try:
        payload = {"query": ANILIST_GRAPHQL_QUERY, "variables": {"search": query}}
        async with session.post(
            "https://graphql.anilist.co",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=6)
        ) as r:
            if r.status == 200:
                res = await r.json(content_type=None)
                media_list = res.get("data", {}).get("Page", {}).get("media", [])
                if media_list:
                    out = []
                    for m in media_list:
                        titles = m.get("title", {})
                        title = titles.get("english") or titles.get("romaji") or titles.get("native")
                        slug = re.sub(r"[^\w\-]", "-", (titles.get("english") or titles.get("romaji") or "anime").lower()).strip("-")
                        slug = re.sub(r"-+", "-", slug)
                        out.append({
                            "slug": slug,
                            "title": title,
                            "episodes": m.get("episodes") or 12,
                            "image": m.get("coverImage", {}).get("large") or IMG_ANIME,
                        })
                    return out
    except Exception as e:
        logger.warning(f"AniList API error: {e}")

    # 2. Fallback Kitsu API (Không cần key, không chặn Datacenter)
    try:
        kitsu_url = f"https://kitsu.io/api/edge/anime?filter[text]={urllib.parse.quote_plus(query)}&page[limit]=6"
        async with session.get(kitsu_url, timeout=aiohttp.ClientTimeout(total=6)) as r:
            if r.status == 200:
                res = await r.json(content_type=None)
                data = res.get("data", [])
                if data:
                    out = []
                    for item in data:
                        attr = item.get("attributes", {})
                        title = attr.get("canonicalTitle") or attr.get("titles", {}).get("en") or "Anime"
                        slug = attr.get("slug") or re.sub(r"[^\w\-]", "-", title.lower()).strip("-")
                        img = attr.get("posterImage", {}).get("medium") or IMG_ANIME
                        eps = attr.get("episodeCount") or 12
                        out.append({
                            "slug": slug,
                            "title": title,
                            "episodes": eps,
                            "image": img
                        })
                    return out
    except Exception as e:
        logger.warning(f"Kitsu API fallback error: {e}")

    return []


async def ani_episodes(session: aiohttp.ClientSession, slug: str, total_eps: int = 12) -> list[dict]:
    cache_item = _EP_CACHE.get(slug)
    if cache_item and time.time() - cache_item["ts"] < 3600:
        return cache_item["eps"]

    # Sinh danh sách tập an toàn từ metadata đã lấy
    eps_count = max(total_eps if total_eps and total_eps > 0 else 12, 1)
    if eps_count > 100:
        eps_count = 100  # Giới hạn phân trang tối đa
    
    eps = [{"num": str(i), "id": f"{slug}-episode-{i}"} for i in range(1, eps_count + 1)]
    _EP_CACHE[slug] = {"eps": eps, "ts": time.time()}
    return eps


async def ani_resolve_stream(session: aiohttp.ClientSession, ep_id: str) -> str | None:
    """Tự động resolve luồng m3u8 sang cụm mirror stream miễn phí"""
    instances = [
        "https://c.delusionz.xyz/anime/gogoanime/watch",
        "https://api.consumet.org/anime/gogoanime/watch",
        "https://consumet-api-production-d055.up.railway.app/anime/gogoanime/watch",
    ]
    for base in instances:
        url = f"{base}/{ep_id}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    sources = data.get("sources", [])
                    for s in sources:
                        if s.get("quality") in ["auto", "default", "1080p", "720p"] and s.get("url"):
                            return s.get("url")
                    if sources and sources[0].get("url"):
                        return sources[0].get("url")
        except Exception:
            continue
    return None


def generic_ytdlp_download(url: str, output_path: str) -> str | None:
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": COMMON_HEADERS["User-Agent"],
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            if os.path.exists(output_path):
                return output_path
    except Exception as e:
        logger.error(f"yt-dlp download fail: {e}")
    return None


async def ani_download(m3u8_url: str, slug: str, ep_num: str) -> str | None:
    tmp_dir = tempfile.gettempdir()
    ts = int(time.time())
    job = uuid.uuid4().hex[:6]
    clean_slug = re.sub(r"[^\w\-]", "_", slug)[:25]
    out = os.path.join(tmp_dir, f"ani_{clean_slug}_e{ep_num}_{ts}_{job}.mp4")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, generic_ytdlp_download, m3u8_url, out)


# ================= VẼ CANVAS DASHBOARD (STATUS ẢNH) =================
def draw_rounded_rect(draw, coords, radius, fill):
    x1, y1, x2, y2 = coords
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


async def generate_system_status_canvas() -> io.BytesIO:
    uptime_sec = int(time.time() - BOT_START_TIME)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days else f"{hours}h {minutes}m {seconds}s"

    session = await get_http_session()
    start_t = time.perf_counter()
    try:
        async with session.get("https://api.telegram.org", timeout=aiohttp.ClientTimeout(total=3)):
            ping_ms = round((time.perf_counter() - start_t) * 1000)
    except Exception:
        ping_ms = 99

    ram_mb = 42.5
    if sys.platform != "win32":
        try:
            import resource
            ram_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except Exception:
            pass

    status_tag = "Mượt mà" if ping_ms < 250 else ("Bình thường" if ping_ms < 700 else "Chậm")

    width, height = 1000, 620
    padding = 45

    img = Image.new("RGBA", (width, height), (22, 27, 38, 255))
    draw = ImageDraw.Draw(img)

    draw_rounded_rect(draw, (padding, padding, width - padding, height - padding), radius=22, fill=(28, 35, 49, 255))

    header_h = 60
    draw_rounded_rect(
        draw,
        (padding + 10, padding + 10, width - padding - 10, padding + 10 + header_h),
        radius=14,
        fill=(35, 44, 62, 255),
    )

    dot_radius = 8
    dot_y = padding + 10 + header_h // 2
    dots = [(padding + 35, (255, 95, 86)), (padding + 60, (255, 189, 46)), (padding + 85, (39, 201, 63))]
    for dot_x, dot_color in dots:
        draw.ellipse([dot_x - dot_radius, dot_y - dot_radius, dot_x + dot_radius, dot_y + dot_radius], fill=dot_color)

    def load_font(size, bold=False):
        font_names = [
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "arialbd.ttf" if bold else "arial.ttf",
        ]
        for name in font_names:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_title = load_font(21, bold=True)
    font_label = load_font(18, bold=True)
    font_val = load_font(18, bold=False)
    font_foot = load_font(14, bold=False)

    draw.text((width // 2, dot_y), "SYSTEM METRICS & BOT STATUS", fill=(255, 255, 255), font=font_title, anchor="mm")

    col_w = (width - 2 * padding - 70) // 2
    left_x = padding + 35
    right_x = left_x + col_w + 50
    y_start = padding + 105
    line_h = 44

    now_vn = datetime.now().strftime("%H:%M:%S | %d/%m/%Y")
    left_data = [
        ("Thời gian:", now_vn, (100, 181, 246)),
        ("Uptime Bot:", uptime_str, (255, 183, 77)),
        ("Trạng thái:", status_tag, (100, 181, 246)),
        ("Độ trễ (Ping):", f"{ping_ms} ms", (255, 183, 77)),
        ("Python Core:", f"{platform.python_implementation()} {platform.python_version()}", (100, 181, 246)),
        ("Môi trường:", f"{platform.system()} ({platform.machine()})", (100, 181, 246)),
    ]

    right_data = [
        ("RAM sử dụng:", f"{ram_mb} MB", (255, 183, 77)),
        ("TikWM Engine:", "ONLINE (HD Ready)", (100, 181, 246)),
        ("Anime Engine:", "AniList GraphQL Core", (100, 181, 246)),
        ("YouTube Core:", "Android/TV Client", (100, 181, 246)),
        ("SoundCloud FB:", "ACTIVE (Auto Fallback)", (100, 181, 246)),
        ("Host Platform:", "Railway Cloud Container", (255, 183, 77)),
    ]

    curr_y = y_start
    for label, val, color in left_data:
        draw.text((left_x, curr_y), label, fill=color, font=font_label)
        draw.text((left_x + 155, curr_y), str(val), fill=(240, 240, 240), font=font_val)
        curr_y += line_h

    curr_y = y_start
    for label, val, color in right_data:
        draw.text((right_x, curr_y), label, fill=color, font=font_label)
        draw.text((right_x + 165, curr_y), str(val), fill=(240, 240, 240), font=font_val)
        curr_y += line_h

    draw.text(
        (width // 2, height - padding - 25),
        "Railway Deployment Engine • Telegram Bot Live Monitor",
        fill=(120, 144, 156),
        font=font_foot,
        anchor="mm",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "status_dashboard.png"
    return buf


# ================= TÌM KIẾM YOUTUBE =================
async def search_youtube_fast(keyword: str, max_results: int = 6) -> list[dict]:
    session = await get_http_session()
    encoded = urllib.parse.quote_plus(keyword)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    headers = {
        **COMMON_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.youtube.com/",
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                html_data = await resp.text()
                match = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", html_data)
                if not match:
                    match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.+?});", html_data)

                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)

                    contents = (
                        data.get("contents", {})
                        .get("twoColumnSearchResultsRenderer", {})
                        .get("primaryContents", {})
                        .get("sectionListRenderer", {})
                        .get("contents", [])
                    )

                    results = []
                    for sec in contents:
                        item_section = sec.get("itemSectionRenderer", {}).get("contents", [])
                        for item in item_section:
                            video = item.get("videoRenderer")
                            if video and "videoId" in video:
                                vid_id = video["videoId"]
                                title = video.get("title", {}).get("runs", [{}])[0].get("text", "Video")
                                channel = video.get("ownerText", {}).get("runs", [{}])[0].get("text", "YouTube")
                                dur_text = video.get("lengthText", {}).get("simpleText", "N/A")

                                results.append({
                                    "id": vid_id,
                                    "title": title,
                                    "channel": channel,
                                    "duration_text": dur_text,
                                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                                })

                                if len(results) >= max_results:
                                    return results
                    if results:
                        return results
    except Exception as e:
        logger.warning(f"Fast HTML search fail: {e}")

    def _fallback_ytdlp():
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "default_search": f"ytsearch{max_results}",
            "skip_download": True,
            "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
        }
        if COOKIE_FILE_PATH:
            ydl_opts["cookiefile"] = COOKIE_FILE_PATH

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(keyword, download=False)
            items = []
            for e in info.get("entries", []) or []:
                if not e:
                    continue
                sec = e.get("duration") or 0
                dur_text = f"{sec // 60}:{sec % 60:02d}" if sec else "N/A"
                items.append({
                    "id": e.get("id"),
                    "title": e.get("title", "Không rõ"),
                    "channel": e.get("channel") or e.get("uploader", "Không rõ"),
                    "duration_text": dur_text,
                    "url": f"https://www.youtube.com/watch?v={e.get('id')}",
                })
            return items

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fallback_ytdlp)
    except Exception as e:
        logger.error(f"Fallback yt-dlp search error: {e}")
        return []


# ================= TẢI AUDIO YOUTUBE & SOUNDCLOUD =================
def extract_youtube_audio_advanced(video_id: str, search_query: str = "") -> tuple[str | None, dict]:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    tmp_dir = tempfile.gettempdir()
    out_id = uuid.uuid4().hex[:6]
    output_template = os.path.join(tmp_dir, f"ytdl_{video_id}_{out_id}.%(ext)s")

    client_strategies = [
        ["android", "ios"],
        ["tv", "mweb"],
    ]

    for clients in client_strategies:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "max_filesize": 48 * 1024 * 1024,
            "extractor_args": {
                "youtube": {
                    "player_client": clients,
                    "skip": ["dash", "hls"],
                    "player_skip": ["configs", "webpage"],
                }
            },
            "http_headers": {
                "User-Agent": "com.google.android.youtube/19.29.35 (Linux; U; Android 14) gzip"
            },
        }
        if COOKIE_FILE_PATH:
            ydl_opts["cookiefile"] = COOKIE_FILE_PATH

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                meta = ydl.extract_info(video_url, download=True)
                if not meta:
                    continue

                details = {
                    "title": meta.get("title", "YouTube Track"),
                    "uploader": meta.get("uploader", "YouTube Artist"),
                    "duration": meta.get("duration", 0),
                    "id": video_id,
                }

                for fname in os.listdir(tmp_dir):
                    if fname.startswith(f"ytdl_{video_id}_{out_id}"):
                        return os.path.join(tmp_dir, fname), details
        except Exception as err:
            logger.warning(f"Lỗi tải với clients {clients}: {err}")

    if search_query:
        logger.info(f"Kích hoạt SoundCloud fallback: {search_query}")
        sc_template = os.path.join(tmp_dir, f"sc_{video_id}_{out_id}.%(ext)s")
        sc_opts = {
            "format": "bestaudio/best",
            "outtmpl": sc_template,
            "quiet": True,
            "default_search": "scsearch1",
            "max_filesize": 48 * 1024 * 1024,
        }
        try:
            with yt_dlp.YoutubeDL(sc_opts) as ydl:
                sc_meta = ydl.extract_info(search_query, download=True)
                entries = sc_meta.get("entries", [])
                meta = entries[0] if entries else sc_meta

                details = {
                    "title": meta.get("title", "SoundCloud Audio"),
                    "uploader": meta.get("uploader", "SoundCloud Artist"),
                    "duration": meta.get("duration", 0),
                    "id": video_id,
                }

                for fname in os.listdir(tmp_dir):
                    if fname.startswith(f"sc_{video_id}_{out_id}"):
                        return os.path.join(tmp_dir, fname), details
        except Exception as sc_err:
            logger.error(f"SoundCloud fallback thất bại: {sc_err}")

    return None, {}


# ================= LOGIC FACEBOOK =================
def estimate_fb_creation_details(uid: str) -> str:
    if not uid.isdigit():
        return "Không công khai"
    val = int(uid)
    if val < 10000000:
        return "Năm 2004 - 2006 (Giai đoạn đầu)"
    elif val < 100000000:
        return "Năm 2006 - 2008"
    elif val < 1000000000:
        return "Năm 2008 - 2009"

    if str(val).startswith("10000"):
        part = int(str(val)[5:8])
        if part < 15:
            return "Năm 2009"
        elif part < 35:
            return "Năm 2010"
        elif part < 65:
            return "Năm 2011"
        elif part < 110:
            return "Năm 2012"
        elif part < 180:
            return "Năm 2013"
        elif part < 260:
            return "Năm 2014"
        elif part < 360:
            return "Năm 2015"
        else:
            return "Năm 2016"

    if str(val).startswith("10001"):
        return "Năm 2016 - 2017"
    elif str(val).startswith("10002"):
        return "Năm 2017 - 2018"
    elif str(val).startswith("10003"):
        return "Năm 2018 - 2019"
    elif str(val).startswith("10004"):
        return "Năm 2019 - 2020"
    elif str(val).startswith("10005"):
        return "Năm 2020 - 2021"
    elif str(val).startswith("10006"):
        return "Năm 2021 - 2022"
    elif str(val).startswith("10007") or str(val).startswith("10008"):
        return "Năm 2022 - 2023"
    elif str(val).startswith("10009"):
        return "Năm 2023 - 2024"
    elif str(val).startswith("6155") or str(val).startswith("6156"):
        return "Năm 2024 - 2025"
    elif str(val).startswith("6157"):
        return "Năm 2025 - 2026"

    return "Tài khoản bảo mật cao"


async def get_fb_id(input_str: str) -> str | None:
    clean = input_str.strip()
    if clean.isdigit():
        return clean

    match_id = re.search(r"[?&]id=(\d+)", clean)
    if match_id:
        return match_id.group(1)

    username = clean
    clean_url = clean.split("?")[0].rstrip("/")
    path_match = re.search(r"(?:facebook\.com|fb\.me|fb\.com)/([a-zA-Z0-9.]+)", clean_url)
    if path_match:
        extracted = path_match.group(1)
        if extracted not in ["profile.php", "groups", "pages", "watch", "stories"]:
            username = extracted

    session = await get_http_session()

    for token in FB_TOKENS:
        if not token:
            continue
        try:
            url = f"https://graph.facebook.com/{username}?fields=id&access_token={token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    j = await resp.json(content_type=None)
                    if "id" in j:
                        return str(j["id"])
        except Exception:
            pass

    try:
        async with session.post(
            "https://id.traodoisub.com/api.php", data={"link": clean}, timeout=aiohttp.ClientTimeout(total=6)
        ) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("id"):
                    return str(j["id"])
    except Exception:
        pass

    try:
        async with session.get(
            f"https://ffb.vn/api/tool/get-id-fb?idfb={clean}", timeout=aiohttp.ClientTimeout(total=6)
        ) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("id"):
                    return str(j["id"])
    except Exception:
        pass

    return None


async def scrape_fb_full_details(uid: str) -> dict:
    session = await get_http_session()
    headers = {
        "User-Agent": COMMON_HEADERS["User-Agent"],
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if FB_COOKIE:
        headers["Cookie"] = FB_COOKIE

    extracted = {
        "followers": None,
        "bio": None,
        "social_links": [],
        "hometown": None,
        "location": None,
        "work": None,
        "education": None,
    }

    try:
        async with session.get(
            f"https://mbasic.facebook.com/{uid}", headers=headers, timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            if r.status == 200:
                html_text = await r.text()
                fol_match = re.search(
                    r"(?:Có|Followed by)\s+([\d.,]+)\s+(?:người theo dõi|people)", html_text, re.IGNORECASE
                )
                if fol_match:
                    extracted["followers"] = fol_match.group(1).replace(".", "").replace(",", "").strip()

                bio_match = re.search(r'<div class="[^"]*" id="bio">([\s\S]*?)</div>', html_text)
                if not bio_match:
                    bio_match = re.search(r"intro_bio[^>]*><span>([\s\S]*?)</span>", html_text)
                if bio_match:
                    clean_bio = re.sub(r"<br\s*/?>", "\n", bio_match.group(1))
                    clean_bio = re.sub(r"<[^>]+>", "", clean_bio).strip()
                    extracted["bio"] = html.unescape(clean_bio)
    except Exception as e:
        logger.warning(f"Lỗi scrape profile: {e}")

    try:
        async with session.get(
            f"https://mbasic.facebook.com/{uid}/about", headers=headers, timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            if r.status == 200:
                raw_html = await r.text()
                m_home = re.search(r"(?:Đến từ|From)\s+<a[^>]*>([^<]+)</a>", raw_html, re.IGNORECASE)
                if not m_home:
                    m_home = re.search(
                        r"(?:Quê quán|Hometown)[^<]*</div><div[^>]*><span[^>]*><a[^>]*>([^<]+)</a>",
                        raw_html,
                        re.IGNORECASE,
                    )
                if m_home:
                    extracted["hometown"] = m_home.group(1).strip()

                m_loc = re.search(r"(?:Sống tại|Lives in)\s+<a[^>]*>([^<]+)</a>", raw_html, re.IGNORECASE)
                if not m_loc:
                    m_loc = re.search(
                        r"(?:Tỉnh/Thành phố hiện tại|Current city)[^<]*</div><div[^>]*><span[^>]*><a[^>]*>([^<]+)</a>",
                        raw_html,
                        re.IGNORECASE,
                    )
                if m_loc:
                    extracted["location"] = m_loc.group(1).strip()

                m_work = re.search(r"(?:Làm việc tại|Works at)\s+<a[^>]*>([^<]+)</a>", raw_html, re.IGNORECASE)
                if m_work:
                    extracted["work"] = f"Làm việc tại {m_work.group(1).strip()}"

                m_edu = re.search(
                    r"(?:Từng học tại|Học tại|Studied at|Studies at)\s+<a[^>]*>([^<]+)</a>",
                    raw_html,
                    re.IGNORECASE,
                )
                if m_edu:
                    extracted["education"] = m_edu.group(1).strip()

                if not extracted["followers"]:
                    m_fol = re.search(
                        r"(?:Có|Followed by)\s+([\d.,]+)\s+(?:người theo dõi|people)",
                        raw_html,
                        re.IGNORECASE,
                    )
                    if m_fol:
                        extracted["followers"] = m_fol.group(1).replace(".", "").replace(",", "").strip()

                redirect_links = re.findall(
                    r'href="https?://(?:[a-z0-9-]+\.)?facebook\.com/l\.php\?u=([^"&]+)', raw_html
                )
                social_domains = [
                    "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
                    "t.me", "threads.net", "twitter.com", "x.com", "github.com",
                    "discord.gg", "linkedin.com", "pinterest.com", "spotify.com",
                ]
                found_links = set()
                for raw_link in redirect_links:
                    decoded_url = urllib.parse.unquote(raw_link)
                    if any(domain in decoded_url for domain in social_domains):
                        clean_item = decoded_url.split("?")[0].rstrip("/")
                        found_links.add(clean_item)

                extracted["social_links"] = list(found_links)
    except Exception as e:
        logger.warning(f"Lỗi scrape about: {e}")

    return extracted


async def fetch_fb_info(uid: str) -> dict | None:
    session = await get_http_session()
    result = {
        "id": uid,
        "name": None,
        "gender": None,
        "followers": None,
        "created_time": None,
        "updated_time": None,
        "hometown": None,
        "location": None,
        "about": None,
        "work": None,
        "education": None,
        "verified": False,
        "username": None,
        "social_links": [],
    }

    fields_target = "id,name,gender,is_verified,short_name,username,updated_time,about,hometown,location,work,education"
    for token in FB_TOKENS:
        if not token:
            continue
        try:
            url = f"https://graph.facebook.com/{uid}?fields={fields_target}&access_token={token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                res = await resp.json(content_type=None)
                if res and "name" in res:
                    result["name"] = res.get("name")
                    result["gender"] = res.get("gender")
                    result["verified"] = res.get("is_verified", False)
                    result["username"] = res.get("username")
                    result["updated_time"] = res.get("updated_time")
                    result["about"] = res.get("about")
                    if isinstance(res.get("hometown"), dict):
                        result["hometown"] = res["hometown"].get("name")
                    if isinstance(res.get("location"), dict):
                        result["location"] = res["location"].get("name")
                    break
        except Exception as e:
            logger.warning(f"Graph API pass: {e}")

    scraped = await scrape_fb_full_details(uid)
    if scraped.get("followers"):
        result["followers"] = scraped["followers"]
    if scraped.get("bio"):
        result["about"] = scraped["bio"]
    if scraped.get("social_links"):
        result["social_links"] = scraped["social_links"]
    if not result["hometown"] and scraped.get("hometown"):
        result["hometown"] = scraped["hometown"]
    if not result["location"] and scraped.get("location"):
        result["location"] = scraped["location"]
    if not result["work"] and scraped.get("work"):
        result["work"] = scraped["work"]
    if not result["education"] and scraped.get("education"):
        result["education"] = scraped["education"]

    if result["name"] or result["id"]:
        return result
    return None


def format_fb_info_panel(data: dict) -> tuple[str, str]:
    uid = str(data.get("id", "—"))
    name = html.escape(str(data.get("name") or "Người dùng Facebook"))
    username = html.escape(str(data.get("username") or "—"))
    raw_gender = data.get("gender")
    gender_map = {"male": "Nam 🚹", "female": "Nữ 🚺"}
    gender = gender_map.get(str(raw_gender).lower(), "Không công khai 🔒")

    raw_fol = data.get("followers")
    if raw_fol:
        clean_fol = str(raw_fol).replace(",", "").replace(".", "").strip()
        followers_str = f"<b>{int(clean_fol):,}</b> người theo dõi" if clean_fol.isdigit() else f"<b>{raw_fol}</b> người theo dõi"
    else:
        followers_str = "<i>Không công khai hoặc tắt follow</i>"

    raw_created = data.get("created_time")
    created_str = (
        str(raw_created).split("T")[0]
        if raw_created and raw_created != "None"
        else estimate_fb_creation_details(uid)
    )

    badge = "💎 ĐÃ XÁC MINH (TÍCH XANH)" if data.get("verified") else "🟢 HOẠT ĐỘNG BÌNH THƯỜNG"
    avatar_token = FB_TOKENS[0] if FB_TOKENS else ""
    avatar_url = f"https://graph.facebook.com/{uid}/picture?width=720&height=720&access_token={avatar_token}" if avatar_token else IMG_FB

    social_lines = []
    for link in data.get("social_links", []):
        clean_tag = link.split("/")[-1]
        if "instagram.com" in link:
            social_lines.append(f"• 📸 <b>Instagram:</b> <a href='{link}'>@{clean_tag}</a>")
        elif "tiktok.com" in link:
            social_lines.append(f"• 🎬 <b>TikTok:</b> <a href='{link}'>@{clean_tag}</a>")
        elif "youtube.com" in link:
            social_lines.append(f"• 🔴 <b>YouTube:</b> <a href='{link}'>Xem kênh</a>")
        elif "t.me" in link:
            social_lines.append(f"• ✈️ <b>Telegram:</b> <a href='{link}'>@{clean_tag}</a>")
        else:
            social_lines.append(f"• 🔗 <b>Khác:</b> <a href='{link}'>{link}</a>")

    social_display = "\n".join(social_lines) if social_lines else "<i>Không có mạng xã hội liên kết ngoài</i>"

    panel = (
        f"⚡ <b>HỒ SƠ FACEBOOK PRO CHI TIẾT</b> ⚡\n"
        f"<code>────────────────────────────</code>\n"
        f"👤 <b>Họ tên:</b> <b>{name}</b>\n"
        f"🆔 <b>Mã UID:</b> <code>{uid}</code>\n"
        f"🔗 <b>Username:</b> <code>{username}</code>\n"
        f"🚻 <b>Giới tính:</b> {gender}\n"
        f"🛡 <b>Trạng thái:</b> <code>{badge}</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"👥 <b>Người theo dõi:</b> {followers_str}\n"
        f"🗓 <b>Ước tính tạo nick:</b> <code>{created_str}</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"🏡 <b>Quê quán:</b> {html.escape(str(data.get('hometown') or 'Không công khai'))}\n"
        f"📍 <b>Nơi sống:</b> {html.escape(str(data.get('location') or 'Không công khai'))}\n"
        f"💼 <b>Công việc:</b> {html.escape(str(data.get('work') or 'Không công khai'))}\n"
        f"🎓 <b>Học vấn:</b> {html.escape(str(data.get('education') or 'Không công khai'))}\n"
        f"<code>────────────────────────────</code>\n"
        f"📝 <b>Tiểu sử:</b>\n<i>« {html.escape(str(data.get('about') or 'Không có tiểu sử.'))} »</i>\n"
        f"<code>────────────────────────────</code>\n"
        f"🌐 <b>MẠNG XÃ HỘI GẮN KÈM:</b>\n"
        f"{social_display}\n"
        f"<code>────────────────────────────</code>\n"
        f"🔗 <b>Liên kết trực tiếp:</b> <a href='https://facebook.com/{uid}'>fb.com/{uid}</a>"
    )
    return truncate_text(panel, 1020), avatar_url


# ================= LOGIC TIKTOK =================
async def resolve_tiktok_url(url: str) -> str:
    session = await get_http_session()
    clean = url.strip()
    if any(short in clean for short in ["vt.tiktok.com", "vm.tiktok.com", "v.douyin.com"]):
        try:
            async with session.get(clean, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return str(resp.url)
        except Exception as e:
            logger.error(f"Lỗi giải mã URL rút gọn: {e}")
    return clean


async def tikwm_req(params: dict):
    session = await get_http_session()
    url = TIKWM_BASE
    post_headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        async with session.post(url, data=params, headers=post_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0:
                    return data
    except Exception as e:
        logger.warning(f"TikWM POST fail: {e}")

    try:
        async with session.get(url, params=params, headers=COMMON_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0:
                    return data
    except Exception as e:
        logger.warning(f"TikWM GET fail: {e}")
    return None


async def fallback_tik_download(tiktok_url: str):
    session = await get_http_session()
    api_url = "https://lovetik.com/api/ajax/search"
    payload = {"query": tiktok_url}
    headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://lovetik.com/",
    }
    try:
        async with session.post(api_url, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("status") == "ok":
                    video_url = None
                    music_url = None
                    for link in j.get("links", []):
                        if link.get("t") == "<b>MP4</b>" or "watermark" not in link.get("t", "").lower():
                            if not video_url and link.get("a"):
                                video_url = link.get("a")
                        if "mp3" in link.get("t", "").lower():
                            music_url = link.get("a")

                    return {
                        "code": 0,
                        "data": {
                            "id": j.get("vid", ""),
                            "title": j.get("desc", "TikTok Media"),
                            "author": {"nickname": j.get("author", "TikTok User")},
                            "digg_count": 0,
                            "comment_count": 0,
                            "share_count": 0,
                            "play": video_url,
                            "hdplay": video_url,
                            "music": music_url,
                            "music_info": {
                                "title": "Original Sound",
                                "author": j.get("author", "TikTok"),
                                "play": music_url,
                            },
                            "images": j.get("images", []),
                        },
                    }
    except Exception as e:
        logger.error(f"Fallback LoveTik error: {e}")
    return None


async def fetch_tiktok_user_info(username: str) -> dict:
    session = await get_http_session()
    clean_user = username.strip().lstrip("@")
    url = f"{TIK_INFO_API}{clean_user}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            return {"error": f"HTTP Status {resp.status}"}
    except Exception as e:
        logger.error(f"Lỗi lấy thông tin TikTok: {e}")
        return {"error": str(e)}


def get_tiktok_creation_time(uid: str) -> str:
    try:
        val = int(uid)
        timestamp = val >> 32
        if 1400000000 <= timestamp <= 2000000000:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d | %H:%M:%S")
    except Exception:
        pass
    return "Không xác định"


def format_user_info_panel(data: dict, username: str) -> tuple[str, str | None]:
    clean_user = html.escape(username.lstrip("@"))

    if not data or data.get("error"):
        err = data.get("error", "Người dùng không tồn tại hoặc API bận.")
        return (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"❌ <b>TRA CỨU THẤT BẠI:</b> <code>@{clean_user}</code>\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"⚠️ <b>Chi tiết:</b> <i>{html.escape(str(err))}</i>\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
            None,
        )

    u = data.get("data", {}).get("user") or data.get("userInfo", {}).get("user") or data.get("user") or data
    s = data.get("data", {}).get("stats") or data.get("userInfo", {}).get("stats") or data.get("stats") or {}

    nickname = html.escape(str(u.get("nickname") or u.get("name") or "—"))
    unique_id = html.escape(str(u.get("uniqueId") or u.get("unique_id") or username).lstrip("@"))
    uid = str(u.get("id") or u.get("uid") or "0")

    is_private = u.get("privateAccount") or u.get("is_private") or False
    status_str = "🔒 Riêng tư" if is_private else "🌐 Công khai"
    is_verified = u.get("verified") or u.get("customVerify") or False
    verified_str = "✅ Đã xác minh" if is_verified else "❌ Chưa xác minh"
    language = html.escape(str(u.get("language") or u.get("region") or "vi").lower())
    bio = html.escape(str(u.get("signature") or u.get("bio") or "Không có tiểu sử."))
    has_shop = u.get("commerceUserInfo", {}).get("commerceUser") or u.get("is_star") or False
    shop_str = "✅ Có" if has_shop else "❌ Không"

    followers = s.get("followerCount") or s.get("followers") or 0
    following = s.get("followingCount") or s.get("following") or 0
    videos = s.get("videoCount") or s.get("video") or 0
    hearts = s.get("heartCount") or s.get("hearts") or s.get("heart") or 0

    created_time_str = get_tiktok_creation_time(uid)
    avatar = u.get("avatarLarger") or u.get("avatarMedium") or u.get("avatarThumb") or u.get("avatar")

    panel = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"ℹ️ Thông Tin TikTok @{unique_id} ⚡\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"👤 Tên: <b>{nickname}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🔒 Trạng thái: {status_str}\n"
        f"✅ Xác minh: {verified_str}\n"
        f"🌐 Ngôn ngữ: {language}\n"
        f"📝 Mô tả: {bio}\n"
        f"🛒 Bán hàng: {shop_str}\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"📊 Thống kê:\n"
        f"   ├ 👥 Follower:   <code>{followers:,}</code>\n"
        f"   ├ 👤 Following:  <code>{following:,}</code>\n"
        f"   ├ 🎥 Video:      <code>{videos:,}</code>\n"
        f"   └ ❤️ Lượt thích: <code>{hearts:,}</code>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"⏰ Ngày tạo: <code>{created_time_str}</code>\n"
        f"🔗 Link: <a href='https://www.tiktok.com/@{unique_id}'>TikTok Profile</a>\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
    )

    return truncate_text(panel, 1020), avatar


# ================= DASHBOARD WELCOME =================
def build_welcome_dashboard(user_name: str = "User") -> tuple[str, InlineKeyboardMarkup]:
    display_name = html.escape(user_name)
    panel = (
        f"⚡ <b>ALL-IN-ONE TOOLKIT BOT ONLINE</b> ⚡\n"
        f"<code>────────────────────────────</code>\n"
        f"👋 Xin chào, <b>{display_name}</b>\n"
        f"Hệ thống đa năng: Tải Anime HD, Nhạc YouTube, TikTok & Tra cứu Facebook.\n\n"
        f"📌 <b>LỆNH TRUY CẬP NHANH:</b>\n"
        f"• 🎬 <b>Xem Anime:</b> <code>/anime &lt;tên anime&gt;</code>\n"
        f"• 🎶 <b>Nhạc YouTube:</b> <code>/sing &lt;tên bài hát&gt;</code>\n"
        f"• 📥 <b>Tải TikTok:</b> Gửi trực tiếp link (Auto Full HD)\n"
        f"• 🎵 <b>Tách nhạc TikTok:</b> <code>/music &lt;link&gt;</code>\n"
        f"• 🔎 <b>Info TikTok:</b> <code>/getinfo &lt;user&gt;</code>\n"
        f"• 🔵 <b>Info Facebook:</b> <code>/fb &lt;uid/link&gt;</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"🟢 <b>Status:</b> <i>Railway Container Engine Online</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎬 Tìm Anime HD", callback_data="panel_guide_anime"),
            InlineKeyboardButton("🎶 Tìm Nhạc YouTube", callback_data="panel_guide_sing"),
        ],
        [
            InlineKeyboardButton("📥 Tải TikTok", callback_data="panel_guide_down"),
            InlineKeyboardButton("🎵 Tách Nhạc TikTok", callback_data="panel_guide_music"),
        ],
        [
            InlineKeyboardButton("🔎 Info TikTok", callback_data="panel_guide_info"),
            InlineKeyboardButton("🔵 Info Facebook", callback_data="panel_guide_fb"),
        ],
        [
            InlineKeyboardButton("📊 Server Status", callback_data="panel_status"),
        ],
    ]
    return panel, InlineKeyboardMarkup(keyboard)


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    user_name = update.effective_user.first_name or "User"
    text, reply_markup = build_welcome_dashboard(user_name)

    if update.message:
        try:
            await update.message.reply_photo(
                photo=IMG_WELCOME,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )


async def handle_panel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    back_btn = [[InlineKeyboardButton("🔙 Quay lại Menu", callback_data="panel_home")]]

    if data == "panel_home":
        user_name = query.from_user.first_name or "User"
        text, reply_markup = build_welcome_dashboard(user_name)
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(media=IMG_WELCOME, caption=text, parse_mode=ParseMode.HTML),
                reply_markup=reply_markup,
            )
        except Exception:
            try:
                await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception:
                await query.message.reply_photo(photo=IMG_WELCOME, caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif data == "panel_guide_anime":
        text = (
            "🎬 <b>HƯỚNG DẪN TẢI & XEM ANIME HD</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/anime &lt;tên anime&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/anime solo leveling</code> hoặc <code>/anime naruto</code>\n"
            "• Sử dụng công nghệ AniList GraphQL đảm bảo tìm thấy mọi bộ anime."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_sing":
        text = (
            "🎶 <b>HƯỚNG DẪN TÌM VÀ TẢI NHẠC YOUTUBE</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/sing &lt;tên bài hát hoặc từ khóa&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/sing tắt đèn đi</code>\n"
            "• Bot sẽ trả về danh sách, bấm số bài hát để nhận file Audio."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_down":
        text = (
            "📥 <b>HƯỚNG DẪN TẢI TIKTOK FULL HD</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Gửi link video hoặc album ảnh trực tiếp vào chat.\n"
            "• Bot tự động tải file <b>HD / 1080p không logo</b>.\n"
            "• Tương thích cả link ngắn như <code>vt.tiktok.com</code>."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            "🎵 <b>TRÍCH XUẤT AUDIO TIKTOK</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/music &lt;link_tiktok&gt;</code>\n"
            "• Hoặc bấm nút <b>[Tải nhạc MP3]</b> bên dưới mỗi video tải về."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_info":
        text = (
            "🔎 <b>TRA CỨU TIKTOK PROFILE</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/getinfo tiktok</code>"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_fb":
        text = (
            "🔵 <b>TRA CỨU FACEBOOK PROFILE PRO</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/fb &lt;link_profile_hoặc_uid&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/fb 4</code> hoặc link tài khoản bất kỳ."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_status":
        await query.answer("📊 Đang render ảnh thống kê...", show_alert=False)
        canvas_buffer = await generate_system_status_canvas()

        caption_text = (
            "📊 <b>BÁO CÁO THỐNG KÊ MÁY CHỦ (CANVAS LIVE)</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Hệ thống giám sát trực tiếp trên Railway Cloud.\n"
            "• Thông số tài nguyên được làm mới theo thời gian thực."
        )

        try:
            await query.message.edit_media(
                media=InputMediaPhoto(media=canvas_buffer, caption=caption_text, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(back_btn),
            )
        except Exception as e:
            logger.error(f"Lỗi edit canvas media: {e}")
            await query.message.reply_photo(
                photo=canvas_buffer,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(back_btn),
            )


# ================= XỬ LÝ ANIME (/anime) =================
async def cmd_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU TÊN PHIM</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/anime &lt;tên phim&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/anime solo leveling</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_ANIME, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    query = " ".join(context.args).strip()
    status_msg = await update.message.reply_text(
        f"🔍 <i>Đang tìm kiếm anime:</i> <b>{html.escape(query)}</b>...", parse_mode=ParseMode.HTML
    )

    session = await get_http_session()
    results = await ani_search(session, query)

    if not results:
        await status_msg.edit_text("❌ Không tìm thấy anime nào. Hãy thử từ khóa ngắn hơn (ví dụ: naruto, one piece, titan)!")
        return

    keyboard = []
    lines = [f"🎬 <b>KẾT QUẢ TÌM KIẾM ANIME:</b> <i>{html.escape(query)}</i>\n<code>────────────────────────────</code>"]

    for i, a in enumerate(results, 1):
        slug = a["slug"]
        title = a["title"]
        eps_count = a.get("episodes", 12)
        short_id = uuid.uuid4().hex[:8]
        context.bot_data[f"ani_slug_{short_id}"] = slug
        context.bot_data[f"ani_name_{short_id}"] = title
        context.bot_data[f"ani_eps_{short_id}"] = eps_count

        lines.append(f"<b>{i}.</b> {html.escape(title)} (<code>{eps_count} tập</code>)")
        keyboard.append([InlineKeyboardButton(f"▶️ {i}. {title[:32]}", callback_data=f"anisel_{short_id}_0")])

    lines.append("<code>────────────────────────────</code>\n👉 <i>Bấm chọn bộ anime để xem danh sách tập:</i>")
    text_content = "\n".join(lines)

    await status_msg.delete()
    thumb_img = results[0].get("image") or IMG_ANIME
    try:
        await update.message.reply_photo(
            photo=thumb_img,
            caption=truncate_text(text_content, 1020),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception:
        await update.message.reply_text(
            truncate_text(text_content, 1020),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_anime_episodes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = query.data.split("_")
    short_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    slug = context.bot_data.get(f"ani_slug_{short_id}")
    anime_name = context.bot_data.get(f"ani_name_{short_id}", "Anime")
    total_eps_count = context.bot_data.get(f"ani_eps_{short_id}", 12)

    if not slug:
        await query.message.reply_text("❌ Phiên tìm kiếm đã hết hạn, vui lòng gõ lại /anime!")
        return

    session = await get_http_session()
    eps = await ani_episodes(session, slug, total_eps_count)

    if not eps:
        await query.message.reply_text("❌ Không thể lấy danh sách tập phim của anime này.")
        return

    page_size = 15
    total_pages = (len(eps) + page_size - 1) // page_size
    current_eps = eps[page * page_size : (page + 1) * page_size]

    keyboard = []
    row = []
    for ep in current_eps:
        ep_num = ep["num"]
        ep_id = ep["id"]
        ep_short = uuid.uuid4().hex[:6]
        context.bot_data[f"ep_{ep_short}"] = ep_id
        row.append(InlineKeyboardButton(f"Tập {ep_num}", callback_data=f"anidl_{short_id}_{ep_num}_{ep_short}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"anisel_{short_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Tiếp ➡️", callback_data=f"anisel_{short_id}_{page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    caption = (
        f"🎬 <b>DANH SÁCH TẬP: {html.escape(anime_name)}</b>\n"
        f"<code>────────────────────────────</code>\n"
        f"• Tổng số tập: <b>{len(eps)}</b> tập\n"
        f"• Trang: <b>{page + 1}/{total_pages}</b>\n"
        f"👉 <i>Bấm chọn tập để bot giải mã & tải xuống:</i>"
    )

    try:
        await query.message.edit_caption(
            caption=caption, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        await query.message.edit_text(
            caption, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_anime_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer("⏳ Đang kết nối luồng tải...", show_alert=False)

    parts = query.data.split("_")
    short_id = parts[1]
    ep_num = parts[2]
    ep_short = parts[3]

    slug = context.bot_data.get(f"ani_slug_{short_id}")
    anime_name = context.bot_data.get(f"ani_name_{short_id}", "Anime")
    ep_id = context.bot_data.get(f"ep_{ep_short}", f"{slug}-episode-{ep_num}")

    status_msg = await query.message.reply_text(
        f"⚡ <i>Đang bóc tách link Stream Tập {ep_num}...</i>", parse_mode=ParseMode.HTML
    )

    session = await get_http_session()
    m3u8_url = await ani_resolve_stream(session, ep_id)

    if not m3u8_url:
        await status_msg.edit_text("❌ Không lấy được luồng video trực tiếp của tập này. Server nguồn đang quá tải!")
        return

    await status_msg.edit_text(f"📥 <i>Đang tải Tập {ep_num} về server bot...</i>", parse_mode=ParseMode.HTML)

    file_path = await ani_download(m3u8_url, slug, ep_num)
    if not file_path or not os.path.exists(file_path):
        await status_msg.edit_text("❌ Tập phim vượt quá 50MB hoặc server CDN ngắt kết nối.")
        return

    caption = (
        f"╔══════════ 🎬 <b>ANIME DOWNLOAD</b> ══════════╗\n"
        f"║ 🎥 <b>Bộ phim:</b> <b>{html.escape(anime_name)}</b>\n"
        f"║ 🎞️ <b>Tập:</b> {ep_num}\n"
        f"║ ⚡ <b>Chất lượng:</b> Full HD 720p/1080p\n"
        f"╚════════════════════════════════════╝"
    )

    await status_msg.edit_text("📤 <i>Đang gửi video lên Telegram...</i>", parse_mode=ParseMode.HTML)

    try:
        with open(file_path, "rb") as vf:
            await query.message.reply_video(
                video=vf,
                caption=truncate_text(caption, 1020),
                parse_mode=ParseMode.HTML,
                read_timeout=180,
                write_timeout=180,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Lỗi gửi anime video: {e}")
        await status_msg.edit_text("❌ Video vượt quá 50MB (giới hạn Telegram Bot) hoặc CDN timeout.")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


# ================= XỬ LÝ LỆNH /sing =================
async def cmd_sing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU TÊN BÀI HÁT</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/sing &lt;tên bài hát&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/sing Tắt đèn đi</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_SING, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    keyword = " ".join(context.args).strip()
    status_msg = await update.message.reply_text(f"🔍 <i>Đang tìm kiếm:</i> <b>{html.escape(keyword)}</b>...", parse_mode=ParseMode.HTML)

    results = await search_youtube_fast(keyword, 6)

    if not results:
        await status_msg.edit_text("❌ Không tìm thấy bài hát phù hợp. Vui lòng thử từ khóa khác!")
        return

    context.bot_data[f"kw_{update.effective_chat.id}"] = keyword

    msg_lines = [f"🎶 <b>KẾT QUẢ TÌM KIẾM CHO:</b> <i>{html.escape(keyword)}</i>\n<code>────────────────────────────</code>"]
    keyboard = []
    row = []

    for idx, item in enumerate(results, 1):
        vid_id = item["id"]
        title = item["title"]
        channel = item["channel"]
        dur_str = item.get("duration_text", "N/A")

        msg_lines.append(f"<b>{idx}.</b> {html.escape(title)}\n   👤 Kênh: <i>{html.escape(channel)}</i> | ⏱️ {dur_str}")
        row.append(InlineKeyboardButton(f"🎵 Bài {idx}", callback_data=f"ytdl_{vid_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    msg_lines.append("<code>────────────────────────────</code>\n👉 <i>Bấm số bài hát để tải âm thanh:</i>")
    text_content = "\n".join(msg_lines)

    await status_msg.delete()
    try:
        await update.message.reply_photo(
            photo=IMG_SING,
            caption=truncate_text(text_content, 1020),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception:
        await update.message.reply_text(
            truncate_text(text_content, 1020),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ================= CALLBACK TẢI AUDIO YOUTUBE =================
async def handle_youtube_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer("⏳ Đang tải audio...", show_alert=False)
    data = query.data

    vid_id = data.replace("ytdl_", "")
    target_url = f"https://www.youtube.com/watch?v={vid_id}"

    saved_kw = context.bot_data.get(f"kw_{query.message.chat_id}", "")

    loading_msg = await query.message.reply_text("⏳ <i>Đang bóc tách audio và mở khóa bản quyền...</i>", parse_mode=ParseMode.HTML)

    loop = asyncio.get_running_loop()
    file_path, details = await loop.run_in_executor(None, extract_youtube_audio_advanced, vid_id, saved_kw)

    await loading_msg.delete()

    if not file_path or not os.path.exists(file_path):
        await query.message.reply_text("❌ Không thể tải được bài hát này. Hãy thử chọn bài số khác trong danh sách!")
        return

    title = html.escape(details.get("title", "YouTube Track"))
    uploader = html.escape(details.get("uploader", "YouTube Artist"))

    caption = (
        f"╔══════════ 🎶 <b>AUDIO TRACK</b> ══════════╗\n"
        f"║ 🎼 <b>Bài hát:</b> <b>{title}</b>\n"
        f"║ 👤 <b>Nghệ sĩ/Kênh:</b> {uploader}\n"
        f"║ 🔗 <b>Nguồn gốc:</b> <a href='{target_url}'>Media Source</a>\n"
        f"╚════════════════════════════════════╝"
    )

    try:
        with open(file_path, "rb") as audio_file:
            await query.message.reply_audio(
                audio=audio_file,
                title=title,
                performer=uploader,
                caption=truncate_text(caption, 1020),
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Lỗi gửi audio: {e}")
        await query.message.reply_text("❌ Kích thước tệp âm thanh vượt quá giới hạn truyền tải của bot.")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass


# ================= LỆNH /fb =================
async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU THAM SỐ</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/fb &lt;link_hoặc_uid&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/fb 4</code> hoặc <code>/fb https://facebook.com/...</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_FB, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    input_data = context.args[0].strip()
    status_msg = await update.message.reply_text("⏳ <i>Đang bóc tách UID Facebook...</i>", parse_mode=ParseMode.HTML)

    uid = await get_fb_id(input_data)
    if not uid:
        await status_msg.edit_text("❌ Không thể giải mã UID. Hãy kiểm tra lại link tài khoản!", parse_mode=ParseMode.HTML)
        return

    await status_msg.edit_text(f"📡 <i>Đang quét dữ liệu OSINT cho UID:</i> <code>{uid}</code>...", parse_mode=ParseMode.HTML)
    data = await fetch_fb_info(uid)

    if not data:
        await status_msg.edit_text("❌ Không lấy được thông tin từ profile này.", parse_mode=ParseMode.HTML)
        return

    report, avatar_url = format_fb_info_panel(data)
    await status_msg.delete()

    try:
        await update.message.reply_photo(photo=avatar_url, caption=report, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await update.message.reply_photo(photo=IMG_FB, caption=report, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(report, parse_mode=ParseMode.HTML)


# ================= NÚT TẢI NHẠC TỪ TIKTOK =================
async def handle_download_music_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer("⏳ Đang tải audio...", show_alert=False)
    data = query.data

    video_id = data.replace("dlmusic_", "")
    tik_url = f"https://www.tiktok.com/@a/video/{video_id}"

    api_res = await tikwm_req({"url": tik_url, "hd": 1})
    if not api_res or api_res.get("code") != 0:
        api_res = await fallback_tik_download(tik_url)

    if not api_res or api_res.get("code") != 0 or not api_res.get("data"):
        await query.message.reply_text("❌ Không lấy được audio từ video này.")
        return

    res = api_res["data"]
    raw_music = res.get("music") or res.get("music_info", {}).get("play")
    music_url = ensure_full_url(raw_music)

    if not music_url:
        await query.message.reply_text("❌ Video này bị tắt tiếng hoặc không có track âm thanh riêng.")
        return

    music_title = html.escape(res.get("music_info", {}).get("title") or "TikTok Audio")
    music_author = html.escape(res.get("music_info", {}).get("author") or "Original Sound")

    audio_panel = (
        f"╔══════════ 🎵 <b>TIKTOK AUDIO PLAYER</b> ══════════╗\n"
        f"║ 🎼 <b>Bài hát:</b> <b>{music_title}</b>\n"
        f"║ 👤 <b>Nghệ sĩ:</b> {music_author}\n"
        f"║ 🆔 <b>Source ID:</b> <code>{video_id}</code>\n"
        f"╚══════════════════════════════════════════╝"
    )

    tmp_music_file = await download_file_to_temp(music_url, max_size_mb=30, suffix=".mp3")
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if tmp_music_file:
            with open(tmp_music_file, "rb") as mf:
                await query.message.reply_audio(
                    audio=mf,
                    title=music_title,
                    performer=music_author,
                    caption=caption_clean,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await query.message.reply_audio(
                audio=music_url,
                title=music_title,
                performer=music_author,
                caption=caption_clean,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Lỗi gửi audio callback: {e}")
        await query.message.reply_text("❌ Lỗi gửi audio: Không thể chuyển tiếp file từ CDN.")
    finally:
        if tmp_music_file and os.path.exists(tmp_music_file):
            try:
                os.remove(tmp_music_file)
            except OSError:
                pass


# ================= LỆNH /music =================
async def cmd_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU ĐƯỜNG LINK</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/music &lt;link_tiktok&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/music https://vt.tiktok.com/...</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_MUSIC, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    raw_url = context.args[0].strip()
    if "tiktok.com" not in raw_url:
        await update.message.reply_text("⚠️ Vui lòng cung cấp link TikTok hợp lệ.", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ <i>Đang bóc tách file âm thanh gốc...</i>", parse_mode=ParseMode.HTML)

    target_url = await resolve_tiktok_url(raw_url)
    data = await tikwm_req({"url": target_url, "hd": 1})
    if not data or data.get("code") != 0:
        data = await fallback_tik_download(target_url)

    if not data or data.get("code") != 0 or not data.get("data"):
        await msg.edit_text("❌ <b>Không trích xuất được:</b> Video riêng tư, bị xoá hoặc link không hợp lệ.")
        return

    res = data["data"]
    raw_music = res.get("music") or res.get("music_info", {}).get("play")
    music_url = ensure_full_url(raw_music)

    if not music_url:
        await msg.edit_text("❌ Video này không có âm thanh hoặc bị tắt tiếng do bản quyền.")
        return

    music_title = html.escape(res.get("music_info", {}).get("title") or "TikTok Audio")
    music_author = html.escape(res.get("music_info", {}).get("author") or "Original Sound")

    audio_panel = (
        f"╔══════════ 🎵 <b>TIKTOK AUDIO EXTRACTED</b> ══════════╗\n"
        f"║ 🎼 <b>Track:</b> <b>{music_title}</b>\n"
        f"║ 👤 <b>Artist:</b> {music_author}\n"
        f"║ ⚡ <b>Format:</b> High Quality MP3 Audio\n"
        f"╚════════════════════════════════════════════╝"
    )

    tmp_music_file = await download_file_to_temp(music_url, max_size_mb=30, suffix=".mp3")
    await msg.delete()
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if tmp_music_file:
            with open(tmp_music_file, "rb") as mf:
                await update.message.reply_audio(
                    audio=mf,
                    title=music_title,
                    performer=music_author,
                    caption=caption_clean,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await update.message.reply_audio(
                audio=music_url,
                title=music_title,
                performer=music_author,
                caption=caption_clean,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Lỗi gửi audio: {e}")
        await update.message.reply_text("❌ Lỗi gửi file audio lên Telegram.")
    finally:
        if tmp_music_file and os.path.exists(tmp_music_file):
            try:
                os.remove(tmp_music_file)
            except OSError:
                pass


# ================= LỆNH /getinfo =================
async def cmd_getinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU THAM SỐ</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/getinfo &lt;username&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/getinfo tiktok</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_GETINFO, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    username = context.args[0].strip().lstrip("@")
    status_msg = await update.message.reply_text(
        f"⚡ <i>Đang quét dữ liệu người dùng</i> <code>@{html.escape(username)}</code>...",
        parse_mode=ParseMode.HTML,
    )

    info_data = await fetch_tiktok_user_info(username)
    report, avatar = format_user_info_panel(info_data, username)

    await status_msg.delete()
    photo_to_send = avatar or IMG_GETINFO
    try:
        await update.message.reply_photo(photo=photo_to_send, caption=report, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)


# ================= TỰ ĐỘNG TẢI KHI GỬI LINK TIKTOK =================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    if "tiktok.com" in text:
        match = re.search(r"https?://[^\s]+", text)
        if not match:
            return
        raw_url = match.group(0)

        msg = await update.message.reply_text("⏳ <i>Đang tải dữ liệu HD...</i>", parse_mode=ParseMode.HTML)

        target_url = await resolve_tiktok_url(raw_url)
        data = await tikwm_req({"url": target_url, "hd": 1})
        if not data or data.get("code") != 0:
            logger.warning("TikWM không phản hồi hoặc lỗi, dùng fallback LoveTik...")
            data = await fallback_tik_download(target_url)

        if not data or data.get("code") != 0 or not data.get("data"):
            await msg.edit_text("❌ <b>Tải thất bại:</b> Video đã bị xóa, tài khoản riêng tư hoặc link không đúng.")
            return

        res = data["data"]
        video_id = str(res.get("id") or "")
        title = html.escape(res.get("title") or "TikTok Video")
        author = html.escape(res.get("author", {}).get("nickname") or "N/A")
        music_title = html.escape(res.get("music_info", {}).get("title") or "Original Sound")

        caption = (
            f"╔══════════ 🎬 <b>TIKTOK HD DOWNLOAD</b> ══════════╗\n"
            f"║ 📝 <b>Tiêu đề:</b> {title}\n"
            f"║ 👤 <b>Tác giả:</b> {author}\n"
            f"║ 🎵 <b>Âm thanh:</b> <i>{music_title}</i>\n"
            f"╠════════════════════════════════════╣\n"
            f"║ ❤️ <code>{res.get('digg_count', 0):,}</code> tym │ "
            f"💬 <code>{res.get('comment_count', 0):,}</code> cmt │ "
            f"🔁 <code>{res.get('share_count', 0):,}</code> share\n"
            f"╚════════════════════════════════════╝"
        )
        caption_clean = truncate_text(caption, 1020)

        keyboard = []
        if video_id:
            keyboard.append([InlineKeyboardButton("🎵 Tải nhạc MP3 của video", callback_data=f"dlmusic_{video_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        if res.get("images"):
            await msg.delete()
            all_images = res["images"]
            for i in range(0, len(all_images), 10):
                batch = all_images[i : i + 10]
                media = [InputMediaPhoto(media=ensure_full_url(img)) for img in batch]
                await update.message.reply_media_group(media=media)

            await update.message.reply_photo(
                photo=IMG_DOWN,
                caption=caption_clean,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return

        raw_video_url = res.get("hdplay") or res.get("play")
        video_url = ensure_full_url(raw_video_url)

        if not video_url:
            await msg.edit_text("❌ Không trích xuất được link video chất lượng cao.")
            return

        tmp_video_file = await download_file_to_temp(video_url, max_size_mb=50, suffix=".mp4")
        await msg.delete()

        try:
            if tmp_video_file:
                with open(tmp_video_file, "rb") as vf:
                    await update.message.reply_video(
                        video=vf,
                        caption=caption_clean,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        read_timeout=90,
                        write_timeout=90,
                    )
            else:
                await update.message.reply_video(
                    video=video_url,
                    caption=caption_clean,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=90,
                    write_timeout=90,
                )
        except Exception as e:
            logger.error(f"Lỗi gửi video: {e}")
            await update.message.reply_text("❌ Video vượt quá giới hạn 50MB của bot hoặc CDN Telegram phản hồi chậm.")
        finally:
            if tmp_video_file and os.path.exists(tmp_video_file):
                try:
                    os.remove(tmp_video_file)
                except OSError:
                    pass


# ================= KHỞI CHẠY BOT =================
def main():
    if not BOT_TOKEN:
        print("[!] Lỗi nghiêm trọng: BOT_TOKEN trống.")
        sys.exit(1)

    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            MULTI-PLATFORM TOOLKIT ONLINE             ║\n"
        "║        Railway Engine • Python Telegram v20+         ║\n"
        "║ Features: Anime (AniList Core) + Music + TT + FB     ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )
    print(terminal_banner)

    app = Application.builder().token(BOT_TOKEN).post_shutdown(close_http_session).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("anime", cmd_anime))
    app.add_handler(CommandHandler("sing", cmd_sing))
    app.add_handler(CommandHandler("getinfo", cmd_getinfo))
    app.add_handler(CommandHandler("music", cmd_music))
    app.add_handler(CommandHandler("downmusic", cmd_music))
    app.add_handler(CommandHandler("fb", cmd_fb))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_anime_episodes_callback, pattern=r"^anisel_"))
    app.add_handler(CallbackQueryHandler(handle_anime_download_callback, pattern=r"^anidl_"))
    app.add_handler(CallbackQueryHandler(handle_youtube_download_callback, pattern=r"^ytdl_"))
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern=r"^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern=r"^panel_"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()

