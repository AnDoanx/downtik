import logging
import html
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# TOKEN ĐÃ ĐƯỢC THAY SẴN
BOT_TOKEN = "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98"
TIKWM_BASE = "https://www.tikwm.com/api/"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- API TIKWM ---
async def tikwm_req(endpoint: str = "", params: dict = None):
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=params or {}) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logging.error(f"API Error: {e}")
            return None

# --- MENU CHÍNH ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Tải Video TikTok", callback_data="menu_tiktok")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🤖 <b>Chào mừng bạn đến với Multi-Tool Bot!</b>\n\n"
        "Vui lòng chọn chức năng bạn muốn sử dụng bên dưới:"
    )
    
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

# --- XỬ LÝ MENU KHỜI ĐỘNG ---
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_tiktok":
        help_text = (
            "🎬 <b>Chức năng Tải TikTok:</b>\n\n"
            "• Gửi trực tiếp <b>link TikTok</b> vào chat để tải Video/Slide/Nhạc.\n"
            "• <code>/trending [VN]</code>: Nguồn cấp xu hướng.\n"
            "• <code>/search &lt;từ khóa&gt;</code>: Tìm kiếm video.\n"
            "• <code>/searchuser &lt;tên&gt;</code>: Tìm người dùng.\n"
            "• <code>/user &lt;unique_id&gt;</code>: Xem profile & video user.\n"
            "• <code>/hashtag &lt;tên&gt;</code>: Video theo Hashtag."
        )
        await query.message.reply_text(help_text, parse_mode="HTML")

# --- TẢI LINK TIKTOK ---
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "tiktok.com" not in url:
        return

    msg = await update.message.reply_text("⏳ Đang xử lý link TikTok...")
    data = await tikwm_req("", {"url": url, "hd": 1})

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
        keyboard.append([InlineKeyboardButton("🎵 Lấy nhạc & Video theo nhạc", callback_data=f"music_{music_id}")])
    keyboard.append([InlineKeyboardButton("💬 Xem bình luận", callback_data=f"comments_{res['id']}")])
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    try:
        if "images" in res and res["images"]:
            await msg.delete()
            images = res["images"][:10]
            media = [InputMediaPhoto(media=img_url) for img_url in images]
            await update.message.reply_media_group(media=media)
            await update.message.reply_text(caption, parse_mode="HTML", reply_markup=markup)
        else:
            video_url = res.get("hdplay") or res.get("play")
            await msg.delete()
            await update.message.reply_video(video=video_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logging.error(f"Error sending media: {e}")
        await update.message.reply_text("❌ Không thể tải hoặc gửi file phương tiện.")

# --- LỆNH TIKTOK MỞ RỘNG ---
async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    region = context.args[0] if context.args else "VN"
    res = await tikwm_req("feed/list", {"region": region, "count": 5})
    
    if res and res.get("code") == 0:
        await update.message.reply_text(f"🔥 <b>Top Xu Hướng ({html.escape(region)}):</b>", parse_mode="HTML")
        for vid in res["data"][:3]:
            caption = f"🎬 {html.escape(vid.get('title', ''))}\n👤 {html.escape(vid['author']['nickname'])}"
            await update.message.reply_video(video=vid["play"], caption=caption)
    else:
        await update.message.reply_text("❌ Không thể lấy nguồn cấp xu hướng.")

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keywords = " ".join(context.args)
    if not keywords:
        await update.message.reply_text("Cú pháp: <code>/search &lt;từ khóa&gt;</code>", parse_mode="HTML")
        return

    res = await tikwm_req("feed/search", {"keywords": keywords, "count": 5, "cursor": 0})
    if res and res.get("code") == 0 and res["data"].get("videos"):
        await update.message.reply_text(f"🔍 <b>Kết quả tìm kiếm cho:</b> <code>{html.escape(keywords)}</code>", parse_mode="HTML")
        for vid in res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))
    else:
        await update.message.reply_text("❌ Không tìm thấy kết quả.")

async def cmd_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args)
    if not keyword:
        await update.message.reply_text("Cú pháp: <code>/searchuser &lt;tên người dùng&gt;</code>", parse_mode="HTML")
        return

    res = await tikwm_req("user/search", {"keyword": keyword, "count": 5})
    if res and res.get("code") == 0 and res["data"].get("users"):
        text = f"🔎 <b>Kết quả tìm kiếm user '{html.escape(keyword)}':</b>\n\n"
        for u in res["data"]["users"][:5]:
            nick = html.escape(u.get('nickname', ''))
            uid = html.escape(u.get('unique_id', ''))
            text += f"• <b>{nick}</b> (@{uid}) - ID: <code>{u['uid']}</code>\n"
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Không tìm thấy user.")

async def cmd_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unique_id = context.args[0] if context.args else ""
    if not unique_id:
        await update.message.reply_text("Cú pháp: <code>/user &lt;unique_id&gt;</code>", parse_mode="HTML")
        return

    info_res = await tikwm_req("user/info", {"unique_id": unique_id})
    if info_res and info_res.get("code") == 0:
        u = info_res["data"]["user"]
        s = info_res["data"]["stats"]
        profile_text = (
            f"👤 <b>{html.escape(u.get('nickname', ''))}</b> (@{html.escape(u.get('unique_id', ''))})\n"
            f"📝 {html.escape(u.get('signature', 'Không có tiểu sử'))}\n\n"
            f"👥 Theo dõi: {s.get('followingCount', 0)} | Người theo dõi: {s.get('followerCount', 0)}\n"
            f"❤️ Tổng Tym: {s.get('heartCount', 0)} | 🎬 Video: {s.get('videoCount', 0)}"
        )
        if u.get("avatarLarger"):
            await update.message.reply_photo(photo=u["avatarLarger"], caption=profile_text, parse_mode="HTML")
        else:
            await update.message.reply_text(profile_text, parse_mode="HTML")

    posts_res = await tikwm_req("user/posts", {"unique_id": unique_id, "count": 3})
    if posts_res and posts_res.get("code") == 0 and posts_res["data"].get("videos"):
        for vid in posts_res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))

async def cmd_hashtag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hashtag = context.args[0] if context.args else ""
    if not hashtag:
        await update.message.reply_text("Cú pháp: <code>/hashtag &lt;tên_hashtag&gt;</code>", parse_mode="HTML")
        return

    res = await tikwm_req("challenge/posts", {"name": hashtag, "count": 3})
    if res and res.get("code") == 0 and res["data"].get("videos"):
        await update.message.reply_text(f"🏷️ <b>Video theo Hashtag #{html.escape(hashtag)}:</b>", parse_mode="HTML")
        for vid in res["data"]["videos"][:3]:
            await update.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))
    else:
        await update.message.reply_text("❌ Không tìm thấy hashtag hoặc chưa có video.")

# --- CALLBACK TIKTOK ---
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
                nick = html.escape(c['user']['nickname'])
                comment = html.escape(c['text'])
                cmt_text += f"👤 <b>{nick}</b>: {comment}\n"
            await query.message.reply_text(cmt_text, parse_mode="HTML")
        else:
            await query.message.reply_text("❌ Không tải được bình luận.")

    elif data.startswith("music_"):
        music_id = data.split("_")[1]
        res = await tikwm_req("music/posts", {"music_id": music_id, "count": 2})
        if res and res.get("code") == 0 and res["data"].get("videos"):
            await query.message.reply_text("🎵 <b>Các video sử dụng cùng nhạc này:</b>", parse_mode="HTML")
            for vid in res["data"]["videos"][:2]:
                await query.message.reply_video(video=vid["play"], caption=html.escape(vid.get("title", "")))

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Lệnh khởi động & Trợ giúp
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^menu_"))

    # Các lệnh tìm kiếm/tải TikTok
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("searchuser", cmd_search_user))
    app.add_handler(CommandHandler("user", cmd_user))
    app.add_handler(CommandHandler("hashtag", cmd_hashtag))

    # Xử lý Callback và Nhận Link
    app.add_handler(CallbackQueryHandler(handle_tiktok_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("Bot đã sẵn sàng hoạt động!")
    app.run_polling()

if __name__ == "__main__":
    main()
