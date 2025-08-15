import asyncio
import os
import re
import tempfile
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from yt_dlp import YoutubeDL

# === إعدادات عامة ===
BOT_TOKEN = "8360006158:AAGBZ1pDVGBkVV0aHj-DtzHdywHseawTRVo"  # (بطلبك) مدموج داخل الكود
MAX_TELEGRAM_UPLOAD = 1_950_000_000  # ~1.95GB هامش أقل من 2GB
ALLOWED_DOMAINS = ("tiktok.com", "vm.tiktok.com", "instagram.com", "www.instagram.com")

HELP_TEXT = (
    "هلا! أنا بوت تحميل من تيك توك وإنستغرام 🎯\n\n"
    "طريقة الاستخدام:\n"
    "1) أرسل رابط المقطع (تيك توك أو ريلز إنستغرام) ✅\n"
    "2) أختار الجودة: 1080p / 720p / 480p أو صوت فقط 🎧\n"
    "3) لو التحميل بياخذ وقت (مثلاً ~20 ثانية)، بعطيك نسبة التقدّم 1% → 100% مع الوقت المتوقع ⏳\n"
    "4) أرسل لك الملف جاهز ✅\n\n"
    "ملاحظات:\n"
    "- الروابط الخاصة/المحفوظة غالبًا ما تشتغل.\n"
    "- لو الحجم كبير ويتعدّى حد تيليجرام، بقولك تختار جودة أقل.\n"
).strip()

QUALITY_OPTIONS = [
    ("1080p", "v1080"),
    ("720p",  "v720"),
    ("480p",  "v480"),
    ("صوت فقط (m4a)", "audio"),
]

def is_supported_url(url: str) -> bool:
    return url.startswith("http") and any(d in url for d in ALLOWED_DOMAINS)

def make_format_str(choice: str) -> str:
    if choice == "v1080":
        return "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
    if choice == "v720":
        return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
    if choice == "v480":
        return "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
    # audio
    return "bestaudio[ext=m4a]/bestaudio"

def human_eta(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "غير معروف"
    try:
        return str(timedelta(seconds=int(seconds)))
    except Exception:
        return f"~{int(seconds)} ث"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("يا هلا فيك 🤝\n\n" + HELP_TEXT)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

def build_quality_keyboard():
    buttons = [[InlineKeyboardButton(txt, callback_data=val)] for txt, val in QUALITY_OPTIONS]
    return InlineKeyboardMarkup(buttons)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    url_match = re.search(r"(https?://\S+)", text)
    if not url_match:
        await update.message.reply_text("أرسل الرابط نفسه لو سمحت 🙏")
        return
    url = url_match.group(1)

    if not is_supported_url(url):
        await update.message.reply_text("حاليًا أدعم تيك توك وإنستغرام فقط. أرسل رابط منهم.")
        return

    context.user_data["pending_url"] = url
    await update.message.reply_text("اختر الجودة اللي تناسبك 👇", reply_markup=build_quality_keyboard())

async def _progress_updater(progress_msg, state):
    """كوروتين يحدّث رسالة التقدّم كل ثانية بناءً على الحالة المشتركة التي تحدّثها yt-dlp."""
    last_pct = -1
    try:
        while not state["done"]:
            pct = state.get("pct", 0)
            eta = state.get("eta")
            if pct != last_pct:
                last_pct = pct
                await progress_msg.edit_text(f"جاري التحميل... {pct}%\nالوقت المتوقع: {human_eta(eta)}")
            await asyncio.sleep(1)
        # عند الانتهاء اعرض رسالة انتقالية
        await progress_msg.edit_text("تم التحميل ✅، الآن أجهّز الإرسال...")
    except Exception:
        # تجاهل أخطاء التعديل (مثلاً لو انحذفت الرسالة)
        pass

def progress_hook_state(state: dict):
    """يرجّع دالة hook للـ yt-dlp تقوم فقط بتحديث الحالة المشتركة (بدون لمس تيليجرام مباشرة)."""
    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            eta = d.get("eta")
            if total:
                state["pct"] = max(0, min(100, int(downloaded * 100 / total)))
            else:
                state["pct"] = state.get("pct", 0)
            state["eta"] = eta
        elif d.get("status") == "finished":
            state["pct"] = 100
    return hook

async def download_and_send(url: str, quality_choice: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress_msg = await update.effective_message.reply_text("ببدأ التحميل الآن... 0%")

    # إعدادات yt-dlp
    format_str = make_format_str(quality_choice)
    is_audio = (quality_choice == "audio")
    state = {"pct": 0, "eta": None, "done": False}

    # شغّل كوروتين تحديث شريط التقدم
    updater_task = asyncio.create_task(_progress_updater(progress_msg, state))

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, "%(title).80s.%(ext)s")
        postprocessors = []
        if is_audio:
            postprocessors = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "192"},
            ]
        else:
            # remux إلى mp4 قدر الإمكان
            postprocessors = [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ]

        ydl_opts = {
            "format": format_str,
            "outtmpl": outtmpl,
            "noplaylist": True,
            "retries": 2,
            "concurrent_fragment_downloads": 4,
            "progress_hooks": [progress_hook_state(state)],
            "postprocessors": postprocessors,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            },
        }

        file_path = None
        title = "video"
        try:
            loop = asyncio.get_running_loop()

            def _download():
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    nonlocal title
                    title = info.get("title", "video")
                    return ydl.prepare_filename(info)

            # شغّل التنزيل في ثريد منفصل عشان ما يوقف الحدث الرئيسي
            file_path = await loop.run_in_executor(None, _download)
            state["done"] = True
            await updater_task

            # تحقق الحجم قبل الإرسال
            if not os.path.exists(file_path):
                await progress_msg.edit_text("صار خطأ: ما قدرت ألقى الملف بعد التحميل.")
                return

            size = os.path.getsize(file_path)
            if size > MAX_TELEGRAM_UPLOAD:
                await progress_msg.edit_text("المعذرة، حجم الملف أكبر من حد تيليجرام (2GB). جرّب جودة أقل.")
                return

            # الإرسال
            await progress_msg.edit_text("أرسل لك الملف الآن...")
            if is_audio:
                with open(file_path, "rb") as f:
                    await update.effective_message.reply_audio(
                        audio=f,
                        title=title,
                        filename=os.path.basename(file_path),
                    )
            else:
                with open(file_path, "rb") as f:
                    await update.effective_message.reply_video(
                        video=f,
                        caption=title,
                        supports_streaming=True,
                    )

            try:
                await progress_msg.delete()
            except Exception:
                pass

        except Exception as e:
            state["done"] = True
            try:
                await updater_task
            except Exception:
                pass
            try:
                await progress_msg.edit_text(f"صار خطأ أثناء التحميل/الإرسال: {e}")
            except Exception:
                pass

async def on_quality_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quality_choice = query.data
    url = context.user_data.get("pending_url")

    if not url:
        await query.edit_message_text("ما لقيت الرابط. أرسل الرابط من جديد لو سمحت.")
        return

    await query.edit_message_text(f"تم ✅\nالرابط:\n{url}\nالخيار: {quality_choice}\nببدأ التحميل الآن.")
    # ننفّذ التنزيل والإرسال
    await download_and_send(url, quality_choice, update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_quality_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()