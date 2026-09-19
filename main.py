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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


# ================= HÀM XỬ LÝ API TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.error(f"TikWM Error: {e}")
            return None

async def fetch_tiktok_user_info(username: str) -> dict:
    """Gọi API kiểm tra thông tin chi tiết tài khoản TikTok."""
    clean_user = username.strip().lstrip("@")
    url = f"{TIK_INFO_API}{clean_user}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                return {"error": f"Lỗi HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"Tik Info API Error: {e}")
            return {"error": str(e)}

def format_user_info_report(data: dict, username: str) -> tuple[str, str | None]:
    """Format kết quả trả về từ API check info."""
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
        f"• <b>Đã thích (Digg):</b> {diggs:,}\n"
    )

    if sec_uid != "—":
        report += f"━━━━━━━━━━━━━━━━━━\n🔑 <b>SecUID:</b> <code>{sec_uid}</code>"

    return report, avatar


# ================= TELEGRAM HANDLERS =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("🎬 Menu Tải TikTok", callback_data="menu_down")],
        [InlineKeyboardButton("🔍 Menu Check Info", callback_data="menu_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🤖 <b>Chào mừng bạn đến với TikTok Multi-Tool Bot!</b>\n\n"
        "✨ <b>Cách sử dụng:</b>\n"
        "• <b>Tải video/ảnh:</b> Gửi trực tiếp link TikTok vào chat (tự động nhận diện).\n"
        "• <b>Kiểm tra tài khoản:</b> Dùng lệnh <code>/check &lt;username&gt;</code>.\n\n"
        "Bấm menu bên dưới để xem hướng dẫn chi tiết:"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_down":
        help_text = (
            "🎬 <b>Chức năng Tải & Khám phá TikTok:</b>\n\n"
            "• Gửi trực tiếp <b>link TikTok</b> vào chat để tải video/ảnh tự động.\n"
            "• <code>/trending [VN]</code>: Nguồn cấp video xu hướng.\n"
            "• <code>/search &lt;từ khóa&gt;</code>: Tìm kiếm video theo từ khóa.\n"
            "• <code>/searchuser &lt;tên&gt;</code>: Tìm kiếm người dùng.\n"
            "• <code>/hashtag &lt;tên&gt;</code>: Xem video theo hashtag."
        )
        await query.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    elif data == "menu_info":
        help_text = (
            "🔍 <b>Chức năng Tra Cứu Tài Khoản TikTok:</b>\n\n"
            "• Dùng lệnh: <code>/check &lt;username&gt;</code>\n"
            "  <i>Ví dụ: <code>/check tiktok</code> hoặc <code>/check nguyenvana</code></i>\n\n"
            "• Dùng lệnh: <code>/user &lt;username&gt;</code> để tra cứu kèm xem 3 video mới nhất."
        )
        await query.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# CHỈ TỰ ĐỘNG XỬ LÝ KHI CÓ LINK TIKTOK (Bỏ check khi tag @user)
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    # Chỉ xử lý khi người dùng gửi Link TikTok
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
            f"❤️ {res.get('digg_count', 0):,} | 💬 {res.get('comment_count', 0):,} | 🔁 {res.get('share_count', 0):,}"
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

# Lệnh /check username
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

# Các lệnh TikTok khác
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
    unique_id = context.args[0].strip().lstrip("@") if context.args else ""
    if not unique_id:
        await update.message.reply_text("Cú pháp: <code>/user &lt;unique_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    info_data = await fetch_tiktok_user_info(unique_id)
    report, avatar = format_user_info_report(info_data, unique_id)
    if avatar:
        try:
            await update.message.reply_photo(photo=avatar, caption=report, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(report, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)

    posts_res = await tikwm_req("user/posts", {"unique_id": unique_id, "count": 3})
    if posts_res and posts_res.get("code") == 0 and posts_res["data"].get("videos"):
        await update.message.reply_text("📹 <b>3 Video gần nhất của kênh:</b>", parse_mode=ParseMode.HTML)
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

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("user", cmd_user))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("searchuser", cmd_search_user))
    app.add_handler(CommandHandler("hashtag", cmd_hashtag))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(handle_tiktok_callback))

    # Message Handler: CHỈ XỬ LÝ LINK TIKTOK ĐỂ TỰ ĐỘNG TẢI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("TikTok Multi-Tool Bot đã khởi chạy thành công!")
    app.run_polling()

if __name__ == "__main__":
    main()
