import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict
from pyrogram import Client
from pyrogram.errors import FloodWait
from config import TARGET_CHANNEL_ID

logger = logging.getLogger(__name__)

class TelegramUploader:
    def __init__(self, bot_client: Client, channel_id: int = TARGET_CHANNEL_ID):
        self.bot = bot_client
        self.channel_id = channel_id

    async def upload_parts_and_post_summary(self, album_name: str, part_paths: List[Path], is_split: bool) -> bool:
        """
        ဖိုင်အပိုင်းများကို Channel သို့ silent upload တင်ပြီး Master Summary Post ထုတ်ပေးခြင်း
        """
        uploaded_records = []
        total_parts = len(part_paths)

        for index, path in enumerate(part_paths, start=1):
            file_name = path.name
            size_mb = path.stat().st_size / (1024 * 1024)
            size_label = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.1f} MB"
            
            caption = f"📦 `{file_name}` ({size_label})"
            success = False

            # FloodWait retry logic
            while not success:
                try:
                    logger.info(f"Uploading part {index}/{total_parts}: {file_name}")
                    sent_msg = await self.bot.send_document(
                        chat_id=self.channel_id,
                        document=str(path),
                        caption=caption,
                        disable_notification=True
                    )
                    
                    # Channel message link တည်ဆောက်ခြင်း
                    chat_id_str = str(self.channel_id).replace("-100", "")
                    msg_link = f"https://t.me/c/{chat_id_str}/{sent_msg.id}"
                    
                    uploaded_records.append({
                        "index": index,
                        "filename": file_name,
                        "size_label": size_label,
                        "link": msg_link
                    })
                    success = True

                    # တင်ပြီးသော အပိုင်းကို Local Disk ပေါ်မှ ချက်ချင်း ရှင်းထုတ်ခြင်း
                    path.unlink(missing_ok=True)
                    await asyncio.sleep(2) # Telegram API flood ကာကွယ်ရန် ယာယီ pause

                except FloodWait as e:
                    logger.warning(f"Telegram FloodWait hit. Sleeping for {e.value} seconds...")
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    logger.error(f"Failed to upload {file_name}: {e}")
                    return False

        # အားလုံးပြီးပါက Master Summary Post ထုတ်ပေးခြင်း
        await self.send_master_post(album_name, uploaded_records, is_split)
        return True

    async def send_master_post(self, album_name: str, records: List[Dict], is_split: bool):
        """Channel ထဲသို့ အပြည့်အစုံ ပါဝင်သော Master Summary Post တင်ပေးခြင်း"""
        try:
            if not is_split and len(records) == 1:
                item = records[0]
                post_text = (
                    f"📁 **Album:** `{album_name}`\n\n"
                    f"✅ `{item['filename']}` ({item['size_label']})\n"
                    f"🔗 {item['link']}"
                )
            else:
                lines = [f"📁 **Album:** `{album_name}` (Total Parts: {len(records)})\n"]
                for r in records:
                    lines.append(f"✅ Part {r['index']:02d} ({r['size_label']})\n🔗 {r['link']}\n")
                post_text = "\n".join(lines)

            # စာသားရှည်ပါက အပိုင်းလိုက် ခွဲပို့ခြင်း
            if len(post_text) > 4000:
                chunks = [post_text[i:i + 4000] for i in range(0, len(post_text), 4000)]
                for ch in chunks:
                    await self.bot.send_message(chat_id=self.channel_id, text=ch)
            else:
                await self.bot.send_message(chat_id=self.channel_id, text=post_text)
                
            logger.info(f"Master summary post created for: {album_name}")
        except Exception as e:
            logger.error(f"Failed to send master summary post: {e}")
