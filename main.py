#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Application, CommandHandler, MessageHandler, filters
import handlers
import services


async def on_startup(app: Application):
    await services.get_http_session()


async def on_shutdown(app: Application):
    await services.close_http_session()


def main():
    if not services.BOT_TOKEN:
        print("Lỗi: Thiếu BOT_TOKEN trong file .env!")
        return

    app = Application.builder().token(services.BOT_TOKEN).post_init(on_startup).post_shutdown(on_shutdown).build()

    app.add_handler(CommandHandler(["start", "help"], handlers.cmd_start))
    app.add_handler(CommandHandler("fb", handlers.cmd_fb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_tiktok_link))

    print("Bot đang chạy với cấu hình đa định dạng (.env, .json, .html)...")
    app.run_polling()


if __name__ == "__main__":
    main()
