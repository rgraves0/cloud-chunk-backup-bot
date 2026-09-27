import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))

# MegaUp API Keys (Setting ထဲရှိ Key 1 နှင့် Key 2)
MEGAUP_KEY_1 = os.getenv("MEGAUP_KEY_1", "")
MEGAUP_KEY_2 = os.getenv("MEGAUP_KEY_2", "")
MEGAUP_BASE_URL = os.getenv("MEGAUP_BASE_URL", "https://megaup.net/api")

# Folder ID (ပုံထဲရှိ "Hi-Res Music" ကဲ့သို့ သီးသန့် folder ရှိပါက ထည့်နိုင်သည်)
MEGAUP_FOLDER_NAME = os.getenv("MEGAUP_FOLDER_NAME", "Hi-Res Music")

# System & Resource Tuning
CHUNK_SIZE_MB = int(os.getenv("CHUNK_SIZE_MB", "1900")) # 1.9 GB per part
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/app/downloads")
AUTO_SCAN_HOURS = os.getenv("AUTO_SCAN_HOURS", "9,21")
