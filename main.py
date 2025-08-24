import os
import re
import asyncio
import tempfile
import shutil
from pathlib import Path
from contextlib import suppress

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# ---------------- إعدادات ----------------
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

TELEGRAM_MAX_MB = int(os.environ.get("TELEGRAM_MAX_MB", "1900"))
TELEGRAM_MAX_BYTES = TELEGRAM_MAX_MB * 1024 * 1024

# ---------------- رسائل ----------------
WELCOME = (
    "👋┇أهلاً بك **Bot-saleh**\n"
    "في بوت تحميل\n\n"
    "**نبذة :**\n"
    "يدعم التحميل من (3) تطبيقات\n\n"
    "**بدون علامة مائية**\n\n"
    "**التطبيقات المدعومة:** ⬇️\n\n"
    "1️⃣- تيك توك - TikTok\n"
    "2️⃣- انستقرام - Instagram\n"
    "4️⃣- يوتيوب - YouTube\n\n"
    "**لمعلومات اكثر :** @l_w2l\n\n"
    "ارسل رابط الفيديو 👇"
)

MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎬 فيديو HD", callback_data="mode:video")],
    [InlineKeyboardButton("🎵 صوت فقط", callback_data="mode:audio")],
    [InlineKeyboardButton("📦 أفضل تلقائي", callback_data="mode:auto")]
])

app = Client("BotSaleh", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
semaphore = asyncio.Semaphore(3)
URL_RGX = re.compile(r"https?://\S+")
app.storage = {}

# ---------------- دوال مساعدة ----------------
def human_readable_size(num: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"

def download_youtube(url, audio_only=False):
    filename = "video.mp4" if not audio_only else "audio.mp3"
    opts = {
        'format': 'bestaudio/best' if audio_only else 'bestvideo+bestaudio/best',
        'outtmpl': filename,
        'noplaylist': True,
        'quiet': True,
        'nocheckcertificate': True,
        'postprocessors': [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if audio_only else []
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    return filename

# ---------------- أوامر ----------------
@app.on_message(filters.command(["start","help"]))
async def start(_, m: Message):
    await m.reply_text(WELCOME, disable_web_page_preview=True)

@app.on_message(filters.text & ~filters.command)
async def on_text(_, m: Message):
    match = URL_RGX.search(m.text or "")
    if not match:
        return
    url = match.group(0)
    # تخزين الرابط
    sent = await m.reply_text("🔎 أفحص الرابط وأجهز التحميل…")
    app.storage[str(sent.id)] = url
    await sent.edit("✅ الرابط واضح\nاختَر طريقة التحميل من تحت:", reply_markup=MENU_KB)

@app.on_callback_query(filters.regex(r"^mode:(video|audio|auto)$"))
async def mode_clicked(_, cq: CallbackQuery):
    mode = cq.data.split(":")[1]
    msg_id = cq.message.id
    url = app.storage.get(str(msg_id))
    if not url:
        await cq.answer("انتهت الجلسة، أرسل الرابط مرة ثانية.", show_alert=True)
        return
    await cq.answer()
    await cq.message.edit_text("🔄 جاري التحميل…")

    audio_only = mode=="audio"
    tmp_dir = Path(tempfile.mkdtemp(prefix="salehbot_"))

    async with semaphore:
        try:
            file_path = download_youtube(url, audio_only=audio_only)
            fsize = Path(file_path).stat().st_size
            if fsize > TELEGRAM_MAX_BYTES:
                raise Exception(f"حجم الملف {human_readable_size(fsize)} أكبر من حد تيليجرام {TELEGRAM_MAX_MB}MB")

            caption = f"📦 التحميل جاهز!\nالحجم: {human_readable_size(fsize)}"
            if audio_only:
                await cq.message.reply_audio(file_path, caption=caption)
            else:
                await cq.message.reply_video(file_path, caption=caption, supports_streaming=True)
            await cq.message.delete()
        except Exception as e:
            await cq.message.edit_text(f"❌ صار خطأ:\n`{e}`")
        finally:
            with suppress(Exception):
                shutil.rmtree(tmp_dir, ignore_errors=True)

# ---------------- تشغيل البوت ----------------
if __name__ == "__main__":
    if not (API_ID and API_HASH and BOT_TOKEN):
        raise SystemExit("⚠️ لازم تضيف API_ID / API_HASH / BOT_TOKEN في Environment Variables.")
    app.run()