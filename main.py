import os
import time
import asyncio
import logging
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, AUTO_SCAN_HOURS, TARGET_CHANNEL_ID
from megaup import MegaUpClient
from file_manager import FileManager
from telegram_uploader import TelegramUploader
from ui_helper import make_progress_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Client(
    "megaup_v2_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

megaup_client = MegaUpClient()
file_manager = FileManager()
uploader = TelegramUploader(bot)
scheduler = AsyncIOScheduler()

TASK_LOCK = asyncio.Lock()
PROCESSED_FILE_IDS = set()


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    sender_id = message.from_user.id if message.from_user else 0
    logger.info(f"Incoming /start from User ID: {sender_id}")

    if ADMIN_ID and int(sender_id) != int(ADMIN_ID):
        await message.reply_text(
            f"⛔ **Access Denied!**\n\nYour Telegram ID: `{sender_id}`\nConfigured ADMIN_ID: `{ADMIN_ID}`"
        )
        return

    text = (
        "🤖 **MegaUp to Telegram Backup Engine (2026 Ready)**\n\n"
        "စနစ်သည် အဆင်သင့်ဖြစ်နေပါပြီ။ Auto Scan စနစ် (တစ်ရက် ၂ ကြိမ်) အလိုအလျောက် လည်ပတ်နေပါသည်။\n\n"
        "📌 **အသုံးပြုနိုင်သော Commands များ:**\n"
        "• `/sync` — MegaUp မှ အသစ်တင်ထားသော ဖိုင်များကို ချက်ချင်း စတင် backup လုပ်မည်။\n"
        "• `/stats` — Host Server ၏ CPU, RAM, Disk နှင့် Uptime စစ်ဆေးမည်။"
    )
    await message.reply_text(text)


@bot.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    sender_id = message.from_user.id if message.from_user else 0
    if ADMIN_ID and int(sender_id) != int(ADMIN_ID):
        return

    stats_text = make_progress_text(
        file_name="System Idle",
        user_name=message.from_user.first_name,
        user_id=message.from_user.id,
        current=0,
        total=1,
        speed=0,
        elapsed=0,
        status="Idle / Monitoring"
    )
    await message.reply_text(stats_text)


@bot.on_message(filters.command("sync") & filters.private)
async def sync_handler(client: Client, message: Message):
    sender_id = message.from_user.id if message.from_user else 0
    if ADMIN_ID and int(sender_id) != int(ADMIN_ID):
        return

    if TASK_LOCK.locked():
        await message.reply_text("⚠️ Task တစ်ခု လုပ်ဆောင်နေဆဲဖြစ်ပါသည်။ ခေတ္တစောင့်ဆိုင်းပေးပါ။")
        return

    status_msg = await message.reply_text("🔍 MegaUp မှ ဖိုင်များကို စစ်ဆေးနေပါသည်...")
    asyncio.create_task(run_backup_pipeline(status_msg, message.from_user))


async def run_backup_pipeline(status_msg: Message = None, user=None):
    if TASK_LOCK.locked():
        logger.info("A backup pipeline is already running. Skipping trigger.")
        return

    async with TASK_LOCK:
        try:
            if status_msg:
                await status_msg.edit_text("🔍 MegaUp ဖိုင်စာရင်း ရယူနေပါသည်...")

            files = await megaup_client.get_recent_completed_files()
            if not files:
                if status_msg:
                    await status_msg.edit_text("ℹ️ Upload ပြီးစီးသော ဖိုင်အသစ် မရှိသေးပါ။")
                return

            pending_files = [f for f in files if f["id"] not in PROCESSED_FILE_IDS]
            if not pending_files:
                if status_msg:
                    await status_msg.edit_text("✅ ဖိုင်အားလုံး Backup လုပ်ဆောင်ပြီးဖြစ်ပါသည်။")
                return

            u_name = user.first_name if user else "AutoScheduler"
            u_id = user.id if user else 0

            for idx, file_info in enumerate(pending_files, start=1):
                f_id = file_info["id"]
                f_name = file_info["name"]
                task_dir = file_manager.get_task_dir(f_id)
                dest_path = task_dir / f_name

                try:
                    if status_msg:
                        await status_msg.edit_text(f"⏳ **[{idx}/{len(pending_files)}]** `{f_name}` အတွက် Direct Link ရယူနေပါသည်...")

                    download_url = await megaup_client.get_download_stream_url(file_info)
                    if not download_url:
                        logger.error(f"Could not get direct link for: {f_name}")
                        continue

                    async def dl_progress(current, total, speed, elapsed, status):
                        if status_msg:
                            p_text = make_progress_text(
                                file_name=f"[{idx}/{len(pending_files)}] {f_name}",
                                user_name=u_name,
                                user_id=u_id,
                                current=current,
                                total=total,
                                speed=speed,
                                elapsed=elapsed,
                                status=status,
                                engine="HTTPX Async",
                                in_mode="MegaUp",
                                out_mode="Local Disk"
                            )
                            try:
                                await status_msg.edit_text(p_text)
                            except Exception:
                                pass

                    dl_success = await file_manager.download_file(download_url, dest_path, progress_callback=dl_progress)
                    if not dl_success:
                        logger.error(f"Download failed for: {f_name}")
                        continue

                    if status_msg:
                        await status_msg.edit_text(f"✂️ `{f_name}` အား လိုအပ်ပါက အပိုင်းခွဲထုတ်နေပါသည် (7z)...")

                    parts, is_split = file_manager.split_file_if_needed(dest_path)

                    user_data = {"name": u_name, "id": u_id}
                    up_success = await uploader.upload_parts_and_post_summary(
                        album_name=f_name,
                        part_paths=parts,
                        is_split=is_split,
                        status_message=status_msg,
                        user_info=user_data
                    )

                    if up_success:
                        PROCESSED_FILE_IDS.add(f_id)

                except Exception as task_err:
                    logger.exception(f"Error during task {f_name}: {task_err}")
                finally:
                    file_manager.cleanup_task_dir(task_dir)

            if status_msg:
                await status_msg.edit_text("🎉 **Batch Backup ပြီးဆုံးပါပြီ။**")

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            if status_msg:
                await status_msg.edit_text(f"❌ Error: {e}")


async def scheduled_scan_job():
    logger.info("Executing scheduled Auto-Scan job...")
    await run_backup_pipeline()


async def startup_routine():
    """Bot စတင်တက်ချိန် background scheduler ကို configure လုပ်ခြင်း"""
    await asyncio.sleep(2)
    me = await bot.get_me()
    logger.info(f"Bot connected: @{me.username} (ID: {me.id})")

    hours = AUTO_SCAN_HOURS.split(",")
    for h in hours:
        if h.strip().isdigit():
            scheduler.add_job(scheduled_scan_job, "cron", hour=int(h.strip()), minute=0)

    scheduler.start()
    logger.info(f"Scheduler active for hours: {AUTO_SCAN_HOURS}")

    if ADMIN_ID:
        try:
            await bot.send_message(
                chat_id=int(ADMIN_ID),
                text="🟢 **Bot Online!**\n\nCommand များ စတင်အသုံးပြုနိုင်ပါပြီ:\n• `/sync`\n• `/stats`"
            )
            logger.info("Startup notification delivered to Admin.")
        except Exception as e:
            logger.error(f"Cannot deliver message to ADMIN_ID {ADMIN_ID}: {e}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(startup_routine())
    logger.info("Starting Pyrogram bot engine...")
    bot.run()
