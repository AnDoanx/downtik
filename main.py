#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import hashlib
import html
import json
import logging
import time
import aiohttp
import requests
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
BOT_TOKEN = "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98"
ALLOWED_USERS = []  # Điền ID Telegram (int) nếu muốn giới hạn quyền, để trống nếu public

# TikTok API Base
TIKWM_BASE = "https://www.tikwm.com/api/"

# CapCut Base Config
CAPCUT_AID = "348188"
CAPCUT_SDK_VER = "2.1.10-tiktok"
CAPCUT_LOGIN_HOST = "https://login-row.www.capcut.com"
CAPCUT_WWW_HOST = "https://www.capcut.com"
CAPCUT_XOR_KEY = 0x05
CAPCUT_HASH_SALT = "aDy0TUhtql92P7hScCs97YWMT-jub2q9"
CAPCUT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.7827.197 Safari/537.36"
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ================= HÀM HỖ TRỢ CAPCUT =================
def capcut_xor_encode(s: str) -> str:
    return "".join(f"{b ^ CAPCUT_XOR_KEY:02x}" for b in s.encode("utf-8"))

def capcut_normalize_email(email: str) -> str:
    e = email.lower().strip()
    if "@" not in e:
        return e
    user, _, dom = e.partition("@")
    if dom == "gmail.com":
        user = user.split("+")[0].replace(".", "")
    return f"{user}@{dom}"

def capcut_hashed_id(email: str) -> str:
    norm = capcut_normalize_email(email) + CAPCUT_HASH_SALT
    return hashlib.sha256(norm.encode()).hexdigest()

def capcut_common_params(extra=None):
    p = {
        "aid": CAPCUT_AID,
        "account_sdk_source": "web",
        "sdk_version": CAPCUT_SDK_VER,
        "language": "en",
        "timezone_name": "Etc/GMT-7",
        "browser_language": "en-US",
        "browser_name": "Mozilla",
        "browser_platform": "Win32",
        "browser_version": "5.0 (Windows NT 10.0; Win64; x64)",
        "cookie_enabled": "true",
        "screen_height": "768",
        "screen_width": "1366",
    }
    if extra:
        p.update(extra)
    return p

def make_capcut_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": CAPCUT_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Origin": "https://www.capcut.com",
        "Referer": "https://www.capcut.com/",
    })
    return s

class CapCutError(Exception):
    pass

class CapCutClient:
    def __init__(self, session):
        self.s = session
        self.commerce_domain = "https://commerce-api-sg.capcut.com"

    def get_region(self, email):
        url = f"{CAPCUT_LOGIN_HOST}/passport/web/region/"
        body = f"type=2&hashed_id={capcut_hashed_id(email)}"
        r = self.s.post(
            url,
            params=capcut_common_params({"mix_mode": "1"}),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25,
        )
        r.raise_for_status()
        return r.json()

    def check_email_registered(self, email):
        url = f"{CAPCUT_LOGIN_HOST}/passport/web/user/check_email_registered"
        body = f"mix_mode=1&email={capcut_xor_encode(email)}&fixed_mix_mode=1"
        r = self.s.post(
            url,
            params=capcut_common_params(),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25,
        )
        r.raise_for_status()
        return r.json()

    def login(self, email, password):
        url = f"{CAPCUT_LOGIN_HOST}/passport/web/email/login/"
        body = (
            f"mix_mode=1&email={capcut_xor_encode(email)}"
            f"&password={capcut_xor_encode(password)}&fixed_mix_mode=1"
        )
        r = self.s.post(
            url,
            params=capcut_common_params(),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25,
        )
        if r.status_code in (403, 429, 461, 462):
            raise CapCutError(f"Login bị chặn WAF (HTTP {r.status_code})")
        r.raise_for_status()
        j = r.json()
        if j.get("message") != "success":
            err_msg = j.get("data", {}).get("description") or j.get("message")
            raise CapCutError(f"{err_msg}")
        return j.get("data", {})

    def get_account_info(self):
        url = f"{CAPCUT_WWW_HOST}/passport/web/account/info/"
        r = self.s.get(url, params=capcut_common_params(), timeout=25)
        r.raise_for_status()
        return r.json().get("data", {})

    def get_subscription_info(self):
        url = f"{self.commerce_domain}/commerce/v1/subscription/user_info"
        r = self.s.post(url, json={"aid": CAPCUT_AID, "scene": "vip"}, timeout=25)
        r.raise_for_status()
        resp = r.json().get("response")
        return json.loads(resp) if isinstance(resp, str) else (resp or {})

    def get_benefits(self):
        url = f"{self.commerce_domain}/commerce/v3/benefits/batch_get_user_benefit"
        body = {
            "query_list": [
                {"resource_type": "aigc", "resource_id": "get_all", "benefit_type_list": []},
                {"resource_type": "normal_func", "resource_id": "get_all", "benefit_type_list": []},
            ]
        }
        r = self.s.post(url, json=body, timeout=25)
        r.raise_for_status()
        resp = r.json().get("response")
        return json.loads(resp) if isinstance(resp, str) else (resp or {})

    def get_credit(self):
        url = f"{self.commerce_domain}/commerce/v1/benefits/user_credit"
        r = self.s.post(url, json={}, timeout=25)
        r.raise_for_status()
        resp = r.json().get("response")
        return json.loads(resp) if isinstance(resp, str) else (resp or {})

def run_capcut_check(email: str, password: str) -> dict:
    c = CapCutClient(make_capcut_session())
    country = None

    try:
        region = c.get_region(email)
        country = region.get("data", {}).get("country_code")
    except Exception:
        pass

    try:
        reg = c.check_email_registered(email)
        if reg.get("data", {}).get("is_registered") is False:
            return {"status": False, "error": "Email chưa đăng ký CapCut"}
    except Exception:
        pass

    try:
        c.login(email, password)
    except CapCutError as e:
        return {"status": False, "error": str(e)}
    except Exception as e:
        return {"status": False, "error": f"Lỗi kết nối: {e}"}

    account = {}
    sub_info = {}
    benefits = {}
    credit = {}

    try:
        account = c.get_account_info()
    except Exception:
        pass

    try:
        sub_info = c.get_subscription_info()
    except Exception:
        pass

    try:
        benefits = c.get_benefits()
    except Exception:
        pass

    try:
        credit = c.get_credit()
    except Exception:
        pass

    return {
        "status": True,
        "email": email,
        "password": password,
        "country": country,
        "account": account,
        "sub_info": sub_info,
        "benefits": benefits,
        "credit": credit,
    }

def format_capcut_report(res: dict) -> str:
    if not res.get("status"):
        return (
            f"❌ <b>Kiểm tra thất bại</b>\n"
            f"• <b>Tài khoản:</b> <code>{html.escape(res.get('email', ''))}</code>\n"
            f"• <b>Lý do:</b> <i>{html.escape(str(res.get('error')))}</i>"
        )

    acc = res.get("account", {})
    sub = res.get("sub_info", {})
    pro = bool(sub.get("flag"))
    country = res.get("country") or "—"
    name = html.escape(str(acc.get("screen_name") or "—"))
    uid = str(acc.get("user_id_str") or acc.get("user_id") or "—")

    created = "—"
    if acc.get("create_time"):
        created = time.strftime("%d/%m/%Y", time.gmtime(acc["create_time"]))

    if pro:
        pro_status = "🌟 <b>PRO / VIP: CÓ</b>"
        end = sub.get("end_time") or 0
        exp_str = time.strftime("%d/%m/%Y %H:%M UTC", time.gmtime(end)) if end else "Không giới hạn"
        sub_type = html.escape(str(sub.get("subscribe_type") or sub.get("product_id") or "—"))
        trial = "Có (Free trial)" if sub.get("is_free_trial") else "Không"
        vip_details = (
            f"  ├ Hạn dùng: <code>{exp_str}</code>\n"
            f"  ├ Gói: <code>{sub_type}</code>\n"
            f"  └ Dùng thử: {trial}"
        )
    else:
        pro_status = "⚪ <b>PRO / VIP: KHÔNG</b>"
        vip_details = "  └ Gói thường (Free)"

    cr = res.get("credit", {}).get("credit", {})
    vip_cr = cr.get("vip_credit", 0)
    gift_cr = cr.get("gift_credit", 0)
    pur_cr = cr.get("purchase_credit", 0)
    total_cr = vip_cr + gift_cr + pur_cr

    vip_items = []
    for asset in res.get("benefits", {}).get("asset_list") or []:
        for det in asset.get("asset_details") or []:
            if det.get("role") == "vip":
                quota_all = det.get("quota_all", 0)
                quota_left = det.get("quota_left", 0)
                if quota_all > 0 or quota_left > 0:
                    vip_items.append(f"  • {asset.get('benefit_type')}: {quota_left}/{quota_all}")

    ben_str = "\n".join(vip_items[:4]) if vip_items else "  • Không có hạn mức VIP riêng"

    return (
        f"🎬 <b>KẾT QUẢ CHECK CAPCUT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Tên:</b> {name}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"📧 <b>Email:</b> <code>{html.escape(res.get('email'))}</code>\n"
        f"🔑 <b>Mật khẩu:</b> <code>{html.escape(res.get('password'))}</code>\n"
        f"🌍 <b>Khu vực:</b> <code>{country}</code> | <b>Tạo:</b> {created}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{pro_status}\n"
        f"{vip_details}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>AI Credit:</b> <b>{total_cr}</b> (VIP: {vip_cr} | Gift: {gift_cr} | Mua: {pur_cr})\n"
        f"🎁 <b>Đặc quyền (Quota):</b>\n{ben_str}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


# ================= HÀM XỬ LÝ TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=params or {}) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"TikWM Error: {e}")
            return None


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("🎬 Menu TikTok", callback_data="menu_tiktok")],
        [InlineKeyboardButton("⚙️ Menu CapCut", callback_data="menu_capcut")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🤖 <b>Chào mừng bạn đến với Multi-Tool Bot!</b>\n\n"
        "Bot tích hợp chức năng tải/tìm kiếm TikTok và kiểm tra tài khoản CapCut Pro.\n"
        "Vui lòng chọn tính năng cần xem hướng dẫn bên dưới:"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_tiktok":
        help_text = (
            "🎬 <b>Chức năng Tải & Tìm kiếm TikTok:</b>\n\n"
            "• Gửi trực tiếp <b>link TikTok</b> vào khung chat để tải.\n"
            "• <code>/trending [VN]</code>: Nguồn cấp xu hướng.\n"
            "• <code>/search &lt;từ khóa&gt;</code>: Tìm kiếm video.\n"
            "• <code>/searchuser &lt;tên&gt;</code>: Tìm người dùng.\n"
            "• <code>/user &lt;unique_id&gt;</code>: Profile & video người dùng.\n"
            "• <code>/hashtag &lt;tên&gt;</code>: Video theo hashtag."
        )
        await query.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    elif data == "menu_capcut":
        help_text = (
            "⚙️ <b>Chức năng Kiểm tra CapCut:</b>\n\n"
            "• Check 1 tài khoản:\n"
            "  <code>/check email|mật_khẩu</code>\n\n"
            "• Check nhiều tài khoản:\n"
            "  Gửi trực tiếp danh sách dạng mỗi dòng một tài khoản:\n"
            "  <code>email|mật_khẩu</code> (hoặc <code>email:mật_khẩu</code>)"
        )
        await query.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    # Nhánh 1: Gửi Link TikTok
    if "tiktok.com" in text:
        msg = await update.message.reply_text("⏳ Đang xử lý link TikTok...")
        data = await tikwm_req("", {"url": text, "hd": 1})

        if not data or data.get("code") != 0:
            await msg.edit_text("❌ Link không hợp lệ hoặc không lấy được dữ liệu.")
            return

        res = data["data"]
        title = html.escape(res.get("title", "TikTok Video"))
        author = html.escape(res.get("author", {}).get("nickname", "N/A"))
        music_id = res.get("music_info", {}).get("id", "")

        caption = (
            f"🎬 <b>{title}</b>\n\n"
            f"👤 Tác giả: {author}\n"
            f"❤️ {res.get('digg_count', 0)} | 💬 {res.get('comment_count', 0)} | 🔁 {res.get('share_count', 0)}"
        )

        keyboard = []
        if music_id:
            keyboard.append([InlineKeyboardButton("🎵 Video cùng nhạc", callback_data=f"music_{music_id}")])
        keyboard.append([InlineKeyboardButton("💬 Xem bình luận", callback_data=f"comments_{res['id']}")])
        markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        try:
            if "images" in res and res["images"]:
                await msg.delete()
                media = [InputMediaPhoto(media=img) for img in res["images"][:10]]
                await update.message.reply_media_group(media=media)
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                video_url = res.get("hdplay") or res.get("play")
                await msg.delete()
                await update.message.reply_video(video=video_url, caption=caption, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error sending media: {e}")
            await update.message.reply_text("❌ Không thể gửi phương tiện.")
        return

    # Nhánh 2: Danh sách CapCut bulk check (hàng loạt qua định dạng email|pass hoặc email:pass)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    accounts = []
    for line in lines:
        if "|" in line:
            u, _, p = line.partition("|")
            accounts.append((u.strip(), p.strip()))
        elif ":" in line and "@" in line:
            u, _, p = line.partition(":")
            accounts.append((u.strip(), p.strip()))

    if accounts:
        if len(accounts) > 20:
            await update.message.reply_text("⚠️ Vui lòng gửi tối đa 20 tài khoản mỗi lần.")
            return

        total = len(accounts)
        prog_msg = await update.message.reply_text(f"⏳ Đang kiểm tra <b>{total}</b> tài khoản CapCut...", parse_mode=ParseMode.HTML)
        loop = asyncio.get_running_loop()

        for email, password in accounts:
            res = await loop.run_in_executor(None, run_capcut_check, email, password)
            report = format_capcut_report(res)
            await update.message.reply_text(report, parse_mode=ParseMode.HTML)
            await asyncio.sleep(1.5)

        await prog_msg.edit_text("✅ <b>Đã kiểm tra xong toàn bộ danh sách!</b>", parse_mode=ParseMode.HTML)

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Cú pháp: <code>/check email|password</code>", parse_mode=ParseMode.HTML
        )
        return

    raw_input = context.args[0]
    sep = "|" if "|" in raw_input else (":" if ":" in raw_input else None)
    if not sep:
        await update.message.reply_text("⚠️ Định dạng sai. Dùng <code>email|password</code>", parse_mode=ParseMode.HTML)
        return

    email, _, password = raw_input.partition(sep)
    email, password = email.strip(), password.strip()

    status_msg = await update.message.reply_text(f"⏳ Đang kiểm tra <code>{email}</code>...", parse_mode=ParseMode.HTML)
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, run_capcut_check, email, password)
    await status_msg.edit_text(format_capcut_report(res), parse_mode=ParseMode.HTML)

# TikTok commands
async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    region = context.args[0] if context.args else "VN"
    res = await tikwm_req("feed/list", {"region": region, "count": 5})
    if res and res.get("code") == 0:
        await update.message.reply_text(f"🔥 <b>Top Xu Hướng ({html.escape(region)}):</b>", parse_mode=ParseMode.HTML)
        for vid in res["data"][:3]:
            caption = f"🎬 {html.escape(vid.get('title', ''))}\n👤 {html.escape(vid['author']['nickname'])}"
            await update.message.reply_video(video=vid["play"], caption=caption)
    else:
        await update.message.reply_text("❌ Không thể lấy nguồn cấp xu hướng.")

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    keywords = " ".join(context.args)
    if not keywords:
        await update.message.reply_text("Cú pháp: <code>/search &lt;từ khóa&gt;</code>", parse_mode=ParseMode.HTML)
        return

    res = await tikwm_req("feed/search", {"keywords": keywords, "count": 5, "cursor": 0})
    if res and res.get("code") == 0 and res["data"].get("videos"):
        await update.message.reply_text(f"🔍 <b>Kết quả:</b> <code>{html.escape(keywords)}</code>", parse_mode=ParseMode.HTML)
        for vid in res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))
    else:
        await update.message.reply_text("❌ Không tìm thấy kết quả.")

async def cmd_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    keyword = " ".join(context.args)
    if not keyword:
        await update.message.reply_text("Cú pháp: <code>/searchuser &lt;tên&gt;</code>", parse_mode=ParseMode.HTML)
        return

    res = await tikwm_req("user/search", {"keyword": keyword, "count": 5})
    if res and res.get("code") == 0 and res["data"].get("users"):
        text = f"🔎 <b>Kết quả tìm user '{html.escape(keyword)}':</b>\n\n"
        for u in res["data"]["users"][:5]:
            text += f"• <b>{html.escape(u.get('nickname', ''))}</b> (@{html.escape(u.get('unique_id', ''))}) - ID: <code>{u['uid']}</code>\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Không tìm thấy user.")

async def cmd_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    unique_id = context.args[0] if context.args else ""
    if not unique_id:
        await update.message.reply_text("Cú pháp: <code>/user &lt;unique_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    info_res = await tikwm_req("user/info", {"unique_id": unique_id})
    if info_res and info_res.get("code") == 0:
        u = info_res["data"]["user"]
        s = info_res["data"]["stats"]
        profile_text = (
            f"👤 <b>{html.escape(u.get('nickname', ''))}</b> (@{html.escape(u.get('unique_id', ''))})\n"
            f"📝 {html.escape(u.get('signature', 'Không có tiểu sử'))}\n\n"
            f"👥 Theo dõi: {s.get('followingCount', 0)} | Follower: {s.get('followerCount', 0)}\n"
            f"❤️ Tổng Tym: {s.get('heartCount', 0)} | 🎬 Video: {s.get('videoCount', 0)}"
        )
        if u.get("avatarLarger"):
            await update.message.reply_photo(photo=u["avatarLarger"], caption=profile_text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML)

    posts_res = await tikwm_req("user/posts", {"unique_id": unique_id, "count": 3})
    if posts_res and posts_res.get("code") == 0 and posts_res["data"].get("videos"):
        for vid in posts_res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))

async def cmd_hashtag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    hashtag = context.args[0] if context.args else ""
    if not hashtag:
        await update.message.reply_text("Cú pháp: <code>/hashtag &lt;tên_hashtag&gt;</code>", parse_mode=ParseMode.HTML)
        return

    res = await tikwm_req("challenge/posts", {"name": hashtag, "count": 3})
    if res and res.get("code") == 0 and res["data"].get("videos"):
        await update.message.reply_text(f"🏷️ <b>Hashtag #{html.escape(hashtag)}:</b>", parse_mode=ParseMode.HTML)
        for vid in res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))
    else:
        await update.message.reply_text("❌ Không tìm thấy hashtag.")

async def handle_tiktok_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("comments_"):
        video_id = data.split("_")[1]
        res = await tikwm_req("comment/list", {"url": f"https://www.tiktok.com/@a/video/{video_id}", "count": 5})
        if res and res.get("code") == 0 and res["data"].get("comments"):
            cmt_text = "💬 <b>Top Bình luận:</b>\n\n"
            for c in res["data"]["comments"][:5]:
                cmt_text += f"👤 <b>{html.escape(c['user']['nickname'])}</b>: {html.escape(c['text'])}\n"
            await query.message.reply_text(cmt_text, parse_mode=ParseMode.HTML)
        else:
            await query.message.reply_text("❌ Không tải được bình luận.")

    elif data.startswith("music_"):
        music_id = data.split("_")[1]
        res = await tikwm_req("music/posts", {"music_id": music_id, "count": 2})
        if res and res.get("code") == 0 and res["data"].get("videos"):
            await query.message.reply_text("🎵 <b>Các video cùng sử dụng nhạc này:</b>", parse_mode=ParseMode.HTML)
            for vid in res["data"]["videos"][:2]:
                await query.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))


# ================= KHỞI CHẠY BOT =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands Menu & CapCut
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))

    # Commands TikTok
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("searchuser", cmd_search_user))
    app.add_handler(CommandHandler("user", cmd_user))
    app.add_handler(CommandHandler("hashtag", cmd_hashtag))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(handle_tiktok_callback))

    # Nhận text: Tự động phân loại Link TikTok hoặc List Account CapCut
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("Bot đã sẵn sàng hoạt động!")
    app.run_polling()

if __name__ == "__main__":
    main()
