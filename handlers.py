import html
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import services

CONFIG = services.CONFIG


def is_authorized(user_id: int) -> bool:
    allowed = CONFIG.get("allowed_users", [])
    return not allowed or user_id in allowed


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    text = services.load_template("welcome.html", name=html.escape(update.effective_user.first_name or "User"))
    keyboard = [
        [InlineKeyboardButton("📥 Tải Video", callback_data="p_guide_down"), InlineKeyboardButton("🎵 Tách Âm Thanh", callback_data="p_guide_music")],
        [InlineKeyboardButton("🔎 Info TikTok", callback_data="p_guide_info"), InlineKeyboardButton("🔵 Info Facebook", callback_data="p_guide_fb")]
    ]
    await update.message.reply_photo(photo=CONFIG["banners"]["welcome"], caption=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id) or not context.args:
        await update.message.reply_text("📌 Cú pháp: <code>/fb &lt;link/uid&gt;</code>", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("⏳ <i>Đang bóc tách thông tin Facebook...</i>", parse_mode=ParseMode.HTML)
    uid = await services.get_fb_id(context.args[0])
    if not uid:
        await msg.edit_text("❌ Không lấy được UID.")
        return

    data = await services.fetch_fb_info(uid)
    if not data:
        await msg.edit_text("❌ Không thể quét profile này.")
        return

    text = services.load_template(
        "fb_profile.html",
        name=html.escape(data.get("name") or "Facebook User"),
        uid=uid,
        username=data.get("username") or "—",
        gender="Nam" if data.get("gender") == "male" else ("Nữ" if data.get("gender") == "female" else "Ẩn"),
        badge="ĐÃ XÁC MINH" if data.get("verified") else "BÌNH THƯỜNG",
        followers=data.get("followers") or "Ẩn",
        created=services.estimate_fb_creation(uid),
        hometown=data.get("hometown") or "Không công khai",
        location=data.get("location") or "Không công khai",
        work=data.get("work") or "Không công khai",
        education=data.get("education") or "Không công khai",
        about=html.escape(data.get("about") or "Không có.")
    )
    avatar = f"https://graph.facebook.com/{uid}/picture?width=720&height=720"
    await msg.delete()
    try:
        await update.message.reply_photo(photo=avatar, caption=text, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    text = update.message.text.strip()
    match = re.search(r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+", text)
    if not match:
        return

    msg = await update.message.reply_text("⏳ <i>Đang tải file...</i>", parse_mode=ParseMode.HTML)
    clean_url = await services.resolve_tiktok_url(match.group(0))
    res = await services.tikwm_req({"url": clean_url, "hd": 1})

    if not res or not res.get("data"):
        await msg.edit_text("❌ Không tải được video.")
        return

    d = res["data"]
    caption = services.load_template(
        "tik_download.html",
        title=html.escape(d.get("title") or "TikTok"),
        author=html.escape(d.get("author", {}).get("nickname") or "N/A"),
        music=html.escape(d.get("music_info", {}).get("title") or "Âm thanh gốc"),
        diggs=f"{d.get('digg_count', 0):,}",
        comments=f"{d.get('comment_count', 0):,}",
        shares=f"{d.get('share_count', 0):,}"
    )

    await msg.delete()
    if d.get("images"):
        media = [InputMediaPhoto(media=img) for img in d["images"][:10]]
        await update.message.reply_media_group(media=media)
    else:
        video_url = d.get("hdplay") or d.get("play")
        await update.message.reply_video(video=video_url, caption=caption, parse_mode=ParseMode.HTML)
