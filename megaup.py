import os
import re
import json
import logging
import httpx
from typing import List, Dict, Optional
from config import MEGAUP_KEY_1, MEGAUP_KEY_2, MEGAUP_FOLDER_NAME

logger = logging.getLogger(__name__)

class MegaUpClient:
    def __init__(self):
        # YetiShare API v2 endpoint အမှန်
        self.api_base_url = "https://megaup.net/api/v2"
        self.site_url = "https://megaup.net"
        self.keys = [k for k in [MEGAUP_KEY_1, MEGAUP_KEY_2] if k]
        self.current_key_index = 0
        self.folder_name = MEGAUP_FOLDER_NAME or "Sync"
        self.session_cookie = os.getenv("MEGAUP_COOKIE", "")

    @property
    def current_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self.current_key_index]

    def switch_key(self):
        if len(self.keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.keys)
            logger.info(f"Switched to API Key {self.current_key_index + 1}")

    def get_headers(self) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        }
        if self.session_cookie:
            headers["Cookie"] = f"file_manager_session={self.session_cookie}; PHPSESSID={self.session_cookie}"
        return headers

    async def get_recent_completed_files(self) -> List[Dict]:
        """Sync folder နှင့် ၎င်းအောက်ရှိ files/folders များကို YetiShare API v2 ဖြင့် ရှာဖွေခြင်း"""
        for _ in range(len(self.keys) or 1):
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    # နည်းလမ်း ၁ - YetiShare API v2 POST method
                    if self.current_key:
                        logger.info(f"Scanning MegaUp root via API v2 for folder: '{self.folder_name}'...")
                        
                        # Root listing ရယူခြင်း
                        payload = {"access_token": self.current_key}
                        res = await client.post(f"{self.api_base_url}/folder/listing", data=payload)
                        
                        # POST မရပါက GET ဖြင့် စမ်းသပ်ခြင်း
                        if res.status_code == 404:
                            res = await client.get(f"{self.api_base_url}/folder/listing", params=payload)

                        logger.info(f"API v2 Response: Status {res.status_code}")

                        if res.status_code == 200:
                            json_data = res.json()
                            data = json_data.get("data") or json_data.get("children") or []
                            
                            target_folder_id = None
                            # Sync folder ကို ရှာဖွေခြင်း
                            for item in data:
                                if item.get("folder_name", item.get("name", "")).strip().lower() == self.folder_name.lower():
                                    target_folder_id = item.get("folder_id", item.get("id"))
                                    break

                            # Sync folder တွေ့ပါက ၎င်းအတွင်းပိုင်းကို ဆက်လက်ခေါ်ယူခြင်း
                            folder_payload = {"access_token": self.current_key}
                            if target_folder_id:
                                folder_payload["parent_folder_id"] = target_folder_id
                                logger.info(f"Accessing folder '{self.folder_name}' (ID: {target_folder_id})")

                            f_res = await client.post(f"{self.api_base_url}/folder/listing", data=folder_payload)
                            if f_res.status_code == 200:
                                files_data = f_res.json().get("data") or f_res.json().get("children") or []
                                valid_files = []
                                
                                for f in files_data:
                                    # Subfolder မဟုတ်ဘဲ ဖိုင်ဖြစ်ပါက ထည့်သွင်းခြင်း
                                    if not f.get("is_folder") and not f.get("is_dir"):
                                        f_name = f.get("filename") or f.get("name")
                                        f_id = f.get("file_id") or f.get("id")
                                        f_url = f.get("url") or f.get("download_url") or f.get("short_url")
                                        f_size = f.get("filesize") or f.get("size") or 0
                                        
                                        if f_name:
                                            valid_files.append({
                                                "id": str(f_id),
                                                "name": f_name,
                                                "album_name": self.folder_name,
                                                "size": int(f_size),
                                                "download_url": f_url
                                            })

                                if valid_files:
                                    logger.info(f"Found {len(valid_files)} files in '{self.folder_name}' via API v2.")
                                    return valid_files

                    # နည်းလမ်း ၂ - Web Dashboard Fallback (account_home.html)
                    logger.info("Using MegaUp dashboard web scraping fallback...")
                    dash_res = await client.get(f"{self.site_url}/account_home.html")
                    if dash_res.status_code == 200:
                        # megaup.net file links extract လုပ်ခြင်း
                        matches = re.findall(r'href="(https://megaup\.net/([a-zA-Z0-9]+)/([^"]+))"', dash_res.text)
                        if matches:
                            files = []
                            for full_url, fid, fname in matches:
                                files.append({
                                    "id": fid,
                                    "name": fname,
                                    "album_name": self.folder_name,
                                    "size": 0,
                                    "download_url": full_url
                                })
                            logger.info(f"Found {len(files)} files via web dashboard scraping.")
                            return files

                except Exception as e:
                    logger.error(f"MegaUp fetch error: {e}")
                    self.switch_key()

        return []

    async def get_download_stream_url(self, file_info: Dict) -> Optional[str]:
        """ဖိုင်၏ Direct Download link ကို ရယူခြင်း"""
        file_url = file_info.get("download_url")
        file_id = file_info.get("id")

        if not file_url and file_id:
            file_url = f"{self.site_url}/{file_id}"

        # API v2 direct download တောင်းယူခြင်း
        if self.current_key and file_id:
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    payload = {
                        "access_token": self.current_key,
                        "file_id": file_id
                    }
                    res = await client.post(f"{self.api_base_url}/file/download", data=payload)
                    if res.status_code == 200:
                        dl_data = res.json()
                        dl_link = dl_data.get("download_url") or dl_data.get("url")
                        if dl_link:
                            return dl_link
                except Exception as e:
                    logger.debug(f"API direct download lookup failed: {e}")

        # Page download parser
        if file_url:
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    res = await client.get(file_url)
                    match = re.search(r'href="(https://download[0-9]*\.megaup\.net/[^"]+)"', res.text)
                    if match:
                        return match.group(1)
                except Exception as e:
                    logger.error(f"Error parsing download page: {e}")

        return file_url
