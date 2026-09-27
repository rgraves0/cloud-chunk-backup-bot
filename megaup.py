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
            headers["Cookie"] = self.session_cookie
        return headers

    async def get_recent_completed_files(self) -> List[Dict]:
        """MegaUp API v2 response မှ folder နှင့် file များကို တိကျစွာ ခွဲထုတ်ခြင်း"""
        for _ in range(len(self.keys) or 1):
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    if self.current_key:
                        logger.info(f"Scanning MegaUp root via API v2 for folder: '{self.folder_name}'...")
                        
                        # Payload တွင် access_token ရော api_key ရော ထည့်သွင်းခြင်း
                        payload = {
                            "access_token": self.current_key,
                            "api_key": self.current_key
                        }
                        res = await client.post(f"{self.api_base_url}/folder/listing", data=payload)
                        if res.status_code != 200:
                            res = await client.get(f"{self.api_base_url}/folder/listing", params=payload)

                        if res.status_code == 200:
                            try:
                                json_data = res.json()
                                # Terminal log တွင် JSON ပုံစံ အမှန်ကို ဖတ်ရှုနိုင်ရန် log ထုတ်ခြင်း
                                logger.info(f"RAW API JSON RESPONSE: {json.dumps(json_data)[:400]}")
                            except Exception:
                                json_data = {}

                            # YetiShare API Keys အားလုံးကို ရှာဖွေခြင်း
                            items = (
                                json_data.get("data")
                                or json_data.get("children")
                                or json_data.get("result")
                                or json_data.get("files")
                                or json_data.get("folders")
                                or []
                            )
                            if isinstance(items, dict):
                                items = items.get("files", []) + items.get("folders", [])

                            target_folder_id = None
                            for item in items:
                                name = str(item.get("folder_name") or item.get("name") or "").strip()
                                if name.lower() == self.folder_name.lower():
                                    target_folder_id = item.get("folder_id") or item.get("id")
                                    logger.info(f"Target folder '{self.folder_name}' matched! ID: {target_folder_id}")
                                    break

                            # Sync Folder ID တွေ့ပါက ၎င်းအောက်ရှိ item များကို ဆက်ဆွဲယူခြင်း
                            folder_payload = {
                                "access_token": self.current_key,
                                "api_key": self.current_key,
                                "folder_id": target_folder_id or "0",
                                "parent_folder_id": target_folder_id or "0"
                            }
                            f_res = await client.post(f"{self.api_base_url}/folder/listing", data=folder_payload)
                            
                            valid_files = []
                            if f_res.status_code == 200:
                                try:
                                    f_json = f_res.json()
                                    logger.info(f"SYNC FOLDER RAW JSON: {json.dumps(f_json)[:400]}")
                                    f_items = (
                                        f_json.get("data")
                                        or f_json.get("children")
                                        or f_json.get("result")
                                        or f_json.get("files")
                                        or []
                                    )
                                    if isinstance(f_items, dict):
                                        f_items = f_items.get("files", [])
                                except Exception:
                                    f_items = []

                                for f in f_items:
                                    is_dir = f.get("is_folder") or f.get("is_dir") or f.get("type") == "folder"
                                    if not is_dir:
                                        f_name = f.get("filename") or f.get("name") or f.get("original_filename")
                                        f_id = f.get("file_id") or f.get("id")
                                        f_url = f.get("url") or f.get("download_url") or f.get("short_url")
                                        f_size = f.get("filesize") or f.get("size") or 0
                                        
                                        if f_name:
                                            valid_files.append({
                                                "id": str(f_id or f_name),
                                                "name": f_name,
                                                "album_name": self.folder_name,
                                                "size": int(f_size),
                                                "download_url": f_url
                                            })

                                if valid_files:
                                    logger.info(f"Found {len(valid_files)} files in '{self.folder_name}' via API v2.")
                                    return valid_files

                    # Fallback (HTML Account Scraping)
                    logger.info("Using MegaUp dashboard web scraping fallback...")
                    dash_res = await client.get(f"{self.site_url}/account_home.html")
                    if dash_res.status_code == 200:
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
                            logger.info(f"Found {len(files)} files via scraping.")
                            return files

                except Exception as e:
                    logger.error(f"MegaUp fetch error: {e}")
                    self.switch_key()

        return []

    async def get_download_stream_url(self, file_info: Dict) -> Optional[str]:
        """Direct Download link ရယူခြင်း"""
        file_url = file_info.get("download_url")
        file_id = file_info.get("id")

        if not file_url and file_id:
            file_url = f"{self.site_url}/{file_id}"

        if self.current_key and file_id:
            async with httpx.AsyncClient(headers=self.get_headers(), timeout=30.0, follow_redirects=True) as client:
                try:
                    payload = {
                        "access_token": self.current_key,
                        "api_key": self.current_key,
                        "file_id": file_id
                    }
                    res = await client.post(f"{self.api_base_url}/file/download", data=payload)
                    if res.status_code == 200:
                        dl_data = res.json()
                        dl_link = dl_data.get("download_url") or dl_data.get("url") or dl_data.get("data", {}).get("url")
                        if dl_link:
                            return dl_link
                except Exception as e:
                    logger.debug(f"API direct download lookup failed: {e}")

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
