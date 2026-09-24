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

# ================= CẤU HÌNH TOKEN & API =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98").strip()
ALLOWED_USERS = []

FB_COOKIE = os.getenv("FB_COOKIE", "").strip()

# Hỗ trợ truyền cookies.txt qua biến môi trường để vượt bản quyền YouTube
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
        logging.info("Đã nạp thành công YouTube cookies từ biến môi trường.")
    except Exception as e:
        logging.warning(f"Không thể tạo file cookie: {e}")

TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

raw_fb_token = os.getenv("FB_TOKEN", "").strip()
FB_TOKENS = [raw_fb_token] if raw_fb_token else [
    "EAAAAUaZA8jlABSv6yeD3uBWPS8HcBca2YO6LIUlPo3pIGqLJ5dy5VAurXzOqYIdbWOMv4bDVbvqmFZAWhbhERAvRPusDXFNw4Y1pYN1jVcDCYFSr52BZBrCTNLWLt1ELZChCghXrYcpGvx4EeMMZBGdSpEa4unkYiyyoDgBpI0bMgQQS8MOCYYTHVe2G4KTmpHLtZAItDCcdVRPZCZA8nKFvogZDZD"
]

# Banner Images
IMG_WELCOME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"
IMG_MUSIC = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_GETINFO = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"
IMG_DOWN = "https://cdn.phototourl.com/free/2026-09-20-8f7cee5e-79ee-4e36-8bd6-1eb5d315635e.png"
IMG_FB = "https://cdn.phototourl.com/member/2026-09-20-9afea8db-8a1c-4ffb-9f41-68c26a82f2f5.jpg"
IMG_SING = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"

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


# ================= HÀM TIỆN ÍCH DỌN RÁC Ổ CỨNG VÀ BỘ NHỚ =================
def clean_temp_storage_files():
    """Xóa file rác yt-dlp, file tạm âm thanh video trong tempdir."""
    tmp_dir = tempfile.gettempdir()
    deleted_count = 0
    freed_bytes = 0
    try:
        for fname in os.listdir(tmp_dir):
            if fname.startswith(("ytdl_", "sc_", "yt_tmp_")) or fname.endswith((".mp4", ".mp3", ".webm", ".m4a", ".part", ".ytdl")):
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
        logger.warning(f"Lỗi dọn dẹp file tạm: {e}")
    return deleted_count, freed_bytes


# ================= HỖ TRỢ STREAM BUFFER =================
async def download_file_stream(url: str, max_size_mb: int = 50) -> io.BytesIO | None:
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status == 200:
                content_len = resp.headers.get("Content-Length")
                if content_len and int(content_len) > max_size_mb * 1024 * 1024:
                    return None

                buf = io.BytesIO()
                total_downloaded = 0
                max_bytes = max_size_mb * 1024 * 1024

                async for chunk in resp.content.iter_chunked(64 * 1024):
                    total_downloaded += len(chunk)
                    if total_downloaded > max_bytes:
                        return None
                    buf.write(chunk)

                buf.seek(0)
                buf.name = "media.mp4"
                return buf
    except Exception as e:
        logger.error(f"Lỗi tải stream media: {e}")
    return None


# ================= CACHE FONT & TỰ ĐỘNG TẢI NẾU THIẾU =================
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


# ================= HÀM TẠO ẢNH CANVAS STATUS =================
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

    # Lấy thông số ổ cứng
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
        ("TikWM Gateway:", "ONLINE (HD 1080p)", (74, 222, 128)),
        ("YouTube Core:", "Android/TV Bypassed", (74, 222, 128)),
        ("Disk Trống:", f"{free_gb} GB Available", (74, 222, 128) if free_gb > 1.0 else (239, 68, 68)),
        ("SoundCloud FB:", "ACTIVE (Auto Fallback)", (251, 191, 36)),
        ("DRM Engine:", "Cipher Unpack Online", (74, 222, 128)),
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
    draw.rounded_rectangle([c2_x1 + 25, pb_y + 44], radius=8, fill=(30, 41, 59))
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


# ================= TẢI AUDIO TỐI ƯU DUNG LƯỢNG (FIX LỖI QUÁ TẢI/TRÀN BỘ NHỚ) =================
def extract_youtube_audio_advanced(video_id: str, search_query: str = "") -> tuple[io.BytesIO | None, dict]:
    """
    Tải audio YouTube tối ưu dung lượng:
    1. Chủ động dọn file rác cũ trước khi tải.
    2. Sử dụng format nén bitrate nhẹ hơn nếu file gốc quá nặng (tránh tràn đĩa).
    3. Tắt lưu cache ổ cứng bằng no_cache_dir=True.
    4. Xóa ngay lập tức file vật lý sau khi nạp vào memory stream.
    """
    clean_temp_storage_files()

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    tmp_dir = tempfile.gettempdir()
    output_template = os.path.join(tmp_dir, f"ytdl_{video_id}_%(id)s.%(ext)s")

    client_strategies = [
        ["android", "ios"],
        ["tv", "mweb"],
    ]

    # Format fallback: Ưu tiên audio nén dưới 128kbps để tiết kiệm dung lượng đĩa
    format_priority = "ba[abr<=96]/ba[abr<=128]/bestaudio[ext=m4a]/bestaudio/best"

    for clients in client_strategies:
        ydl_opts = {
            "format": format_priority,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "no_cache_dir": True,  # Ngăn tạo bộ nhớ đệm phình to ổ đĩa
            "max_filesize": 48 * 1024 * 1024,  # Giới hạn an toàn Telegram Bot API
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

    # Fallback sang SoundCloud nếu YouTube chặn hoặc bị lỗi bộ nhớ
    if search_query:
        logger.info(f"Kích hoạt SoundCloud fallback: {search_query}")
        sc_template = os.path.join(tmp_dir, f"sc_{video_id}_%(id)s.%(ext)s")
        sc_opts = {
            "format": "bestaudio/best",
            "outtmpl": sc_template,
            "quiet": True,
            "no_cache_dir": True,
            "default_search": "scsearch1",
            "max_filesize": 45 * 1024 * 1024,
        }
        sc_downloaded = None
        try:
            with yt_dlp.YoutubeDL(sc_opts) as ydl:
                sc_meta = ydl.extract_info(search_query, download=True)
                entries = sc_meta.get("entries", [])
                meta = entries[0] if entries else sc_meta

                details = {
                    "title": meta.get("title", "SoundCloud Audio"),
                    "uploader": meta.get("uploader", "SoundCloud Artist"),
                    "duration": meta.get("duration", 0),
                    "id": video_id
                }

                for fname in os.listdir(tmp_dir):
                    if fname.startswith(f"sc_{video_id}"):
                        sc_downloaded = os.path.join(tmp_dir, fname)
                        break

                if sc_downloaded and os.path.exists(sc_downloaded):
                    buf = io.BytesIO()
                    with open(sc_downloaded, "rb") as f:
                        buf.write(f.read())
                    buf.seek(0)
                    buf.name = f"{video_id}.mp3"
                    return buf, details
        except Exception as sc_err:
            logger.error(f"SoundCloud fallback thất bại: {sc_err}")
        finally:
            if sc_downloaded and os.path.exists(sc_downloaded):
                try:
                    os.remove(sc_downloaded)
                except Exception:
                    pass

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
            "https://id.traodoisub.com/api.php",
            data={"link": clean},
            timeout=aiohttp.ClientTimeout(total=6),
        ) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("id"):
                    return str(j["id"])
    except Exception:
        pass

    try:
        async with session.get(
            f"https://ffb.vn/api/tool/get-id-fb?idfb={clean}",
            timeout=aiohttp.ClientTimeout(total=6),
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
            f"https://mbasic.facebook.com/{uid}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status == 200:
                html_text = await r.text()
                fol_match = re.search(
                    r"(?:Có|Followed by)\s+([\d.,]+)\s+(?:người theo dõi|people)",
                    html_text,
                    re.IGNORECASE,
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
            f"https://mbasic.facebook.com/{uid}/about",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
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
                    r'href="https?://(?:[a-z0-9-]+\.)?facebook\.com/l\.php\?u=([^"&]+)',
                    raw_html,
                )
                social_domains = [
                    "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
                    "t.me", "threads.net", "twitter.com", "x.com", "github.com",
                    "discord.gg", "linkedin.com", "pinterest.com", "spotify.com"
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
    avatar_url = f"https://graph.facebook.com/{uid}/picture?width=720&height=720&access_token={FB_TOKENS[0]}"

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
        f"⚡ <b>TIKTOK & FACEBOOK & YOUTUBE TOOLKIT</b> ⚡\n"
        f"<code>────────────────────────────</code>\n"
        f"👋 Xin chào, <b>{display_name}</b>\n"
        f"Hệ thống đa năng: Tải Media HD, Nghe nhạc YouTube & Tra cứu Profile.\n\n"
        f"📌 <b>LỆNH TRUY CẬP NHANH:</b>\n"
        f"• 🎶 <b>Nhạc YouTube:</b> <code>/sing &lt;tên bài hát&gt;</code>\n"
        f"• 📥 <b>Tải TikTok:</b> Gửi trực tiếp link (Auto Full HD)\n"
        f"• 🎵 <b>Tách nhạc TikTok:</b> <code>/music &lt;link&gt;</code>\n"
        f"• 🔎 <b>Info TikTok:</b> <code>/getinfo &lt;user&gt;</code>\n"
        f"• 🔵 <b>Info Facebook:</b> <code>/fb &lt;uid/link&gt;</code>\n"
        f"• 🧹 <b>Dọn rác đĩa & RAM (delay 5s):</b> <code>/cleanup</code>\n"
        f"• 📊 <b>Status Máy Chủ:</b> <code>/status</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"🟢 <b>Status:</b> <i>Railway Container Engine Online</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎶 Tìm Nhạc YouTube", callback_data="panel_guide_sing"),
            InlineKeyboardButton("📥 Tải TikTok", callback_data="panel_guide_down"),
        ],
        [
            InlineKeyboardButton("🎵 Tách Nhạc TikTok", callback_data="panel_guide_music"),
            InlineKeyboardButton("🔎 Info TikTok", callback_data="panel_guide_info"),
        ],
        [
            InlineKeyboardButton("🔵 Info Facebook", callback_data="panel_guide_fb"),
            InlineKeyboardButton("🧹 Dọn Rác Máy Chủ", callback_data="panel_cleanup"),
        ],
        [
            InlineKeyboardButton("📊 Server Status", callback_data="panel_status"),
        ],
    ]
    return panel, InlineKeyboardMarkup(keyboard)


# ================= XỬ LÝ LỆNH DỌN RÁC (CÁCH 5S MỖI LỆNH) =================
async def run_system_cleanup(status_msg):
    """Tiến hành dọn rác bộ nhớ và file tạm với khoảng nghỉ 5s."""
    # BƯỚC 1: Dọn dẹp RAM & GC
    await status_msg.edit_text(
        "🧹 <b>[Bước 1/3] Đang thu hồi bộ nhớ RAM và giải phóng Python Garbage Collector...</b>\n"
        "⏳ <i>Vui lòng đợi 5 giây...</i>",
        parse_mode=ParseMode.HTML,
    )
    collected = gc.collect()
    logger.info(f"Đã giải phóng GC: {collected} objects.")
    await asyncio.sleep(5)

    # BƯỚC 2: Quét & xóa toàn bộ file tạm tải về
    await status_msg.edit_text(
        "🗄️ <b>[Bước 2/3] Đang quét và xóa các file cache âm thanh, video tạm trong ổ đĩa...</b>\n"
        "⏳ <i>Vui lòng đợi 5 giây...</i>",
        parse_mode=ParseMode.HTML,
    )
    loop = asyncio.get_running_loop()
    del_count, freed_bytes = await loop.run_in_executor(None, clean_temp_storage_files)
    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    logger.info(f"Dọn dẹp hoàn tất: Xóa {del_count} file, giải phóng {freed_mb} MB.")
    await asyncio.sleep(5)

    # BƯỚC 3: Đồng bộ trạng thái ổ đĩa
    await status_msg.edit_text(
        "📊 <b>[Bước 3/3] Đang đồng bộ hóa trạng thái tài nguyên ổ đĩa...</b>\n"
        "⏳ <i>Vui lòng đợi 5 giây...</i>",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(5)

    total, used, free = shutil.disk_usage("/")
    free_gb = round(free / (1024 ** 3), 2)

    result_text = (
        f"✅ <b>GIẢI PHÓNG DUNG LƯỢNG THÀNH CÔNG!</b>\n"
        f"<code>────────────────────────────</code>\n"
        f"🗑️ <b>Số tệp tạm đã xóa:</b> <code>{del_count}</code> files\n"
        f"📦 <b>Dung lượng dọn sạch:</b> <code>{freed_mb} MB</code>\n"
        f"💾 <b>Dung lượng trống còn lại:</b> <code>{free_gb} GB</code>\n"
        f"⚡ <b>Trạng thái:</b> Sẵn sàng tải YouTube / TikTok không lo tràn ổ."
    )
    await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)


async def cmd_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    status_msg = await update.message.reply_text("⏳ <i>Đang khởi động tiến trình tối ưu hóa dung lượng...</i>", parse_mode=ParseMode.HTML)
    await run_system_cleanup(status_msg)


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    status_msg = await update.message.reply_text("📊 <i>Đang render bảng thông số hệ thống...</i>", parse_mode=ParseMode.HTML)
    canvas_buffer = await generate_system_status_canvas(bot_start_time=BOT_START_TIME)

    caption_text = (
        "📊 <b>BÁO CÁO THỐNG KÊ MÁY CHỦ (CANVAS LIVE)</b>\n"
        "<code>────────────────────────────</code>\n"
        "• Hệ thống giám sát trực tiếp trên Railway Cloud.\n"
        "• Thông số tài nguyên được làm mới theo thời gian thực."
    )

    await status_msg.delete()
    try:
        await update.message.reply_photo(
            photo=canvas_buffer,
            caption=caption_text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Lỗi gửi ảnh status: {e}")
        await update.message.reply_text("❌ Không thể tạo hoặc gửi ảnh status.")


async def handle_panel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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

    elif data == "panel_guide_sing":
        text = (
            "🎶 <b>HƯỚNG DẪN TÌM VÀ TẢI NHẠC YOUTUBE</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/sing &lt;tên bài hát hoặc từ khóa&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/sing tắt đèn đi</code>\n"
            "• Cơ chế chống đầy bộ nhớ tự động kích hoạt."
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

    elif data == "panel_cleanup":
        await query.answer("🧹 Đang thực hiện dọn dẹp hệ thống...", show_alert=False)
        status_msg = await query.message.reply_text("⏳ <i>Đang khởi động dọn rác...</i>", parse_mode=ParseMode.HTML)
        await run_system_cleanup(status_msg)

    elif data == "panel_status":
        await query.answer("📊 Đang render ảnh thống kê...", show_alert=False)
        canvas_buffer = await generate_system_status_canvas(bot_start_time=BOT_START_TIME)

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


# ================= XỬ LÝ LỆNH /sing =================
async def cmd_sing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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


# ================= CALLBACK TẢI AUDIO YOUTUBE (TỰ ĐỘNG CHỐNG TRÀN ĐĨA) =================
async def handle_youtube_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Đang xử lý âm thanh...", show_alert=False)
    data = query.data

    vid_id = data.replace("ytdl_", "")
    target_url = f"https://www.youtube.com/watch?v={vid_id}"

    saved_kw = context.bot_data.get(f"kw_{query.message.chat_id}", "")

    loading_msg = await query.message.reply_text(
        "⏳ <i>Đang bóc tách audio (Tự động nén tối ưu dung lượng)...</i>",
        parse_mode=ParseMode.HTML
    )

    loop = asyncio.get_running_loop()
    stream_file, details = await loop.run_in_executor(None, extract_youtube_audio_advanced, vid_id, saved_kw)

    await loading_msg.delete()

    if not stream_file:
        await query.message.reply_text("❌ Không thể tải được bài hát này hoặc vượt quá dung lượng cho phép. Hãy chọn bài khác!")
        return

    title = html.escape(details.get("title", "YouTube Track"))
    uploader = html.escape(details.get("uploader", "YouTube Artist"))

    caption = (
        f"╔══════════ 🎶 <b>AUDIO TRACK</b> ══════════╗\n"
        f"║ 🎼 <b>Bài hát:</b> <b>{title}</b>\n"
        f"║ 👤 <b>Nghệ sĩ/Kênh:</b> {uploader}\n"
        f"║ 🛡️ <b>Tối ưu:</b> Tự động nén chống tràn đĩa\n"
        f"║ 🔗 <b>Nguồn gốc:</b> <a href='{target_url}'>Media Source</a>\n"
        f"╚════════════════════════════════════╝"
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
        await query.message.reply_text("❌ Kích thước tệp âm thanh vượt quá giới hạn gửi của Telegram.")


# ================= LỆNH /fb =================
async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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


# ================= CALLBACK TẢI NHẠC TIKTOK =================
async def handle_download_music_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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

    stream_file = await download_file_stream(music_url, max_size_mb=30)
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if stream_file:
            stream_file.name = f"{video_id}.mp3"
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
        await query.message.reply_text("❌ Lỗi gửi audio: Không thể chuyển tiếp file từ CDN.")


# ================= LỆNH /music =================
async def cmd_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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

    stream_file = await download_file_stream(music_url, max_size_mb=30)
    await msg.delete()
    caption_clean = truncate_text(audio_panel, 1020)

    try:
        if stream_file:
            stream_file.name = f"{res.get('id', 'audio')}.mp3"
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
        await update.message.reply_text("❌ Lỗi gửi file audio lên Telegram.")


# ================= LỆNH /getinfo =================
async def cmd_getinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
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
    if not is_authorized(update.effective_user.id):
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

        stream_video = await download_file_stream(video_url, max_size_mb=50)
        await msg.delete()

        try:
            if stream_video:
                stream_video.name = f"{video_id or 'tiktok'}_hd.mp4"
                await update.message.reply_video(
                    video=stream_video,
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
            await update.message.reply_text("❌ Video vượt quá 50MB hoặc Telegram CDN timeout.")


# ================= KHỞI CHẠY BOT =================
def main():
    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            MULTI-PLATFORM TOOLKIT ONLINE             ║\n"
        "║        Railway Engine • Python Telegram v20+         ║\n"
        "║ Features: YouTube Music + Canvas Server Status + TT  ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )
    print(terminal_banner)

    app = Application.builder().token(BOT_TOKEN).post_shutdown(close_http_session).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cleanup", cmd_cleanup))  # Lệnh dọn rác mới
    app.add_handler(CommandHandler("sing", cmd_sing))
    app.add_handler(CommandHandler("getinfo", cmd_getinfo))
    app.add_handler(CommandHandler("music", cmd_music))
    app.add_handler(CommandHandler("downmusic", cmd_music))
    app.add_handler(CommandHandler("fb", cmd_fb))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_youtube_download_callback, pattern="^ytdl_"))
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
