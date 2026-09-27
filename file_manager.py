import os
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple
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

    async def download_file(self, url: str, dest_path: Path) -> bool:
        """ဖိုင်ကို Memory မပြည့်စေဘဲ Stream ပုံစံဖြင့် Disk ပေါ်သို့ Download ဆွဲခြင်း"""
        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.error(f"Download failed with status: {response.status_code}")
                        return False
                    
                    with open(dest_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024): # 1MB buffer
                            f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return False

    def split_file_if_needed(self, file_path: Path) -> Tuple[List[Path], bool]:
        """
        ဖိုင်ဆိုဒ် 1.9GB ထက် ကြီးပါက 7z ဖြင့် အပိုင်းခွဲထုတ်ခြင်း။
        ခွဲပြီးပါက မူရင်းဖိုင်ကြီးကို ချက်ချင်း ဖျက်ထုတ်ပြီး Disk နေရာချွေတာသည်။
        """
        file_size = file_path.stat().st_size
        if file_size <= self.chunk_size_bytes:
            return [file_path], False

        logger.info(f"File size {file_size / (1024**3):.2f} GB exceeds chunk size. Splitting...")
        archive_name = f"{file_path.stem}_archive.7z"
        output_archive_path = file_path.parent / archive_name

        # 7z split command: 1900m စီ ခွဲထုတ်ခြင်း (Store mode - မချုံ့ဘဲ အမြန်ခွဲရန် -mx0)
        cmd = [
            "7z", "a",
            f"-v{self.chunk_size_mb}m",
            "-mx0",
            str(output_archive_path),
            str(file_path)
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logger.error(f"7z split error: {result.stderr}")
            return [file_path], False

        # မူရင်းဖိုင်ကြီးကို ချက်ချင်းဖျက်၍ Disk ရှင်းခြင်း
        file_path.unlink(missing_ok=True)

        # ထွက်လာသော အပိုင်းများကို စာရင်းထုတ်ယူခြင်း (.7z.001, .7z.002, ...)
        parts = sorted(list(file_path.parent.glob(f"{file_path.stem}_archive.7z.*")))
        if not parts and output_archive_path.exists():
            parts = [output_archive_path]

        return parts, True

    def cleanup_task_dir(self, task_dir: Path):
        """လုပ်ငန်းပြီးဆုံးသွားပါက Disk ပေါ်ရှိ Task Directory တစ်ခုလုံးကို အမြစ်ပြတ်ရှင်းလင်းခြင်း"""
        try:
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
                logger.info(f"Cleaned up directory: {task_dir}")
        except Exception as e:
            logger.error(f"Cleanup error for {task_dir}: {e}")
