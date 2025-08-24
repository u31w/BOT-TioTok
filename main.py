import os
from pyrogram import Client, filters
from pyrogram.types import Message
import youtube_dl
from TikTokApi import TikTokApi
import instaloader
from io import BytesIO
import requests

# ------------------ إعدادات البوت ------------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = Client("BotSaleh", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ------------------ رسالة الترحيب ------------------
WELCOME_MESSAGE = """👋┇أهلاً بك Bot-saleh
في بوت تحميل

نبذة :
يدعم التحميل من (3) تطبيقات

بدون علامة مائية 

التطبيقات المدعومة: ⬇️

1️⃣- تيك توك - TikTok 
2️⃣- انستقرام - Instagram 
4️⃣- يوتيوب - YouTube 

لمعلومات اكثر : @l_w2l

ارسل رابط الفيديو 👇
"""

# ------------------ START COMMAND ------------------
@app.on_message(filters.command("start"))
def start(client, message: Message):
    message.reply_text(WELCOME_MESSAGE)

# ------------------ استقبال الروابط ------------------
@app.on_message(filters.text & ~filters.command)
def download_video(client, message: Message):
    url = message.text.strip()

    try:
        # ------------------ YouTube ------------------
        if "youtube.com" in url or "youtu.be" in url:
            message.reply_text("🔄 جاري تحميل فيديو يوتيوب ...")
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',  # HD
                'outtmpl': 'video.mp4',
                'noplaylist': True
            }
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            message.reply_video("video.mp4")
            os.remove("video.mp4")

        # ------------------ TikTok ------------------
        elif "tiktok.com" in url:
            message.reply_text("🔄 جاري تحميل فيديو تيك توك ...")
            with TikTokApi() as api:
                video_bytes = api.video(url=url).bytes()
            message.reply_video(video_bytes)

        # ------------------ Instagram ------------------
        elif "instagram.com" in url:
            message.reply_text("🔄 جاري تحميل فيديو انستقرام ...")
            L = instaloader.Instaloader()
            post = instaloader.Post.from_shortcode(L.context, url.split("/")[-2])
            L.download_post(post, target=".")
            video_file = [f for f in os.listdir(".") if f.endswith(".mp4")][0]
            message.reply_video(video_file)
            os.remove(video_file)

        else:
            message.reply_text("⚠️ الرابط غير مدعوم!")

    except Exception as e:
        message.reply_text(f"❌ حدث خطأ أثناء التحميل: {str(e)}")

# ------------------ تشغيل البوت ------------------
app.run()