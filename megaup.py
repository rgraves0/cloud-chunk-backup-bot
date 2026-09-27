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
        # S အကြီးဖြင့် Sync သတ်မှတ်ခြင်း သို့မဟုတ် .env တန်ဖိုးကို ယူခြင်း
        self.folder_name = MEGAUP_FOLDER_NAME or "Sync"
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
        """Sync folder နှင့် ၎င်းအောက်ရှိ Subfolder/Album များထဲမှ ဖိုင်များကို ရှာဖွေထုတ်ယူခြင်း"""
        for _ in range(len(self.keys) or 1):
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    if self.current_key:
                        # 1. ပထမဆုံး Folder အမည် (Sync) ဖြင့် စစ်ဆေးခြင်း
                        params = {"folder": self.folder_name}
                        res = await client.get(f"{self.base_url}/files", params=params)
                        logger.info(f"Checking MegaUp API for folder '{self.folder_name}' | Status: {res.status_code}")

                        if res.status_code == 200:
                            json_res = res.json()
                            raw_items = json_res.get("data") or json_res.get("files") or json_res.get("result") or []
                            
                            valid_files = []
                            for item in raw_items:
                                # Subfolder ဖြစ်ပါက ထို Subfolder (Album) အောက်သို့ ဆက်လက်ဝင်ရောက်ရှာဖွေခြင်း
                                if item.get("is_dir") or item.get("type") == "folder":
                                    sub_folder_id = item.get("id")
                                    sub_folder_name = item.get("name")
                                    logger.info(f"Found Album Folder: {sub_folder_name} (ID: {sub_folder_id}). Scanning contents...")
                                    
                                    sub_res = await client.get(f"{self.base_url}/files", params={"folder_id": sub_folder_id})
                                    if sub_res.status_code == 200:
                                        sub_items = sub_res.json().get("data") or sub_res.json().get("files") or []
                                        for s_item in sub_items:
                                            f_status = str(s_item.get("status", "")).lower()
                                            f_size = s_item.get("size", 0)
                                            if f_status in ("completed", "ready", "active", "") and int(f_size) > 0:
                                                valid_files.append({
                                                    "id": str(s_item.get("id")),
                                                    "name": s_item.get("name"),
                                                    "album_name": sub_folder_name, # Album အမည်တွဲယူခြင်း
                                                    "size": int(f_size),
                                                    "download_url": s_item.get("download_url")
                                                })
                                    continue

                                # Sync folder ထဲတွင် တိုက်ရိုက်ရှိနေသော ဖိုင်များ
                                status = str(item.get("status", "")).lower()
                                size = item.get("size", 0)
                                if status in ("completed", "ready", "active", "") and int(size) > 0:
                                    valid_files.append({
                                        "id": str(item.get("id")),
                                        "name": item.get("name"),
                                        "album_name": self.folder_name,
                                        "size": int(size),
                                        "download_url": item.get("download_url")
                                    })
                            
                            logger.info(f"Total valid files found to sync: {len(valid_files)}")
                            return valid_files

                        elif res.status_code in (401, 429):
                            self.switch_key()
                            continue

                    # Fallback (User Dashboard Parsing)
                    logger.info("Using MegaUp dashboard fallback parser...")
                    res = await client.get("https://megaup.net/user/files")
                    if res.status_code == 200:
                        matches = re.findall(r'href="(https://megaup\.net/([a-zA-Z0-9]+)/([^"]+))"', res.text)
                        files = []
                        for full_url, fid, fname in matches:
                            files.append({
                                "id": fid,
                                "name": fname,
                                "album_name": self.folder_name,
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
