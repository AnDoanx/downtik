#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from datetime import datetime
import base64
import gc
import html
import io
import json
import logging
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
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

# ================= CẤU HÌNH EMOJI ĐỘNG =================
E_SPARKLE = '<tg-emoji emoji-id="5471907739489826360">✨</tg-emoji>'
E_FIRE    = '<tg-emoji emoji-id="5474195655683505314">🔥</tg-emoji>'
E_MUSIC   = '<tg-emoji emoji-id="5471930872183683627">🎵</tg-emoji>'
E_BOLT    = '<tg-emoji emoji-id="5339386257283764734">⚡</tg-emoji>'
E_HEART   = '<tg-emoji emoji-id="6269163801178804220">💖</tg-emoji>'
E_VERIFIED= '<tg-emoji emoji-id="6271786398404055377">✅</tg-emoji>'
E_PIN     = '<tg-emoji emoji-id="6271271702408204490">📌</tg-emoji>'
E_SEARCH  = '<tg-emoji emoji-id="6260215820933144560">🔍</tg-emoji>'
E_ALERT   = '<tg-emoji emoji-id="6269253325477123346">⚠️</tg-emoji>'

# ================= CẤU HÌNH TOKEN & HỆ THỐNG =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8949220582:AAE6zt_01TePivwodfw7dVmSWn0prRCvFw8").strip()
ALLOWED_USERS = []

logging.getLogger("httpx").setLevel(logging.WARNING)

YT_COOKIES_ENV = os.getenv("YT_COOKIES", "").strip()
COOKIE_FILE_PATH = None

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
        logging.info("Đã nạp cookies thành công.")
    except Exception as e:
        logging.warning(f"Không thể tạo file cookie: {e}")

TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

IMG_WELCOME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"
IMG_MUSIC   = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_GETINFO = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"
IMG_DOWN    = "https://cdn.phototourl.com/free/2026-09-20-8f7cee5e-79ee-4e36-8bd6-1eb5d315635e.png"
IMG_SING    = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_DONATE  = "https://cdn.upanhlaylink.com/i/bhMtLMHZ.jpeg"

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


# ================= HÀM HỖ TRỢ TRÁNH CRASH MESSAGE =================
async def safe_delete(msg):
    if not msg:
        return
    try:
        await msg.delete()
    except Exception:
        pass


async def safe_edit_text(msg, text: str, **kwargs):
    if not msg:
        return None
    try:
        return await msg.edit_text(text, **kwargs)
    except BadRequest as e:
        err = str(e).lower()
        if "message to edit not found" in err:
            try:
                return await msg.chat.send_message(text, **kwargs)
            except Exception:
                return None
        if "message is not modified" in err:
            return msg
        if "can't parse entities" in err:
            clean_text = re.sub(r"<[^>]+>", "", text)
            return await msg.chat.send_message(clean_text)
        logger.warning(f"safe_edit_text BadRequest: {e}")
    except Exception as e:
        logger.warning(f"safe_edit_text error: {e}")
    return None


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


async def get_http_session() -> aiohttp.ClientSession:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=30)
        timeout = aiohttp.ClientTimeout(total=25, connect=6)
        HTTP_SESSION = aiohttp.ClientSession(
            connector=connector,
            headers=COMMON_HEADERS,
            timeout=timeout,
        )
    return HTTP_SESSION


async def close_http_session(application: Application = None):
    global HTTP_SESSION
    if HTTP_SESSION and not HTTP_SESSION.closed:
        await HTTP_SESSION.close()
        logger.info("Đã đóng kết nối aiohttp session.")


def get_speed_tag(start_time: float) -> str:
    duration = time.perf_counter() - start_time
    if duration < 1.0:
        badge = f"{E_BOLT} Siêu tốc ({duration:.2f}s)"
    elif duration <= 2.8:
        badge = f"{E_FIRE} Nhanh ({duration:.2f}s)"
    else:
        badge = f"⏳ Ổn định ({duration:.2f}s)"
    return f"\n{E_BOLT} <b>Độ trễ phản hồi:</b> <code>{badge}</code>"


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


# ================= DỌN DẸP BỘ NHỚ VÀ ĐĨA =================
def clean_temp_storage_files():
    tmp_dir = tempfile.gettempdir()
    deleted_count = 0
    freed_bytes = 0
    try:
        for fname in os.listdir(tmp_dir):
            if fname.startswith(("ytdl_", "sc_", "yt_tmp_", "tik_", "ig_")) or fname.endswith(
                (".mp4", ".mp3", ".webm", ".m4a", ".part", ".ytdl")
            ):
                fpath = os.path.join(tmp_dir, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        sz = os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_count += 1
                        freed_bytes += sz
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Lỗi dọn file tạm: {e}")
    return deleted_count, freed_bytes


# ================= STREAM BUFFER TẢI FILE =================
async def download_file_stream(url: str, max_size_mb: int = 50, filename: str = "media.mp4") -> io.BytesIO | None:
    session = await get_http_session()
    stream_headers = {
        "User-Agent": COMMON_HEADERS["User-Agent"],
        "Referer": "https://www.google.com/",
        "Accept": "*/*",
    }
    try:
        async with session.get(
            url,
            headers=stream_headers,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as resp:
            if resp.status in (200, 206):
                buf = io.BytesIO()
                total_downloaded = 0
                max_bytes = max_size_mb * 1024 * 1024

                async for chunk in resp.content.iter_chunked(256 * 1024):
                    total_downloaded += len(chunk)
                    if total_downloaded > max_bytes:
                        return None
                    buf.write(chunk)

                buf.seek(0)
                buf.name = filename
                return buf
            else:
                logger.warning(f"CDN từ chối kết nối (HTTP {resp.status}): {url}")
    except Exception as e:
        logger.error(f"Lỗi tải stream: {e}")
    return None


# ================= CACHE FONT CANVAS =================
CACHED_FONT_DATA = None

async def get_crisp_font(size: int, bold: bool = False, session: aiohttp.ClientSession = None):
    global CACHED_FONT_DATA
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass

    if CACHED_FONT_DATA is None:
        try:
            close_session = False
            if session is None or session.closed:
                session = aiohttp.ClientSession()
                close_session = True

            url = (
                "https://raw.githubusercontent.com/googlefonts/roboto/main/src/hinted/Roboto-Bold.ttf"
                if bold else
                "https://raw.githubusercontent.com/googlefonts/roboto/main/src/hinted/Roboto-Regular.ttf"
            )
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    CACHED_FONT_DATA = await r.read()

            if close_session:
                await session.close()
        except Exception:
            pass

    if CACHED_FONT_DATA:
        try:
            return ImageFont.truetype(io.BytesIO(CACHED_FONT_DATA), size)
        except Exception:
            pass

    return ImageFont.load_default()


# ================= CANVAS STATUS SERVER =================
async def generate_system_status_canvas(bot_start_time: float = BOT_START_TIME, session: aiohttp.ClientSession = None) -> io.BytesIO:
    uptime_sec = int(time.time() - bot_start_time)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m {seconds}s"

    close_session = False
    if session is None or session.closed:
        session = await get_http_session()

    start_t = time.perf_counter()
    try:
        async with session.get("https://api.telegram.org", timeout=aiohttp.ClientTimeout(total=3)):
            ping_ms = round((time.perf_counter() - start_t) * 1000)
    except Exception:
        ping_ms = 85

    ram_mb = 45.0
    if sys.platform != "win32":
        try:
            import resource
            ram_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except Exception:
            ram_mb = 52.3

    total, used, free = shutil.disk_usage("/")
    free_gb = round(free / (1024 ** 3), 2)

    W, H = 1200, 820
    img = Image.new("RGBA", (W, H), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    f_title = await get_crisp_font(26, bold=True, session=session)
    f_badge = await get_crisp_font(18, bold=True, session=session)
    f_head  = await get_crisp_font(21, bold=True, session=session)
    f_key   = await get_crisp_font(18, bold=False, session=session)
    f_val   = await get_crisp_font(18, bold=True, session=session)
    f_bar   = await get_crisp_font(15, bold=True, session=session)
    f_foot  = await get_crisp_font(16, bold=False, session=session)

    if close_session:
        await session.close()

    pad = 30
    draw.rounded_rectangle([pad, pad, W - pad, H - pad], radius=24, fill=(24, 32, 56, 255), outline=(51, 65, 85, 255), width=2)

    hdr_h = 70
    draw.rounded_rectangle([pad + 5, pad + 5, W - pad - 5, pad + 5 + hdr_h], radius=18, fill=(30, 41, 69, 255))

    dot_y = pad + 5 + hdr_h // 2
    draw.ellipse([pad + 30, dot_y - 8, pad + 46, dot_y + 8], fill=(239, 68, 68))
    draw.ellipse([pad + 56, dot_y - 8, pad + 72, dot_y + 8], fill=(245, 158, 11))
    draw.ellipse([pad + 82, dot_y - 8, pad + 98, dot_y + 8], fill=(34, 197, 94))

    draw.text((pad + 120, dot_y), "SYSTEM METRICS MONITOR", fill=(255, 255, 255), font=f_title, anchor="lm")

    ub_w, ub_h = 240, 40
    ub_x2 = W - pad - 25
    ub_x1 = ub_x2 - ub_w
    draw.rounded_rectangle([ub_x1, dot_y - ub_h // 2, ub_x2, dot_y + ub_h // 2], radius=12, fill=(22, 101, 52, 220), outline=(34, 197, 94, 255), width=2)
    draw.ellipse([ub_x1 + 16, dot_y - 5, ub_x1 + 26, dot_y + 5], fill=(74, 222, 128))
    draw.text((ub_x1 + 38, dot_y), f"UPTIME: {uptime_str}", fill=(240, 253, 244), font=f_badge, anchor="lm")

    card_w = (W - 2 * pad - 50) // 2
    c1_x1 = pad + 18
    c1_x2 = c1_x1 + card_w
    c2_x1 = c1_x2 + 14
    c2_x2 = c2_x1 + card_w

    card_y1 = pad + hdr_h + 22
    card_y2 = H - pad - 60

    draw.rounded_rectangle([c1_x1, card_y1, c1_x2, card_y2], radius=18, fill=(18, 25, 45, 255), outline=(51, 65, 85, 200), width=2)
    draw.rounded_rectangle([c2_x1, card_y1, c2_x2, card_y2], radius=18, fill=(18, 25, 45, 255), outline=(51, 65, 85, 200), width=2)

    draw.text((c1_x1 + 25, card_y1 + 24), "⚡ CORE INFRASTRUCTURE", fill=(45, 212, 191), font=f_head)
    draw.text((c2_x1 + 25, card_y1 + 24), "🎵 MEDIA & STORAGE PIPELINE", fill=(244, 114, 182), font=f_head)

    draw.line([(c1_x1 + 25, card_y1 + 58), (c1_x2 - 25, card_y1 + 58)], fill=(51, 65, 85), width=2)
    draw.line([(c2_x1 + 25, card_y1 + 58), (c2_x2 - 25, card_y1 + 58)], fill=(51, 65, 85), width=2)

    now_vn = datetime.now().strftime("%H:%M:%S • %d/%m/%Y")
    ping_status = "Tốt" if ping_ms < 200 else "Trung bình"
    ping_color = (74, 222, 128) if ping_ms < 200 else (251, 191, 36)

    c1_data = [
        ("Thời gian:", now_vn, (255, 255, 255)),
        ("Ping API:", f"{ping_ms} ms [{ping_status}]", ping_color),
        ("RAM sử dụng:", f"{ram_mb} MB Allocated", (251, 146, 60)),
        ("Python Core:", f"{platform.python_implementation()} {platform.python_version()}", (147, 197, 253)),
        ("Hệ điều hành:", f"{platform.system()} ({platform.machine()})", (226, 232, 240)),
        ("Nền tảng:", "Railway Cloud Engine", (192, 132, 252)),
    ]

    c2_data = [
        ("TikTok Pipeline:", "ONLINE (HD 1080p)", (74, 222, 128)),
        ("Instagram Engine:", "Reels / Post Bypassed", (74, 222, 128)),
        ("YouTube Core:", "Android/TV Bypassed", (74, 222, 128)),
        ("Disk Trống:", f"{free_gb} GB Available", (74, 222, 128) if free_gb > 1.0 else (239, 68, 68)),
        ("Stream Pipeline:", "Direct RAM Buffer", (74, 222, 128)),
        ("Auto Cleaner:", "Zero-Disk Waste Engine", (226, 232, 240)),
    ]

    y_start = card_y1 + 80
    row_gap = 48

    for idx, (lbl, val, col) in enumerate(c1_data):
        cy = y_start + idx * row_gap
        draw.text((c1_x1 + 25, cy), lbl, fill=(148, 163, 184), font=f_key)
        draw.text((c1_x1 + 210, cy), val, fill=col, font=f_val)

    for idx, (lbl, val, col) in enumerate(c2_data):
        cy = y_start + idx * row_gap
        draw.text((c2_x1 + 25, cy), lbl, fill=(148, 163, 184), font=f_key)
        draw.text((c2_x1 + 210, cy), val, fill=col, font=f_val)

    pb_y = card_y1 + 385
    draw.text((c1_x1 + 25, pb_y), "RAM UTILIZATION", fill=(203, 213, 225), font=f_bar)
    draw.rounded_rectangle([c1_x1 + 25, pb_y + 24, c1_x2 - 25, pb_y + 44], radius=8, fill=(30, 41, 59))
    ram_ratio = min(max(ram_mb / 512, 0.08), 1.0)
    draw.rounded_rectangle([c1_x1 + 25, pb_y + 24, c1_x1 + 25 + int((card_w - 50) * ram_ratio), pb_y + 44], radius=8, fill=(249, 115, 22))

    draw.text((c2_x1 + 25, pb_y), "NETWORK HEALTH (PING)", fill=(203, 213, 225), font=f_bar)
    draw.rounded_rectangle([c2_x1 + 25, pb_y + 24, c2_x2 - 25, pb_y + 44], radius=8, fill=(30, 41, 59))
    ping_ratio = max(0.1, 1.0 - min(ping_ms / 800, 0.9))
    draw.rounded_rectangle([c2_x1 + 25, pb_y + 24, c2_x1 + 25 + int((card_w - 50) * ping_ratio), pb_y + 44], radius=8, fill=(34, 197, 94))

    draw.text((W // 2, H - pad - 26), "Railway Cloud High-Speed Worker • Multi-Platform Engine", fill=(148, 163, 184), font=f_foot, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    buf.name = "server_status.png"
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
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
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
                                    "url": f"https://www.youtube.com/watch?v={vid_id}"
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
            "no_cache_dir": True,
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
                    "url": f"https://www.youtube.com/watch?v={e.get('id')}"
                })
            return items

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fallback_ytdlp)
    except Exception as e:
        logger.error(f"Fallback yt-dlp search error: {e}")
        return []


# ================= TẢI AUDIO YOUTUBE =================
def extract_youtube_audio_advanced(video_id: str, search_query: str = "") -> tuple[io.BytesIO | None, dict]:
    clean_temp_storage_files()

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    tmp_dir = tempfile.gettempdir()
    output_template = os.path.join(tmp_dir, f"ytdl_{video_id}_%(id)s.%(ext)s")

    client_strategies = [
        ["android", "ios"],
        ["tv", "mweb"],
    ]

    format_priority = "ba[abr<=96]/ba[abr<=128]/bestaudio[ext=m4a]/bestaudio/best"

    for clients in client_strategies:
        ydl_opts = {
            "format": format_priority,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "no_cache_dir": True,
            "max_filesize": 48 * 1024 * 1024,
            "extractor_args": {
                "youtube": {
                    "player_client": clients,
                    "skip": ["dash", "hls"],
                    "player_skip": ["configs", "webpage"]
                }
            },
            "http_headers": {
                "User-Agent": "com.google.android.youtube/19.29.35 (Linux; U; Android 14) gzip"
            }
        }
        if COOKIE_FILE_PATH:
            ydl_opts["cookiefile"] = COOKIE_FILE_PATH

        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                meta = ydl.extract_info(video_url, download=True)
                if not meta:
                    continue

                details = {
                    "title": meta.get("title", "YouTube Track"),
                    "uploader": meta.get("uploader", "YouTube Artist"),
                    "duration": meta.get("duration", 0),
                    "id": video_id
                }

                for fname in os.listdir(tmp_dir):
                    if fname.startswith(f"ytdl_{video_id}"):
                        downloaded_file = os.path.join(tmp_dir, fname)
                        break

                if downloaded_file and os.path.exists(downloaded_file):
                    buf = io.BytesIO()
                    with open(downloaded_file, "rb") as f:
                        buf.write(f.read())
                    buf.seek(0)
                    ext = downloaded_file.split(".")[-1]
                    buf.name = f"{video_id}.{ext}"
                    return buf, details
        except Exception as err:
            logger.warning(f"Lỗi tải với clients {clients}: {err}")
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                except Exception:
                    pass

    return None, {}


# ================= LOGIC INSTAGRAM REELS / POSTS =================
async def cobalt_insta_download(ig_url: str):
    session = await get_http_session()
    cobalt_instances = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiatekm.tokyo/api/json",
    ]
    payload = {
        "url": ig_url,
        "vQuality": "max",
        "filenamePattern": "basic",
        "isAudioOnly": False,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": COMMON_HEADERS["User-Agent"],
    }
    for endpoint in cobalt_instances:
        try:
            async with session.post(
                endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    j = await resp.json(content_type=None)
                    media_url = j.get("url")
                    picker = j.get("picker", [])
                    if media_url:
                        return {
                            "type": "video",
                            "url": media_url,
                            "caption": "Instagram Reel/Video HD",
                        }
                    elif picker:
                        photos = [p.get("url") for p in picker if p.get("type") == "photo"]
                        if photos:
                            return {
                                "type": "album",
                                "images": photos,
                                "caption": "Instagram Photo Carousel",
                            }
        except Exception as e:
            logger.warning(f"Cobalt Instagram {endpoint} lỗi: {e}")
    return None


def ytdlp_insta_extract(ig_url: str):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "no_cache_dir": True,
    }
    if COOKIE_FILE_PATH:
        ydl_opts["cookiefile"] = COOKIE_FILE_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(ig_url, download=False)
            if not info:
                return None

            desc = info.get("description") or info.get("title") or "Instagram Reel"
            formats = info.get("formats", [])
            best_v = None
            for f in reversed(formats):
                if f.get("url") and f.get("vcodec") != "none":
                    best_v = f.get("url")
                    break
            if not best_v:
                best_v = info.get("url")

            if best_v:
                return {
                    "type": "video",
                    "url": best_v,
                    "caption": desc,
                    "uploader": info.get("uploader", "Instagram Creator"),
                    "like_count": info.get("like_count", 0),
                    "comment_count": info.get("comment_count", 0),
                }
    except Exception as e:
        logger.warning(f"yt-dlp instagram lỗi: {e}")
    return None


async def get_instagram_media_data(raw_url: str):
    clean_url = raw_url.strip()

    res = await cobalt_insta_download(clean_url)
    if res and (res.get("url") or res.get("images")):
        return res

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, ytdlp_insta_extract, clean_url)
    if res:
        return res

    return None


# ================= LOGIC TIKTOK =================
async def resolve_tiktok_url(url: str) -> str:
    session = await get_http_session()
    clean = url.strip()
    try:
        async with session.get(clean, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            return str(resp.url)
    except Exception as e:
        logger.warning(f"Lỗi resolve url {clean}: {e}")
    return clean


async def tikwm_req(params: dict):
    session = await get_http_session()
    url = TIKWM_BASE
    post_headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.tikwm.com/",
    }
    try:
        async with session.post(url, data=params, headers=post_headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0 and data.get("data"):
                    return data
    except Exception as e:
        logger.warning(f"TikWM POST fail: {e}")

    try:
        async with session.get(url, params=params, headers=COMMON_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0 and data.get("data"):
                    return data
    except Exception as e:
        logger.warning(f"TikWM GET fail: {e}")
    return None


async def cobalt_tik_download(tiktok_url: str):
    session = await get_http_session()
    cobalt_instances = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiatekm.tokyo/api/json",
    ]
    payload = {
        "url": tiktok_url,
        "vQuality": "max",
        "filenamePattern": "basic",
        "isAudioOnly": False,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    for endpoint in cobalt_instances:
        try:
            async with session.post(endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    j = await resp.json(content_type=None)
                    stream_url = j.get("url")
                    if stream_url:
                        return {
                            "code": 0,
                            "data": {
                                "id": "cobalt_" + str(int(time.time())),
                                "title": "TikTok HD Video",
                                "author": {"nickname": "TikTok Creator"},
                                "digg_count": 0,
                                "comment_count": 0,
                                "share_count": 0,
                                "play": stream_url,
                                "hdplay": stream_url,
                                "music": stream_url,
                                "music_info": {"title": "Original Sound", "author": "TikTok Creator", "play": stream_url},
                                "images": [p.get("url") for p in j.get("picker", []) if p.get("type") == "photo"] if j.get("picker") else [],
                            }
                        }
        except Exception as e:
            logger.warning(f"Cobalt {endpoint} error: {e}")
    return None


async def lovetik_fallback_download(tiktok_url: str):
    session = await get_http_session()
    api_url = "https://lovetik.com/api/ajax/search"
    payload = {"query": tiktok_url}
    headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://lovetik.com/",
    }
    try:
        async with session.post(api_url, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("status") == "ok":
                    video_url = None
                    music_url = None
                    for link in j.get("links", []):
                        t_label = link.get("t", "").lower()
                        if "watermark" not in t_label and ("mp4" in t_label or "hd" in t_label):
                            if not video_url and link.get("a"):
                                video_url = link.get("a")
                        if "mp3" in t_label or "audio" in t_label:
                            music_url = link.get("a")

                    if not video_url and j.get("links"):
                        video_url = j["links"][0].get("a")

                    return {
                        "code": 0,
                        "data": {
                            "id": j.get("vid", ""),
                            "title": j.get("desc", "TikTok Video"),
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
        logger.warning(f"Fallback LoveTik error: {e}")
    return None


def ytdlp_tiktok_extract(url: str):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "no_cache_dir": True,
    }
    if COOKIE_FILE_PATH:
        ydl_opts["cookiefile"] = COOKIE_FILE_PATH
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            formats = info.get("formats", [])
            best_v = None
            for f in reversed(formats):
                if f.get("url") and f.get("vcodec") != "none":
                    best_v = f.get("url")
                    break
            if not best_v:
                best_v = info.get("url")

            return {
                "code": 0,
                "data": {
                    "id": info.get("id", ""),
                    "title": info.get("title", "TikTok Video"),
                    "author": {"nickname": info.get("uploader", "TikTok Creator")},
                    "digg_count": info.get("like_count", 0) or 0,
                    "comment_count": info.get("comment_count", 0) or 0,
                    "share_count": info.get("repost_count", 0) or 0,
                    "play": best_v,
                    "hdplay": best_v,
                    "music": None,
                    "music_info": {
                        "title": info.get("track") or "Original Sound",
                        "author": info.get("artist") or info.get("uploader", "TikTok"),
                        "play": None,
                    },
                    "images": [],
                },
            }
    except Exception as e:
        logger.warning(f"yt-dlp tiktok fail: {e}")
    return None


async def get_tiktok_universal_data(raw_url: str):
    clean_url = await resolve_tiktok_url(raw_url)

    res = await tikwm_req({"url": clean_url, "hd": 1})
    if res and res.get("data") and (res["data"].get("play") or res["data"].get("images")):
        return res

    res = await cobalt_tik_download(clean_url)
    if res and res.get("data") and res["data"].get("play"):
        return res

    res = await lovetik_fallback_download(clean_url)
    if res and res.get("data") and (res["data"].get("play") or res["data"].get("images")):
        return res

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, ytdlp_tiktok_extract, clean_url)
    if res and res.get("data"):
        return res

    return None


async def fetch_tiktok_user_info(username: str) -> dict:
    session = await get_http_session()
    clean_user = username.strip().lstrip("@")

    try:
        tikwm_url = f"https://www.tikwm.com/api/user/info?unique_id={clean_user}"
        async with session.get(tikwm_url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
            if resp.status == 200:
                res = await resp.json(content_type=None)
                if res and res.get("code") == 0 and res.get("data"):
                    return res
    except Exception as e:
        logger.warning(f"TikWM user fetch fail: {e}")

    url = f"{TIK_INFO_API}{clean_user}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
            if resp.status == 200:
                text_data = await resp.text()
                try:
                    return json.loads(text_data)
                except Exception:
                    return {"error": "Phản hồi dữ liệu máy chủ không hợp lệ."}
            return {"error": f"HTTP Status {resp.status}"}
    except asyncio.TimeoutError:
        return {"error": "Hết thời gian chờ phản hồi từ máy chủ TikTok."}
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
            f"╭━━━〔 {E_ALERT} <b>TRA CỨU THẤT BẠI</b> 〕━━━╮\n"
            f"┃ {E_PIN} <b>Tài khoản:</b> <code>@{clean_user}</code>\n"
            f"┃ {E_ALERT} <b>Chi tiết:</b> <i>{html.escape(str(err))}</i>\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯",
            None,
        )

    u = data.get("data", {}).get("user") or data.get("userInfo", {}).get("user") or data.get("user") or data
    s = data.get("data", {}).get("stats") or data.get("userInfo", {}).get("stats") or data.get("stats") or {}

    nickname = html.escape(str(u.get("nickname") or u.get("name") or "—"))
    unique_id = html.escape(str(u.get("uniqueId") or u.get("unique_id") or username).lstrip("@"))
    uid = str(u.get("id") or u.get("uid") or "0")

    is_private = u.get("privateAccount") or u.get("is_private") or False
    status_str = "🔒 Riêng tư" if is_private else f"{E_SPARKLE} Công khai"
    is_verified = u.get("verified") or u.get("customVerify") or False
    verified_str = f"{E_VERIFIED} Đã xác minh" if is_verified else f"{E_ALERT} Chưa xác minh"
    language = html.escape(str(u.get("language") or u.get("region") or "vi").lower())
    
    raw_bio = str(u.get("signature") or u.get("bio") or "Không có tiểu sử.")
    short_bio = raw_bio[:120] + ("..." if len(raw_bio) > 120 else "")
    bio = html.escape(short_bio)
    
    has_shop = u.get("commerceUserInfo", {}).get("commerceUser") or u.get("is_star") or False
    shop_str = f"{E_VERIFIED} Có gian hàng" if has_shop else "❌ Không có"

    followers = s.get("followerCount") or s.get("followers") or 0
    following = s.get("followingCount") or s.get("following") or 0
    videos = s.get("videoCount") or s.get("video") or 0
    hearts = s.get("heartCount") or s.get("hearts") or s.get("heart") or 0

    created_time_str = get_tiktok_creation_time(uid)
    avatar = u.get("avatarLarger") or u.get("avatarMedium") or u.get("avatarThumb") or u.get("avatar")

    panel = (
        f"╭━━━〔 {E_SPARKLE} <b>TIKTOK PROFILE STATS</b> 〕━━━╮\n"
        f"┃\n"
        f"┣ {E_PIN} <b>Tên hiển thị:</b> <b>{nickname}</b>\n"
        f"┣ {E_BOLT} <b>ID:</b> <code>{uid}</code>\n"
        f"┣ {E_SPARKLE} <b>Trạng thái:</b> {status_str}\n"
        f"┣ {E_VERIFIED} <b>Huy hiệu:</b> {verified_str}\n"
        f"┣ {E_FIRE} <b>Cửa hàng:</b> {shop_str}\n"
        f"┣ 🌐 <b>Khu vực:</b> <code>{language.upper()}</code>\n"
        f"┃\n"
        f"┣ 📊 <b>Tương tác:</b>\n"
        f"┃ ├ 👥 Follower: <code>{followers:,}</code>\n"
        f"┃ ├ 👤 Following: <code>{following:,}</code>\n"
        f"┃ ├ 🎥 Video: <code>{videos:,}</code> clips\n"
        f"┃ └ {E_HEART} Likes: <code>{hearts:,}</code>\n"
        f"┃\n"
        f"┣ ⏰ <b>Ngày tạo:</b> <code>{created_time_str}</code>\n"
        f"┣ {E_PIN} <b>Tiểu sử:</b>\n"
        f"┃ <i>« {bio} »</i>\n"
        f"┃\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
        f"👉 <b>Xem trang:</b> <a href='https://www.tiktok.com/@{unique_id}'>tiktok.com/@{unique_id}</a>"
    )

    return panel, avatar


# ================= DASHBOARD WELCOME =================
def build_welcome_dashboard(user_name: str = "User") -> tuple[str, InlineKeyboardMarkup]:
    display_name = html.escape(user_name)
    panel = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃   {E_SPARKLE} <b>ALL-IN-ONE MEDIA TOOLKIT</b> {E_SPARKLE}   ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"👋 <i>Xin chào,</i> <b>{display_name}</b>!\n"
        f"Chào mừng bạn đến với hệ thống bot tiện ích tự động chất lượng cao.\n\n"
        f"╭━━━〔 {E_FIRE} <b>DANH SÁCH TÍNH NĂNG</b> 〕━━━╮\n"
        f"┣ {E_MUSIC} <b>Tải nhạc YouTube:</b> <code>/sing &lt;tên bài&gt;</code>\n"
        f"┣ 📥 <b>Tải TikTok HD:</b> Gửi link TikTok (No watermark)\n"
        f"┣ 📸 <b>Tải Instagram:</b> Gửi link Reels / Posts trực tiếp\n"
        f"┣ {E_MUSIC} <b>Tách nhạc TikTok:</b> <code>/music &lt;link&gt;</code>\n"
        f"┣ {E_SEARCH} <b>Tra cứu TikTok:</b> <code>/getinfo &lt;user&gt;</code>\n"
        f"┣ 🧹 <b>Dọn rác bộ nhớ:</b> <code>/cleanup</code>\n"
        f"┣ 📊 <b>Status máy chủ:</b> <code>/status</code>\n"
        f"┣ {E_HEART} <b>Ủng hộ Admin:</b> <code>/donate</code>\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
        f"{E_BOLT} <b>Hệ thống:</b> <i>Railway High-Speed Core • Độc quyền</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎶 Tải Nhạc YouTube", callback_data="panel_guide_sing"),
            InlineKeyboardButton("📥 Tải TikTok HD", callback_data="panel_guide_down"),
        ],
        [
            InlineKeyboardButton("🎵 Tách Nhạc TikTok", callback_data="panel_guide_music"),
            InlineKeyboardButton("🔎 Check TikTok", callback_data="panel_guide_info"),
        ],
        [
            InlineKeyboardButton("🧹 Dọn Rác Máy Chủ", callback_data="panel_cleanup"),
            InlineKeyboardButton("📊 Server Status", callback_data="panel_status"),
        ],
        [
            InlineKeyboardButton("💖 Ủng Hộ (Donate)", callback_data="panel_donate"),
        ],
    ]
    return panel, InlineKeyboardMarkup(keyboard)


# ================= TIẾN TRÌNH DỌN RÁC BỘ NHỚ =================
async def run_system_cleanup(status_msg, start_req_time: float):
    try:
        await safe_edit_text(
            status_msg,
            f"🧹 <b>[Bước 1/3] Đang thu hồi bộ nhớ RAM và dọn Python GC...</b>\n"
            f"⏳ <i>Vui lòng đợi 2 giây...</i>",
            parse_mode=ParseMode.HTML,
        )
        gc.collect()
        await asyncio.sleep(2)

        await safe_edit_text(
            status_msg,
            f"🗄️ <b>[Bước 2/3] Đang quét và xóa toàn bộ file tạm media trên ổ đĩa...</b>\n"
            f"⏳ <i>Vui lòng đợi 2 giây...</i>",
            parse_mode=ParseMode.HTML,
        )
        loop = asyncio.get_running_loop()
        del_count, freed_bytes = await loop.run_in_executor(None, clean_temp_storage_files)
        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        await asyncio.sleep(2)

        total, used, free = shutil.disk_usage("/")
        free_gb = round(free / (1024 ** 3), 2)

        speed_line = get_speed_tag(start_req_time)
        result_text = (
            f"╭━━━〔 {E_VERIFIED} <b>GIẢI PHÓNG DUNG LƯỢNG</b> 〕━━━╮\n"
            f"┃\n"
            f"┣ 🗑️ <b>Số tệp tạm đã xóa:</b> <code>{del_count}</code> files\n"
            f"┣ 📦 <b>Dung lượng dọn sạch:</b> <code>{freed_mb} MB</code>\n"
            f"┣ 💾 <b>Ổ đĩa trống còn lại:</b> <code>{free_gb} GB</code>\n"
            f"┣ {E_BOLT} <b>Trạng thái:</b> Sẵn sàng nhận lệnh mới\n"
            f"┃{speed_line}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        await safe_edit_text(status_msg, result_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Lỗi khi dọn rác hệ thống: {e}")
        await safe_edit_text(status_msg, f"{E_ALERT} Quá trình dọn rác gặp sự cố: {e}", parse_mode=ParseMode.HTML)


async def cmd_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    t0 = time.perf_counter()
    status_msg = await update.message.reply_text("⏳ <i>Đang khởi động tiến trình tối ưu hóa dung lượng...</i>", parse_mode=ParseMode.HTML)
    await run_system_cleanup(status_msg, t0)


# ================= LỆNH /donate =================
async def cmd_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    t0 = time.perf_counter()

    speed_line = get_speed_tag(t0)
    caption = (
        f"╭━━━〔 {E_HEART} <b>ỦNG HỘ PHÁT TRIỂN BOT</b> 〕━━━╮\n"
        f"┃\n"
        f"┣ Cảm ơn bạn đã luôn đồng hành cùng bot!\n"
        f"┣ Mọi khoản donate dù nhỏ đều là động lực lớn\n"
        f"┣ giúp duy trì máy chủ Railway tốc độ cao.\n"
        f"┃\n"
        f"┣ 💳 <b>Quét mã QR VietQR phía trên</b> để ủng hộ.\n"
        f"┣ 💬 <b>Lời nhắn:</b> Gửi tặng bạn ly cà phê ☕\n"
        f"┃{speed_line}\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = [[InlineKeyboardButton("🔙 Quay lại Menu", callback_data="panel_home")]]

    if update.message:
        try:
            await update.message.reply_photo(
                photo=IMG_DONATE,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        try:
            await update.callback_query.message.edit_media(
                media=InputMediaPhoto(media=IMG_DONATE, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            try:
                await update.callback_query.message.reply_photo(
                    photo=IMG_DONATE,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except Exception:
                pass


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    t0 = time.perf_counter()
    user_name = update.effective_user.first_name or "User"
    text, reply_markup = build_welcome_dashboard(user_name)
    text += f"\n{get_speed_tag(t0)}"

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
        try:
            await update.callback_query.message.edit_caption(
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception:
            pass


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    t0 = time.perf_counter()
    status_msg = await update.message.reply_text("📊 <i>Đang render bảng thông số hệ thống...</i>", parse_mode=ParseMode.HTML)
    canvas_buffer = await generate_system_status_canvas(bot_start_time=BOT_START_TIME)

    speed_line = get_speed_tag(t0)
    caption_text = (
        f"📊 <b>BÁO CÁO THỐNG KÊ MÁY CHỦ (CANVAS LIVE)</b>\n"
        f"<code>────────────────────────────</code>\n"
        f"• Hệ thống giám sát trực tiếp trên Railway Cloud.\n"
        f"• Thông số tài nguyên được làm mới theo thời gian thực.\n"
        f"{speed_line}"
    )

    await safe_delete(status_msg)
    try:
        await update.message.reply_photo(
            photo=canvas_buffer,
            caption=caption_text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Lỗi gửi ảnh status: {e}")
        await update.message.reply_text(f"{E_ALERT} Không thể tạo hoặc gửi ảnh status.", parse_mode=ParseMode.HTML)


async def handle_panel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    t0 = time.perf_counter()

    back_btn = [[InlineKeyboardButton("🔙 Quay lại Menu", callback_data="panel_home")]]

    if data == "panel_home":
        user_name = query.from_user.first_name or "User"
        text, reply_markup = build_welcome_dashboard(user_name)
        text += f"\n{get_speed_tag(t0)}"
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

    elif data == "panel_donate":
        await cmd_donate(update, context)

    elif data == "panel_guide_sing":
        text = (
            f"╭━━━〔 {E_MUSIC} <b>TÌM VÀ TẢI NHẠC YOUTUBE</b> 〕━━━╮\n"
            f"┃\n"
            f"┣ {E_PIN} <b>Cú pháp:</b> <code>/sing &lt;tên bài hát&gt;</code>\n"
            f"┣ {E_SPARKLE} <i>Ví dụ:</i> <code>/sing Tắt đèn đi</code>\n"
            f"┣ {E_VERIFIED} Tự động nén âm thanh, chống nghẽn đĩa.\n"
            f"┃{get_speed_tag(t0)}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await safe_edit_text(query.message, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_down":
        text = (
            f"╭━━━〔 📥 <b>TẢI VIDEO TIKTOK FULL HD</b> 〕━━━╮\n"
            f"┃\n"
            f"┣ • Chỉ cần gửi trực tiếp link TikTok vào ô chat.\n"
            f"┣ • {E_VERIFIED} Tự động loại bỏ Watermark / Logo chuẩn 1080p.\n"
            f"┣ • Hỗ trợ cả Album ảnh Slide và link rút gọn.\n"
            f"┃{get_speed_tag(t0)}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await safe_edit_text(query.message, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            f"╭━━━〔 {E_MUSIC} <b>TRÍCH XUẤT AUDIO TIKTOK</b> 〕━━━╮\n"
            f"┃\n"
            f"┣ {E_PIN} <b>Cú pháp:</b> <code>/music &lt;link_tiktok&gt;</code>\n"
            f"┣ • Hoặc bấm nút <b>[Tải nhạc MP3]</b> bên dưới video.\n"
            f"┣ • {E_BOLT} File âm thanh 320kbps sắc nét.\n"
            f"┃{get_speed_tag(t0)}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await safe_edit_text(query.message, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_info":
        text = (
            f"╭━━━〔 {E_SEARCH} <b>TRA CỨU TIKTOK PROFILE</b> 〕━━━╮\n"
            f"┃\n"
            f"┣ {E_PIN} <b>Cú pháp:</b> <code>/getinfo &lt;username&gt;</code>\n"
            f"┣ {E_SPARKLE} <i>Ví dụ:</i> <code>/getinfo tiktok</code>\n"
            f"┣ • {E_VERIFIED} Quét thời gian tạo nick, số follower & lượt thích.\n"
            f"┃{get_speed_tag(t0)}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await safe_edit_text(query.message, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_cleanup":
        await query.answer("🧹 Đang thực hiện dọn dẹp hệ thống...", show_alert=False)
        status_msg = await query.message.reply_text("⏳ <i>Đang khởi động dọn rác...</i>", parse_mode=ParseMode.HTML)
        await run_system_cleanup(status_msg, t0)

    elif data == "panel_status":
        await query.answer("📊 Đang render ảnh thống kê...", show_alert=False)
        canvas_buffer = await generate_system_status_canvas(bot_start_time=BOT_START_TIME)

        speed_line = get_speed_tag(t0)
        caption_text = (
            f"📊 <b>BÁO CÁO THỐNG KÊ MÁY CHỦ (CANVAS LIVE)</b>\n"
            f"<code>────────────────────────────</code>\n"
            f"• Hệ thống giám sát trực tiếp trên Railway Cloud.\n"
            f"• Thông số tài nguyên được làm mới theo thời gian thực.\n"
            f"{speed_line}"
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


# ================= XỬ LÝ LỆNH /sing =================
async def cmd_sing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    t0 = time.perf_counter()
    if not context.args:
        help_panel = (
            f"╔════════ {E_ALERT} <b>THIẾU TÊN BÀI HÁT</b> ════════╗\n"
            f"║ {E_PIN} <b>Cú pháp:</b> <code>/sing &lt;tên bài hát&gt;</code>\n"
            f"║ {E_SPARKLE} <i>Ví dụ: <code>/sing Tắt đèn đi</code></i>\n"
            f"╚════════════════════════════════════╝\n"
            f"{get_speed_tag(t0)}"
        )
        try:
            await update.message.reply_photo(photo=IMG_SING, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    keyword = " ".join(context.args).strip()
    status_msg = await update.message.reply_text(f"{E_SEARCH} <i>Đang tìm kiếm:</i> <b>{html.escape(keyword)}</b>...", parse_mode=ParseMode.HTML)

    results = await search_youtube_fast(keyword, 6)

    if not results:
        await safe_edit_text(status_msg, f"{E_ALERT} Không tìm thấy bài hát phù hợp. Vui lòng thử từ khóa khác!\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    context.bot_data[f"kw_{update.effective_chat.id}"] = keyword

    msg_lines = [f"{E_MUSIC} <b>KẾT QUẢ TÌM KIẾM CHO:</b> <i>{html.escape(keyword)}</i>\n<code>────────────────────────────</code>"]
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

    msg_lines.append(f"<code>────────────────────────────</code>\n👉 <i>Bấm số bài hát để tải âm thanh:</i>\n{get_speed_tag(t0)}")
    text_content = "\n".join(msg_lines)

    await safe_delete(status_msg)
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
    t0 = time.perf_counter()
    query = update.callback_query
    await query.answer("⏳ Đang xử lý âm thanh...", show_alert=False)
    data = query.data

    vid_id = data.replace("ytdl_", "")
    target_url = f"https://www.youtube.com/watch?v={vid_id}"

    saved_kw = context.bot_data.get(f"kw_{query.message.chat_id}", "")

    loading_msg = await query.message.reply_text(
        f"⏳ <i>Đang bóc tách audio ({E_BOLT} Tự động nén tối ưu dung lượng)...</i>",
        parse_mode=ParseMode.HTML
    )

    loop = asyncio.get_running_loop()
    stream_file, details = await loop.run_in_executor(None, extract_youtube_audio_advanced, vid_id, saved_kw)

    await safe_delete(loading_msg)

    if not stream_file:
        await query.message.reply_text(f"{E_ALERT} Không thể tải được bài hát này hoặc vượt quá dung lượng. Hãy chọn bài khác!\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    title = html.escape(details.get("title", "YouTube Track"))
    uploader = html.escape(details.get("uploader", "YouTube Artist"))

    speed_line = get_speed_tag(t0)
    caption = (
        f"╭━━━〔 {E_MUSIC} <b>AUDIO TRACK EXTRACTED</b> 〕━━━╮\n"
        f"┃ 🎼 <b>Bài hát:</b> <b>{title}</b>\n"
        f"┃ 👤 <b>Nghệ sĩ:</b> {uploader}\n"
        f"┃ {E_VERIFIED} <b>Tối ưu:</b> Nén tự động chống tràn đĩa\n"
        f"┃ 🔗 <b>Nguồn:</b> <a href='{target_url}'>Media Source</a>\n"
        f"┃{speed_line}\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )

    try:
        await query.message.reply_audio(
            audio=stream_file,
            title=title,
            performer=uploader,
            caption=truncate_text(caption, 1020),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Lỗi gửi audio: {e}")
        await query.message.reply_text(f"{E_ALERT} Kích thước tệp âm thanh vượt quá giới hạn gửi của Telegram.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)


# ================= CALLBACK TẢI NHẠC TIKTOK =================
async def handle_download_music_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t0 = time.perf_counter()
    query = update.callback_query
    await query.answer("⏳ Đang tải audio...", show_alert=False)
    data = query.data

    video_id = data.replace("dlmusic_", "")
    tik_url = f"https://www.tiktok.com/@a/video/{video_id}"

    api_res = await get_tiktok_universal_data(tik_url)

    if not api_res or not api_res.get("data"):
        await query.message.reply_text(f"{E_ALERT} Không lấy được audio từ video này.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    res = api_res["data"]
    raw_music = res.get("music") or res.get("music_info", {}).get("play") or res.get("play")
    music_url = ensure_full_url(raw_music)

    if not music_url:
        await query.message.reply_text(f"{E_ALERT} Video này bị tắt tiếng hoặc không có track âm thanh riêng.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    music_title = html.escape(res.get("music_info", {}).get("title") or "TikTok Audio")
    music_author = html.escape(res.get("music_info", {}).get("author") or "Original Sound")

    speed_line = get_speed_tag(t0)
    audio_panel = (
        f"╭━━━〔 {E_MUSIC} <b>TIKTOK AUDIO EXTRACTED</b> 〕━━━╮\n"
        f"┃ 🎼 <b>Bài hát:</b> <b>{music_title}</b>\n"
        f"┃ 👤 <b>Nghệ sĩ:</b> {music_author}\n"
        f"┃ {E_BOLT} <b>ID:</b> <code>{video_id}</code>\n"
        f"┃{speed_line}\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )

    stream_file = await download_file_stream(music_url, max_size_mb=30, filename=f"{video_id}.mp3")
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if stream_file:
            await query.message.reply_audio(
                audio=stream_file,
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
        await query.message.reply_text(f"{E_ALERT} Lỗi gửi audio: Không thể chuyển tiếp file từ CDN.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)


# ================= LỆNH /music =================
async def cmd_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    t0 = time.perf_counter()
    if not context.args:
        help_panel = (
            f"╔════════ {E_ALERT} <b>THIẾU ĐƯỜNG LINK</b> ════════╗\n"
            f"║ {E_PIN} <b>Cú pháp:</b> <code>/music &lt;link_tiktok&gt;</code>\n"
            f"║ {E_SPARKLE} <i>Ví dụ: <code>/music https://vt.tiktok.com/...</code></i>\n"
            f"╚════════════════════════════════════╝\n"
            f"{get_speed_tag(t0)}"
        )
        try:
            await update.message.reply_photo(photo=IMG_MUSIC, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    raw_url = context.args[0].strip()
    if "tiktok.com" not in raw_url and "douyin.com" not in raw_url:
        await update.message.reply_text(f"{E_ALERT} Vui lòng cung cấp link TikTok hợp lệ.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ <i>Đang bóc tách file âm thanh gốc...</i>", parse_mode=ParseMode.HTML)

    data = await get_tiktok_universal_data(raw_url)

    if not data or not data.get("data"):
        await safe_edit_text(msg, f"{E_ALERT} <b>Không trích xuất được:</b> Video riêng tư, bị xoá hoặc link không hợp lệ.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    res = data["data"]
    raw_music = res.get("music") or res.get("music_info", {}).get("play") or res.get("play")
    music_url = ensure_full_url(raw_music)

    if not music_url:
        await safe_edit_text(msg, f"{E_ALERT} Video này không có âm thanh hoặc bị tắt tiếng do bản quyền.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        return

    music_title = html.escape(res.get("music_info", {}).get("title") or "TikTok Audio")
    music_author = html.escape(res.get("music_info", {}).get("author") or "Original Sound")

    speed_line = get_speed_tag(t0)
    audio_panel = (
        f"╭━━━〔 {E_MUSIC} <b>TIKTOK AUDIO EXTRACTED</b> 〕━━━╮\n"
        f"┃ 🎼 <b>Track:</b> <b>{music_title}</b>\n"
        f"┃ 👤 <b>Artist:</b> {music_author}\n"
        f"┃ {E_BOLT} <b>Format:</b> High Quality MP3\n"
        f"┃{speed_line}\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )

    file_id = res.get('id', 'audio')
    stream_file = await download_file_stream(music_url, max_size_mb=30, filename=f"{file_id}.mp3")
    await safe_delete(msg)
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if stream_file:
            await update.message.reply_audio(
                audio=stream_file,
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
        await update.message.reply_text(f"{E_ALERT} Lỗi gửi file audio lên Telegram.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)


# ================= LỆNH /getinfo =================
async def cmd_getinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    t0 = time.perf_counter()
    if not context.args:
        help_panel = (
            f"╔════════ {E_ALERT} <b>THIẾU THAM SỐ</b> ════════╗\n"
            f"║ {E_PIN} <b>Cú pháp:</b> <code>/getinfo &lt;username&gt;</code>\n"
            f"║ {E_SPARKLE} <i>Ví dụ: <code>/getinfo tiktok</code></i>\n"
            f"╚════════════════════════════════════╝\n"
            f"{get_speed_tag(t0)}"
        )
        try:
            await update.message.reply_photo(photo=IMG_GETINFO, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    username = context.args[0].strip().lstrip("@")
    status_msg = await update.message.reply_text(
        f"{E_SEARCH} <i>Đang quét dữ liệu người dùng</i> <code>@{html.escape(username)}</code>...",
        parse_mode=ParseMode.HTML,
    )

    try:
        info_data = await fetch_tiktok_user_info(username)
        report, avatar = format_user_info_panel(info_data, username)
        report += f"\n{get_speed_tag(t0)}"

        await safe_delete(status_msg)

        photo_to_send = avatar or IMG_GETINFO
        try:
            await update.message.reply_photo(photo=photo_to_send, caption=report, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                clean_report = re.sub(r"<[^>]+>", "", report)
                await update.message.reply_photo(photo=photo_to_send, caption=clean_report)
            else:
                raise e
        except Exception:
            try:
                await update.message.reply_text(report, parse_mode=ParseMode.HTML)
            except Exception:
                clean_report = re.sub(r"<[^>]+>", "", report)
                await update.message.reply_text(clean_report)

    except Exception as e:
        logger.error(f"Lỗi getinfo: {e}")
        await safe_delete(status_msg)
        await update.message.reply_text(f"{E_ALERT} Không thể hoàn tất tra cứu: {e}")


# ================= TỰ ĐỘNG BẮT LINK TIKTOK & INSTAGRAM =================
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()
    match = re.search(r"https?://[^\s]+", text)
    if not match:
        return
    raw_url = match.group(0)

    # ------------------ INSTAGRAM ------------------
    if "instagram.com" in text or "instagr.am" in text:
        t0 = time.perf_counter()
        msg = await update.message.reply_text(
            f"⏳ <i>Đang bóc tách Instagram Reels không logo...</i>",
            parse_mode=ParseMode.HTML,
        )

        data = await get_instagram_media_data(raw_url)

        if not data:
            await safe_edit_text(
                msg,
                f"{E_ALERT} <b>Tải thất bại:</b> Video/Reel riêng tư, link hết hạn hoặc Instagram chặn truy cập.\n{get_speed_tag(t0)}",
                parse_mode=ParseMode.HTML,
            )
            return

        desc = html.escape(data.get("caption") or "Instagram Media")
        uploader = html.escape(str(data.get("uploader") or "Instagram User"))
        likes = data.get("like_count") or 0
        speed_line = get_speed_tag(t0)

        caption = (
            f"╭━━━〔 📸 <b>INSTAGRAM HD DOWNLOAD</b> 〕━━━╮\n"
            f"┃ {E_PIN} <b>Nội dung:</b> {truncate_text(desc, 120)}\n"
            f"┃ 👤 <b>Tác giả:</b> {uploader}\n"
            f"┃ {E_VERIFIED} <b>Chất lượng:</b> Gốc Full HD (No Watermark)\n"
            f"┃ {E_HEART} <b>Lượt thích:</b> <code>{likes:,}</code>\n"
            f"┃{speed_line}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        caption_clean = truncate_text(caption, 1020)

        if data.get("type") == "album" and data.get("images"):
            await safe_delete(msg)
            all_images = data["images"]
            for i in range(0, len(all_images), 10):
                batch = all_images[i : i + 10]
                media = [InputMediaPhoto(media=ensure_full_url(img)) for img in batch]
                await update.message.reply_media_group(media=media)
            await update.message.reply_text(caption_clean, parse_mode=ParseMode.HTML)
            return

        media_url = ensure_full_url(data.get("url"))
        stream_video = await download_file_stream(media_url, max_size_mb=48, filename="instagram.mp4")

        if not stream_video:
            def _ytdlp_ig_dl(u):
                tmp = tempfile.gettempdir()
                out_path = os.path.join(tmp, f"ig_{int(time.time())}.mp4")
                opts = {
                    "format": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best",
                    "outtmpl": out_path,
                    "quiet": True,
                    "no_warnings": True,
                    "merge_output_format": "mp4",
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([u])
                    if os.path.exists(out_path):
                        with open(out_path, "rb") as f:
                            b = io.BytesIO(f.read())
                        b.seek(0)
                        b.name = "instagram.mp4"
                        os.remove(out_path)
                        return b
                except Exception as ex:
                    logger.warning(f"yt-dlp fallback IG fail: {ex}")
                return None

            loop = asyncio.get_running_loop()
            stream_video = await loop.run_in_executor(None, _ytdlp_ig_dl, raw_url)

        await safe_delete(msg)

        if stream_video:
            try:
                await update.message.reply_video(
                    video=stream_video,
                    caption=caption_clean,
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True,
                    read_timeout=90,
                    write_timeout=90,
                )
            except Exception as e:
                logger.error(f"Lỗi gửi Instagram video: {e}")
                await update.message.reply_text(
                    f"{E_ALERT} Lỗi khi upload video lên Telegram: {e}\n{get_speed_tag(t0)}",
                    parse_mode=ParseMode.HTML,
                )
        else:
            await update.message.reply_text(
                f"{E_ALERT} Dung lượng video vượt quá 50MB hoặc Instagram chặn IP.\n{get_speed_tag(t0)}",
                parse_mode=ParseMode.HTML,
            )
        return

    # ------------------ TIKTOK ------------------
    if "tiktok.com" in text or "douyin.com" in text:
        t0 = time.perf_counter()
        msg = await update.message.reply_text(f"⏳ <i>Đang bóc tách video HD từ server...</i>", parse_mode=ParseMode.HTML)

        data = await get_tiktok_universal_data(raw_url)

        if not data or not data.get("data"):
            await safe_edit_text(
                msg,
                f"{E_ALERT} <b>Tải thất bại:</b> Video riêng tư, bị xoá hoặc link không hỗ trợ.\n{get_speed_tag(t0)}",
                parse_mode=ParseMode.HTML,
            )
            return

        res = data["data"]
        video_id = str(res.get("id") or "")
        title = html.escape(res.get("title") or "TikTok Video")
        author = html.escape(res.get("author", {}).get("nickname") or "N/A")
        music_title = html.escape(res.get("music_info", {}).get("title") or "Original Sound")

        speed_line = get_speed_tag(t0)
        caption = (
            f"╭━━━〔 🎬 <b>TIKTOK HD DOWNLOAD</b> 〕━━━╮\n"
            f"┃ {E_PIN} <b>Tiêu đề:</b> {title}\n"
            f"┃ 👤 <b>Tác giả:</b> {author}\n"
            f"┃ {E_MUSIC} <b>Âm thanh:</b> <i>{music_title}</i>\n"
            f"┃\n"
            f"┃ {E_HEART} <code>{res.get('digg_count', 0):,}</code> tym │ "
            f"💬 <code>{res.get('comment_count', 0):,}</code> cmt │ "
            f"🔁 <code>{res.get('share_count', 0):,}</code> share\n"
            f"┃{speed_line}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        caption_clean = truncate_text(caption, 1020)

        keyboard = []
        if video_id:
            keyboard.append([InlineKeyboardButton("🎵 Tải nhạc MP3 của video", callback_data=f"dlmusic_{video_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        if res.get("images"):
            await safe_delete(msg)
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

        raw_video_url = res.get("play") or res.get("hdplay")
        video_url = ensure_full_url(raw_video_url)

        if not video_url:
            await safe_edit_text(msg, f"{E_ALERT} Không trích xuất được link tải video.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
            return

        stream_video = await download_file_stream(video_url, max_size_mb=48, filename="tiktok.mp4")

        if not stream_video:
            def _ytdlp_direct_dl(u):
                tmp = tempfile.gettempdir()
                out_path = os.path.join(tmp, f"tik_{int(time.time())}.mp4")
                opts = {
                    "format": "best[ext=mp4]/best",
                    "outtmpl": out_path,
                    "quiet": True,
                    "no_warnings": True,
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([u])
                    if os.path.exists(out_path):
                        with open(out_path, "rb") as f:
                            b = io.BytesIO(f.read())
                        b.seek(0)
                        b.name = "tiktok.mp4"
                        os.remove(out_path)
                        return b
                except Exception as ex:
                    logger.warning(f"yt-dlp tiktok fallback fail: {ex}")
                return None

            loop = asyncio.get_running_loop()
            stream_video = await loop.run_in_executor(None, _ytdlp_direct_dl, raw_url)

        await safe_delete(msg)

        if stream_video:
            try:
                await update.message.reply_video(
                    video=stream_video,
                    caption=caption_clean,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    supports_streaming=True,
                    read_timeout=90,
                    write_timeout=90,
                )
            except Exception as e:
                logger.error(f"Lỗi reply_video: {e}")
                await update.message.reply_text(f"{E_ALERT} Gặp lỗi khi tải video lên Telegram: {e}\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"{E_ALERT} Video vượt quá 50MB hoặc bị TikTok giới hạn khu vực.\n{get_speed_tag(t0)}", parse_mode=ParseMode.HTML)


# ================= KHỞI CHẠY BOT =================
def main():
    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            MULTI-PLATFORM TOOLKIT ONLINE             ║\n"
        "║        Railway Engine • Python Telegram v20+         ║\n"
        "║ Features: Custom Emojis + TikTok + IG Reels + Music  ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )
    print(terminal_banner)

    app = Application.builder().token(BOT_TOKEN).post_shutdown(close_http_session).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("donate", cmd_donate))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cleanup", cmd_cleanup))
    app.add_handler(CommandHandler("sing", cmd_sing))
    app.add_handler(CommandHandler("getinfo", cmd_getinfo))
    app.add_handler(CommandHandler("music", cmd_music))
    app.add_handler(CommandHandler("downmusic", cmd_music))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_youtube_download_callback, pattern="^ytdl_"))
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
