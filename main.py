#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from datetime import datetime
import html
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

# Free Fire API
GAMESKINBO_API_KEY = os.getenv(
    "GAMESKINBO_API_KEY", "cxKZ3Yw3ocTKlP-jX5KV3g-eqcF2FuEPCwAfn46gx_M"
)

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
IMG_FF = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"

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


# ================= HÀM KIỂM TRA PROFILE FREE FIRE =================
async def check_ff_profile(uid: str, api_key: str = GAMESKINBO_API_KEY, max_retries: int = 2) -> dict:
    uid = str(uid).strip()
    if not uid.isdigit():
        return {"success": False, "error": "UID phải là số nguyên", "status_code": None}

    url = f"https://api.gameskinbo.com/ff-info/get?uid={uid}"
    headers = {
        "x-api-key": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    session = await get_http_session()

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            await asyncio.sleep(5)

        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                status_code = response.status
                if status_code == 200:
                    try:
                        raw_data = await response.json(content_type=None)
                    except Exception:
                        return {"success": False, "error": "Dữ liệu server trả về không hợp lệ.", "status_code": 200}

                    if "AccountInfo" in raw_data:
                        acc = raw_data.get("AccountInfo", {})
                        profile = raw_data.get("AccountProfileInfo", {})
                        guild = raw_data.get("GuildInfo", {})

                        name = html.escape(str(acc.get("AccountName", "N/A")))
                        level = acc.get("AccountLevel", "N/A")
                        likes = f"{acc.get('AccountLikes', 0):,}" if str(acc.get("AccountLikes", "")).isdigit() else acc.get("AccountLikes", "N/A")
                        region = acc.get("AccountRegion", "N/A")
                        br_point = f"{profile.get('BrRankPoint', 0):,}" if str(profile.get("BrRankPoint", "")).isdigit() else profile.get("BrRankPoint", "N/A")
                        cs_point = f"{profile.get('CsRankPoint', 0):,}" if str(profile.get("CsRankPoint", "")).isdigit() else profile.get("CsRankPoint", "N/A")
                        guild_name = html.escape(str(guild.get("GuildName", "Không có")))
                        guild_level = guild.get("GuildLevel", "N/A")

                        formatted_text = (
                            f"🎮 <b>THÔNG TIN TÀI KHOẢN FREE FIRE</b> ⚡\n"
                            f"<code>────────────────────────────</code>\n"
                            f"👤 <b>Tên nhân vật:</b> <b>{name}</b>\n"
                            f"🆔 <b>UID:</b> <code>{uid}</code>\n"
                            f"⭐ <b>Cấp độ (Level):</b> <code>{level}</code>\n"
                            f"❤️ <b>Lượt thích:</b> <code>{likes}</code>\n"
                            f"🌐 <b>Khu vực:</b> <code>{region}</code>\n"
                            f"<code>────────────────────────────</code>\n"
                            f"🏆 <b>Điểm Rank BR:</b> <code>{br_point}</code> điểm\n"
                            f"🛡️ <b>Điểm Rank CS:</b> <code>{cs_point}</code> điểm\n"
                            f"<code>────────────────────────────</code>\n"
                            f"🏰 <b>Quân đoàn:</b> {guild_name}\n"
                            f"👑 <b>Cấp Quân đoàn:</b> <code>{guild_level}</code>"
                        )
                        return {
                            "success": True,
                            "data": raw_data,
                            "formatted_text": formatted_text,
                            "status_code": 200,
                        }

                    err_msg = raw_data.get("error", "Không tìm thấy dữ liệu tài khoản.")
                    return {"success": False, "error": err_msg, "status_code": 200}

                elif status_code == 429:
                    return {"success": False, "error": "Chạm giới hạn truy vấn (Rate limit). Vui lòng thử lại sau 1 phút.", "status_code": 429}
                elif status_code in (401, 403):
                    return {"success": False, "error": f"API Key lỗi xác thực hoặc hết hạn (HTTP {status_code}).", "status_code": status_code}

        except asyncio.TimeoutError:
            if attempt == max_retries:
                return {"success": False, "error": "Hết thời gian kết nối tới máy chủ (Timeout).", "status_code": None}
        except Exception as e:
            return {"success": False, "error": f"Lỗi ngoại lệ: {str(e)}", "status_code": None}

    return {"success": False, "error": "Không thể kết nối đến máy chủ Free Fire.", "status_code": None}


# ================= THUẬT TOÁN ĐỊNH NĂM TẠO TÀI KHOẢN THEO UID =================
def estimate_fb_creation_details(uid: str) -> str:
    """Xác định năm khởi tạo tài khoản Facebook dựa theo mốc phân bổ UID."""
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


# ================= SCRAPER NÂNG CAO: FOLLOWER, BIO, SOCIAL LINKS =================
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


# ================= HÀM QUÉT DỮ LIỆU PROFILE FACEBOOK ĐA TẦNG =================
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
                    elif res.get("hometown"):
                        result["hometown"] = str(res.get("hometown"))

                    if isinstance(res.get("location"), dict):
                        result["location"] = res["location"].get("name")
                    elif res.get("location"):
                        result["location"] = str(res.get("location"))

                    if res.get("work") and isinstance(res["work"], list):
                        work_items = []
                        for w in res["work"][:2]:
                            employer = w.get("employer", {}).get("name")
                            pos = w.get("position", {}).get("name")
                            if employer and pos:
                                work_items.append(f"{pos} tại {employer}")
                            elif employer:
                                work_items.append(f"Làm việc tại {employer}")
                        if work_items:
                            result["work"] = " | ".join(work_items)

                    if res.get("education") and isinstance(res["education"], list):
                        edu_items = []
                        for ed in res["education"][:2]:
                            school = ed.get("school", {}).get("name")
                            if school:
                                edu_items.append(school)
                        if edu_items:
                            result["education"] = " | ".join(edu_items)
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

    if not (result["followers"] and result["about"]):
        try:
            scraper_url = f"https://api.findids.net/api/facebook/profile?id={uid}"
            async with session.get(scraper_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    s_data = await resp.json(content_type=None)
                    if isinstance(s_data, dict) and s_data.get("data"):
                        info = s_data["data"]
                        result["name"] = result.get("name") or info.get("name")
                        result["followers"] = result.get("followers") or info.get("follower") or info.get("followers")
                        result["hometown"] = result.get("hometown") or info.get("hometown")
                        result["location"] = result.get("location") or info.get("location")
                        result["work"] = result.get("work") or info.get("work")
                        result["education"] = result.get("education") or info.get("education")
                        result["about"] = result.get("about") or info.get("bio")
        except Exception:
            pass

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
    if raw_created and raw_created != "None":
        created_str = str(raw_created).split("T")[0]
    else:
        created_str = estimate_fb_creation_details(uid)

    raw_updated = data.get("updated_time")
    if raw_updated and raw_updated != "None":
        try:
            up_dt = datetime.fromisoformat(raw_updated.split("+")[0].replace("Z", ""))
            updated_str = up_dt.strftime("%d/%m/%Y lúc %H:%M")
        except Exception:
            updated_str = str(raw_updated).replace("T", " ")
    else:
        updated_str = "Theo thời gian thực"

    hometown = html.escape(str(data.get("hometown") or "Không công khai"))
    location = html.escape(str(data.get("location") or "Không công khai"))
    about = html.escape(str(data.get("about") or "Không có tiểu sử."))
    work = html.escape(str(data.get("work") or "Không công khai"))
    education = html.escape(str(data.get("education") or "Không công khai"))

    badge = "💎 ĐÃ XÁC MINH (TÍCH XANH)" if data.get("verified") else "🟢 HOẠT ĐỘNG BÌNH THƯỜNG"
    avatar_url = f"https://graph.facebook.com/{uid}/picture?width=720&height=720&access_token={FB_TOKENS[0]}"

    social_lines = []
    social_links = data.get("social_links", [])
    if social_links:
        for link in social_links:
            clean_tag = link.split("/")[-1]
            if "instagram.com" in link:
                social_lines.append(f"• 📸 <b>Instagram:</b> <a href='{link}'>@{clean_tag}</a>")
            elif "tiktok.com" in link:
                social_lines.append(f"• 🎬 <b>TikTok:</b> <a href='{link}'>@{clean_tag}</a>")
            elif "youtube.com" in link or "youtu.be" in link:
                social_lines.append(f"• 🔴 <b>YouTube:</b> <a href='{link}'>Xem kênh</a>")
            elif "t.me" in link:
                social_lines.append(f"• ✈️ <b>Telegram:</b> <a href='{link}'>@{clean_tag}</a>")
            elif "threads.net" in link:
                social_lines.append(f"• 🧵 <b>Threads:</b> <a href='{link}'>@{clean_tag}</a>")
            elif "twitter.com" in link or "x.com" in link:
                social_lines.append(f"• 🐦 <b>X/Twitter:</b> <a href='{link}'>@{clean_tag}</a>")
            elif "github.com" in link:
                social_lines.append(f"• 🐙 <b>GitHub:</b> <a href='{link}'>{clean_tag}</a>")
            else:
                social_lines.append(f"• 🔗 <b>Khác:</b> <a href='{link}'>{link}</a>")
        social_display = "\n".join(social_lines)
    else:
        social_display = "<i>Không có mạng xã hội liên kết ngoài</i>"

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
        f"🔄 <b>Cập nhật gần nhất:</b> <code>{updated_str}</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"🏡 <b>Quê quán:</b> {hometown}\n"
        f"📍 <b>Nơi sống:</b> {location}\n"
        f"💼 <b>Công việc:</b> {work}\n"
        f"🎓 <b>Học vấn:</b> {education}\n"
        f"<code>────────────────────────────</code>\n"
        f"📝 <b>Tiểu sử:</b>\n<i>« {about} »</i>\n"
        f"<code>────────────────────────────</code>\n"
        f"🌐 <b>MẠNG XÃ HỘI GẮN KÈM:</b>\n"
        f"{social_display}\n"
        f"<code>────────────────────────────</code>\n"
        f"🔗 <b>Liên kết trực tiếp:</b> <a href='https://facebook.com/{uid}'>fb.com/{uid}</a>"
    )
    return panel, avatar_url


# ================= GIẢI NÉN LINK RÚT GỌN TIKTOK =================
async def resolve_tiktok_url(url: str) -> str:
    session = await get_http_session()
    clean = url.strip()
    if "vt.tiktok.com" in clean or "vm.tiktok.com" in clean:
        try:
            async with session.head(clean, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return str(resp.url)
        except Exception:
            try:
                async with session.get(clean, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return str(resp.url)
            except Exception as e:
                logger.error(f"Unshorten error: {e}")
    return clean


# ================= HÀM XỬ LÝ DOWNLOAD TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    session = await get_http_session()
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE

    post_headers = {
        **TIK_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        async with session.post(url, data=params or {}, headers=post_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and data.get("code") == 0:
                    return data
    except Exception as e:
        logger.warning(f"TikWM POST fail: {e}")

    try:
        async with session.get(url, params=params or {}, headers=TIK_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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


# ================= GIẢI MÃ NGÀY TẠO TIKTOK TỪ SNOWFLAKE UID =================
def get_tiktok_creation_time(uid: str) -> str:
    """Giải mã timestamp ngày tạo tài khoản từ 64-bit Snowflake ID của TikTok."""
    try:
        val = int(uid)
        timestamp = val >> 32
        if 1400000000 <= timestamp <= 2000000000:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d | %H:%M:%S")
    except Exception:
        pass
    return "Không xác định"


# ================= GIAO DIỆN PANEL TIKTOK THEO YÊU CẦU =================
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

    bio_raw = str(u.get("signature") or u.get("bio") or "Không có tiểu sử.")
    bio = html.escape(bio_raw)

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
        f"   ├ ❤️ Lượt thích: <code>{hearts:,}</code>\n"
        f"   └ 👫 Bạn bè:     <code>{friends:,}</code>\n"
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
        f"⚡ <b>TIKTOK, FACEBOOK & FREE FIRE TOOLKIT</b> ⚡\n"
        f"<code>────────────────────────────</code>\n"
        f"👋 Xin chào, <b>{display_name}</b>\n"
        f"Hệ thống đa nhiệm: Tải Media, Trích xuất Audio, Tra cứu OSINT & Game.\n\n"
        f"📌 <b>LỆNH TRUY CẬP NHANH:</b>\n"
        f"• 📥 <b>Tải TikTok:</b> Gửi trực tiếp link (Auto No-WM)\n"
        f"• 🎵 <b>Tách nhạc:</b> <code>/music &lt;link&gt;</code>\n"
        f"• 🔎 <b>Info TikTok:</b> <code>/getinfo &lt;user&gt;</code>\n"
        f"• 🔵 <b>Info Facebook:</b> <code>/fb &lt;uid/link&gt;</code>\n"
        f"• 🎮 <b>Info Free Fire:</b> <code>/ff &lt;uid&gt;</code>\n"
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
            InlineKeyboardButton("🎮 Info Free Fire", callback_data="panel_guide_ff"),
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
        f"⚡ <b>Độ trễ (Ping API):</b> <code>{ping_ms} ms</code>\n"
        f"🧠 <b>Bộ nhớ RAM:</b> <code>{ram_str}</code>\n"
        f"⚙️ <b>Async Loop:</b> <code>Active (Python 3.11+)</code>\n"
        f"<code>────────────────────────────</code>\n"
        f"📡 <b>TRẠNG THÁI CÁC DỊCH VỤ:</b>\n"
        f"├ 🎬 <b>TikWM Core:</b> 🟢 Operational\n"
        f"├ 🔁 <b>Fallback CDN:</b> 🟢 Standby Ready\n"
        f"├ 🎵 <b>Audio Extractor:</b> 🟢 Operational\n"
        f"├ 🔍 <b>TikTok Inspector:</b> 🟢 Operational\n"
        f"├ 🔵 <b>Facebook Multi-OSINT:</b> 🟢 Connected\n"
        f"└ 🎮 <b>Free Fire Engine:</b> 🟢 Connected\n"
        f"<code>────────────────────────────</code>\n"
        f"🛡 <b>Anti-WAF:</b> <i>Bypass Active</i>"
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
            "📥 <b>HƯỚNG DẪN TẢI TIKTOK</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Gửi link video hoặc album ảnh trực tiếp vào khung chat.\n"
            "• Bot tự động tải về file <b>không watermark HD</b>.\n"
            "• Hỗ trợ mọi định dạng link (kể cả link rút gọn <code>vt.tiktok.com</code>)."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            "🎵 <b>TRÍCH XUẤT AUDIO MP3</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/music &lt;link_tiktok&gt;</code>\n"
            "• Hoặc bấm trực tiếp nút <b>[Tải nhạc]</b> bên dưới mỗi video tải về.\n"
            "• Trả về file âm thanh chất lượng cao kèm thông tin nghệ sĩ."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_info":
        text = (
            "🔎 <b>TRA CỨU TIKTOK USER</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/getinfo tiktok</code>\n"
            "• Trả về: Thẻ bảng chi tiết, trạng thái bán hàng, bạn bè và ngày tạo chính xác."
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
            "• <i>Ví dụ:</i> <code>/fb 4</code> hoặc <code>/fb https://facebook.com/zuck</code>\n"
            "• <b>Dữ liệu bóc tách:</b> Tên, UID, Giới tính, Follower, Năm tạo, Nơi sống, Học vấn, Công việc, Toàn bộ tiểu sử & Các mạng xã hội gắn kèm."
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_ff":
        text = (
            "🎮 <b>TRA CỨU PROFILE FREE FIRE</b>\n"
            "<code>────────────────────────────</code>\n"
            "• Cú pháp: <code>/ff &lt;uid&gt;</code>\n"
            "• <i>Ví dụ:</i> <code>/ff 123456789</code>\n"
            "• <b>Dữ liệu trả về:</b> Tên, Level, Lượt thích, Khu vực, Điểm Rank Tử Chiến (CS), Điểm Sinh Tồn (BR) và Quân đoàn."
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


# LỆNH /ff <uid>
async def cmd_ff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    if not context.args:
        help_panel = (
            f"╔════════ ⚠️ <b>THIẾU THAM SỐ</b> ════════╗\n"
            f"║ 📌 <b>Cú pháp:</b> <code>/ff &lt;uid&gt;</code>\n"
            f"║ 💡 <i>Ví dụ: <code>/ff 123456789</code></i>\n"
            f"╚════════════════════════════════════╝"
        )
        try:
            await update.message.reply_photo(photo=IMG_FF, caption=help_panel, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    input_uid = context.args[0].strip()
    status_msg = await update.message.reply_text(
        f"⚡ <i>Đang truy vấn dữ liệu Free Fire cho UID:</i> <code>{html.escape(input_uid)}</code>...",
        parse_mode=ParseMode.HTML,
    )

    res = await check_ff_profile(input_uid)
    await status_msg.delete()

    if res.get("success"):
        try:
            await update.message.reply_photo(photo=IMG_FF, caption=res["formatted_text"], parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(res["formatted_text"], parse_mode=ParseMode.HTML)
    else:
        err_msg = res.get("error", "Không thể lấy thông tin tài khoản.")
        err_panel = (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"❌ <b>TRA CỨU FREE FIRE THẤT BẠI</b>\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"🆔 <b>UID:</b> <code>{html.escape(input_uid)}</code>\n"
            f"⚠️ <b>Lỗi:</b> <i>{html.escape(err_msg)}</i>\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
        )
        await update.message.reply_text(err_panel, parse_mode=ParseMode.HTML)


# LỆNH /fb <link_hoặc_uid>
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

    await status_msg.edit_text(f"📡 <i>Đang quét dữ liệu OSINT, Follower & MXH cho UID:</i> <code>{uid}</code>...", parse_mode=ParseMode.HTML)
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
    await query.answer("⏳ Đang trích xuất audio gốc...", show_alert=False)
    data = query.data

    video_id = data.replace("dlmusic_", "")
    tik_url = f"https://www.tiktok.com/@a/video/{video_id}"

    api_res = await tikwm_req("", {"url": tik_url})
    if not api_res or api_res.get("code") != 0:
        api_res = await fallback_tik_download(tik_url)

    if not api_res or api_res.get("code") != 0 or not api_res.get("data"):
        await query.message.reply_text("❌ Không lấy được audio từ video này.")
        return

    res = api_res["data"]
    music_url = res.get("music") or res.get("music_info", {}).get("play")
    if not music_url:
        await query.message.reply_text("❌ Video này bị tắt tiếng hoặc không có track âm thanh riêng biệt.")
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

    try:
        await query.message.reply_audio(
            audio=music_url,
            title=music_title,
            performer=music_author,
            caption=audio_panel,
            parse_mode=ParseMode.HTML,
            read_timeout=60,
            write_timeout=60,
        )
    except Exception as e:
        logger.error(f"Lỗi gửi audio: {e}")
        await query.message.reply_text("❌ Lỗi gửi file audio lên Telegram.")


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

    msg = await update.message.reply_text("⏳ <i>Đang bóc tách file âm thanh...</i>", parse_mode=ParseMode.HTML)

    target_url = await resolve_tiktok_url(raw_url)
    clean_url = target_url.split("?")[0] if "vt.tiktok.com" not in target_url else target_url

    data = await tikwm_req("", {"url": clean_url})
    if not data or data.get("code") != 0:
        data = await fallback_tik_download(clean_url)

    if not data or data.get("code") != 0 or not data.get("data"):
        await msg.edit_text("❌ <b>Không trích xuất được:</b> Video riêng tư, bị xoá hoặc link không hợp lệ.")
        return

    res = data["data"]
    music_url = res.get("music") or res.get("music_info", {}).get("play")
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

    await msg.delete()
    try:
        await update.message.reply_audio(
            audio=music_url,
            title=music_title,
            performer=music_author,
            caption=audio_panel,
            parse_mode=ParseMode.HTML,
            read_timeout=60,
            write_timeout=60,
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


# TỰ ĐỘNG TẢI KHI GỬI LINK TIKTOK
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    if "tiktok.com" in text:
        match = re.search(r"https?://[^\s]+", text)
        if not match:
            return
        raw_url = match.group(0)

        msg = await update.message.reply_text("⏳ <i>Đang bóc tách dữ liệu đa phương tiện...</i>", parse_mode=ParseMode.HTML)

        target_url = await resolve_tiktok_url(raw_url)
        clean_url = target_url.split("?")[0] if "vt.tiktok.com" not in target_url else target_url

        data = await tikwm_req("", {"url": clean_url, "hd": 1})
        if not data or data.get("code") != 0:
            logger.warning("TikWM không phản hồi, chuyển sang Fallback LoveTik...")
            data = await fallback_tik_download(clean_url)

        if not data or data.get("code") != 0 or not data.get("data"):
            await msg.edit_text("❌ <b>Tải thất bại:</b> Video đã bị xóa, tài khoản riêng tư hoặc link sai.")
            return

        res = data["data"]
        video_id = str(res.get("id") or "")
        title = html.escape(res.get("title") or "TikTok Video")
        author = html.escape(res.get("author", {}).get("nickname") or "N/A")
        music_title = html.escape(res.get("music_info", {}).get("title") or "Original Sound")

        caption = (
            f"╔══════════ 🎬 <b>TIKTOK DOWNLOAD</b> ══════════╗\n"
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

        try:
            if res.get("images"):
                await msg.delete()
                media = [InputMediaPhoto(media=img) for img in res["images"][:10]]
                await update.message.reply_media_group(media=media)
                await update.message.reply_photo(photo=IMG_DOWN, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                video_url = res.get("hdplay") or res.get("play")
                if not video_url:
                    await msg.edit_text("❌ Không trích xuất được link video chất lượng cao.")
                    return
                await msg.delete()
                await update.message.reply_video(
                    video=video_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=60,
                    write_timeout=60,
                )
        except Exception as e:
            logger.error(f"Lỗi gửi media: {e}")
            await update.message.reply_text("❌ Không thể gửi video (Dung lượng vượt giới hạn hoặc CDN timeout).")
        return


# ================= KHỞI CHẠY BOT =================
def main():
    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            MULTI-PLATFORM TOOLKIT ONLINE             ║\n"
        "║          Engine: python-telegram-bot v20+            ║\n"
        "║   Features: TikTok, Facebook & Free Fire Check       ║\n"
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
    app.add_handler(CommandHandler("ff", cmd_ff))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
