import os
import re
import logging
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98")

# Các API Endpoint
COBALT_API_URL = "https://api.cobalt.tools/"
TIKWM_API_URL = "https://www.tikwm.com/api/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào bạn! Hãy gửi link TikTok, Instagram, Facebook, YouTube... tôi sẽ tải về giúp bạn."
    )

# Hàm dự phòng xử lý TikTok bằng TikWM API
async def fetch_tikwm(session, url):
    try:
        async with session.get(TIKWM_API_URL, params={"url": url}) as resp:
            if resp.status == 200:
                res = await resp.json()
                if res.get("code") == 0:
                    data = res.get("data", {})
                    images = data.get("images")
                    if images:
                        return {"type": "images", "urls": images}
                    video = data.get("play")
                    if video:
                        return {"type": "video", "url": video, "title": data.get("title", "")}
    except Exception as e:
        logging.error(f"TikWM Error: {e}")
    return None

# Hàm xử lý chính qua Cobalt API
async def fetch_cobalt(session, url):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    payload = {"url": url, "videoQuality": "max"}
    try:
        async with session.post(COBALT_API_URL, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logging.error(f"Cobalt Error: {e}")
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith("http://") and not url.startswith("https://"):
        return

    status_msg = await update.message.reply_text("⏳ Đang xử lý link, vui lòng chờ...")

    async with aiohttp.ClientSession() as session:
        # 1. Thử gọi Cobalt API trước
        cobalt_data = await fetch_cobalt(session, url)

        if cobalt_data:
            status = cobalt_data.get("status")
            
            # Xử lý Video / Direct link từ Cobalt
            if status in ["stream", "redirect", "tunnel"]:
                media_url = cobalt_data.get("url")
                filename = cobalt_data.get("filename", "").lower()
                
                await status_msg.edit_text("🚀 Đang gửi file...")
                if any(ext in filename for ext in [".mp3", ".m4a", ".ogg", ".wav"]):
                    await update.message.reply_audio(audio=media_url)
                else:
                    await update.message.reply_video(video=media_url)
                await status_msg.delete()
                return

            # Xử lý bộ ảnh từ Cobalt
            elif status == "picker":
                picker_items = cobalt_data.get("picker", [])
                images = [item.get("url") for item in picker_items if item.get("url")]
                if images:
                    await status_msg.edit_text(f"📸 Tìm thấy {len(images)} ảnh. Đang gửi...")
                    for i in range(0, len(images), 10):
                        batch = images[i:i + 10]
                        await update.message.reply_media_group(
                            media=[{"type": "photo", "media": img_url} for img_url in batch]
                        )
                    await status_msg.delete()
                    return

        # 2. Nếu Cobalt thất bại và link là TikTok -> Chuyển sang dùng TikWM API làm dự phòng
        if "tiktok.com" in url:
            tikwm_data = await fetch_tikwm(session, url)
            if tikwm_data:
                if tikwm_data["type"] == "images":
                    images = tikwm_data["urls"]
                    await status_msg.edit_text(f"📸 (Dự phòng) Tìm thấy {len(images)} ảnh. Đang gửi...")
                    for i in range(0, len(images), 10):
                        batch = images[i:i + 10]
                        await update.message.reply_media_group(
                            media=[{"type": "photo", "media": img_url} for img_url in batch]
                        )
                    await status_msg.delete()
                    return
                elif tikwm_data["type"] == "video":
                    await status_msg.edit_text("🚀 (Dự phòng) Đang gửi video...")
                    await update.message.reply_video(
                        video=tikwm_data["url"], 
                        caption=tikwm_data["title"][:1024]
                    )
                    await status_msg.delete()
                    return

        # 3. Nếu cả 2 đều không tải được
        await status_msg.edit_text("❌ Không thể xử lý link này. Vui lòng kiểm tra lại link hoặc thử lại sau!")

def main():
    if not BOT_TOKEN:
        print("Lỗi: Chưa cài đặt BOT_TOKEN!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
