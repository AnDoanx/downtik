#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import html
import logging
import os
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
logger = logging.getLogger("TikTokMasterBot")


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


# ================= HÀM XỬ LÝ API TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    async with aiohttp.ClientSession(headers=TIK_HEADERS) as session:
        try:
            if not endpoint:
                async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
            else:
                async with session.post(url, data=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
            return None
        except Exception as e:
            logger.error(f"TikWM Error: {e}")
            return None

async def fallback_tik_download(tiktok_url: str):
    url = f"https://api.tiklydown.eu.org/api/download?url={tiktok_url}"
    async with aiohttp.ClientSession(headers=TIK_HEADERS) as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    j = await resp.json(content_type=None)
                    video_url = j.get("video", {}).get("noWatermark") or j.get("video", {}).get("watermark")
                    images = [img.get("url") for img in j.get("images", []) if img.get("url")]
                    return {
                        "code": 0,
                        "data": {
                            "title": j.get("title", "TikTok Media"),
                            "author": {"nickname": j.get("author", {}).get("name", "N/A")},
                            "digg_count": j.get("stats", {}).get("likeCount", 0),
                            "comment_count": j.get("stats", {}).get("commentCount", 0),
                            "share_count": j.get("stats", {}).get("shareCount", 0),
                            "play": video_url,
                            "images": images,
                            "music_info": {"id": ""},
                            "id": j.get("id", ""),
                        },
                    }
        except Exception as e:
            logger.error(f"Fallback API Error: {e}")
    return None

async def fetch_tiktok_user_info(username: str) -> dict:
    clean_user = username.strip().lstrip("@")
    url = f"{TIK_INFO_API}{clean_user}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                return {"error": f"Mã phản hồi HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"Tik Info API Error: {e}")
            return {"error": str(e)}

# GIAO DIỆN PANEL GETINFO (ĐÃ LOẠI BỎ SECUID)
def format_user_info_panel(data: dict, username: str) -> tuple[str, str | None]:
    if not data or data.get("error"):
        err = data.get("error", "Không tìm thấy người dùng hoặc máy chủ không phản hồi.")
        return (
            f"┌───────────────────────────┐\n"
            f"│  ❌  <b>TRA CỨU THẤT BẠI</b>\n"
            f"├───────────────────────────┤\n"
            f"│ 🎯 <b>Target:</b> <code>@{html.escape(username)}</code>\n"
            f"│ ⚠️ <b>Lỗi:</b> <i>{html.escape(str(err))}</i>\n"
            f"└───────────────────────────┘",
            None,
        )

    u = data.get("data", {}).get("user") or data.get("userInfo", {}).get("user") or data.get("user") or data
    s = data.get("data", {}).get("stats") or data.get("userInfo", {}).get("stats") or data.get("stats") or {}

    nickname = html.escape(str(u.get("nickname") or u.get("name") or "—"))
    unique_id = html.escape(str(u.get("uniqueId") or u.get("unique_id") or username))
    uid = str(u.get("id") or u.get("uid") or "—")
    bio = html.escape(str(u.get("signature") or u.get("bio") or "Không có tiểu sử."))
    region = str(u.get("region") or u.get("country") or "N/A").upper()

    verified_badge = "💠 [TÍCH XANH]" if u.get("verified") or u.get("customVerify") else "⚪ [THƯỜNG]"
    private_badge = "🔒 [RIÊNG TƯ]" if u.get("privateAccount") or u.get("is_private") else "🌐 [CÔNG KHAI]"

    followers = s.get("followerCount") or s.get("followers") or 0
    following = s.get("followingCount") or s.get("following") or 0
    hearts = s.get("heartCount") or s.get("hearts") or s.get("heart") or 0
    videos = s.get("videoCount") or s.get("video") or 0
    diggs = s.get("diggCount") or 0

    avatar = u.get("avatarLarger") or u.get("avatarMedium") or u.get("avatarThumb") or u.get("avatar")

    panel = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"   ✨ <b>HỒ SƠ TÀI KHOẢN TIKTOK</b> ✨\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"🏷 <b>Định danh cá nhân:</b>\n"
        f" ├ 👤 <b>Tên hiển thị:</b> <b>{nickname}</b>\n"
        f" ├ 🆔 <b>ID TikTok:</b> <code>@{unique_id}</code>\n"
        f" ├ 🔢 <b>Mã UID:</b> <code>{uid}</code>\n"
        f" ├ 🌏 <b>Khu vực:</b> <code>{region}</code>\n"
        f" └ 🛡 <b>Huy hiệu:</b> {verified_badge} │ {private_badge}\n\n"
        f"📊 <b>Chỉ số phân tích kênh:</b>\n"
        f" ┌ 👥 <b>Người theo dõi:</b> <code>{followers:,}</code>\n"
        f" ├ 👣 <b>Đang theo dõi:</b> <code>{following:,}</code>\n"
        f" ├ ❤️ <b>Tổng lượt thả tim:</b> <code>{hearts:,}</code>\n"
        f" ├ 🎬 <b>Video đã đăng tải:</b> <code>{videos:,}</code>\n"
        f" └ 👍 <b>Lượt video đã thích:</b> <code>{diggs:,}</code>\n\n"
        f"📝 <b>Lời giới thiệu (Bio):</b>\n"
        f" <i>« {bio} »</i>\n"
        f"─────────────────────────────"
    )

    return panel, avatar


# ================= GIAO DIỆN PANEL CHÍNH =================
def build_main_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "╔══════════════════════════════╗\n"
        "   ⚡ <b>TIKTOK MASTER DASHBOARD</b> ⚡\n"
        "╚══════════════════════════════╝\n\n"
        "🟢 <b>Trạng thái:</b> <code>ĐANG HOẠT ĐỘNG</code>\n\n"
        "📌 <b>BỘ LỆNH ĐIỀU KHIỂN:</b>\n"
        "├ 📥 <b>Tải Video / Slide:</b> Gửi trực tiếp link TikTok vào chat.\n"
        "└ 🔎 <b>Tra cứu User:</b> <code>/getinfo &lt;username&gt;</code> (hoặc <code>/check</code>)\n\n"
        "💡 <i>Tự động gỡ logo, tải ảnh full chất lượng, trích xuất UID nhanh.</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("📥 Hướng Dẫn Tải", callback_data="panel_guide_down"),
            InlineKeyboardButton("🔎 Hướng Dẫn GetInfo", callback_data="panel_guide_check"),
        ],
        [
            InlineKeyboardButton("⚡ Kiểm Tra Trạng Thái", callback_data="panel_status"),
        ],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    text, reply_markup = build_main_dashboard()
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def handle_panel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    back_btn = [[InlineKeyboardButton("⬅️ Quay lại Dashboard", callback_data="panel_home")]]

    if data == "panel_home":
        text, reply_markup = build_main_dashboard()
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif data == "panel_guide_down":
        text = (
            "╭━━━ 📥 <b>HƯỚNG DẪN TẢI VIDEO / ẢNH</b>\n"
            "┃\n"
            "┃ 1️⃣ Sao chép link video TikTok (hoặc link rút gọn <code>vt.tiktok.com</code>).\n"
            "┃ 2️⃣ Gửi trực tiếp link vào hộp chat của bot.\n"
            "┃ 3️⃣ Bot tự động tải về video MP4 không watermark hoặc toàn bộ ảnh HD.\n"
            "┃\n"
            "╰━━━━━━━━━━━━━━━━━━━━"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_check":
        text = (
            "╭━━━ 🔎 <b>HƯỚNG DẪN DÙNG GETINFO</b>\n"
            "┃\n"
            "┃ • Cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "┃ • Hoặc: <code>/check &lt;username&gt;</code>\n"
            "┃ • Ví dụ: <code>/getinfo tiktok</code>\n"
            "┃\n"
            "┃ 💡 <i>Hệ thống sẽ trích xuất chi tiết UID, số người theo dõi, tym và ảnh đại diện.</i>\n"
            "╰━━━━━━━━━━━━━━━━━━━━"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_status":
        text = (
            "┌───────────────────────────┐\n"
            "│  ⚡ <b>HỆ THỐNG MÁY CHỦ SẴN SÀNG</b> │\n"
            "├───────────────────────────┤\n"
            "│ 🟢 <b>TikWM Service:</b> Hoạt động tốt\n"
            "│ 🟢 <b>User API:</b> Phản hồi ổn định\n"
            "│ 🛡️ <b>Backup CDN:</b> Active\n"
            "│ ⏱️ <b>Ping Engine:</b> Tức thời\n"
            "└───────────────────────────┘"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

# Lệnh /getinfo và /check
async def cmd_getinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Thiếu tên người dùng!</b>\n"
            "👉 Hãy dùng cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "<i>Ví dụ: <code>/getinfo tiktok</code></i>",
            parse_mode=ParseMode.HTML,
        )
        return

    username = context.args[0].strip().lstrip("@")
    status_msg = await update.message.reply_text(
        f"⚡ <i>Đang bóc tách thông tin</i> <code>@{html.escape(username)}</code>...",
        parse_mode=ParseMode.HTML,
    )

    info_data = await fetch_tiktok_user_info(username)
    report, avatar = format_user_info_panel(info_data, username)

    await status_msg.delete()
    if avatar:
        try:
            await update.message.reply_photo(photo=avatar, caption=report, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            logger.warning(f"Lỗi gửi avatar: {e}")

    await update.message.reply_text(report, parse_mode=ParseMode.HTML)

# CHỈ TỰ ĐỘNG BẮT LINK TIKTOK
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    if "tiktok.com" in text:
        words = text.split()
        target_url = next((w for w in words if "tiktok.com" in w), text)

        msg = await update.message.reply_text("⏳ <i>Đang bóc tách dữ liệu TikTok...</i>", parse_mode=ParseMode.HTML)

        # 1. Thử lấy từ TikWM
        data = await tikwm_req("", {"url": target_url, "hd": 1})

        # 2. Dự phòng API phụ nếu TikWM lỗi
        if not data or data.get("code") != 0:
            logger.warning("TikWM không phản hồi, chuyển fallback downloader...")
            data = await fallback_tik_download(target_url)

        if not data or data.get("code") != 0 or not data.get("data"):
            await msg.edit_text("❌ <b>Không tải được:</b> Link không đúng, video riêng tư hoặc đã bị xóa.")
            return

        res = data["data"]
        title = html.escape(res.get("title") or "TikTok Video")
        author = html.escape(res.get("author", {}).get("nickname") or "N/A")

        caption = (
            f"🎬 <b>{title}</b>\n"
            f"─────────────────────────────\n"
            f"👤 <b>Tác giả:</b> {author}\n"
            f"❤️ <code>{res.get('digg_count', 0):,}</code> tym │ "
            f"💬 <code>{res.get('comment_count', 0):,}</code> cmt │ "
            f"🔁 <code>{res.get('share_count', 0):,}</code> share\n"
            f"─────────────────────────────"
        )

        try:
            # Dạng bài Album ảnh
            if res.get("images"):
                await msg.delete()
                media = [InputMediaPhoto(media=img) for img in res["images"][:10]]
                await update.message.reply_media_group(media=media)
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
            else:
                # Dạng Video MP4
                video_url = res.get("hdplay") or res.get("play")
                if not video_url:
                    await msg.edit_text("❌ Không bóc tách được URL video chất lượng cao.")
                    return
                await msg.delete()
                await update.message.reply_video(
                    video=video_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=60,
                    write_timeout=60,
                )
        except Exception as e:
            logger.error(f"Lỗi gửi media: {e}")
            await update.message.reply_text("❌ Không thể gửi video (Dung lượng tệp vượt giới hạn Telegram hoặc timeout).")
        return


# ================= KHỞI CHẠY BOT =================
def main():
    terminal_banner = (
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║            TIKTOK TOOLKIT BOT ONLINE                 ║\n"
        "║          Engine: python-telegram-bot v20+            ║\n"
        "║       Commands: /getinfo, /check & Auto-Downloader   ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )
    print(terminal_banner)

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("getinfo", cmd_getinfo))
    app.add_handler(CommandHandler("check", cmd_getinfo))

    # Callbacks tương tác Panel
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Tự động tải khi gửi link TikTok
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
