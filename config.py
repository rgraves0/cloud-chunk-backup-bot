import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))

# MegaUp Credentials
MEGAUP_API_KEY = os.getenv("MEGAUP_API_KEY", "")
MEGAUP_BASE_URL = os.getenv("MEGAUP_BASE_URL", "https://megaup.net/api")

# System & Resource Tuning (Specs အလိုက် လိုအပ်သလို ပြင်ဆင်နိုင်သည်)
# Telegram Free Tier အတွက် အများဆုံး 1900 MB (1.9 GB) သတ်မှတ်ထားသည်
CHUNK_SIZE_MB = int(os.getenv("CHUNK_SIZE_MB", "1900"))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/app/downloads")

# Auto-scan စနစ်အတွက် တစ်ရက်လျှင် ၂ ကြိမ် (မနက် ၉ နာရီ နှင့် ည ၉ နာရီ)
AUTO_SCAN_HOURS = os.getenv("AUTO_SCAN_HOURS", "9,21")
