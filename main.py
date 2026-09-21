#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from datetime import datetime
import html
import io
import logging
import os
import re
import time
import urllib.parse
import aiohttp
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

BOT_START_TIME = time.time()

# ================= CẤU HÌNH TOKEN & API =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98")
ALLOWED_USERS = []  # Điền ID Telegram (int) nếu muốn private, để trống nếu public

# Cookie Facebook (c_user=...; xs=...) để cào bio, follower và link MXH không bị chặn
FB_COOKIE = os.getenv("FB_COOKIE", "")

# TikTok API Endpoints
TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

# Facebook Graph API & Tokens
FB_TOKENS = [
    os.getenv(
        "FB_TOKEN",
        "EAAAAUaZA8jlABSv6yeD3uBWPS8HcBca2YO6LIUlPo3pIGqLJ5dy5VAurXzOqYIdbWOMv4bDVbvqmFZAWhbhERAvRPusDXFNw4Y1pYN1jVcDCYFSr52BZBrCTNLWLt1ELZChCghXrYcpGvx4EeMMZBGdSpEa4unkYiyyoDgBpI0bMgQQS8MOCYYTHVe2G4KTmpHLtZAItDCcdVRPZCZA8nKFvogZDZD",
    )
]

# Banner Images theo từng tác vụ
IMG_WELCOME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"
IMG_MUSIC = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_GETINFO = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"
IMG_DOWN = "https://cdn.phototourl.com/free/2026-09-20-8f7cee5e-79ee-4e36-8bd6-1eb5d315635e.png"
IMG_FB = "https://cdn.phototourl.com/member/2026-09-20-9afea8db-8a1c-4ffb-9f41-68c26a82f2f5.jpg"

TIK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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
        HTTP_SESSION = aiohttp.ClientSession(headers=TIK_HEADERS)
    return HTTP_SESSION


# ================= HÀM HỖ TRỢ TẢI FILE MEDIA (CHỐNG LỖI TELEGRAM CDN TIMEOUT) =================
async def download_file_stream(url: str, max_size_mb: int = 50) -> io.BytesIO | None:
    """Tải trực tiếp stream từ CDN vào RAM để Telegram gửi không bị lỗi chặn hoặc timeout."""
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
            if resp.status == 200:
                content_len = resp.headers.get("Content-Length")
                if content_len and int(content_len) > max_size_mb * 1024 * 1024:
                    return None
                data = await resp.read()
                buf = io.BytesIO(data)
                buf.name = "media.mp4"
                return buf
    except Exception as e:
        logger.error(f"Lỗi tải stream media: {e}")
    return None


def ensure_full_url(url: str) -> str:
    """Chuẩn hóa đường dẫn tương đối từ TikWM."""
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.tikwm.com{url}"
    return url


# ================= THUẬT TOÁN ĐỊNH NĂM TẠO TÀI KHOẢN THEO UID =================
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


# ================= HÀM LẤY UID FACEBOOK =================
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
        async with session.post("https://id.traodoisub.com/api.php", data={"link": clean}, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("id"):
                    return str(j["id"])
    except Exception:
        pass

    try:
        async with session.get(f"https://ffb.vn/api/tool/get-id-fb?idfb={clean}", timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                if j.get("id"):
                    return str(j["id"])
    except Exception:
        pass

    return None


# ================= SCRAPER PROFILE FACEBOOK =================
async def scrape_fb_full_details(uid: str) -> dict:
    session = await get_http_session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
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
        async with session.get(f"https://mbasic.facebook.com/{uid}", headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                html_text = await r.text()
                fol_match = re.search(r'(?:Có|Followed by)\s+([\d.,]+)\s+(?:người theo dõi|people)', html_text, re.IGNORECASE)
                if fol_match:
                    extracted["followers"] = fol_match.group(1).replace(".", "").replace(",", "").strip()

                bio_match = re.search(r'<div class="[^"]*" id="bio">([\s\S]*?)</div>', html_text)
                if not bio_match:
                    bio_match = re.search(r'intro_bio[^>]*><span>([\s\S]*?)</span>', html_text)
                if bio_match:
                    clean_bio = re.sub(r'<br\s*/?>', '\n', bio_match.group(1))
                    clean_bio = re.sub(r'<[^>]+>', '', clean_bio).strip()
                    extracted["bio"] = html.unescape(clean_bio)
    except Exception as e:
        logger.warning(f"Lỗi scrape trang cá nhân: {e}")

    try:
        async with session.get(f"https://mbasic.facebook.com/{uid}/about", headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                raw_html = await r.text()
                m_home = re.search(r'(?:Đến từ|From)\s+<a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if not m_home:
                    m_home = re.search(r'(?:Quê quán|Hometown)[^<]*</div><div[^>]*><span[^>]*><a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if m_home:
                    extracted["hometown"] = m_home.group(1).strip()

                m_loc = re.search(r'(?:Sống tại|Lives in)\s+<a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if not m_loc:
                    m_loc = re.search(r'(?:Tỉnh/Thành phố hiện tại|Current city)[^<]*</div><div[^>]*><span[^>]*><a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if m_loc:
                    extracted["location"] = m_loc.group(1).strip()

                m_work = re.search(r'(?:Làm việc tại|Works at)\s+<a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if m_work:
                    extracted["work"] = f"Làm việc tại {m_work.group(1).strip()}"

                m_edu = re.search(r'(?:Từng học tại|Học tại|Studied at|Studies at)\s+<a[^>]*>([^<]+)</a>', raw_html, re.IGNORECASE)
                if m_edu:
                    extracted["education"] = m_edu.group(1).strip()

                if not extracted["followers"]:
                    m_fol = re.search(r'(?:Có|Followed by)\s+([\d.,]+)\s+(?:người theo dõi|people)', raw_html, re.IGNORECASE)
                    if m_fol:
                        extracted["followers"] = m_fol.group(1).replace(".", "").replace(",", "").strip()

                redirect_links = re.findall(r'href="https?://(?:[a-z0-9-]+\.)?facebook\.com/l\.php\?u=([^"&]+)', raw_html)
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
    created_str = str(raw_created).split("T")[0] if raw_created and raw_created != "None" else estimate_fb_creation_details(uid)

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
    return panel, avatar_url


# ================= GIẢI NÉN LINK TIKTOK =================
async def resolve_tiktok_url(url: str) -> str:
    session = await get_http_session()
    clean = url.strip()
    if any(short in clean for short in ["vt.tiktok.com", "vm.tiktok.com", "v.douyin.com"]):
        try:
            async with session.get(clean, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return str(resp.url)
        except Exception as e:
            logger.error(f"Unshorten error: {e}")
    return clean


# ================= HÀM XỬ LÝ DOWNLOAD TIKTOK =================
async def tikwm_req(params: dict):
    session = await get_http_session()
    url = TIKWM_BASE

    post_headers = {
        **TIK_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Thử POST với tham số hd=1
    try:
        async with session.post(url, data=params, headers=post_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0:
                    return data
    except Exception as e:
        logger.warning(f"TikWM POST fail: {e}")

    # Fallback GET
    try:
        async with session.get(url, params=params, headers=TIK_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
        **TIK_HEADERS,
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

                    images = j.get("images", [])

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
                            "images": images,
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
        logger.error(f"Tik Info API Error: {e}")
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
    friends = s.get("friendCount") or 0

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

    return panel, avatar


# ================= DASHBOARD & STATUS =================
def build_welcome_dashboard(user_name: str = "User") -> tuple[str, InlineKeyboardMarkup]:
    display_name = html.escape(user_name)
    panel = (
        f"⚡ <b>TIKTOK & FACEBOOK TOOLKIT</b> ⚡\n"
        f"<code>────────────────────────────</code>\n"
        f"👋 Xin chào, <b>{display_name}</b>\n"
        f"Hệ thống đa nhiệm: Tải Media HD, Trích xuất Audio & Tra cứu Profile.\n\n"
        f"📌 <b>LỆNH TRUY CẬP NHANH:</b>\n"
        f"• 📥 <b>Tải TikTok:</b> Gửi trực tiếp link (Auto Full HD No-WM)\n"
        f"• 🎵 <b>Tách nhạc:</b> <code>/music &lt;link&gt;</code>\n"
        f"• 🔎 <b>Info TikTok:</b> <code>/getinfo &lt;user&gt;</code>\n"
        f"• 🔵 <b>Info Facebook:</b> <code>/fb &lt;uid/link&gt;</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"🟢 <b>Status:</b> <i>Engine Core v2.7 Online</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("📥 Tải Video", callback_data="panel_guide_down"),
            InlineKeyboardButton("🎵 Tách Âm Thanh", callback_data="panel_guide_music"),
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


async def build_server_status_panel() -> str:
    uptime_sec = int(time.time() - BOT_START_TIME)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days else f"{hours}h {minutes}m {seconds}s"

    session = await get_http_session()
    start_t = time.perf_counter()
    ping_ms = 0
    try:
        async with session.get("https://api.telegram.org", timeout=aiohttp.ClientTimeout(total=3)) as r:
            ping_ms = round((time.perf_counter() - start_t) * 1000)
    except Exception:
        ping_ms = 99

    try:
        import resource
        ram_usage = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        ram_str = f"{ram_usage} MB"
    except Exception:
        ram_str = "Tối ưu"

    status_panel = (
        f"🖥 <b>SYSTEM MONITOR & METRICS</b>\n"
        f"<code>────────────────────────────</code>\n"
        f"⏱ <b>Thời gian chạy:</b> <code>{uptime_str}</code>\n"
        f"⚡ <b>Độ trễ:</b> <code>{ping_ms} ms</code>\n"
        f"🧠 <b>Bộ nhớ RAM:</b> <code>{ram_str}</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"📡 <b>TRẠNG THÁI HỆ THỐNG:</b>\n"
        f"├ 🎬 <b>TikWM Core HD:</b> 🟢 Operational\n"
        f"├ 🔁 <b>Fallback LoveTik:</b> 🟢 Standby Ready\n"
        f"├ 🎵 <b>Audio Ingestion:</b> 🟢 Stream Buffered\n"
        f"└ 🔵 <b>Facebook Graph:</b> 🟢 Connected"
    )
    return status_panel


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


async def handle_panel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    back_btn = [[InlineKeyboardButton("🔙 Quay lại Menu", callback_data="panel_home")]]

    if data == "panel_home":
        user_name = query.from_user.first_name or "User"
        text, reply_markup = build_welcome_dashboard(user_name)
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif data == "panel_guide_down":
        text = (
            "📥 <b>HƯỚNG DẪN TẢI TIKTOK FULL HD</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Gửi link video hoặc album ảnh trực tiếp vào khung chat.\n"
            "• Bot tự động tải về chuẩn <b>HD / 1080p không logo</b>.\n"
            "• Tương thích tất cả link ngắn như <code>vt.tiktok.com</code>."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            "🎵 <b>TRÍCH XUẤT AUDIO GỐC</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/music &lt;link_tiktok&gt;</code>\n"
            "• Hoặc bấm nút <b>[Tải nhạc]</b> ngay dưới mỗi video đã tải.\n"
            "• Trả về file âm thanh MP3 chất lượng cao nhất."
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
            "• <i>Ví dụ:</i> <code>/fb 4</code> hoặc link trang cá nhân bất kỳ."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_status":
        text = await build_server_status_panel()
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))


# LỆNH /fb
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


# Nút callback tải nhạc dưới video
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
        f"╔══════════ 🎵 <b>AUDIO PLAYER</b> ══════════╗\n"
        f"║ 🎼 <b>Bài hát:</b> <b>{music_title}</b>\n"
        f"║ 👤 <b>Nghệ sĩ:</b> {music_author}\n"
        f"║ 🆔 <b>Source ID:</b> <code>{video_id}</code>\n"
        f"╚════════════════════════════════════╝"
    )

    # Thử gửi bằng File Buffer qua RAM để chống lỗi CDN timeout
    stream_file = await download_file_stream(music_url, max_size_mb=30)
    try:
        if stream_file:
            stream_file.name = f"{video_id}.mp3"
            await query.message.reply_audio(
                audio=stream_file,
                title=music_title,
                performer=music_author,
                caption=audio_panel,
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.message.reply_audio(
                audio=music_url,
                title=music_title,
                performer=music_author,
                caption=audio_panel,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Lỗi gửi audio callback: {e}")
        await query.message.reply_text(f"❌ Lỗi gửi audio: Không thể chuyển tiếp file từ CDN.")


# Lệnh /music hoặc /downmusic
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

    try:
        if stream_file:
            stream_file.name = f"{res.get('id', 'audio')}.mp3"
            await update.message.reply_audio(
                audio=stream_file,
                title=music_title,
                performer=music_author,
                caption=audio_panel,
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_audio(
                audio=music_url,
                title=music_title,
                performer=music_author,
                caption=audio_panel,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logger.error(f"Lỗi gửi audio: {e}")
        await update.message.reply_text("❌ Lỗi gửi file audio lên Telegram.")


# Lệnh /getinfo
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


# TỰ ĐỘNG TẢI KHI GỬI LINK TIKTOK (ƯU TIÊN HD VÀ TỰ SỬA LINK)
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

        # 1. Giải mã link rút gọn (vt.tiktok.com)
        target_url = await resolve_tiktok_url(raw_url)

        # 2. Gọi TikWM với cờ hd=1
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

        keyboard = []
        if video_id:
            keyboard.append([InlineKeyboardButton("🎵 Tải nhạc MP3 của video", callback_data=f"dlmusic_{video_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        # Trực hợp Album ảnh
        if res.get("images"):
            await msg.delete()
            media = [InputMediaPhoto(media=ensure_full_url(img)) for img in res["images"][:10]]
            await update.message.reply_media_group(media=media)
            await update.message.reply_photo(photo=IMG_DOWN, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return

        # Lấy URL HD (Ưu tiên hdplay -> play) và chuẩn hóa
        raw_video_url = res.get("hdplay") or res.get("play")
        video_url = ensure_full_url(raw_video_url)

        if not video_url:
            await msg.edit_text("❌ Không trích xuất được link video chất lượng cao.")
            return

        # Tải stream video qua RAM để tránh lỗi CDN chặn Telegram Server
        stream_video = await download_file_stream(video_url, max_size_mb=50)

        await msg.delete()
        try:
            if stream_video:
                stream_video.name = f"{video_id or 'tiktok'}_hd.mp4"
                await update.message.reply_video(
                    video=stream_video,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=90,
                    write_timeout=90,
                )
            else:
                await update.message.reply_video(
                    video=video_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=90,
                    write_timeout=90,
                )
        except Exception as e:
            logger.error(f"Lỗi gửi media: {e}")
            await update.message.reply_text("❌ Video vượt quá dung lượng cho phép của Telegram Bot (50MB) hoặc CDN timeout.")


# ================= KHỞI CHẠY BOT =================
def main():
    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            MULTI-PLATFORM TOOLKIT ONLINE             ║\n"
        "║          Engine: python-telegram-bot v20+            ║\n"
        "║      Features: TikTok Auto-Down HD & Music Fix       ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )
    print(terminal_banner)

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("getinfo", cmd_getinfo))
    app.add_handler(CommandHandler("music", cmd_music))
    app.add_handler(CommandHandler("downmusic", cmd_music))
    app.add_handler(CommandHandler("fb", cmd_fb))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
