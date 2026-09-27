import os
import re
import logging
import httpx
from typing import List, Dict, Optional
from config import MEGAUP_KEY_1, MEGAUP_KEY_2, MEGAUP_BASE_URL, MEGAUP_FOLDER_NAME

logger = logging.getLogger(__name__)

class MegaUpClient:
    def __init__(self, base_url: str = MEGAUP_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.keys = [k for k in [MEGAUP_KEY_1, MEGAUP_KEY_2] if k]
        self.current_key_index = 0
        self.folder_name = MEGAUP_FOLDER_NAME
        self.session_cookie = os.getenv("MEGAUP_COOKIE", "")

    @property
    def current_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self.current_key_index]

    def switch_key(self):
        """Key 1 မှ Key 2 သို့ (သို့မဟုတ် ပြောင်းပြန်) လဲလှယ်ခြင်း"""
        if len(self.keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.keys)
            logger.info(f"Switched to API Key {self.current_key_index + 1}")

    def get_headers(self) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        if self.current_key:
            headers["Authorization"] = f"Bearer {self.current_key}"
        elif self.session_cookie:
            headers["Cookie"] = f"session={self.session_cookie}"
        return headers

    async def get_recent_completed_files(self) -> List[Dict]:
        """ပြီးစီးပြီးသား ဖိုင်များကို စစ်ဆေးထုတ်ယူခြင်း"""
        for _ in range(len(self.keys) or 1):
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    if self.current_key:
                        params = {}
                        if self.folder_name:
                            params["folder"] = self.folder_name
                            
                        res = await client.get(f"{self.base_url}/files", params=params)
                        if res.status_code == 200:
                            data = res.json().get("data", [])
                            valid_files = []
                            for item in data:
                                status = item.get("status", "").lower()
                                size = item.get("size", 0)
                                if status in ("completed", "ready", "active", "") and size > 0:
                                    valid_files.append({
                                        "id": str(item.get("id")),
                                        "name": item.get("name"),
                                        "size": int(size),
                                        "download_url": item.get("download_url")
                                    })
                            return valid_files
                        elif res.status_code in (401, 429):
                            self.switch_key()
                            continue

                    # Fallback (Cookie သို့မဟုတ် Free parsing)
                    logger.info("Using MegaUp fallback file parser...")
                    res = await client.get("https://megaup.net/user/files")
                    if res.status_code == 200:
                        matches = re.findall(r'href="(https://megaup\.net/([a-zA-Z0-9]+)/([^"]+))"', res.text)
                        files = []
                        for full_url, fid, fname in matches:
                            files.append({
                                "id": fid,
                                "name": fname,
                                "size": 0,
                                "download_url": full_url
                            })
                        return files
                except Exception as e:
                    logger.error(f"MegaUp fetch error: {e}")
                    self.switch_key()
        return []

    async def get_download_stream_url(self, file_info: Dict) -> Optional[str]:
        """ဖိုင်၏ Direct Download URL ကို ရယူခြင်း"""
        if file_info.get("download_url") and "download" in file_info["download_url"]:
            return file_info["download_url"]

        file_id = file_info["id"]
        for _ in range(len(self.keys) or 1):
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    if self.current_key:
                        res = await client.get(f"{self.base_url}/file/{file_id}/download")
                        if res.status_code == 200:
                            return res.json().get("download_url")
                        elif res.status_code in (401, 429):
                            self.switch_key()
                            continue

                    raw_url = file_info.get("download_url", f"https://megaup.net/{file_id}")
                    res = await client.get(raw_url)
                    direct_match = re.search(r'href="(https://download[0-9]*\.megaup\.net/[^"]+)"', res.text)
                    if direct_match:
                        return direct_match.group(1)
                except Exception as e:
                    logger.error(f"Error getting download link for {file_id}: {e}")
                    self.switch_key()
        return None
