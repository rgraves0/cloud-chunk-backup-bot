# MegaUp to Telegram Mirror & Backup Bot

A lightweight, automated hybrid pipeline designed to sync files from **MegaUp** to a **Telegram Channel**. Built specifically to handle large files (such as DSD audio collections and archives) by automatically splitting files larger than 1.9GB into multi-part 7z archives, uploading them silently, and generating structured Master Index summary posts.

Designed to be stealthy, resource-efficient, and safe to deploy on PaaS environments (like Railway) or resource-constrained Linux VPS instances (like Oracle Cloud, GCP, or Vultr) without triggering abuse detection.

---

## Key Features

- **Dynamic Auto-Splitting (7z)**: Files $\le$ 1.9GB are uploaded directly; files $>$ 1.9GB are automatically split into 1900MB parts (`.7z.001`, `.7z.002`, etc.) using store mode (`-mx0`) to minimize CPU usage.
- **Strict FIFO Sequential Processing**: Queues incoming tasks one by one. Never downloads multiple archives simultaneously, preventing disk exhaustion.
- **Atomic Disk Cleanup**: Working folders are purged immediately after parts are uploaded, restoring 100% of temporary disk space before the next job starts.
- **Dual API Key Failover**: Supports rotating between MegaUp Primary (Key 1) and Secondary (Key 2) keys with a web-session fallback.
- **Stealth Networking**: Zero external mass downloaders (no `aria2`, `wget`, or torrent engines). Runs purely on native asynchronous HTTP streaming via `httpx`.
- **Live Progress & Bot Stats**: Real-time tree UI displaying download/upload speeds, ETAs, percentage bars, memory usage, free disk capacity, and host uptime.
- **Hybrid Triggering**: Automated twice-daily scans alongside Telegram inline manual controls.

---

## Bot Commands & Controls

| Command / Button | Type | Description |
| :--- | :--- | :--- |
| `/start` | Bot Command | Initializes the bot control dashboard and displays manual action buttons (Admin only). |
| `[ 🔄 Sync Now ]` | Inline Button | Manually triggers an instant check for newly uploaded, completed files on MegaUp. |
| `[ 📊 Server Stats ]` | Inline Button | Refreshes and displays system resource metrics (CPU, RAM, free disk space, uptime). |

---

## Environment Variables

Configure these variables inside your `.env` file or within your hosting provider's environment settings:

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `API_ID` | Yes | - | Telegram API ID from [my.telegram.org](https://my.telegram.org). |
| `API_HASH` | Yes | - | Telegram API Hash from [my.telegram.org](https://my.telegram.org). |
| `BOT_TOKEN` | Yes | - | Bot token generated via [@BotFather](https://t.me/BotFather). |
| `ADMIN_ID` | Yes | - | Numeric Telegram User ID of the bot administrator. |
| `TARGET_CHANNEL_ID` | Yes | - | Telegram Channel ID (must start with `-100`) where files and summary posts will be published. |
| `MEGAUP_KEY_1` | Yes | - | MegaUp Primary API Key (`Key 1` under Account Settings -> API Access). |
| `MEGAUP_KEY_2` | Optional | - | MegaUp Secondary API Key (`Key 2`) used for automatic failover. |
| `MEGAUP_BASE_URL` | No | `https://megaup.net/api` | Base API endpoint for MegaUp. |
| `MEGAUP_FOLDER_NAME` | No | `Hi-Res Music` | Specific MegaUp folder name to monitor. |
| `MEGAUP_COOKIE` | Optional | - | Web session cookie fallback for non-API accounts. |
| `CHUNK_SIZE_MB` | No | `1900` | Maximum split chunk size in MB (1900MB fits Telegram's standard 2GB limit). |
| `DOWNLOAD_DIR` | No | `/app/downloads` | Temporary download and staging path inside the container. |
| `AUTO_SCAN_HOURS` | No | `9,21` | Comma-separated 24-hour markers for scheduled scans (e.g., 09:00 and 21:00). |

---

## Deployment & Installation

### Option 1: Deploy with Docker (Recommended for VPS / Oracle Cloud)

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/](https://github.com/)<your-username>/<your-repo-name>.git
   cd <your-repo-name>
