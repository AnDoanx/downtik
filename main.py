#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from datetime import datetime
import html
import logging
import os
import re
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

# ================= CẤU HÌNH TOKEN & API =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98")
ALLOWED_USERS = []  # Điền ID Telegram (int) nếu muốn private, để trống nếu public

# TikTok API Endpoints
TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

# Facebook Graph API & Tokens
FB_TOKENS = [
    "EAAAAUaZA8jlABSv6yeD3uBWPS8HcBca2YO6LIUlPo3pIGqLJ5dy5VAurXzOqYIdbWOMv4bDVbvqmFZAWhbhERAvRPusDXFNw4Y1pYN1jVcDCYFSr52BZBrCTNLWLt1ELZChCghXrYcpGvx4EeMMZBGdSpEa4unkYiyyoDgBpI0bMgQQS8MOCYYTHVe2G4KTmpHLtZAItDCcdVRPZCZA8nKFvogZDZD"
]

# Banner Images theo từng tác vụ
IMG_WELCOME = "https://cdn.phototourl.com/free/2026-09-20-707fd5ce-5572-4eb5-a904-e3f6002bcbdf.jpg"
IMG_MUSIC = "https://cdn.phototourl.com/free/2026-09-20-df9907e7-6ec8-424b-9d69-69b26659cb3b.jpg"
IMG_GETINFO = "https://cdn.phototourl.com/free/2026-09-20-c38e193c-d60a-418e-8b23-c2e122c5a350.jpg"
IMG_DOWN = "https://cdn.phototourl.com/free/2026-09-20-8f7cee5e-79ee-4e36-8bd6-1eb5d315635e.png"

TIK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.tikwm.com/",
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


# ================= CÁC HÀM XỬ LÝ FACEBOOK =================
def estimate_fb_creation_year(uid: str) -> str:
    """Ước lượng thời gian tạo tài khoản nếu Meta ẩn created_time."""
    if not uid.isdigit():
        return "Không công khai"

    val = int(uid)
    if val < 1000000:
        return "Khoảng 2004 - 2006 (Giai đoạn đầu)"
    elif val < 100000000:
        return "Khoảng 2006 - 2008"

    if str(val).startswith("10000"):
        prefix = str(val)[5:8]
        if prefix.isdigit():
            p_val = int(prefix)
            if p_val < 50:
                return "Khoảng 2009 - 2010"
            elif p_val < 150:
                return "Khoảng 2010 - 2012"
            elif p_val < 300:
                return "Khoảng 2012 - 2014"
            else:
                return "Khoảng 2014 - 2016"

    if str(val).startswith("10001") or str(val).startswith("10002"):
        return "Khoảng 2016 - 2018"
    elif str(val).startswith("10003") or str(val).startswith("10004"):
        return "Khoảng 2018 - 2020"
    elif str(val).startswith("10005") or str(val).startswith("10006") or str(val).startswith("10007"):
        return "Khoảng 2020 - 2022"
    elif str(val).startswith("10008") or str(val).startswith("10009"):
        return "Khoảng 2022 - 2024"
    elif str(val).startswith("6155") or str(val).startswith("6156") or str(val).startswith("6157"):
        return "Khoảng 2023 - 2026 (Tài khoản mới)"

    return "Không công khai"


def format_fb_time(time_str: str | None) -> str:
    """Format thời gian ISO 8601 sang ngày giờ Việt Nam."""
    if not time_str or time_str == "None":
        return "Không công khai"
    try:
        clean_time = time_str.split("+")[0].replace("Z", "")
        dt = datetime.fromisoformat(clean_time)
        return dt.strftime("%d/%m/%Y lúc %H:%M:%S")
    except Exception:
        return time_str.replace("T", " ")


async def get_fb_id(input_str: str) -> str | None:
    """Bóc tách UID Facebook trực tiếp, qua Graph API hoặc các endpoint dự phòng."""
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
            fb_graph_url = f"https://graph.facebook.com/{username}?fields=id&access_token={token}"
            async with session.get(fb_graph_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    res = await resp.json(content_type=None)
                    if "id" in res:
                        return str(res["id"])
        except Exception:
            pass

    try:
        tds_url = "https://id.traodoisub.com/api.php"
        async with session.post(tds_url, data={"link": clean}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data.get("id"):
                    return str(data["id"])
    except Exception:
        pass

    try:
        api_url = f"https://ffb.vn/api/tool/get-id-fb?idfb={clean}"
        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data.get("id"):
                    return str(data["id"])
    except Exception as e:
        logger.error(f"FFB Error: {e}")

    return None


async def fetch_fb_info(uid: str) -> dict | None:
    """Truy vấn full thông tin Facebook bao gồm followers, created_time và updated_time."""
    session = await get_http_session()

    full_fields = (
        "id,name,first_name,last_name,is_verified,gender,locale,timezone,short_name,"
        "subscribers.limit(0).summary(true),followers_count,updated_time,created_time,"
        "about,website,quotes,location,hometown,birthday,relationship_status,education,work,link"
    )
    safe_fields = (
        "id,name,is_verified,gender,locale,subscribers.limit(0).summary(true),"
        "followers_count,updated_time,created_time,link"
    )
    minimal_fields = "id,name,subscribers.limit(0).summary(true),followers_count,updated_time"

    for token in FB_TOKENS:
        try:
            url_full = f"https://graph.facebook.com/v19.0/{uid}?fields={full_fields}&access_token={token}"
            async with session.get(url_full, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                res = await resp.json(content_type=None)
                if "id" in res:
                    return res
        except Exception:
            pass

        try:
            url_safe = f"https://graph.facebook.com/v19.0/{uid}?fields={safe_fields}&access_token={token}"
            async with session.get(url_safe, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                res = await resp.json(content_type=None)
                if "id" in res:
                    return res
        except Exception:
            pass

        try:
            url_min = f"https://graph.facebook.com/v19.0/{uid}?fields={minimal_fields}&access_token={token}"
            async with session.get(url_min, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                res = await resp.json(content_type=None)
                if "id" in res:
                    return res
        except Exception:
            pass

    return None


def format_fb_info_panel(data: dict) -> tuple[str, str]:
    """Bóc tách và hiển thị chuẩn xác Followers, Ngày tạo và Cập nhật lần cuối."""
    uid = str(data.get("id", "—"))
    name = html.escape(str(data.get("name") or "Facebook User"))
    first_name = html.escape(str(data.get("first_name") or "—"))
    last_name = html.escape(str(data.get("last_name") or "—"))
    gender = html.escape(str(data.get("gender") or "Không công khai")).capitalize()
    birthday = html.escape(str(data.get("birthday") or "Không công khai"))
    relationship = html.escape(str(data.get("relationship_status") or "Không công khai"))
    locale = html.escape(str(data.get("locale") or "N/A"))
    timezone = str(data.get("timezone") or "N/A")

    hometown = html.escape(str(data.get("hometown", {}).get("name") or "Không công khai"))
    location = html.escape(str(data.get("location", {}).get("name") or "Không công khai"))
    about = html.escape(str(data.get("about") or "Không có tiểu sử."))
    website = html.escape(str(data.get("website") or "Không có"))
    quotes = html.escape(str(data.get("quotes") or "Không có"))

    # 1. Bóc tách người theo dõi (Followers)
    followers_val = None
    if "subscribers" in data and "summary" in data["subscribers"]:
        followers_val = data["subscribers"]["summary"].get("total_count")
    if followers_val is None and "followers_count" in data:
        followers_val = data.get("followers_count")

    if followers_val is not None:
        followers_str = f"<b>{followers_val:,}</b> người theo dõi"
    else:
        followers_str = "<i>Không công khai hoặc đã tắt</i>"

    # 2. Bóc tách Ngày tạo & Cập nhật lần cuối
    raw_created = data.get("created_time")
    if raw_created:
        created_str = format_fb_time(raw_created)
    else:
        created_str = f"~ {estimate_fb_creation_year(uid)}"

    raw_updated = data.get("updated_time")
    updated_str = format_fb_time(raw_updated)

    # 3. Học vấn & Công việc
    edu_list = []
    for edu in data.get("education", [])[:2]:
        school_name = edu.get("school", {}).get("name")
        edu_type = edu.get("type", "Trường học")
        if school_name:
            edu_list.append(f"  • {html.escape(edu_type)}: <b>{html.escape(school_name)}</b>")
    edu_str = "\n".join(edu_list) if edu_list else "  • Không công khai"

    work_list = []
    for w in data.get("work", [])[:2]:
        employer = w.get("employer", {}).get("name")
        position = w.get("position", {}).get("name")
        if employer and position:
            work_list.append(f"  • <b>{html.escape(position)}</b> tại <b>{html.escape(employer)}</b>")
        elif employer:
            work_list.append(f"  • Làm việc tại <b>{html.escape(employer)}</b>")
    work_str = "\n".join(work_list) if work_list else "  • Không công khai"

    verified = "💎 [ĐÃ XÁC MINH - TÍCH XANH]" if data.get("is_verified") else "⚪ [TÀI KHOẢN THƯỜNG]"
    avatar_url = f"https://graph.facebook.com/{uid}/picture?width=720&height=720&access_token={FB_TOKENS[0]}"

    panel = (
        f"╔══════════ 👤 <b>HỒ SƠ FACEBOOK PRO</b> ══════════╗\n"
        f"║ 📛 <b>Họ tên:</b> <b>{name}</b> (Họ: {last_name} | Tên: {first_name})\n"
        f"║ 🆔 <b>UID:</b> <code>{uid}</code>\n"
        f"║ 🚻 <b>Giới tính:</b> {gender}\n"
        f"║ 🎂 <b>Ngày sinh:</b> {birthday}\n"
        f"║ 💍 <b>Hôn nhân:</b> {relationship}\n"
        f"║ 🌐 <b>Ngôn ngữ:</b> {locale} │ <b>Múi giờ:</b> GMT{timezone}\n"
        f"║ 🛡 <b>Xác thực:</b> {verified}\n"
        f"╠══════════ 🕒 <b>THỜI GIAN HOẠT ĐỘNG</b> ══════════╣\n"
        f"║ 🗓 <b>Ngày tạo tài khoản:</b> <code>{created_str}</code>\n"
        f"║ 🔄 <b>Cập nhật gần nhất:</b> <code>{updated_str}</code>\n"
        f"╠══════════ 📊 <b>TƯƠNG TÁC & FOLLOWERS</b> ══════════╣\n"
        f"║ 👥 <b>Người theo dõi:</b> {followers_str}\n"
        f"╠══════════ 📍 <b>QUÊ QUÁN & NƠI Ở</b> ══════════╣\n"
        f"║ 🏡 <b>Quê quán:</b> {hometown}\n"
        f"║ 📌 <b>Nơi sống:</b> {location}\n"
        f"╠══════════ 💼 <b>CÔNG VIỆC & HỌC VẤN</b> ══════════╣\n"
        f"║ 🎓 <b>Học vấn:</b>\n{edu_str}\n"
        f"║ 🏢 <b>Công việc:</b>\n{work_str}\n"
        f"╠══════════ 📝 <b>TIỂU SỬ & LIÊN KẾT</b> ══════════╣\n"
        f"║ 🌐 <b>Website:</b> {website}\n"
        f"║ 💬 <b>Tiểu sử:</b> <i>« {about} »</i>\n"
        f"║ 🔗 <b>Trang cá nhân:</b> <a href='https://facebook.com/{uid}'>facebook.com/{uid}</a>\n"
        f"╚════════════════════════════════════════════╝"
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


# ================= GIAO DIỆN PANEL TIKTOK =================
def format_user_info_panel(data: dict, username: str) -> tuple[str, str | None]:
    if not data or data.get("error"):
        err = data.get("error", "Người dùng không tồn tại hoặc API bận.")
        return (
            f"╔════════ ❌ <b>TRA CỨU THẤT BẠI</b> ════════╗\n"
            f"║ 🎯 <b>Mục tiêu:</b> <code>@{html.escape(username)}</code>\n"
            f"║ ⚠️ <b>Chi tiết:</b> <i>{html.escape(str(err))}</i>\n"
            f"╚════════════════════════════════════╝",
            None,
        )

    u = data.get("data", {}).get("user") or data.get("userInfo", {}).get("user") or data.get("user") or data
    s = data.get("data", {}).get("stats") or data.get("userInfo", {}).get("stats") or data.get("stats") or {}

    nickname = html.escape(str(u.get("nickname") or u.get("name") or "—"))
    unique_id = html.escape(str(u.get("uniqueId") or u.get("unique_id") or username))
    uid = str(u.get("id") or u.get("uid") or "—")
    bio = html.escape(str(u.get("signature") or u.get("bio") or "Không có tiểu sử."))
    region = str(u.get("region") or u.get("country") or "N/A").upper()

    verified_badge = "💎 <b>Verified</b>" if u.get("verified") or u.get("customVerify") else "⚪ <b>Standard</b>"
    private_badge = "🔒 <b>Private</b>" if u.get("privateAccount") or u.get("is_private") else "🌐 <b>Public</b>"

    followers = s.get("followerCount") or s.get("followers") or 0
    following = s.get("followingCount") or s.get("following") or 0
    hearts = s.get("heartCount") or s.get("hearts") or s.get("heart") or 0
    videos = s.get("videoCount") or s.get("video") or 0
    diggs = s.get("diggCount") or 0

    avatar = u.get("avatarLarger") or u.get("avatarMedium") or u.get("avatarThumb") or u.get("avatar")

    panel = (
        f"╔══════════ 👤 <b>HỒ SƠ TIKTOK</b> ══════════╗\n"
        f"║ 📛 <b>Tên:</b> <b>{nickname}</b>\n"
        f"║ 🆔 <b>ID:</b> <code>@{unique_id}</code>\n"
        f"║ 🔢 <b>Mã UID:</b> <code>{uid}</code>\n"
        f"║ 🌍 <b>Khu vực:</b> <code>{region}</code>\n"
        f"║ 🛡 <b>Trạng thái:</b> {verified_badge} │ {private_badge}\n"
        f"╠══════════ 📊 <b>CHỈ SỐ TƯƠNG TÁC</b> ══════════╣\n"
        f"║ 👥 <b>Followers:</b> <code>{followers:,}</code>\n"
        f"║ 👣 <b>Following:</b> <code>{following:,}</code>\n"
        f"║ ❤️ <b>Tổng Tym:</b> <code>{hearts:,}</code>\n"
        f"║ 🎬 <b>Video đã đăng:</b> <code>{videos:,}</code>\n"
        f"║ 👍 <b>Đã thả tim:</b> <code>{diggs:,}</code>\n"
        f"╠══════════ 📝 <b>TIỂU SỬ KÊNH</b> ══════════╣\n"
        f"║ <i>« {bio} »</i>\n"
        f"╚════════════════════════════════════╝"
    )

    return panel, avatar


def build_welcome_dashboard(user_name: str = "Bạn") -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"╔════════════════════════════════════╗\n"
        f"   👋 <b>WELCOME, {html.escape(user_name).upper()}!</b>\n"
        f"   ⚡ <b>MULTI-PLATFORM AUTOMATION BOT</b> ⚡\n"
        f"╚════════════════════════════════════╝\n\n"
        f"🤖 <b>GIỚI THIỆU HỆ THỐNG:</b>\n"
        f"Hệ thống đa chức năng hỗ trợ tải media TikTok không logo, tách MP3 và trích xuất hồ sơ chi tiết TikTok & Facebook trực tiếp.\n\n"
        f"📌 <b>BỘ LỆNH ĐIỀU KHIỂN:</b>\n"
        f"├ 📥 <b>Tự động tải TikTok:</b> Dán trực tiếp link TikTok vào khung chat.\n"
        f"├ 🎵 <b>Tách Audio MP3:</b> <code>/music &lt;link&gt;</code> lấy track âm thanh.\n"
        f"├ 🔎 <b>Info TikTok:</b> <code>/getinfo &lt;username&gt;</code> phân tích chỉ số.\n"
        f"└ 🔵 <b>Info Facebook:</b> <code>/fb &lt;link_hoặc_uid&gt;</code> check full thông tin FB.\n\n"
        f"🟢 <i>Hệ thống trực tuyến 24/7 sẵn sàng hoạt động!</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("📥 Hướng Dẫn Tải", callback_data="panel_guide_down"),
            InlineKeyboardButton("🎵 Hướng Dẫn Audio", callback_data="panel_guide_music"),
        ],
        [
            InlineKeyboardButton("🔎 Info TikTok", callback_data="panel_guide_info"),
            InlineKeyboardButton("🔵 Info Facebook", callback_data="panel_guide_fb"),
        ],
        [
            InlineKeyboardButton("📡 Server Status", callback_data="panel_status"),
        ],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    user_name = update.effective_user.first_name or "Bạn"
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

    back_btn = [[InlineKeyboardButton("⬅️ Quay lại Menu Chính", callback_data="panel_home")]]

    if data == "panel_home":
        user_name = query.from_user.first_name or "Bạn"
        text, reply_markup = build_welcome_dashboard(user_name)
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif data == "panel_guide_down":
        text = (
            "╔══════ 📥 <b>HƯỚNG DẪN TẢI VIDEO & ALBUM</b> ══════╗\n"
            "║\n"
            "║ 1️⃣ Sao chép link video hoặc slide ảnh trên TikTok.\n"
            "║ 2️⃣ Dán trực tiếp link vào khung chat này.\n"
            "║ 3️⃣ Bot tự động tải về tệp không dính watermark.\n"
            "║ 💡 <i>Hỗ trợ cả link rút gọn dạng vt.tiktok.com</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            "╔══════ 🎵 <b>HƯỚNG DẪN TÁCH NHẠC MP3</b> ══════╗\n"
            "║\n"
            "║ • Cú pháp: <code>/music &lt;link_tiktok&gt;</code>\n"
            "║ • Hoặc bấm trực tiếp nút <b>[🎵 Tải nhạc MP3]</b> bên dưới\n"
            "║   mỗi video mà bot vừa tải về.\n"
            "║ 💡 <i>Trích xuất âm thanh gốc 320kbps sắc nét.</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_info":
        text = (
            "╔══════ 🔎 <b>HƯỚNG DẪN INFO TIKTOK</b> ══════╗\n"
            "║\n"
            "║ • Cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "║ • Ví dụ: <code>/getinfo tiktok</code>\n"
            "║ 💡 <i>Bóc tách số UID, tym, follower và ảnh đại diện.</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_fb":
        text = (
            "╔══════ 🔵 <b>HƯỚNG DẪN CHECK FACEBOOK</b> ══════╗\n"
            "║\n"
            "║ • Cú pháp: <code>/fb &lt;link_profile_hoặc_uid&gt;</code>\n"
            "║ • Ví dụ: <code>/fb 4</code>\n"
            "║ • Ví dụ: <code>/fb https://facebook.com/zuck</code>\n"
            "║ 💡 <i>Bóc tách full thông tin: người theo dõi, ngày tạo,</i>\n"
            "║ <i>cập nhật lần cuối, học vấn, công việc, quê quán...</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_status":
        text = (
            "╔══════ 📡 <b>TRẠNG THÁI MÁY CHỦ BOT</b> ══════╗\n"
            "║\n"
            "║ 🟢 <b>Core Engine:</b> Python AsyncIO\n"
            "║ 🟢 <b>TikWM Service:</b> Connected\n"
            "║ 🟢 <b>Fallback Service:</b> LoveTik Ready\n"
            "║ 🟢 <b>Audio Extractor:</b> Online\n"
            "║ 🟢 <b>TikTok Lookup:</b> Online\n"
            "║ 🟢 <b>Facebook Full Graph:</b> Connected\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))
        except Exception:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))


# LỆNH /fb <link_hoặc_uid> (FULL INFO)
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
        await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    input_data = context.args[0].strip()
    status_msg = await update.message.reply_text("⏳ <i>Đang bóc tách UID Facebook...</i>", parse_mode=ParseMode.HTML)

    uid = await get_fb_id(input_data)
    if not uid:
        await status_msg.edit_text("❌ Không lấy được UID. Vui lòng kiểm tra lại link hoặc định dạng!", parse_mode=ParseMode.HTML)
        return

    await status_msg.edit_text(f"📡 <i>Đang truy vấn dữ liệu chi tiết cho UID:</i> <code>{uid}</code>...", parse_mode=ParseMode.HTML)
    data = await fetch_fb_info(uid)

    if not data:
        await status_msg.edit_text("❌ Không tìm thấy thông tin hoặc Token Facebook đã hết hạn.", parse_mode=ParseMode.HTML)
        return

    report, avatar_url = format_fb_info_panel(data)
    await status_msg.delete()

    try:
        await update.message.reply_photo(photo=avatar_url, caption=report, parse_mode=ParseMode.HTML)
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
        "║      Features: TikTok Auto-Down, Music & FB Info     ║\n"
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

    # Callbacks tương tác Panel & Download Audio
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Tự động bắt link TikTok
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
