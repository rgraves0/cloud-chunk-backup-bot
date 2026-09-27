import os
import time
import asyncio
import logging
import traceback
from pathlib import Path
from pyrogram import Client, filters, idle
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, AUTO_SCAN_HOURS, TARGET_CHANNEL_ID
from megaup import MegaUpClient
from file_manager import FileManager
from telegram_uploader import TelegramUploader
from ui_helper import make_progress_text

logging.basicConfig(
    level=logging.DEBUG, # DEBUG level သို့ တင်ထားသည်
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Client(
    "megaup_backup_session",
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


def get_control_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Sync Now", callback_data="manual_sync")],
        [InlineKeyboardButton("📊 Server Stats", callback_data="server_stats")]
    ])


# 1. RAW HANDLER: ဝင်လာသမျှ Telegram Update အားလုံးကို ဖမ်းယူ Log ထုတ်ပေးခြင်း
@bot.on_raw_update()
async def raw_update_logger(client: Client, update, users, chats):
    logger.debug(f"[RAW UPDATE RECEIVED]: Type={type(update).__name__} | Update={update}")


# 2. MESSAGE HANDLER: မက်ဆေ့ခ်ျအားလုံးကို Debug Log မှတ်ပြီး /start စစ်ဆေးခြင်း
@bot.on_message()
async def global_message_handler(client: Client, message: Message):
    try:
        sender_id = message.from_user.id if message.from_user else 0
        sender_name = message.from_user.first_name if message.from_user else "Unknown"
        text = message.text or ""
        
        logger.info(f"[INCOMING MSG] User: {sender_name} (ID: {sender_id}) | Chat: {message.chat.id} | Text: '{text}'")

        if text.startswith("/start"):
            logger.info(f"Processing /start command from {sender_id}. Checking against ADMIN_ID={ADMIN_ID}")
            
            # Admin ID စစ်ဆေးခြင်း
            if ADMIN_ID and int(sender_id) != int(ADMIN_ID):
                logger.warning(f"Unauthorized access attempt by ID: {sender_id}")
                await message.reply_text(
                    f"⛔ **Access Denied!**\n\nYour Telegram ID: `{sender_id}`\nConfigured ADMIN_ID: `{ADMIN_ID}`"
                )
                return

            welcome_text = (
                "🤖 **MegaUp to Telegram Backup Engine (2026 Ready)**\n\n"
                "စနစ်သည် အဆင်သင့်ဖြစ်နေပါပြီ။ Auto Scan စနစ် (တစ်ရက် ၂ ကြိမ်) အပြင် "
                "အောက်ပါခလုတ်ကို နှိပ်၍လည်း အချိန်မရွေး Sync စတင်နိုင်ပါသည်။"
            )
            await message.reply_text(welcome_text, reply_markup=get_control_keyboard())
            logger.info("Successfully sent welcome reply to admin.")

    except Exception as e:
        logger.error(f"Error inside global_message_handler: {e}\n{traceback.format_exc()}")


@bot.on_callback_query()
async def global_callback_handler(client: Client, query: CallbackQuery):
    try:
        sender_id = query.from_user.id if query.from_user else 0
        data = query.data or ""
        logger.info(f"[CALLBACK RECEIVED] User ID: {sender_id} | Data: '{data}'")

        if ADMIN_ID and int(sender_id) != int(ADMIN_ID):
            await query.answer("⛔ Access Denied", show_alert=True)
            return

        if data == "server_stats":
            stats_text = make_progress_text(
                file_name="System Idle",
                user_name=query.from_user.first_name,
                user_id=query.from_user.id,
                current=0,
                total=1,
                speed=0,
                elapsed=0,
                status="Idle / Monitoring"
            )
            await query.message.edit_text(stats_text, reply_markup=get_control_keyboard())
            await query.answer()

        elif data == "manual_sync":
            if TASK_LOCK.locked():
                await query.answer("⚠️ Task တစ်ခု လုပ်ဆောင်နေဆဲဖြစ်ပါသည်။ ခေတ္တစောင့်ပါ။", show_alert=True)
                return

            await query.answer("🚀 Sync စတင်နေပါပြီ...")
            status_msg = await query.message.reply_text("🔍 MegaUp မှ ဖိုင်များကို စစ်ဆေးနေပါသည်...")
            asyncio.create_task(run_backup_pipeline(status_msg, query.from_user))

    except Exception as e:
        logger.error(f"Error inside global_callback_handler: {e}\n{traceback.format_exc()}")


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
                await status_msg.edit_text("🎉 **Batch Backup ပြီးဆုံးပါပြီ။**", reply_markup=get_control_keyboard())

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            if status_msg:
                await status_msg.edit_text(f"❌ Error: {e}", reply_markup=get_control_keyboard())


async def scheduled_scan_job():
    logger.info("Executing scheduled Auto-Scan job...")
    await run_backup_pipeline()


async def main():
    async with bot:
        me = await bot.get_me()
        logger.info(f"Bot connected: @{me.username} (ID: {me.id})")

        # Admin ထံသို့ စမ်းသပ်မက်ဆေ့ခ်ျ ပို့ကြည့်ခြင်း
        if ADMIN_ID:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text="🟢 **Bot Online!** Debug mode is active. Send `/start` now.",
                    reply_markup=get_control_keyboard()
                )
                logger.info(f"Startup ping message sent successfully to ADMIN_ID: {ADMIN_ID}")
            except Exception as e:
                logger.error(f"Failed to send startup message to ADMIN_ID ({ADMIN_ID}): {e}")

        # Scheduler စတင်ခြင်း
        hours = AUTO_SCAN_HOURS.split(",")
        for h in hours:
            if h.strip().isdigit():
                scheduler.add_job(scheduled_scan_job, "cron", hour=int(h.strip()), minute=0)

        scheduler.start()
        logger.info(f"Scheduler active for hours: {AUTO_SCAN_HOURS}")

        # Dispatcher loop စောင့်ဆိုင်းခြင်း
        await idle()


if __name__ == "__main__":
    asyncio.run(main())
