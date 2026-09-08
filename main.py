import os
import re
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# Cấu hình log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Tự động lấy Token từ biến môi trường của Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào bạn! Hãy gửi link TikTok (Video, Slide ảnh hoặc Nhạc), tôi sẽ tải về giúp bạn."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not re.search(r'(tiktok\.com|vt\.tiktok\.com)', url):
        return

    status_msg = await update.message.reply_text("⏳ Đang xử lý link, vui lòng chờ...")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
    }

    try:
        loop = asyncio.get_running_loop()
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, extract_info)
        
        if not info:
            await status_msg.edit_text("❌ Không thể lấy thông tin từ link này.")
            return

        # 1. TRƯỜNG HỢP: SLIDESHOW / BỘ ẢNH
        entries = info.get('entries') or ([info] if info.get('_type') == 'playlist' else None)
        if entries and len(entries) > 1 and not info.get('requested_formats'):
            image_urls = [entry.get('url') for entry in entries if entry.get('url')]

            if image_urls:
                await status_msg.edit_text(f"📸 Tìm thấy {len(image_urls)} ảnh. Đang gửi...")
                for i in range(0, len(image_urls), 10):
                    batch = image_urls[i:i + 10]
                    await update.message.reply_media_group(
                        media=[{"type": "photo", "media": img_url} for img_url in batch]
                    )
                await status_msg.delete()
                return

        # 2. TRƯỜNG HỢP: VIDEO HẶC AUDIO
        direct_url = info.get('url')
        ext = info.get('ext', '')

        if direct_url:
            await status_msg.edit_text("🚀 Đang gửi file...")
            title = info.get('title', 'TikTok Content')
            
            if ext in ['mp3', 'm4a', 'wav', 'aac'] or 'audio' in info.get('vcodec', ''):
                await update.message.reply_audio(audio=direct_url, title=title)
            else:
                await update.message.reply_video(video=direct_url, caption=title[:1024])
            
            await status_msg.delete()
            return

        await status_msg.edit_text("❌ Không tìm thấy link tải phù hợp.")

    except Exception as e:
        logging.error(f"Error handling URL: {e}")
        await status_msg.edit_text("❌ Có lỗi xảy ra trong quá trình tải.")

def main():
    if not BOT_TOKEN:
        print("Lỗi: Chưa cài đặt BOT_TOKEN trên Railway!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
