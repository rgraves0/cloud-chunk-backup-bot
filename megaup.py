import json
import logging
import os
import re
from typing import Dict, List, Optional, Set
import httpx
from config import (
    MEGAUP_BASE_URL,
    MEGAUP_FOLDER_NAME,
    MEGAUP_KEY_1,
    MEGAUP_KEY_2,
)

logger = logging.getLogger(__name__)


class MegaUpClient:

    def __init__(self):
        # config.py ရှိ MEGAUP_BASE_URL ကို အသုံးပြုခြင်း (v2 endpoint အဖြစ် သတ်မှတ်ခြင်း)
        base = MEGAUP_BASE_URL.rstrip("/")
        self.api_base_url = (
            base if base.endswith("/v2") else f"{base}/v2"
        )  # e.g., https://megaup.net/api/v2
        self.site_url = "https://megaup.net"
        self.keys = [k for k in [MEGAUP_KEY_1, MEGAUP_KEY_2] if k]
        self.current_key_index = 0
        self.folder_name = MEGAUP_FOLDER_NAME or "Hi-Res Music"
        self.session_cookie = os.getenv("MEGAUP_COOKIE", "")

    @property
    def current_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self.current_key_index]

    def switch_key(self) -> bool:
        """Key တစ်ခုမှ နောက်တစ်ခုသို့ ကူးပြောင်းခြင်း (နောက်ဆုံး Key ဖြစ်ပါက False ပြန်မည်)"""
        if self.current_key_index + 1 < len(self.keys):
            self.current_key_index += 1
            logger.info(
                f"Switched to fallback API Key {self.current_key_index + 1}"
            )
            return True
        return False

    def get_headers(self) -> dict:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return headers

    async def _post_api(
        self, client: httpx.AsyncClient, endpoint: str, extra_data: dict = None
    ) -> Optional[dict]:
        """API Response status နှင့် internal JSON error များကို တိကျစွာ စစ်ဆေးခြင်း"""
        data = {
            "access_token": self.current_key,
            "api_key": self.current_key,
        }
        if extra_data:
            data.update(extra_data)

        try:
            res = await client.post(
                f"{self.api_base_url}/{endpoint}", data=data
            )
            if res.status_code == 200:
                json_res = res.json()
                # YetiShare API error status response များကို စစ်ဆေးခြင်း
                if (
                    json_res.get("error")
                    or json_res.get("_status") == "error"
                    or json_res.get("status") == "error"
                ):
                    logger.warning(
                        f"API Endpoint '{endpoint}' returned error status: {json_res}"
                    )
                    return None
                return json_res
            logger.warning(
                f"API Endpoint '{endpoint}' failed with HTTP {res.status_code}"
            )
        except Exception as e:
            logger.error(f"Network error on {endpoint}: {e}")
        return None

    def _extract_items(self, json_data: dict) -> tuple[list, list]:
        """JSON ထဲမှ Folder များနှင့် File များကို field အမည်ပေါင်းစုံဖြင့် ဆွဲထုတ်ခြင်း"""
        folders = []
        files = []

        raw_data = (
            json_data.get("data")
            or json_data.get("result")
            or json_data.get("children")
            or json_data
        )

        if isinstance(raw_data, dict):
            folders = (
                raw_data.get("folders")
                or raw_data.get("subfolders")
                or raw_data.get("children", [])
            )
            files = raw_data.get("files") or raw_data.get("file_list", [])
        elif isinstance(raw_data, list):
            for item in raw_data:
                is_dir = (
                    item.get("is_folder")
                    or item.get("is_dir")
                    or item.get("type") == "folder"
                    or ("folderName" in item)
                    or ("folder_name" in item)
                )
                if is_dir:
                    folders.append(item)
                else:
                    files.append(item)

        return (
            folders if isinstance(folders, list) else [],
            files if isinstance(files, list) else [],
        )

    async def _crawl_folder_recursive(
        self,
        client: httpx.AsyncClient,
        folder_id: str,
        current_path: str,
        visited_folders: Set[str],
    ) -> List[Dict]:
        """Folder နှင့် Sub-folder များကို recursive ဆင်း၍ ဖိုင်အားလုံး စာရင်းထုတ်ခြင်း"""
        collected_files = []
        if folder_id in visited_folders:
            return collected_files
        visited_folders.add(folder_id)

        # YetiShare API တွင် folder အောက်ရှိ items များကို တောင်းယူခြင်း
        payload = {
            "folder_id": folder_id,
            "parent_id": folder_id,
            "parent_folder_id": folder_id,
        }
        res_json = await self._post_api(client, "folder/listing", payload)
        if not res_json:
            res_json = await self._post_api(client, "file/listing", payload)

        if not res_json:
            return collected_files

        folders, files = self._extract_items(res_json)

        # 1. ဖိုင်များကို စာရင်းသွင်းခြင်း
        for f in files:
            f_name = (
                f.get("filename")
                or f.get("name")
                or f.get("original_filename")
                or f.get("title")
            )
            f_id = f.get("file_id") or f.get("id")
            f_url = (
                f.get("url")
                or f.get("download_url")
                or f.get("short_url")
                or f.get("link")
            )
            f_size = (
                f.get("filesize")
                or f.get("size")
                or f.get("file_size")
                or f.get("fileSize")
                or 0
            )

            if f_name:
                collected_files.append(
                    {
                        "id": str(f_id or f_name),
                        "name": f_name,
                        "album_name": current_path,
                        "size": int(f_size),
                        "download_url": f_url,
                    }
                )

        # 2. Sub-folders များထဲသို့ ဆက်လက် scan ဖတ်ခြင်း (Recursive scan)
        for sub in folders:
            sub_id = sub.get("id") or sub.get("folder_id") or sub.get("folderId")
            sub_name = (
                sub.get("folderName")
                or sub.get("folder_name")
                or sub.get("name")
                or sub.get("title")
            )
            if sub_id:
                sub_path = f"{current_path}/{sub_name}" if sub_name else current_path
                nested_files = await self._crawl_folder_recursive(
                    client, str(sub_id), sub_path, visited_folders
                )
                collected_files.extend(nested_files)

        return collected_files

    async def get_recent_completed_files(self) -> List[Dict]:
        """Key 1 -> Key 2 -> Cookie Fallback ဖြင့် အလုပ်လုပ်ဆောင်ခြင်း"""

        # ၁။ API KEY (Key 1 -> Key 2 Failover) ဖြင့် စစ်ဆေးခြင်း
        while self.current_key:
            logger.info(
                f"Checking MegaUp via API Key {self.current_key_index + 1} for"
                f" target: '{self.folder_name}'"
            )
            async with httpx.AsyncClient(
                headers=self.get_headers(), timeout=35.0, follow_redirects=True
            ) as client:
                root_res = await self._post_api(
                    client, "folder/listing", {"folder_id": "0"}
                )

                if root_res:
                    folders, root_files = self._extract_items(root_res)
                    target_folder_id = None
                    actual_folder_name = self.folder_name

                    # Root folders ထဲတွင် ပစ်မှတ် folder (Sync သို့မဟုတ် Hi-Res Music) ကို ရှာခြင်း
                    for f in folders:
                        name = str(
                            f.get("folderName")
                            or f.get("folder_name")
                            or f.get("name")
                            or f.get("title")
                            or ""
                        ).strip()
                        if name.lower() == self.folder_name.lower():
                            target_folder_id = str(
                                f.get("id")
                                or f.get("folder_id")
                                or f.get("folderId")
                            )
                            actual_folder_name = name
                            logger.info(
                                f"Match confirmed: '{name}' (ID:"
                                f" {target_folder_id})"
                            )
                            break

                    visited = set()
                    files_found = []

                    if target_folder_id:
                        # Target folder တွေ့ပါက ၎င်းအောက်ရှိ sub-folders နှင့် files အားလုံးကို Recursive ဆွဲယူခြင်း
                        files_found = await self._crawl_folder_recursive(
                            client,
                            target_folder_id,
                            actual_folder_name,
                            visited,
                        )
                    else:
                        logger.warning(
                            f"Folder '{self.folder_name}' not detected in root."
                            " Checking root files..."
                        )
                        for rf in root_files:
                            rf_name = rf.get("filename") or rf.get("name")
                            rf_id = rf.get("file_id") or rf.get("id")
                            if rf_name:
                                files_found.append(
                                    {
                                        "id": str(rf_id or rf_name),
                                        "name": rf_name,
                                        "album_name": "Root",
                                        "size": int(
                                            rf.get("filesize")
                                            or rf.get("size")
                                            or 0
                                        ),
                                        "download_url": rf.get("url")
                                        or rf.get("download_url"),
                                    }
                                )

                    if files_found:
                        logger.info(
                            f"Total {len(files_found)} files found via API Key"
                            f" {self.current_key_index + 1}."
                        )
                        return files_found

            # လက်ရှိ Key အလုပ်မဖြစ်ပါက နောက်ထပ် Key ရှိမရှိ စစ်ဆေးပြီး ပြောင်းလဲခြင်း
            if not self.switch_key():
                break

        # ၂။ Cookies ဖြင့် Session Fallback အသုံးပြုခြင်း (Key များ မရသည့်အခါ)
        if self.session_cookie:
            logger.info(
                "API keys unsuccessful. Attempting Web Session Cookie"
                " Fallback..."
            )
            async with httpx.AsyncClient(
                headers=self.get_headers(), timeout=35.0, follow_redirects=True
            ) as client:
                try:
                    # Account home စာမျက်နှာကို cookie session ဖြင့် တောင်းယူခြင်း
                    res = await client.get(f"{self.site_url}/account_home.html")
                    if res.status_code == 200:
                        # HTML ထဲရှိ download link pattern များကို ရှာဖွေခြင်း
                        pattern = r'href="(https://megaup\.net/([a-zA-Z0-9]+)/([^"]+\.(?:zip|rar|7z|dsf|dff|iso|flac|tar|gz|mp3|m4a|wav)))"'
                        matches = re.findall(pattern, res.text, re.IGNORECASE)
                        if not matches:
                            matches = re.findall(
                                r'href="(https://megaup\.net/([a-zA-Z0-9]+)/([^"]+))"',
                                res.text,
                            )

                        cookie_files = []
                        seen_ids = set()
                        for full_url, fid, fname in matches:
                            if fid not in seen_ids:
                                seen_ids.add(fid)
                                cookie_files.append(
                                    {
                                        "id": fid,
                                        "name": fname,
                                        "album_name": self.folder_name,
                                        "size": 0,
                                        "download_url": full_url,
                                    }
                                )

                        if cookie_files:
                            logger.info(
                                f"Found {len(cookie_files)} files via Session"
                                " Cookie fallback."
                            )
                            return cookie_files
                except Exception as ce:
                    logger.error(f"Cookie fallback execution error: {ce}")

        return []

    async def get_download_stream_url(self, file_info: Dict) -> Optional[str]:
        """ဖိုင်၏ Direct Download Link ကို ရှာဖွေဆွဲယူခြင်း"""
        file_url = file_info.get("download_url")
        file_id = file_info.get("id")

        if not file_url and file_id:
            file_url = f"{self.site_url}/{file_id}"

        # API Direct Link lookup
        if self.current_key and file_id:
            async with httpx.AsyncClient(
                headers=self.get_headers(), timeout=30.0, follow_redirects=True
            ) as client:
                try:
                    payload = {
                        "access_token": self.current_key,
                        "api_key": self.current_key,
                        "file_id": file_id,
                    }
                    res = await client.post(
                        f"{self.api_base_url}/file/download", data=payload
                    )
                    if res.status_code == 200:
                        dl_data = res.json()
                        dl_link = (
                            dl_data.get("download_url")
                            or dl_data.get("url")
                            or dl_data.get("data", {}).get("url")
                        )
                        if dl_link:
                            return dl_link
                except Exception as e:
                    logger.debug(f"Direct download link lookup error: {e}")

        # Web page Parsing lookup
        if file_url:
            async with httpx.AsyncClient(
                headers=self.get_headers(), timeout=30.0, follow_redirects=True
            ) as client:
                try:
                    res = await client.get(file_url)
                    match = re.search(
                        r'href="(https://download[0-9]*\.megaup\.net/[^"]+)"',
                        res.text,
                    )
                    if match:
                        return match.group(1)
                except Exception as e:
                    logger.error(f"Error parsing download page: {e}")

        return file_url
