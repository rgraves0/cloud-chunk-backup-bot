import time
import shutil
import psutil
from datetime import timedelta

BOOT_TIME = time.time()

def get_readable_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f}{units[i]}"

def get_readable_time(seconds: int) -> str:
    return str(timedelta(seconds=int(seconds)))

def format_progress_bar(percentage: float, total_blocks: int = 10) -> str:
    filled = int(total_blocks * (percentage / 100))
    empty = total_blocks - filled
    # Custom block style [■■■▦□□□□□□]
    if filled > 0 and filled < total_blocks:
        return "■" * (filled - 1) + "▦" + "□" * empty
    elif filled >= total_blocks:
        return "■" * total_blocks
    else:
        return "□" * total_blocks

def make_progress_text(
    file_name: str,
    user_name: str,
    user_id: int,
    current: int,
    total: int,
    speed: float,
    elapsed: float,
    status: str = "Download",
    engine: str = "HTTPX Async",
    in_mode: str = "MegaUp",
    out_mode: str = "Telegram"
) -> str:
    percent = (current / total) * 100 if total > 0 else 0
    bar = format_progress_bar(percent, total_blocks=10)
    
    current_str = get_readable_size(current)
    total_str = get_readable_size(total)
    speed_str = f"{get_readable_size(int(speed))}/s"
    
    eta = (total - current) / speed if speed > 0 else 0
    time_info = f"{get_readable_time(elapsed)} of {get_readable_time(elapsed + eta)} ( {get_readable_time(eta)} )"

    # Server stats
    cpu_percent = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    total_disk, used_disk, free_disk = shutil.disk_usage("/")
    disk_used_percent = (used_disk / total_disk) * 100
    uptime = get_readable_time(time.time() - BOOT_TIME)

    msg = (
        f"🎵 **{file_name}**\n\n"
        f"**Task By** {user_name} ( `#{user_id}` )\n"
        f"├ [{bar}] {percent:.2f}%\n"
        f"├ **Processed** → {current_str} of {total_str}\n"
        f"├ **Status** → {status}\n"
        f"├ **Speed** → {speed_str}\n"
        f"├ **Time** → {time_info}\n"
        f"├ **Engine** → {engine}\n"
        f"├ **In Mode** → #{in_mode}\n"
        f"└ **Out Mode** → #{out_mode}\n\n"
        f"⚙️ **Bot Stats**\n"
        f"├ **CPU** → {cpu_percent}% | **F** → {get_readable_size(free_disk)} [{disk_used_percent:.1f}%]\n"
        f"└ **RAM** → {ram.percent}% | **UP** → {uptime}"
    )
    return msg
