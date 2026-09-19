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
ALLOWED_USERS = []  # Điền ID Telegram (int) nếu muốn giới hạn quyền, để trống nếu public

# TikTok API Endpoints
TIKWM_BASE = "https://www.tikwm.com/api/"
TIK_INFO_API = "https://ksjdjdmfmxm.x10.mx/tik1.php?user="

# SoundCloud API
SCL_API_BASE = "https://api-v2.soundcloud.com/search/tracks"
SCL_CLIENT_ID = "Tbe9YspsDY5jcNlK6GmSimUxBQeXn8Ho"

# Headers giả lập trình duyệt
COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


# ================= HÀM XỬ LÝ TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    headers = {**COMMON_HEADERS, "Referer": "https://www.tikwm.com/"}
    async with aiohttp.ClientSession(headers=headers) as session:
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
    headers = {**COMMON_HEADERS, "Referer": "https://www.tikwm.com/"}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    j = await resp.json(content_type=None)
                    video_url = j.get("video", {}).get("noWatermark") or j.get("video", {}).get("watermark")
                    images = [img.get("url") for img in j.get("images", []) if img.get("url")]
                    return {
                        "code": 0,
                        "data": {
                            "title": j.get("title", "TikTok Video"),
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
            logger.error(f"Fallback Download Error: {e}")
    return None

async def fetch_tiktok_user_info(username: str) -> dict:
    clean_user = username.strip().lstrip("@")
    url = f"{TIK_INFO_API}{clean_user}"
    async with aiohttp.ClientSession(headers=COMMON_HEADERS) as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                return {"error": f"Lỗi HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"Tik Info API Error: {e}")
            return {"error": str(e)}

def format_user_info_report(data: dict, username: str) -> tuple[str, str | None]:
    if not data or data.get("error"):
        err = data.get("error", "Không tìm thấy người dùng hoặc API không phản hồi.")
        return f"❌ <b>Kiểm tra thất bại (@{html.escape(username)}):</b>\n<i>{html.escape(str(err))}</i>", None

    u = data.get("data", {}).get("user") or data.get("userInfo", {}).get("user") or data.get("user") or data
    s = data.get("data", {}).get("stats") or data.get("userInfo", {}).get("stats") or data.get("stats") or {}

    nickname = html.escape(str(u.get("nickname") or u.get("name") or "—"))
    unique_id = html.escape(str(u.get("uniqueId") or u.get("unique_id") or username))
    uid = str(u.get("id") or u.get("uid") or "—")
    bio = html.escape(str(u.get("signature") or u.get("bio") or "Không có tiểu sử"))
    sec_uid = str(u.get("secUid") or u.get("sec_uid") or "—")
    region = str(u.get("region") or u.get("country") or "—")

    verified = "✅ Đã xác minh (Tích xanh)" if u.get("verified") or u.get("customVerify") else "❌ Chưa xác minh"
    private_acc = "🔒 Riêng tư" if u.get("privateAccount") or u.get("is_private") else "🌍 Công khai"

    followers = s.get("followerCount") or s.get("followers") or 0
    following = s.get("followingCount") or s.get("following") or 0
    hearts = s.get("heartCount") or s.get("hearts") or s.get("heart") or 0
    videos = s.get("videoCount") or s.get("video") or 0
    diggs = s.get("diggCount") or 0

    avatar = u.get("avatarLarger") or u.get("avatarMedium") or u.get("avatarThumb") or u.get("avatar")

    report = (
        f"👤 <b>THÔNG TIN TÀI KHOẢN TIKTOK</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Tên:</b> {nickname}\n"
        f"🆔 <b>Username:</b> @{unique_id}\n"
        f"🔢 <b>UID:</b> <code>{uid}</code>\n"
        f"🌍 <b>Khu vực:</b> {region} | <b>Trạng thái:</b> {private_acc}\n"
        f"🏅 <b>Tích xanh:</b> {verified}\n"
        f"📝 <b>Tiểu sử:</b> <i>{bio}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>THỐNG KÊ:</b>\n"
        f"• <b>Followers:</b> {followers:,}\n"
        f"• <b>Đang theo dõi:</b> {following:,}\n"
        f"• <b>Lượt thích (Tym):</b> {hearts:,}\n"
        f"• <b>Video đã đăng:</b> {videos:,}\n"
        f"• <b>Đã thích:</b> {diggs:,}\n"
    )

    if sec_uid != "—":
        report += f"━━━━━━━━━━━━━━━━━━\n🔑 <b>SecUID:</b> <code>{sec_uid}</code>"

    return report, avatar


# ================= HÀM XỬ LÝ SOUNDCLOUD =================
async def search_soundcloud(query: str, limit: int = 5):
    params = {
        "q": query,
        "client_id": SCL_CLIENT_ID,
        "limit": limit,
    }
    headers = {**COMMON_HEADERS, "Referer": "https://soundcloud.com/"}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(SCL_API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 401:
                    return {"error": "unauthorized"}
                elif resp.status != 200:
                    return {"error": f"status_{resp.status}"}
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"SoundCloud Error: {e}")
            return {"error": str(e)}


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = (
        "🤖 <b>Chào mừng bạn đến với Multi-Tool Bot!</b>\n\n"
        "✨ <b>Danh sách tính năng:</b>\n"
        "1. <b>Tải TikTok:</b> Gửi trực tiếp link TikTok vào khung chat.\n"
        "2. <b>Check Info TikTok:</b> <code>/check &lt;username&gt;</code>\n"
        "3. <b>Tìm nhạc SoundCloud:</b> <code>/scl &lt;tên bài hát&gt;</code>\n"
        "4. <b>Khám phá TikTok:</b> <code>/trending</code>, <code>/search</code>, <code>/searchuser</code>\n"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# Lệnh /scl tìm nhạc SoundCloud
async def cmd_scl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Vui lòng nhập từ khóa tìm kiếm.\nVí dụ: <code>/scl Cắt đôi nỗi sầu</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args).strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    res = await search_soundcloud(query, limit=5)

    if isinstance(res, dict) and res.get("error") == "unauthorized":
        await update.message.reply_text("❌ Client ID SoundCloud đã hết hạn. Vui lòng cập nhật Client ID mới!")
        return
    elif not res or "collection" not in res or not res["collection"]:
        await update.message.reply_text("❌ Không tìm thấy bài hát nào trên SoundCloud.")
        return

    for item in res["collection"]:
        title = html.escape(item.get("title") or "Không rõ tiêu đề")
        artist = html.escape(item.get("user", {}).get("username") or "Không rõ nghệ sĩ")
        link = item.get("permalink_url") or "https://soundcloud.com"
        thumb = item.get("artwork_url") or item.get("user", {}).get("avatar_url")

        if thumb:
            thumb = thumb.replace("large", "t500x500")

        text = (
            f"🎵 <b>{title}</b>\n"
            f"👤 <b>Nghệ sĩ:</b> {artist}\n"
            f"🔗 <a href='{link}'>Nghe trên SoundCloud</a>"
        )

        try:
            if thumb:
                await update.message.reply_photo(photo=thumb, caption=text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# Lệnh /check info TikTok
async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Cú pháp: <code>/check &lt;username&gt;</code>\nVí dụ: <code>/check tiktok</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    username = context.args[0].strip().lstrip("@")
    status_msg = await update.message.reply_text(f"⏳ Đang tra cứu <code>@{username}</code>...", parse_mode=ParseMode.HTML)

    info_data = await fetch_tiktok_user_info(username)
    report, avatar = format_user_info_report(info_data, username)

    await status_msg.delete()
    if avatar:
        try:
            await update.message.reply_photo(photo=avatar, caption=report, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            logger.warning(f"Không thể gửi avatar: {e}")

    await update.message.reply_text(report, parse_mode=ParseMode.HTML)

# XỬ LÝ TEXT: CHỈ TỰ ĐỘNG TẢI KHI GỬI LINK TIKTOK
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    if "tiktok.com" in text:
        words = text.split()
        target_url = next((w for w in words if "tiktok.com" in w), text)

        msg = await update.message.reply_text("⏳ Đang xử lý link TikTok...")

        data = await tikwm_req("", {"url": target_url, "hd": 1})
        if not data or data.get("code") != 0:
            logger.warning("TikWM lỗi, chuyển sang Fallback API...")
            data = await fallback_tik_download(target_url)

        if not data or data.get("code") != 0 or not data.get("data"):
            await msg.edit_text("❌ Link không hợp lệ, video riêng tư hoặc server tải đang bảo trì.")
            return

        res = data["data"]
        title = html.escape(res.get("title", "TikTok Video"))
        author = html.escape(res.get("author", {}).get("nickname", "N/A"))

        caption = (
            f"🎬 <b>{title}</b>\n\n"
            f"👤 Tác giả: {author}\n"
            f"❤️ {res.get('digg_count', 0):,} | 💬 {res.get('comment_count', 0):,} | 🔁 {res.get('share_count', 0):,}"
        )

        try:
            if res.get("images"):
                await msg.delete()
                media = [InputMediaPhoto(media=img) for img in res["images"][:10]]
                await update.message.reply_media_group(media=media)
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
            else:
                video_url = res.get("hdplay") or res.get("play")
                if not video_url:
                    await msg.edit_text("❌ Không tìm thấy URL video tải xuống.")
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
            await update.message.reply_text("❌ Lỗi gửi media lên Telegram.")
        return

# Các lệnh phụ khác
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


# ================= KHỞI CHẠY BOT =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("scl", cmd_scl))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("search", cmd_search))

    # Tự động tải link TikTok
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("Bot tổng hợp TikTok + SoundCloud đã khởi chạy thành công!")
    app.run_polling()

if __name__ == "__main__":
    main()
