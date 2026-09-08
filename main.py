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

# Lấy Token từ biến môi trường Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8949220582:AAGtDVbFiZnkmp5xEIPmn9txu8yVFzdfv98")

# Endpoint công cộng của Cobalt API
COBALT_API_URL = "https://api.cobalt.tools/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào bạn! Hãy gửi link từ TikTok, Instagram, Facebook, YouTube, Twitter/X... tôi sẽ tải video/ảnh/nhạc về giúp bạn."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Kiểm tra link cơ bản
    if not url.startswith("http://") and not url.startswith("https://"):
        return

    status_msg = await update.message.reply_text("⏳ Đang xử lý qua Cobalt API, vui lòng chờ...")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    payload = {
        "url": url,
        "videoQuality": "max"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(COBALT_API_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Không thể xử lý link này hoặc Cobalt API đang bận.")
                    return
                
                data = await resp.json()

        status = data.get("status")

        # 1. TRƯỜNG HỢP: TRẢ VỀ FILE TRỰC TIẾP HOẶC LINK REDIRECT (Video / Single Media / Audio)
        if status in ["stream", "redirect", "tunnel"]:
            media_url = data.get("url")
            filename = data.get("filename", "media")
            
            await status_msg.edit_text("🚀 Đang gửi nội dung cho bạn...")
            
            # Kiểm tra xem có phải file audio hay không dựa vào tên file hoặc đuôi mở rộng
            if any(ext in filename.lower() for ext in [".mp3", ".m4a", ".ogg", ".wav"]):
                await update.message.reply_audio(audio=media_url)
            else:
                await update.message.reply_video(video=media_url)
                
            await status_msg.delete()
            return

        # 2. TRƯỜNG HỢP: DẠNG PICKER (BỘ ẢNH SLIDESHOW / NHIỀU MEDIA)
        elif status == "picker":
            picker_items = data.get("picker", [])
            images = [item.get("url") for item in picker_items if item.get("type") == "photo" or item.get("url")]
            
            if images:
                await status_msg.edit_text(f"📸 Tìm thấy {len(images)} tệp. Đang gửi...")
                # Gửi tối đa 10 ảnh mỗi đợt theo giới hạn Telegram API
                for i in range(0, len(images), 10):
                    batch = images[i:i + 10]
                    await update.message.reply_media_group(
                        media=[{"type": "photo", "media": img_url} for img_url in batch]
                    )
                await status_msg.delete()
                return

        # 3. TRƯỜNG HỢP LỖI
        elif status == "error":
            error_code = data.get("text", "Lỗi không xác định từ API")
            await status_msg.edit_text(f"❌ Lỗi: {error_code}")
            return

        await status_msg.edit_text("❌ Không tìm thấy định dạng media phù hợp.")

    except Exception as e:
        logging.error(f"Error handling request: {e}")
        await status_msg.edit_text("❌ Có lỗi xảy ra trong quá trình kết nối tới Cobalt API.")

def main():
    if not BOT_TOKEN:
        print("Lỗi: Chưa cài đặt BOT_TOKEN!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot Cobalt đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
