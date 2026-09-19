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

# Biến lưu session toàn cục tối ưu kết nối
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


# ================= HÀM XỬ LÝ API TIKTOK =================
async def tikwm_req(endpoint: str = "", params: dict = None):
    session = await get_http_session()
    url = f"{TIKWM_BASE}{endpoint}" if endpoint else TIKWM_BASE
    try:
        if not endpoint:
            async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        else:
            async with session.post(url, data=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"TikWM Error: {e}")
    return None


async def fallback_tik_download(tiktok_url: str):
    session = await get_http_session()
    url = f"https://api.tiklydown.eu.org/api/download?url={tiktok_url}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                j = await resp.json(content_type=None)
                video_url = j.get("video", {}).get("noWatermark") or j.get("video", {}).get("watermark")
                music_url = j.get("music", {}).get("play_url")
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
                        "music": music_url,
                        "music_info": {
                            "title": j.get("music", {}).get("title", "Original Sound"),
                            "author": j.get("music", {}).get("author", "TikTok"),
                        },
                        "images": images,
                        "id": j.get("id", ""),
                    },
                }
    except Exception as e:
        logger.error(f"Fallback API Error: {e}")
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


# ================= GIAO DIỆN PANEL ĐỒNG BỘ =================
def format_user_info_panel(data: dict, username: str) -> tuple[str, str | None]:
    if not data or data.get("error"):
        err = data.get("error", "Người dùng không tồn tại hoặc API lỗi.")
        return (
            f"╔════════ ❌ <b>TRA CỨU THẤT BẠI</b> ════════╗\n"
            f"║ 🎯 <b>Target:</b> <code>@{html.escape(username)}</code>\n"
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
        f"╔══════════ 👤 <b>USER PROFILE</b> ══════════╗\n"
        f"║ 📛 <b>Nickname:</b> <b>{nickname}</b>\n"
        f"║ 🆔 <b>Username:</b> <code>@{unique_id}</code>\n"
        f"║ 🔢 <b>Mã UID:</b> <code>{uid}</code>\n"
        f"║ 🌍 <b>Khu vực:</b> <code>{region}</code>\n"
        f"║ 🛡 <b>Xác thực:</b> {verified_badge} │ {private_badge}\n"
        f"╠══════════ 📊 <b>CHỈ SỐ PHÂN TÍCH</b> ══════════╣\n"
        f"║ 👥 <b>Followers:</b> <code>{followers:,}</code>\n"
        f"║ 👣 <b>Following:</b> <code>{following:,}</code>\n"
        f"║ ❤️ <b>Lượt thích:</b> <code>{hearts:,}</code>\n"
        f"║ 🎬 <b>Tổng Video:</b> <code>{videos:,}</code>\n"
        f"║ 👍 <b>Đã thích:</b> <code>{diggs:,}</code>\n"
        f"╠══════════ 📝 <b>TIỂU SỬ KÊNH</b> ══════════╣\n"
        f"║ <i>« {bio} »</i>\n"
        f"╚════════════════════════════════════╝"
    )

    return panel, avatar


def build_main_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "╔════════════════════════════════════╗\n"
        "║      ⚡ <b>TIKTOK ULTRA TOOLKIT</b> ⚡       ║\n"
        "║     <i>Professional Audio & Media Suite</i>     ║\n"
        "╚════════════════════════════════════╝\n\n"
        "🟢 <b>Trạng thái:</b> <code>ONLINE (Ready)</code>\n\n"
        "💎 <b>CÁC TÍNH NĂNG CHÍNH:</b>\n"
        "├ 📥 <b>Auto Downloader:</b> Gửi trực tiếp link TikTok để tải Video HD / Album ảnh không logo.\n"
        "├ 🎵 <b>Trích xuất Audio:</b> <code>/music &lt;link&gt;</code> tách nhạc MP3 âm thanh gốc.\n"
        "└ 🔎 <b>Tra cứu User:</b> <code>/getinfo &lt;username&gt;</code> phân tích số liệu kênh.\n\n"
        "👇 <i>Chọn danh mục điều hướng bên dưới để xem chi tiết:</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("📥 Hướng Dẫn Tải", callback_data="panel_guide_down"),
            InlineKeyboardButton("🎵 Hướng Dẫn Tách Nhạc", callback_data="panel_guide_music"),
        ],
        [
            InlineKeyboardButton("🔎 Tra Cứu User", callback_data="panel_guide_info"),
            InlineKeyboardButton("📡 Server Status", callback_data="panel_status"),
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

    back_btn = [[InlineKeyboardButton("⬅️ Quay lại Dashboard Chính", callback_data="panel_home")]]

    if data == "panel_home":
        text, reply_markup = build_main_dashboard()
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif data == "panel_guide_down":
        text = (
            "╔══════ 📥 <b>HƯỚNG DẪN TẢI VIDEO & ALBUM</b> ══════╗\n"
            "║\n"
            "║ 1️⃣ Sao chép liên kết video hoặc slide ảnh trên TikTok.\n"
            "║ 2️⃣ Gửi thẳng link vào khung chat này.\n"
            "║ 3️⃣ Bot tự xử lý và trả về video chất lượng gốc không watermark.\n"
            "║ 💡 <i>Hỗ trợ cả link rút gọn dạng vt.tiktok.com</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_music":
        text = (
            "╔══════ 🎵 <b>HƯỚNG DẪN TÁCH NHẠC MP3</b> ══════╗\n"
            "║\n"
            "║ • Cú pháp: <code>/music &lt;link_tiktok&gt;</code>\n"
            "║ • Hoặc bấm trực tiếp nút <b>[🎵 Tải nhạc MP3]</b> bên dưới\n"
            "║   mỗi video mà bot vừa tải về.\n"
            "║ 💡 <i>Trích xuất âm thanh gốc 320kbps rõ ràng, không lẫn tạp âm.</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_guide_info":
        text = (
            "╔══════ 🔎 <b>HƯỚNG DẪN TRA CỨU USER</b> ══════╗\n"
            "║\n"
            "║ • Cú pháp: <code>/getinfo &lt;username&gt;</code>\n"
            "║ • Ví dụ: <code>/getinfo tiktok</code>\n"
            "║ 💡 <i>Xem thông tin UID, tổng view, tym, follower và avatar chất lượng cao.</i>\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "panel_status":
        text = (
            "╔══════ 📡 <b>HỆ THỐNG MÁY CHỦ BOT</b> ══════╗\n"
            "║\n"
            "║ 🟢 <b>Core Engine:</b> Python AsyncIO\n"
            "║ 🟢 <b>TikWM Service:</b> Connected (Low Ping)\n"
            "║ 🟢 <b>Backup CDN:</b> Ready\n"
            "║ 🟢 <b>Audio Extractor:</b> Active\n"
            "║ 🟢 <b>User Lookup:</b> Active\n"
            "║\n"
            "╚════════════════════════════════════╝"
        )
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(back_btn))


# Xử lý nút bấm callback tải nhạc trực tiếp dưới video
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
        await update.message.reply_text(help_panel, parse_mode=ParseMode.HTML)
        return

    target_url = context.args[0].strip()
    if "tiktok.com" not in target_url:
        await update.message.reply_text("⚠️ Vui lòng cung cấp link TikTok hợp lệ.", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ <i>Đang bóc tách file âm thanh chất lượng cao...</i>", parse_mode=ParseMode.HTML)

    data = await tikwm_req("", {"url": target_url})
    if not data or data.get("code") != 0:
        data = await fallback_tik_download(target_url)

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
    if avatar:
        try:
            await update.message.reply_photo(photo=avatar, caption=report, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            logger.warning(f"Lỗi gửi avatar: {e}")

    await update.message.reply_text(report, parse_mode=ParseMode.HTML)


# TỰ ĐỘNG TẢI KHI GỬI LINK TIKTOK
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text.strip()

    if "tiktok.com" in text:
        words = text.split()
        target_url = next((w for w in words if "tiktok.com" in w), text)

        msg = await update.message.reply_text("⏳ <i>Đang bóc tách dữ liệu đa phương tiện...</i>", parse_mode=ParseMode.HTML)

        # 1. Thử qua TikWM
        data = await tikwm_req("", {"url": target_url, "hd": 1})

        # 2. Dự phòng API phụ
        if not data or data.get("code") != 0:
            logger.warning("TikWM không phản hồi, chuyển sang fallback API...")
            data = await fallback_tik_download(target_url)

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
            # Nếu là album slide ảnh
            if res.get("images"):
                await msg.delete()
                media = [InputMediaPhoto(media=img) for img in res["images"][:10]]
                await update.message.reply_media_group(media=media)
                await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                # Video MP4 HD
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
        "║            TIKTOK ULTRA TOOLKIT ONLINE               ║\n"
        "║          Engine: python-telegram-bot v20+            ║\n"
        "║        Commands: /getinfo, /music & Auto-Down        ║\n"
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

    # Callbacks tương tác Panel & Download Audio
    app.add_handler(CallbackQueryHandler(handle_download_music_callback, pattern="^dlmusic_"))
    app.add_handler(CallbackQueryHandler(handle_panel_callbacks, pattern="^panel_"))

    # Tự động bắt link TikTok
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    app.run_polling()


if __name__ == "__main__":
    main()
