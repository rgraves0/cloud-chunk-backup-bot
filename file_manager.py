import os
import time
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple, Callable, Optional
import httpx
from config import CHUNK_SIZE_MB, DOWNLOAD_DIR

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, base_dir: str = DOWNLOAD_DIR, chunk_size_mb: int = CHUNK_SIZE_MB):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size_mb = chunk_size_mb
        self.chunk_size_bytes = chunk_size_mb * 1024 * 1024

    def get_task_dir(self, task_id: str) -> Path:
        """Task တစ်ခုချင်းစီအတွက် သီးခြား temporary folder ဖန်တီးခြင်း"""
        task_path = self.base_dir / f"task_{task_id}"
        task_path.mkdir(parents=True, exist_ok=True)
        return task_path

    async def download_file(
        self,
        url: str,
        dest_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """ဖိုင်ကို Stream ဆွဲယူပြီး Progress Bar callback သို့ အချိန်နှင့်တစ်ပြေးညီ ပို့ပေးခြင်း"""
        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.error(f"Download failed with HTTP status: {response.status_code}")
                        return False

                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    start_time = time.time()
                    last_update = 0.0

                    with open(dest_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024): # 1MB chunks
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            # Telegram flood wait ကာကွယ်ရန် 3.5 စက္ကန့်ခြားမှ UI callback ပေးပို့ခြင်း
                            if progress_callback and (now - last_update > 3.5 or downloaded == total_size):
                                elapsed = now - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                try:
                                    await progress_callback(downloaded, total_size, speed, elapsed, "Download")
                                except Exception as cb_err:
                                    logger.debug(f"Progress callback error: {cb_err}")
                                last_update = now

            return True
        except Exception as e:
            logger.error(f"Error downloading file from {url}: {e}")
            return False

    def split_file_if_needed(self, file_path: Path) -> Tuple[List[Path], bool]:
        """
        ဖိုင်ဆိုဒ် 1.9GB ထက် ကြီးပါက 7z ဖြင့် အပိုင်းခွဲထုတ်ခြင်း။
        ခွဲထုတ်ပြီးပါက မူရင်းဖိုင်ကြီးကို ချက်ချင်း ဖျက်ပစ်ပြီး နေရာချွေတာသည်။
        """
        if not file_path.exists():
            return [], False

        file_size = file_path.stat().st_size
        if file_size <= self.chunk_size_bytes:
            return [file_path], False

        logger.info(f"File size {file_size / (1024**3):.2f} GB exceeds chunk limit. Splitting via 7z...")
        archive_name = f"{file_path.stem}_archive.7z"
        output_archive_path = file_path.parent / archive_name

        # 7z split command: 1900m စီ ခွဲထုတ်ခြင်း (-mx0 store mode ဖြင့် CPU ဝန်မပိစေဘဲ အမြန်ခွဲထုတ်ခြင်း)
        cmd = [
            "7z", "a",
            f"-v{self.chunk_size_mb}m",
            "-mx0",
            str(output_archive_path),
            str(file_path)
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logger.error(f"7z split execution failed: {result.stderr}")
            return [file_path], False

        # အပိုင်းခွဲပြီးပါက မူရင်းဖိုင်ကြီးကို ချက်ချင်းဖျက်၍ Disk space ရှင်းလင်းခြင်း
        file_path.unlink(missing_ok=True)

        # ထွက်လာသော အပိုင်းများကို စာရင်းထုတ်ယူခြင်း (.7z.001, .7z.002, ...)
        parts = sorted(list(file_path.parent.glob(f"{file_path.stem}_archive.7z.*")))
        if not parts and output_archive_path.exists():
            parts = [output_archive_path]

        return parts, True

    def cleanup_task_dir(self, task_dir: Path):
        """Task တစ်ခု ပြီးဆုံးတိုင်း Disk ပေါ်ရှိ Working Directory ကို အမြစ်ပြတ်ဖျက်ထုတ်ခြင်း"""
        try:
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
                logger.info(f"Cleaned up working directory: {task_dir}")
        except Exception as e:
            logger.error(f"Directory cleanup failed for {task_dir}: {e}")
