#!/usr/bin/env python3
"""
 ██████╗ ██╗  ██╗ ██████╗ ███╗   ██╗██╗    ██████╗  ██████╗ ██╗    ██╗███╗   ██╗██╗      ██████╗  █████╗ ██████╗ ███████╗██████╗
██╔═████╗╚██╗██╔╝██╔═══██╗████╗  ██║██║    ██╔══██╗██╔═══██╗██║    ██║████╗  ██║██║     ██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
██║██╔██║ ╚███╔╝ ██║   ██║██╔██╗ ██║██║    ██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║██║     ██║   ██║███████║██║  ██║█████╗  ██████╔╝
████╔╝██║ ██╔██╗ ██║   ██║██║╚██╗██║██║    ██║  ██║██║   ██║██║███╗██║██║╚██╗██║██║     ██║   ██║██╔══██║██║  ██║██╔══╝  ██╔══██╗
╚██████╔╝██╔╝ ██╗╚██████╔╝██║ ╚████║██║    ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║███████╗╚██████╔╝██║  ██║██████╔╝███████╗██║  ██║
 ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝    ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
  Video Downloader — 1800+ sites • playlists • channels • MP3 • multi-threaded
  Powered by yt-dlp + NiceGUI
"""

import os
import sys
import re
import time
import json
import html
import shutil
import asyncio
import threading
import tempfile
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import yt_dlp
from nicegui import ui, run, app

# ─── Browser cookie support ─────────────────────────────────────
try:
    import browser_cookie3
    BROWSER_COOKIES = True
except ImportError:
    BROWSER_COOKIES = False

# ─── Constants ───────────────────────────────────────────────────
APP_NAME = "0xONI Downloader"
APP_VERSION = "2.0.0"
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIES_FILE = Path(__file__).parent / "cookies.txt"
_HAS_COOKIES = COOKIES_FILE.exists()

# ─── Counters ────────────────────────────────────────────────────
VISITOR_COUNT_FILE = Path("visitor_count.json")
DOWNLOAD_COUNT_FILE = Path("download_count.json")
SETTINGS_FILE = Path("settings.json")
visitor_count = 0
download_count = 0
_counter_lock = threading.Lock()

def load_visitor_count():
    global visitor_count
    if VISITOR_COUNT_FILE.exists():
        try:
            data = json.loads(VISITOR_COUNT_FILE.read_text(encoding='utf-8'))
            visitor_count = int(data.get('count', 0))
        except Exception:
            visitor_count = 0

def save_visitor_count():
    try:
        tmp = VISITOR_COUNT_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps({'count': visitor_count}), encoding='utf-8')
        tmp.replace(VISITOR_COUNT_FILE)
    except Exception:
        pass

def increment_visitor():
    global visitor_count
    with _counter_lock:
        visitor_count += 1
        save_visitor_count()

def load_download_count():
    global download_count
    if DOWNLOAD_COUNT_FILE.exists():
        try:
            data = json.loads(DOWNLOAD_COUNT_FILE.read_text(encoding='utf-8'))
            download_count = int(data.get('count', 0))
        except Exception:
            download_count = 0

def save_download_count():
    try:
        tmp = DOWNLOAD_COUNT_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps({'count': download_count}), encoding='utf-8')
        tmp.replace(DOWNLOAD_COUNT_FILE)
    except Exception:
        pass

def increment_download():
    global download_count
    with _counter_lock:
        download_count += 1
        save_download_count()

load_visitor_count()
load_download_count()

# ─── Compiled regex ──────────────────────────────────────────────
_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z_\\-]|\[[0-?]*[ -/]*[@-~])')

def clean_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub('', text).strip()

# ─── Utilities ───────────────────────────────────────────────────
def format_size(bytes_value) -> str:
    """Format bytes to human-readable string."""
    if not bytes_value:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} PB"

def format_speed(bytes_per_second) -> str:
    if not bytes_per_second:
        return "0 B/s"
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.1f} {unit}"
        bytes_per_second /= 1024
    return f"{bytes_per_second:.1f} TB/s"

def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain = re.sub(r'^www\.', '', domain)
        return domain
    except Exception:
        return ''

def get_free_disk_mb(path) -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 * 1024)

def validate_time_input(val: str) -> str | None:
    val = val.strip()
    if not val:
        return ''
    if val.isdigit():
        return val
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', val):
        return val
    return None

async def apply_ffmpeg_trim(input_path: str, start: str, end: str) -> str | None:
    """Обрезает видео через ffmpeg -ss/-to без перекодировки. Возвращает путь к обрезанному файлу."""
    if not os.path.exists(input_path):
        return None
    if not start and not end:
        return None
    if not shutil.which('ffmpeg'):
        return None
    # Имя: video_trimmed.mp4
    p = Path(input_path)
    output_path = str(p.with_stem(p.stem + '_trimmed'))
    cmd = ['ffmpeg', '-i', input_path]
    if start:
        cmd.extend(['-ss', start])
    if end:
        cmd.extend(['-to', end])
    cmd.extend(['-c', 'copy', output_path, '-y'])
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception:
        pass
    return None

def safe_filename(title: str, max_length: int = 120) -> str:
    """Sanitize filename — remove problematic characters."""
    # Remove path separators and other dangerous chars
    name = re.sub(r'[<>:"/\\|?*]', '_', title)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > max_length:
        name = name[:max_length-3] + '...'
    return name or 'video'

def get_random_user_agent() -> str:
    """Return a random modern User-Agent string."""
    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    ]
    import random
    return random.choice(agents)

# ─── Site-specific configuration ─────────────────────────────────
def get_site_presets(url: str) -> dict:
    """
    Returns yt-dlp options tailored to the specific site.
    Includes extractor_args, referer, headers, cookie strategies.
    """
    url_low = url.lower()
    opts = {}
    
    # YouTube
    if 'youtube.com' in url_low or 'youtu.be' in url_low:
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android_vr', 'android', 'web'],
                'skip': ['hls', 'dash'],
            }
        }
        opts['user_agent'] = get_random_user_agent()
    
    # Rutube
    elif 'rutube.ru' in url_low:
        opts['extractor_args'] = {'rutube': {}}
        opts['referer'] = 'https://rutube.ru/'
        opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
    
    # VK / VK Video
    elif 'vk.com' in url_low or 'vkvideo.ru' in url_low:
        opts['extractor_args'] = {'vk': {}}
        opts['referer'] = 'https://vk.com/'
        opts['user_agent'] = get_random_user_agent()
        if BROWSER_COOKIES:
            try:
                cj = browser_cookie3.load(domain_name='vk.com')
                opts['cookiefile'] = cj
            except Exception:
                pass
    
    # Dzen / Zen.Yandex
    elif 'dzen.ru' in url_low or 'zen.yandex.ru' in url_low:
        opts['extractor_args'] = {'zenyandex': {}}
        opts['referer'] = 'https://zen.yandex.ru/'
        opts['headers'] = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        }
    
    # Bilibili
    elif 'bilibili.com' in url_low:
        opts['extractor_args'] = {'bilibili': {}}
        opts['user_agent'] = get_random_user_agent()
    
    # Twitch
    elif 'twitch.tv' in url_low:
        opts['user_agent'] = get_random_user_agent()
        if BROWSER_COOKIES:
            try:
                cj = browser_cookie3.load(domain_name='twitch.tv')
                opts['cookiefile'] = cj
            except Exception:
                pass
    
    # Generic — random UA still helps
    else:
        opts['user_agent'] = get_random_user_agent()
    
    return opts

# ─── yt-dlp Auto-updater ─────────────────────────────────────────
class YtDlpUpdater:
    """Checks and updates yt-dlp from PyPI."""
    
    @staticmethod
    def get_local_version() -> str | None:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'yt_dlp', '--version'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def get_latest_version() -> str | None:
        try:
            import urllib.request
            url = "https://pypi.org/pypi/yt-dlp/json"
            req = urllib.request.Request(url, headers={'User-Agent': get_random_user_agent()})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return data.get('info', {}).get('version')
        except Exception:
            pass
        return None

    @staticmethod
    def update(log_callback=None) -> tuple[bool, str]:
        """Update yt-dlp via pip. Returns (success, message)."""
        try:
            if log_callback:
                log_callback("Обновление yt-dlp...", '#38bdf8')
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                new_ver = YtDlpUpdater.get_local_version()
                msg = f"✓ yt-dlp обновлён до {new_ver}" if new_ver else "✓ yt-dlp обновлён"
                if log_callback:
                    log_callback(msg, '#4ade80')
                return True, msg
            else:
                err = result.stderr[:200] if result.stderr else 'неизвестная ошибка'
                msg = f"✗ Ошибка обновления: {err}"
                if log_callback:
                    log_callback(msg, '#f87171')
                return False, msg
        except Exception as e:
            msg = f"✗ Ошибка: {str(e)[:100]}"
            if log_callback:
                log_callback(msg, '#f87171')
            return False, msg

# ─── Cleanup ──────────────────────────────────────────────────────
def cleanup_downloads(max_age_minutes: int = 30, max_size_gb: int = 5):
    if not DOWNLOAD_DIR.exists():
        return
    files = []
    for f in DOWNLOAD_DIR.iterdir():
        try:
            if f.is_file() and f.suffix not in ('.part', '.ytdl'):
                files.append(f)
        except Exception:
            pass
    now = time.time()
    cutoff = now - max_age_minutes * 60
    deleted_age = 0
    remaining = []
    for f in files:
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted_age += 1
            else:
                remaining.append(f)
        except Exception:
            remaining.append(f)
    if deleted_age:
        print(f'🧹 Deleted {deleted_age} old files (>{max_age_minutes}min)')
    total_size = sum(f.stat().st_size for f in remaining if f.exists())
    max_bytes = max_size_gb * 1024 ** 3
    if total_size > max_bytes:
        remaining.sort(key=lambda f: f.stat().st_mtime)
        deleted_fifo = 0
        freed = 0
        for f in remaining:
            if total_size - freed <= max_bytes:
                break
            try:
                sz = f.stat().st_size
                f.unlink()
                deleted_fifo += 1
                freed += sz
            except Exception:
                pass
        if deleted_fifo:
            print(f'🧹 Deleted {deleted_fifo} files by FIFO (>{max_size_gb}GB)')

# ─── Main Page ────────────────────────────────────────────────────
@ui.page('/')
async def main_page():
    global visitor_count
    if 'visited' not in app.storage.user:
        app.storage.user['visited'] = True
        increment_visitor()
    cleanup_downloads()

    # Default dark mode
    ui.dark_mode().enable()

    # ── Favicon + fonts ──────────────────────────────────────────
    ui.add_head_html(f'''
        <link rel="icon" type="image/x-icon" href="/favicon.ico?v={int(time.time())}">
    ''')
    ui.add_head_html('''
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            /* ── CSS Variables ─────────────────────────── */
            :root {
                --bg: #05070a;
                --bg-secondary: #0a0e14;
                --card-bg: rgba(13, 17, 25, 0.8);
                --card-bg-solid: #111827;
                --border: rgba(99, 102, 241, 0.12);
                --border-hover: rgba(99, 102, 241, 0.3);
                --accent: #6366f1;
                --accent-glow: rgba(99, 102, 241, 0.3);
                --accent2: #8b5cf6;
                --accent3: #ec4899;
                --success: #10b981;
                --warning: #f59e0b;
                --danger: #ef4444;
                --fg: #e2e8f0;
                --fg-secondary: #94a3b8;
                --fg-muted: #64748b;
                --input-bg: rgba(15, 23, 42, 0.7);
                --radius: 16px;
                --radius-sm: 10px;
                --radius-xs: 8px;
                --shadow-card: 0 4px 24px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.03);
                --shadow-glow: 0 0 40px rgba(99,102,241,.15);
                --transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            /* ── Light theme overrides ──────────────────── */
            .body--light {
                --bg: #f1f5f9;
                --bg-secondary: #e2e8f0;
                --card-bg: rgba(255, 255, 255, 0.85);
                --card-bg-solid: #ffffff;
                --border: rgba(99, 102, 241, 0.15);
                --border-hover: rgba(99, 102, 241, 0.4);
                --fg: #0f172a;
                --fg-secondary: #475569;
                --fg-muted: #94a3b8;
                --input-bg: rgba(241, 245, 249, 0.9);
                --shadow-card: 0 4px 24px rgba(0,0,0,.08), inset 0 1px 0 rgba(255,255,255,.6);
                --shadow-glow: 0 0 30px rgba(99,102,241,.1);
            }

            body {
                background: var(--bg) !important;
                font-family: 'Inter', -apple-system, sans-serif !important;
                overflow-x: hidden;
                transition: background 0.4s ease;
            }

            /* ── Animated background ────────────────────── */
            .bg-grid {
                position: fixed; inset: 0; z-index: 0; pointer-events: none;
                background-image:
                    radial-gradient(circle at 25% 20%, var(--accent-glow) 0%, transparent 50%),
                    radial-gradient(circle at 75% 60%, rgba(139, 92, 246, 0.2) 0%, transparent 50%),
                    radial-gradient(circle at 40% 80%, rgba(236, 72, 153, 0.15) 0%, transparent 50%);
                animation: bgPulse 12s ease-in-out infinite;
            }
            @keyframes bgPulse {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
            }

            /* ── Glass card ─────────────────────────────── */
            .glass {
                background: var(--card-bg) !important;
                backdrop-filter: blur(24px) saturate(180%);
                -webkit-backdrop-filter: blur(24px) saturate(180%);
                border: 1px solid var(--border) !important;
                border-radius: var(--radius) !important;
                box-shadow: var(--shadow-card) !important;
                transition: border-color var(--transition), box-shadow var(--transition);
            }
            .glass:hover {
                border-color: var(--border-hover) !important;
                box-shadow: var(--shadow-card), var(--shadow-glow) !important;
            }

            /* ── Log scrollbar ──────────────────────────── */
            .log-scroll::-webkit-scrollbar { width: 5px; }
            .log-scroll::-webkit-scrollbar-track { background: transparent; }
            .log-scroll::-webkit-scrollbar-thumb { background: var(--fg-muted); border-radius: 4px; }
            .log-scroll::-webkit-scrollbar-thumb:hover { background: var(--fg-secondary); }

            /* ── Input fields ───────────────────────────── */
            .q-field--outlined .q-field__control {
                background: var(--input-bg) !important;
                border-radius: var(--radius-sm) !important;
                border-color: var(--border) !important;
                transition: border-color var(--transition), box-shadow var(--transition);
            }
            .q-field--outlined .q-field__control:hover {
                border-color: var(--border-hover) !important;
            }
            .q-field--outlined.q-field--focused .q-field__control {
                border-color: var(--accent) !important;
                box-shadow: 0 0 0 3px var(--accent-glow) !important;
            }
            .q-field__label { color: var(--fg-muted) !important; }
            .q-field__native, .q-field__input { color: var(--fg) !important; }
            .q-select__dropdown-menu {
                background: var(--card-bg-solid) !important;
                border: 1px solid var(--border) !important;
                border-radius: var(--radius-sm) !important;
            }

            /* ── Buttons ────────────────────────────────── */
            .btn-primary {
                background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
                border-radius: 14px !important;
                font-weight: 700 !important;
                letter-spacing: 0.5px !important;
                text-transform: uppercase !important;
                position: relative; overflow: hidden;
                transition: transform 0.2s, box-shadow 0.3s !important;
            }
            .btn-primary:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 30px var(--accent-glow) !important;
            }
            .btn-primary:active { transform: translateY(0) !important; }
            .btn-primary::after {
                content: ''; position: absolute; inset: 0;
                background: linear-gradient(105deg, transparent 35%, rgba(255,255,255,.15) 50%, transparent 65%);
                transform: translateX(-110%);
                transition: transform 0.6s ease;
            }
            .btn-primary:hover::after { transform: translateX(110%); }

            .btn-danger {
                background: linear-gradient(135deg, var(--danger), #dc2626) !important;
                border-radius: 14px !important;
                font-weight: 700 !important;
                letter-spacing: 0.5px !important;
                text-transform: uppercase !important;
                transition: transform 0.2s, box-shadow 0.3s !important;
            }
            .btn-danger:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 30px rgba(239,68,68,.35) !important;
            }
            .btn-danger:active { transform: translateY(0) !important; }

            .btn-ghost {
                background: transparent !important;
                border: 1px solid var(--border) !important;
                border-radius: var(--radius-xs) !important;
                transition: all var(--transition) !important;
            }
            .btn-ghost:hover {
                border-color: var(--accent) !important;
                background: var(--accent-glow) !important;
            }

            /* ── Progress bar ───────────────────────────── */
            .q-linear-progress__track {
                border-radius: 999px !important;
                background: rgba(30, 41, 59, 0.6) !important;
                height: 8px !important;
            }
            .q-linear-progress__bar {
                border-radius: 999px !important;
                background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3)) !important;
                background-size: 200% 100% !important;
                animation: gshift 3s ease infinite;
            }
            @keyframes gshift {
                0%, 100% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
            }

            /* ── Status dots ────────────────────────────── */
            .dot {
                display: inline-block; width: 9px; height: 9px;
                border-radius: 50%; margin-right: 8px; vertical-align: middle;
            }
            .dot-idle   { background: var(--success); box-shadow: 0 0 8px rgba(16,185,129,.5); }
            .dot-active { background: var(--warning); box-shadow: 0 0 8px rgba(245,158,11,.5); animation: pdot 1.2s ease-in-out infinite; }
            .dot-error  { background: var(--danger); box-shadow: 0 0 8px rgba(239,68,68,.5); }
            @keyframes pdot { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }

            /* ── Video card in playlist ─────────────────── */
            .video-card {
                background: var(--input-bg);
                border: 1px solid var(--border);
                border-radius: var(--radius-sm);
                padding: 12px;
                transition: all var(--transition);
                cursor: pointer;
            }
            .video-card:hover {
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.05);
            }
            .video-card.selected {
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.1);
                box-shadow: 0 0 12px rgba(99,102,241,.1);
            }
            .video-card.skipped {
                opacity: 0.35;
                text-decoration: line-through;
            }

            /* ── Format table ───────────────────────────── */
            .format-row {
                display: flex; align-items: center; gap: 12px;
                padding: 8px 14px;
                border-bottom: 1px solid var(--border);
                transition: background var(--transition);
            }
            .format-row:hover { background: rgba(99, 102, 241, 0.04); }
            .format-row:last-child { border-bottom: none; }

            /* ── Counter badges ─────────────────────────── */
            .counter-badge {
                display: inline-flex; align-items: center; gap: 5px;
                padding: 4px 12px;
                background: var(--input-bg);
                border: 1px solid var(--border);
                border-radius: 20px;
                font-size: 0.8rem;
                color: var(--fg-secondary);
                transition: all var(--transition);
            }
            .counter-badge:hover {
                border-color: var(--accent);
                color: var(--fg);
            }

            /* ── Tab system ─────────────────────────────── */
            .tab-btn {
                padding: 8px 20px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 0.9rem;
                cursor: pointer;
                transition: all var(--transition);
                background: transparent;
                color: var(--fg-muted);
                border: 1px solid transparent;
            }
            .tab-btn.active {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .tab-btn:hover:not(.active) {
                color: var(--fg);
                border-color: var(--border);
            }

            /* ── Animations ─────────────────────────────── */
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(12px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .animate-in {
                animation: fadeInUp 0.4s ease-out;
            }

            /* ── Theme switch ───────────────────────────── */
            .theme-switch {
                position: fixed; top: 16px; right: 16px; z-index: 100;
            }
        </style>
    ''')

    # ── Background ────────────────────────────────────────────────
    ui.html('<div class="bg-grid"></div>', sanitize=False)

    # ── Session state ─────────────────────────────────────────────
    client_log = []
    is_downloading = False
    cancel_requested = False
    before_files = set()
    progress_info = {'percent': 0.0, 'speed': '?', 'eta': '?', 'phase': 'idle', 'convert_start': 0}
    history_data = []
    current_video_info = None
    playlist_videos = []
    playlist_skipped = set()
    selected_format_id = None
    available_formats = []
    dark_mode = True
    # ── Theme toggle ──────────────────────────────────────────────
    def toggle_theme():
        nonlocal dark_mode
        dark_mode = not dark_mode
        if dark_mode:
            ui.dark_mode().enable()
            ui.run_javascript('document.body.classList.remove("body--light")')
        else:
            ui.dark_mode().disable()
            ui.run_javascript('document.body.classList.add("body--light")')
        theme_icon.set_value('dark_mode' if dark_mode else 'light_mode')

    # ── Log helpers ───────────────────────────────────────────────
    def add_log(message: str, color: str = '#94a3b8'):
        ts = datetime.now().strftime('%d.%m %H:%M:%S')
        safe_msg = html.escape(message)
        client_log.append(
            f'<span style="color:#475569">[{ts}]</span> '
            f'<span style="color:{color}">{safe_msg}</span>'
        )
        if len(client_log) > 300:
            client_log.pop(0)
        update_log()

    def update_log():
        content = '<br>'.join(client_log)
        log_output.content = content or '<span style="color:#334155">[ лог пуст ]</span>'
        log_output.update()

    def set_status(text: str, state: str = 'idle'):
        dot_cls = {'idle': 'dot-idle', 'active': 'dot-active', 'error': 'dot-error'}.get(state, 'dot-idle')
        color = {'idle': '#94a3b8', 'active': '#fbbf24', 'error': '#f87171'}.get(state, '#94a3b8')
        status_html.content = f'<span class="dot {dot_cls}"></span><span style="color:{color}">{text}</span>'
        status_html.update()

    # ── History ───────────────────────────────────────────────────
    def render_history():
        history_col.clear()
        with history_col:
            if not history_data:
                ui.label('Пока пусто').classes('text-gray-600 text-sm italic')
            for fname, sz, fpath in reversed(history_data[-20:]):
                with ui.row().classes('w-full items-center gap-3 py-2') as row:
                    row.style('border-bottom: 1px solid var(--border);')
                    ui.icon('video_file', size='16px').classes('text-indigo-400/60')
                    ui.label(fname).classes('text-sm flex-1 truncate').style(f'color: var(--fg-secondary)')
                    ui.label(f'{sz:.1f} MB').classes('text-xs tabular-nums').style('color: var(--fg-muted)')

    def add_history_item(filename: str, size_mb: float, full_path: str):
        history_data.append((filename, size_mb, full_path))
        render_history()

    # ── File sending ──────────────────────────────────────────────
    def send_file_to_browser(file_path: str):
        if not os.path.exists(file_path):
            ui.notify('Файл не найден', type='error')
            return
        try:
            suffix = Path(file_path).suffix
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.close()
            shutil.move(file_path, tmp.name)
            tmp_path = tmp.name
            original_name = Path(file_path).name
            ui.download(src=tmp_path, filename=original_name)
            ui.timer(10, lambda p=tmp_path: cleanup_temp(p), once=True)
        except Exception as e:
            add_log(f'Ошибка отдачи: {str(e)[:80]}', '#fb923c')
            ui.notify(f'Ошибка отправки: {e}', type='error')

    def cleanup_temp(path):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass

    # ── Format fetching ───────────────────────────────────────────
    async def fetch_formats(url: str):
        """Fetch and return available formats with size info."""
        nonlocal available_formats
        try:
            opts = {
                'quiet': True, 'no_warnings': True,
                'user_agent': get_random_user_agent(),
            }
            opts.update(get_site_presets(url))
            
            def get_info():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await run.io_bound(get_info)
            if not info:
                return []
            
            formats = info.get('formats', [])
            result = []
            seen = set()
            
            for f in formats:
                fid = f.get('format_id', '')
                if fid in seen:
                    continue
                seen.add(fid)
                
                height = f.get('height') or 0
                width = f.get('width') or 0
                ext = f.get('ext', '?')
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                fps = f.get('fps') or 0
                tbr = f.get('tbr') or 0
                note = f.get('format_note', '')
                
                # Build human-readable description
                has_video = vcodec and vcodec != 'none'
                has_audio = acodec and acodec != 'none'
                
                if has_video and has_audio:
                    type_str = f"{width}x{height}" if width and height else note or "video+audio"
                elif has_video:
                    type_str = f"{width}x{height} (video only)" if width and height else "video only"
                elif has_audio:
                    type_str = "audio only"
                else:
                    type_str = note or "unknown"
                
                size_str = format_size(filesize) if filesize else "? B"
                
                result.append({
                    'format_id': fid,
                    'description': f"{type_str} · {ext} · {size_str}",
                    'height': height,
                    'filesize': filesize,
                    'ext': ext,
                    'note': note,
                })
            
            # Sort: video by height desc, then by size
            result.sort(key=lambda x: (-x['height'], -x['filesize']))
            available_formats = result
            return result
        except Exception as e:
            add_log(f'Ошибка форматов: {str(e)[:80]}', '#f87171')
            return []

    # ── Preview ───────────────────────────────────────────────────
    async def preview_video(e=None):
        url = (url_input.value or '').strip()
        if not url.startswith(('http://', 'https://')):
            ui.notify('Сначала вставь ссылку', type='info', position='top')
            return
        
        add_log('Получаю информацию...', '#38bdf8')
        set_status('Загрузка информации...', 'active')
        
        try:
            opts = {
                'quiet': True, 'no_warnings': True,
                'user_agent': get_random_user_agent(),
            }
            opts.update(get_site_presets(url))
            
            def get_info():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await run.io_bound(get_info)
            if info:
                nonlocal current_video_info
                current_video_info = info
                
                title = info.get('title', '?')
                duration = info.get('duration') or 0
                thumb = info.get('thumbnail', '')
                uploader = info.get('uploader') or info.get('channel') or ''
                view_count = info.get('view_count') or 0
                
                mins, secs = divmod(int(duration), 60)
                hours, mins = divmod(mins, 60)
                
                if hours:
                    dur_str = f'{hours}:{mins:02d}:{secs:02d}'
                else:
                    dur_str = f'{mins}:{secs:02d}'
                
                views_str = f'{view_count:,}' if view_count else '?'
                
                safe_title = html.escape(title[:120])
                safe_thumb = html.escape(thumb)
                safe_uploader = html.escape(uploader[:60])
                
                html_content = (
                    f'<div style="display:flex;align-items:center;gap:16px;width:100%;">'
                    f'<img src="{safe_thumb}" style="width:160px;height:90px;object-fit:cover;border-radius:10px;" '
                    f'onerror="this.style.display=\'none\'">'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="font-weight:600;font-size:0.95rem;color:var(--fg);'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{safe_title}</div>'
                    f'<div style="display:flex;gap:16px;margin-top:6px;font-size:0.8rem;color:var(--fg-muted);">'
                    f'<span>⏱ {dur_str}</span>'
                    f'<span>👤 {safe_uploader}</span>'
                    f'<span>👁 {views_str}</span>'
                    f'</div></div></div>'
                )
                preview_html.set_content(html_content)
                preview_html.update()
                preview_row.set_visibility(True)
                preview_row.update()
                add_log(f'Найдено: {title[:80]}', '#4ade80')
                
                # Update trim slider max to video duration
                update_trim_range(int(duration))
                
                # Auto-fetch formats
                await fetch_formats(url)
                render_format_list()
            else:
                add_log('Не удалось получить информацию', '#f87171')
                ui.notify('Видео не найдено', type='warning')
                preview_row.set_visibility(False)
                preview_row.update()
        except Exception as e:
            add_log(f'Ошибка предпросмотра: {str(e)[:80]}', '#f87171')
            ui.notify(f'Ошибка: {str(e)[:60]}', type='error')
            preview_row.set_visibility(False)
            preview_row.update()
        finally:
            set_status('Готов к работе', 'idle')

    # ── Format list rendering ─────────────────────────────────────
    def render_format_list():
        format_col.clear()
        with format_col:
            if not available_formats:
                ui.label('Нажмите "Анализ" для загрузки списка форматов').classes('text-xs text-gray-500')
                return
            
            # Header
            with ui.row().classes('w-full items-center gap-2 mb-2'):
                ui.label('Доступные форматы:').classes('text-xs font-semibold').style('color: var(--fg-secondary)')
                ui.space()
                ui.label(f'{len(available_formats)} шт.').classes('text-xs').style('color: var(--fg-muted)')
            
            # Format rows (show top 15)
            for i, fmt in enumerate(available_formats[:15]):
                fid = fmt['format_id']
                desc = fmt['description']
                height = fmt['height']
                
                with ui.row().classes('format-row w-full items-center gap-3') as row:
                    # Radio-like indicator
                    is_sel = (selected_format_id == fid)
                    indicator = '●' if is_sel else '○'
                    color = 'var(--accent)' if is_sel else 'var(--fg-muted)'
                    
                    ui.html(
                        f'<span style="color:{color};font-size:1.1rem;cursor:pointer;'
                        f'min-width:20px;text-align:center;">{indicator}</span>',
                        sanitize=False
                    ).on('click', lambda f=fid: select_format(f))
                    
                    ui.label(desc).classes('text-xs flex-1').style(f'color: {"var(--fg)" if is_sel else "var(--fg-secondary)"}')

    def select_format(fid: str):
        nonlocal selected_format_id
        selected_format_id = fid
        render_format_list()
        fmt = next((f for f in available_formats if f['format_id'] == fid), None)
        if fmt:
            add_log(f'Выбран формат: {fmt["description"]}', '#a78bfa')

    # ── Playlist analysis ─────────────────────────────────────────
    async def analyze_playlist(url: str):
        nonlocal playlist_videos, playlist_skipped
        try:
            opts = {
                'quiet': True, 'no_warnings': True,
                'extract_flat': 'in_playlist',
                'user_agent': get_random_user_agent(),
                'socket_timeout': 30,
                'ignoreerrors': True,
            }
            opts.update(get_site_presets(url))
            
            def get_pl():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return []
                    if info.get('_type') == 'playlist' or 'entries' in info:
                        entries = list(info.get('entries', []))
                        return [e for e in entries if e is not None]
                    return []
            
            videos = await run.io_bound(get_pl)
            playlist_videos = videos
            playlist_skipped = set()
            
            pl_title = ''
            try:
                pl_title = (await run.io_bound(
                    lambda: yt_dlp.YoutubeDL({'quiet': True}).extract_info(url, download=False)
                )).get('title', 'Плейлист')
            except Exception:
                pl_title = 'Плейлист'
            
            add_log(f'📋 Плейлист: {pl_title} ({len(videos)} видео)', '#38bdf8')
            render_playlist()
            
        except Exception as e:
            add_log(f'Ошибка плейлиста: {str(e)[:80]}', '#f87171')
            ui.notify(f'Ошибка анализа плейлиста: {str(e)[:60]}', type='error')

    def render_playlist():
        playlist_col.clear()
        with playlist_col:
            if not playlist_videos:
                ui.label('Плейлист пуст').classes('text-sm text-gray-500')
                return
            
            # Controls
            with ui.row().classes('w-full items-center gap-3 mb-3'):
                ui.label(f'Видео в плейлисте: {len(playlist_videos)}').classes('text-sm font-semibold').style('color: var(--fg-secondary)')
                ui.space()
                select_all_btn = ui.button('Выбрать все', icon='select_all').props('flat dense size=sm')
                deselect_all_btn = ui.button('Снять все', icon='deselect').props('flat dense size=sm')
            
            select_all_btn.on('click', lambda: select_all_playlist())
            deselect_all_btn.on('click', lambda: deselect_all_playlist())
            
            # Video list (show up to 50, scrollable)
            with ui.scroll_area().classes('w-full max-h-80'):
                for i, v in enumerate(playlist_videos[:50]):
                    vid = v
                    title = vid.get('title', f'Видео {i+1}')[:100]
                    duration = vid.get('duration') or 0
                    mins, secs = divmod(int(duration), 60)
                    dur_str = f'{mins}:{secs:02d}' if duration else '?:??'
                    skipped = i in playlist_skipped
                    
                    cls = 'video-card'
                    if skipped:
                        cls += ' skipped'
                    
                    with ui.row().classes(f'{cls} w-full items-center gap-3'):
                        cb = ui.checkbox('').props('dense').bind_value_to(
                            target_object=None,
                            forward=lambda x, idx=i: idx not in playlist_skipped,
                            backward=None,
                        )
                        cb.set_value(not skipped)
                        cb.on('update:model-value', lambda v, idx=i: toggle_playlist_video(idx, v))
                        
                        ui.label(f'{i+1}. {title}').classes('text-xs flex-1 truncate').style('color: var(--fg-secondary)')
                        ui.label(dur_str).classes('text-xs tabular-nums').style('color: var(--fg-muted)')
            
            if len(playlist_videos) > 50:
                ui.label(f'... и ещё {len(playlist_videos) - 50} видео').classes('text-xs text-gray-500 mt-2')

    def toggle_playlist_video(idx: int, selected: bool):
        if selected:
            playlist_skipped.discard(idx)
        else:
            playlist_skipped.add(idx)

    def select_all_playlist():
        nonlocal playlist_skipped
        playlist_skipped.clear()
        render_playlist()
        add_log('Выбраны все видео плейлиста', '#a78bfa')

    def deselect_all_playlist():
        nonlocal playlist_skipped
        playlist_skipped = set(range(len(playlist_videos)))
        render_playlist()
        add_log('Снят выбор со всех видео', '#a78bfa')

    # ── Download logic ────────────────────────────────────────────
    def build_ydl_opts(url: str, audio_only_flag: bool, quality_val: str, 
                       fmt_val: str, speed_val: str, subtitles_flag: bool,
                       custom_format_id: str = None) -> dict:
        """Build yt-dlp options with site-specific presets."""
        outtmpl = str(DOWNLOAD_DIR / '%(title).80s_%(id)s_%(epoch)d.%(ext)s')
        
        ydl_opts = {
            'outtmpl': outtmpl,
            'restrictfilenames': True,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'continuedl': True,
            'abort_on_error': False,
        }
        
        # Site presets
        ydl_opts.update(get_site_presets(url))
        
        # Cookies file
        if _HAS_COOKIES:
            ydl_opts['cookiefile'] = str(COOKIES_FILE)
        
        # Format selection
        if audio_only_flag:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif custom_format_id:
            ydl_opts['format'] = custom_format_id
        else:
            if quality_val != 'Авто':
                ydl_opts['format'] = (
                    f'bestvideo[height<={quality_val}]+bestaudio/'
                    f'best[height<={quality_val}]'
                )
            else:
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
            
            if fmt_val != 'best':
                ydl_opts['merge_output_format'] = fmt_val
        
        # Rate limit
        if speed_val != 'Без ограничения':
            rate = speed_val.replace('M', '000000').replace('K', '000')
            ydl_opts['ratelimit'] = int(rate)
        
        # Subtitles
        if subtitles_flag:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['ru', 'en']
            ydl_opts['subtitlesformat'] = 'srt'
        
        return ydl_opts

    async def start_download(e=None):
        nonlocal is_downloading, cancel_requested, before_files, current_video_info
        
        if is_downloading:
            return
        
        url = (url_input.value or '').strip()
        if not url or not url.startswith(('http://', 'https://')):
            ui.notify('Вставь корректную ссылку', type='warning', position='top')
            return
        
        # Detect if playlist
        is_playlist = ('playlist' in url.lower() or 'list=' in url.lower() or 
                       '/channel/' in url.lower() or '/@' in url.lower() or
                       '/c/' in url.lower())
        
        is_downloading = True
        cancel_requested = False
        before_files = set(f.name for f in DOWNLOAD_DIR.iterdir()) if DOWNLOAD_DIR.exists() else set()
        
        free_mb = get_free_disk_mb(DOWNLOAD_DIR)
        if free_mb < 200:
            add_log(f'⚠ Осталось всего {free_mb:.0f} MB на диске!', '#fbbf24')
            ui.notify(f'Мало места: {free_mb:.0f} MB', type='warning', position='top')
        
        download_btn.classes(add='hidden')
        cancel_btn.classes(remove='hidden')
        progress.classes(remove='hidden')
        progress.props(remove='indeterminate')
        progress.value = 0
        progress_info.update({'percent': 0, 'speed': '?', 'eta': '?', 'phase': 'idle', 'convert_start': 0})
        error_occurred = False
        
        add_log(f'▶ Начинаю: {url}', '#38bdf8')
        set_status('Подключаюсь...', 'active')
        
        actual_file = None
        
        try:
            def hook(d):
                if cancel_requested:
                    raise Exception("Download cancelled by user")
                if d['status'] == 'downloading':
                    raw = clean_ansi(d.get('_percent_str', '0%'))
                    try:
                        progress_info['percent'] = float(raw.rstrip('%').strip())
                    except ValueError:
                        pass
                    progress_info['speed'] = clean_ansi(d.get('_speed_str', '?'))
                    progress_info['eta'] = clean_ansi(d.get('_eta_str', '?'))
                    progress_info['phase'] = 'downloading'
                elif d['status'] == 'finished':
                    progress_info['phase'] = 'converting' if audio_only.value else 'merging'
                    if audio_only.value:
                        progress_info['convert_start'] = time.time()
            
            ydl_opts = build_ydl_opts(
                url, audio_only.value, quality.value, 
                fmt.value, speed.value, subtitles_opt.value,
                selected_format_id
            )
            ydl_opts['progress_hooks'] = [hook]
            
            def blocking_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    nonlocal current_video_info
                    current_video_info = info
                    if info and 'requested_downloads' in info:
                        for rd in info['requested_downloads']:
                            filepath = rd.get('filepath')
                            if filepath and os.path.exists(filepath):
                                return filepath
                    return ydl.prepare_filename(info)
            
            filename = await run.io_bound(blocking_download)
            actual_file = filename if filename and os.path.exists(filename) else None
            
            # For audio-only: find resulting MP3
            if audio_only.value and not actual_file:
                mp3_files = sorted(DOWNLOAD_DIR.glob('*.mp3'), key=os.path.getmtime, reverse=True)
                if mp3_files:
                    actual_file = str(mp3_files[0])
                    add_log(f'✓ Конвертировано в MP3: {Path(actual_file).name}', '#4ade80')
            
            if not actual_file:
                # Check for new files
                after_files = set(f.name for f in DOWNLOAD_DIR.iterdir()) if DOWNLOAD_DIR.exists() else set()
                new_files = after_files - before_files
                if new_files:
                    newest = sorted(
                        [DOWNLOAD_DIR / n for n in new_files],
                        key=os.path.getmtime, reverse=True
                    )
                    for nf in newest:
                        if nf.suffix not in ('.part', '.ytdl'):
                            actual_file = str(nf)
                            break
                
                if not actual_file:
                    error_occurred = True
                    add_log('✗ Файл не найден после загрузки', '#f87171')
                    set_status('Файл не найден', 'error')
                    return
            
            add_log(f'✓ Сохранено: {Path(actual_file).name}', '#4ade80')
            progress.value = 1.0
            progress_info['phase'] = 'idle'
            set_status('Готово!', 'idle')
        
        except Exception as e:
            if cancel_requested:
                add_log('⏹ Загрузка отменена пользователем', '#fbbf24')
            else:
                error_occurred = True
                err_msg = str(e)[:150]
                add_log(f'✗ Ошибка: {err_msg}', '#f87171')
                set_status(f'Ошибка: {err_msg[:80]}', 'error')
        
        finally:
            progress.classes(add='hidden')
            progress_info['phase'] = 'idle'
            
            # Cleanup on cancel
            if cancel_requested:
                deleted = 0
                for f in DOWNLOAD_DIR.iterdir():
                    try:
                        if f.is_file() and f.name not in before_files:
                            f.unlink()
                            deleted += 1
                    except Exception:
                        pass
                if deleted:
                    add_log(f'🗑 Удалено {deleted} файлов (отмена)', '#fbbf24')
                cancel_requested = False
            
            # Trim after download (if enabled)
            if not error_occurred and actual_file and os.path.exists(actual_file) and enable_trim.value:
                raw_start = start_time.value.strip()
                raw_end = end_time.value.strip()
                trim_start = validate_time_input(raw_start)
                trim_end = validate_time_input(raw_end)
                if trim_start is None:
                    add_log(f'⚠ Неверный формат начала: {raw_start}', '#fbbf24')
                    trim_start = ''
                if trim_end is None:
                    add_log(f'⚠ Неверный формат конца: {raw_end}', '#fbbf24')
                    trim_end = ''
                if trim_start or trim_end:
                    set_status('Обрезка видео...', 'active')
                    progress.classes(remove='hidden')
                    progress.props('indeterminate')
                    trimmed = await apply_ffmpeg_trim(actual_file, trim_start, trim_end)
                    progress.classes(add='hidden')
                    progress.props(remove='indeterminate')
                    if trimmed:
                        actual_file = trimmed
                        add_log(f'✂️ Обрезано: {Path(trimmed).name}', '#4ade80')
                    else:
                        add_log('⚠ Обрезка не удалась (возможно, нет ffmpeg). Отдаю полное видео.', '#fbbf24')
                        ui.notify('Обрезка не выполнена, отдаётся полное видео', type='warning')
            
            # Send file
            elif not error_occurred and actual_file and os.path.exists(actual_file):
                try:
                    size_mb = os.path.getsize(actual_file) / (1024 * 1024)
                    send_file_to_browser(actual_file)
                    increment_download()
                    ui.notify('Файл отправлен в браузер!', type='positive', position='top')
                    add_log(f'→ Отправлено ({size_mb:.1f} MB)', '#7dd3fc')
                    add_history_item(Path(actual_file).name, size_mb, actual_file)
                    # Cleanup moved file if still exists
                    try:
                        if os.path.exists(actual_file):
                            os.remove(actual_file)
                            add_log(f'✓ Файл удалён: {Path(actual_file).name}', '#4ade80')
                    except Exception as e:
                        add_log(f'⚠ Ошибка удаления: {e}', '#fb923c')
                except Exception as dl_err:
                    add_log(f'✗ Ошибка отдачи: {str(dl_err)[:80]}', '#fb923c')
            
            # Restore UI
            is_downloading = False
            download_btn.classes(remove='hidden')
            cancel_btn.classes(add='hidden')
            
            cleanup_downloads()
            
            if not error_occurred:
                set_status('Готов к работе', 'idle')
            else:
                set_status('Ошибка', 'error')

    async def cancel_download():
        nonlocal cancel_requested
        cancel_requested = True
        add_log('⏹ Отмена загрузки...', '#fbbf24')
        set_status('Отмена...', 'error')
        ui.notify('Останавливаю загрузку...', type='warning', position='top')

    # ── Playlist download ─────────────────────────────────────────
    async def download_playlist_action():
        nonlocal is_downloading, cancel_requested, playlist_videos, playlist_skipped
        
        if not playlist_videos:
            ui.notify('Сначала проанализируйте плейлист', type='warning')
            return
        
        # Filter selected videos
        tasks = [
            (i, v.get('webpage_url') or v.get('url'), v.get('title', f'Видео {i+1}'))
            for i, v in enumerate(playlist_videos)
            if i not in playlist_skipped
        ]
        
        if not tasks:
            ui.notify('Не выбрано ни одного видео', type='warning')
            return
        
        is_downloading = True
        cancel_requested = False
        download_btn.classes(add='hidden')
        cancel_btn.classes(remove='hidden')
        progress.classes(remove='hidden')
        progress.props(remove='indeterminate')
        
        total = len(tasks)
        completed = 0
        failed = 0
        
        add_log(f'📋 Загрузка плейлиста: {total} видео', '#38bdf8')
        set_status(f'Плейлист: 0/{total}', 'active')
        
        def download_one(idx: int, v_url: str, title: str) -> tuple[int, bool]:
            if cancel_requested:
                return (idx, False)
            try:
                ydl_opts = build_ydl_opts(
                    v_url, audio_only.value, quality.value,
                    fmt.value, speed.value, subtitles_opt.value,
                    selected_format_id
                )
                ydl_opts['outtmpl'] = str(DOWNLOAD_DIR / '%(title).80s_%(id)s.%(ext)s')
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(v_url, download=True)
                    if info:
                        filename = ydl.prepare_filename(info)
                        if os.path.exists(filename):
                            return (idx, True)
                        # Check for new files
                        return (idx, True)
                return (idx, False)
            except Exception:
                return (idx, False)
        
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(download_one, i, u, t): (i, u, t) for i, u, t in tasks}
                
                for future in as_completed(futures):
                    if cancel_requested:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    idx, success = future.result()
                    completed += 1
                    if not success:
                        failed += 1
                    
                    progress.value = completed / total
                    set_status(f'Плейлист: {completed}/{total}', 'active')
                    
                    if success:
                        add_log(f'✓ [{completed}/{total}] {tasks[idx][2][:60]}', '#4ade80')
                    else:
                        add_log(f'✗ [{completed}/{total}] Ошибка', '#f87171')
        
        except Exception as e:
            add_log(f'✗ Ошибка плейлиста: {str(e)[:80]}', '#f87171')
        
        finally:
            is_downloading = False
            download_btn.classes(remove='hidden')
            cancel_btn.classes(add='hidden')
            progress.classes(add='hidden')
            
            if cancel_requested:
                add_log('⏹ Загрузка плейлиста отменена', '#fbbf24')
            else:
                add_log(f'📋 Плейлист завершён: {completed - failed}/{total} успешно', '#4ade80')
            
            set_status('Готов к работе', 'idle')
            cancel_requested = False
            
            # Cleanup & send files
            cleanup_downloads()
            
            # Send downloaded files
            for f in sorted(DOWNLOAD_DIR.iterdir(), key=os.path.getmtime, reverse=True):
                if f.suffix not in ('.part', '.ytdl'):
                    try:
                        size_mb = f.stat().st_size / (1024 * 1024)
                        send_file_to_browser(str(f))
                        increment_download()
                        add_history_item(f.name, size_mb, str(f))
                        await asyncio.sleep(0.5)
                    except Exception:
                        break
                    # Stop after sending 5 files to avoid flooding
                    if completed - failed >= 5:
                        break

    # ── Thumbnail download ────────────────────────────────────────
    async def download_thumbnail(e=None):
        url = (url_input.value or '').strip()
        if not url:
            ui.notify('Вставьте ссылку', type='warning')
            return
        try:
            opts = {
                'quiet': True, 'no_warnings': True,
                'skip_download': True,
                'user_agent': get_random_user_agent(),
            }
            opts.update(get_site_presets(url))
            
            def get_thumb():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    thumb = info.get('thumbnail')
                    if not thumb and info.get('id'):
                        thumb = f"https://img.youtube.com/vi/{info['id']}/maxresdefault.jpg"
                    return thumb
            
            thumb_url = await run.io_bound(get_thumb)
            add_log(f'Обложка: {thumb_url}', '#38bdf8')
            
            if thumb_url:
                import aiohttp
                headers = {'User-Agent': get_random_user_agent()}
                async with aiohttp.ClientSession() as session:
                    async with session.get(thumb_url, headers=headers) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            suffix = '.jpg' if 'jpg' in thumb_url.lower() else '.png'
                            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                                tmp.write(content)
                                tmp_path = tmp.name
                            ui.download(src=tmp_path, filename=f'thumbnail{suffix}')
                            add_log('Обложка отправлена', '#4ade80')
                            ui.timer(10, lambda p=tmp_path: cleanup_temp(p), once=True)
                        else:
                            ui.notify('Не удалось загрузить обложку', type='warning')
            else:
                ui.notify('Превью не найдено', type='warning')
        except Exception as e:
            add_log(f'Ошибка: {str(e)[:80]}', '#f87171')
            ui.notify(f'Ошибка: {str(e)[:60]}', type='error')

    # ── Paste from clipboard ──────────────────────────────────────
    async def paste_clipboard(e=None):
        try:
            text = await ui.run_javascript('navigator.clipboard.readText()')
            if text:
                url_input.set_value(text.strip())
        except Exception:
            ui.notify('Буфер обмена недоступен (нужен HTTPS)', type='warning', position='top')

    # ── yt-dlp update check ──────────────────────────────────────
    async def check_ytdlp_update():
        add_log('Проверка обновлений yt-dlp...', '#38bdf8')
        local = YtDlpUpdater.get_local_version()
        latest = await run.io_bound(YtDlpUpdater.get_latest_version)
        
        if local and latest:
            add_log(f'yt-dlp: локальная {local} / последняя {latest}', '#94a3b8')
            if local != latest:
                result = await clarify_update(f'Доступна новая версия yt-dlp: {local} → {latest}. Обновить?')
                if result:
                    await run.io_bound(lambda: YtDlpUpdater.update(add_log))
            else:
                add_log('✓ yt-dlp актуален', '#4ade80')
        else:
            add_log(f'yt-dlp: локальная {local or "?"} / последняя {latest or "?"}', '#94a3b8')

    async def clarify_update(msg: str) -> bool:
        result = await ui.confirm(msg, cancel='Позже')
        return result

    # ══════════════════════════════════════════════════════════════
    # UI LAYOUT
    # ══════════════════════════════════════════════════════════════
    
    # ── Top bar ────────────────────────────────────────────────────
    with ui.row().classes('items-center justify-between w-full px-4 mt-6 relative z-10'):
        with ui.row().classes('items-center gap-3'):
            # Logo icon
            ui.icon('download_rounded', size='28px').classes('text-indigo-400')
            # Brand name
            ui.html(
                '<span style="font-size:1.6rem;font-weight:800;letter-spacing:-0.03em;'
                'background:linear-gradient(135deg,#6366f1,#8b5cf6,#ec4899);'
                '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
                'font-family:\'Space Grotesk\',sans-serif;">0xONI Downloader</span>',
                sanitize=False
            )
            # Version badge
            ui.html(
                f'<span style="font-size:0.7rem;padding:2px 8px;border-radius:8px;'
                f'background:rgba(99,102,241,.15);color:#818cf8;font-weight:600;">v{APP_VERSION}</span>',
                sanitize=False
            )
        
        # Theme toggle + counters
        with ui.row().classes('items-center gap-3'):
            ui.html(
                f'<span class="counter-badge">👁 {visitor_count}</span>'
                f'<span class="counter-badge">⬇ {download_count}</span>',
                sanitize=False
            )
            theme_icon = ui.icon('dark_mode', size='20px').classes('cursor-pointer text-gray-400 hover:text-gray-200 transition-colors')
            theme_icon.on('click', lambda: toggle_theme())

    # ── Main card ──────────────────────────────────────────────────
    with ui.card().classes('glass w-full max-w-4xl mx-auto p-6 md:p-8 relative z-10 animate-in'):
        
        # URL input row
        with ui.row().classes('w-full items-center gap-2 mb-4'):
            url_input = ui.input(
                placeholder='https://youtube.com/watch?v=... / rutube / vk / dzen / bilibili ...'
            ).props('outlined clearable dense').classes('flex-1').style('font-size:1rem;')
            
            paste_btn = ui.button(icon='content_paste').props('flat round size=sm').tooltip('Вставить из буфера')
            preview_btn = ui.button(icon='search', color=None).props('flat').tooltip('Анализировать')
            thumb_btn = ui.button(icon='image').props('flat round size=sm').tooltip('Скачать обложку')
            update_btn = ui.button(icon='sync').props('flat round size=sm').tooltip('Проверить обновления yt-dlp')
        
        # Preview strip
        with ui.row().classes('w-full p-3 mb-4 items-center gap-4') as preview_row:
            preview_row.style('background:var(--input-bg);border-radius:var(--radius-sm);border:1px solid var(--border);')
            preview_html = ui.html('', sanitize=False).classes('flex items-center gap-4 w-full')
        preview_row.set_visibility(False)
        
        # Format list (collapsible)
        with ui.expansion('📋 Доступные форматы', icon='list').classes('w-full mb-4').props('header-class="text-sm text-gray-400"'):
            format_col = ui.column().classes('w-full gap-1')
            ui.label('Нажмите "Анализ" для загрузки списка форматов').classes('text-xs text-gray-500')
        
        # Quality + format + speed row
        with ui.row().classes('w-full gap-3 flex-wrap'):
            quality = ui.select(
                ['Авто', '2160', '1440', '1080', '720', '480', '360', '240'],
                label='Качество', value='720'
            ).props('outlined dense').classes('flex-1 min-w-[120px]')
            
            fmt = ui.select(
                ['mp4', 'webm', 'mkv', 'best'],
                label='Формат', value='mp4'
            ).props('outlined dense').classes('flex-1 min-w-[120px]')
            
            speed = ui.select(
                ['Без ограничения', '10M', '5M', '2M', '1M', '500K'],
                label='Скорость', value='Без ограничения'
            ).props('outlined dense').classes('flex-1 min-w-[120px]')
        
        # Checkboxes row
        with ui.row().classes('w-full gap-6 mt-3 flex-wrap'):
            audio_only = ui.checkbox('🎵 Только аудио (MP3)').props('color=indigo')
            subtitles_opt = ui.checkbox('📝 Субтитры (RU/EN)').props('color=indigo')
            enable_trim = ui.checkbox('✂️ Обрезать по времени').props('color=indigo')
        
        # Trim time inputs (hidden until enabled)
        with ui.column().classes('w-full gap-2 mt-2') as trim_row:
            # Range slider — двойной ползунок
            trim_range = ui.range(min=0, max=100, value={'min': 0, 'max': 60}).props('label-always switch-label-side color=indigo').classes('w-full')
            # Метки времени
            with ui.row().classes('w-full justify-between text-xs'):
                trim_start_label = ui.label('0:00').style('color: var(--fg-muted)')
                trim_end_label = ui.label('1:00').style('color: var(--fg-muted)')
            # Текстовые поля для ручного ввода
            with ui.row().classes('w-full gap-3 items-center'):
                start_time = ui.input(label='Начало', placeholder='0 или 00:01:30', value='').props('outlined dense').classes('flex-1')
                end_time = ui.input(label='Конец', placeholder='60 или 00:02:30', value='').props('outlined dense').classes('flex-1')
            trim_row.set_visibility(False)
        
        # Duration cache (заполняется при preview)
        video_duration = 0
        
        def sync_slider_to_text():
            """Обновляет текстовые поля из значений ползунка."""
            v = trim_range.value
            s, e = int(v['min']), int(v['max'])
            ms, ss = divmod(s, 60)
            me, se = divmod(e, 60)
            start_time.set_value(f'{ms}:{ss:02d}')
            end_time.set_value(f'{me}:{se:02d}')
            trim_start_label.set_text(f'{ms}:{ss:02d}')
            trim_end_label.set_text(f'{me}:{se:02d}')
        
        def sync_text_to_slider():
            """Обновляет ползунок из текстовых полей."""
            raw_s = start_time.value.strip()
            raw_e = end_time.value.strip()
            s = _parse_time_to_seconds(raw_s)
            e = _parse_time_to_seconds(raw_e)
            if s is not None and e is not None and s < e:
                trim_range.set_value({'min': s, 'max': e})
                ms, ss = divmod(s, 60)
                me, se = divmod(e, 60)
                trim_start_label.set_text(f'{ms}:{ss:02d}')
                trim_end_label.set_text(f'{me}:{se:02d}')
        
        def _parse_time_to_seconds(val: str) -> int | None:
            """Парсит '1:30' или '90' в секунды."""
            if not val:
                return None
            val = val.strip()
            if val.isdigit():
                return int(val)
            m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$', val)
            if m:
                h = int(m.group(1)) if m.group(3) else 0
                mi = int(m.group(2)) if m.group(3) else int(m.group(1))
                s = int(m.group(3)) if m.group(3) else int(m.group(2))
                return h * 3600 + mi * 60 + s
            return None
        
        trim_range.on('update:model-value', sync_slider_to_text)
        start_time.on('update:model-value', sync_text_to_slider)
        end_time.on('update:model-value', sync_text_to_slider)
        
        def update_trim_range(duration_sec: int):
            """Устанавливает max ползунка = длительности видео."""
            nonlocal video_duration
            video_duration = duration_sec
            if duration_sec > 0:
                trim_range.props(f'max={duration_sec}')
                trim_range.set_value({'min': 0, 'max': min(duration_sec, 60)})
                ms, ss = divmod(duration_sec, 60)
                trim_end_label.set_text(f'{ms}:{ss:02d}')
                sync_slider_to_text()
        
        def toggle_trim(e):
            trim_row.set_visibility(enable_trim.value)
        enable_trim.on('update:model-value', toggle_trim)
        
        # Status dot + text
        status_html = ui.html(
            '<span class="dot dot-idle"></span>'
            '<span style="color:#94a3b8">Готов к работе</span>',
            sanitize=False
        ).classes('mt-4')
        
        # Progress bar
        progress = ui.linear_progress(value=0, show_value=False) \
            .props('instant-feedback size=8px') \
            .classes('mt-2 hidden')
        
        # Download + Cancel buttons
        with ui.row().classes('w-full gap-3 mt-5'):
            download_btn = ui.button(
                '⬇ СКАЧАТЬ', icon='cloud_download'
            ).props('push no-caps size=lg') \
             .classes('btn-primary flex-1 text-white py-4 text-lg')
            
            cancel_btn = ui.button(
                '⏹ ОТМЕНИТЬ', icon='cancel'
            ).props('no-caps size=lg') \
             .classes('btn-danger flex-1 text-white py-4 text-lg hidden')
        
        # Playlist button
        with ui.row().classes('w-full mt-2'):
            playlist_btn = ui.button(
                '📋 Загрузить как плейлист', icon='playlist_play'
            ).props('no-caps').classes('btn-ghost w-full text-sm')

    # ── Playlist panel ─────────────────────────────────────────────
    with ui.card().classes('glass w-full max-w-4xl mx-auto mt-4 p-6 relative z-10') as playlist_panel:
        playlist_panel.set_visibility(False)
        ui.label('Плейлист').classes('text-base font-semibold mb-3').style('color: var(--fg-secondary)')
        playlist_col = ui.column().classes('w-full gap-1')
        with ui.row().classes('w-full gap-3 mt-3'):
            playlist_dl_btn = ui.button('⬇ Скачать выбранное', icon='download').props('no-caps').classes('btn-primary flex-1')
            playlist_cancel_btn = ui.button('⏹ Отменить', icon='cancel').props('no-caps').classes('btn-danger hidden')

    # ── Log expansion ──────────────────────────────────────────────
    with ui.card().classes('glass w-full max-w-4xl mx-auto mt-4 p-6 relative z-10'):
        with ui.expansion('📜 Лог загрузок', icon='terminal').classes('w-full') \
                .props('header-class="text-sm" dense'):
            log_output = ui.html('', sanitize=False).classes(
                'w-full p-4 rounded-xl font-mono text-xs overflow-y-auto h-56 log-scroll'
            ).style(
                'background:rgba(6,8,13,.85);'
                'border:1px solid rgba(99,102,241,.08);'
            )
            with ui.row().classes('mt-2 gap-2'):
                clear_log_btn_el = ui.button('Очистить', icon='delete_sweep').props('flat dense size=sm')
                copy_log_btn_el = ui.button('Копировать', icon='content_copy').props('flat dense size=sm')

    # ── History card ───────────────────────────────────────────────
    with ui.card().classes('glass w-full max-w-4xl mx-auto mt-4 mb-12 p-6 relative z-10'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('📂 История загрузок').classes('text-base font-semibold').style('color: var(--fg-secondary)')
            clear_history_btn_el = ui.button('Очистить', icon='delete').props('flat dense size=sm')
        history_col = ui.column().classes('w-full gap-2 mt-3')

    # ══════════════════════════════════════════════════════════════
    # EVENT BINDINGS
    # ══════════════════════════════════════════════════════════════
    
    # Clear log
    def clear_log_btn(e=None):
        async def confirm():
            result = await ui.confirm('Очистить весь лог?', cancel='Нет')
            if result:
                client_log.clear()
                update_log()
                ui.notify('Лог очищен', type='positive', position='top')
        confirm()

    def copy_log_btn(e=None):
        plain = re.sub(r'<[^>]+>', '', '\n'.join(client_log))
        safe_str = json.dumps(plain)
        ui.run_javascript(f'navigator.clipboard.writeText({safe_str})')
        ui.notify('Скопировано', type='positive', position='top')

    def clear_history_btn(e=None):
        async def confirm():
            result = await ui.confirm('Очистить всю историю загрузок?', cancel='Нет')
            if result:
                history_data.clear()
                render_history()
                ui.notify('История очищена', type='positive', position='top')
        confirm()

    # Playlist analysis trigger
    async def analyze_and_show_playlist(e=None):
        url = (url_input.value or '').strip()
        if not url:
            ui.notify('Вставьте ссылку на плейлист/канал', type='warning')
            return
        await analyze_playlist(url)
        playlist_panel.set_visibility(True)
        playlist_dl_btn.classes(remove='hidden')
        playlist_cancel_btn.classes(add='hidden')

    # Playlist download
    async def start_playlist_download(e=None):
        nonlocal is_downloading
        if is_downloading:
            return
        playlist_dl_btn.classes(add='hidden')
        playlist_cancel_btn.classes(remove='hidden')
        await download_playlist_action()
        playlist_dl_btn.classes(remove='hidden')
        playlist_cancel_btn.classes(add='hidden')

    async def cancel_playlist_download(e=None):
        nonlocal cancel_requested
        cancel_requested = True
        add_log('⏹ Отмена плейлиста...', '#fbbf24')

    # Bind buttons
    download_btn.on('click', start_download)
    cancel_btn.on('click', cancel_download)
    paste_btn.on('click', paste_clipboard)
    preview_btn.on('click', preview_video)
    thumb_btn.on('click', download_thumbnail)
    update_btn.on('click', check_ytdlp_update)
    playlist_btn.on('click', analyze_and_show_playlist)
    playlist_dl_btn.on('click', start_playlist_download)
    playlist_cancel_btn.on('click', cancel_playlist_download)
    clear_log_btn_el.on('click', clear_log_btn)
    copy_log_btn_el.on('click', copy_log_btn)
    clear_history_btn_el.on('click', clear_history_btn)

    # Initial states
    render_history()
    update_log()
    
    # Progress polling
    ui.timer(0.3, lambda: poll_progress())

    def poll_progress():
        p = progress_info
        if p['phase'] == 'downloading':
            progress.value = p['percent'] / 100.0
            set_status(
                f"Загрузка {p['percent']:.1f}%  —  {p['speed']}  —  {p['eta']}",
                'active'
            )
        elif p['phase'] == 'merging':
            set_status('Слияние аудио и видео...', 'active')
        elif p['phase'] == 'converting':
            elapsed = int(time.time() - p.get('convert_start', time.time()))
            progress.props('indeterminate')
            progress.classes(remove='hidden')
            set_status(f'Конвертация в MP3… {elapsed}с', 'active')

    # Check yt-dlp version on startup (silently)
    async def startup_check():
        await asyncio.sleep(2)
        local = YtDlpUpdater.get_local_version()
        if local:
            add_log(f'yt-dlp v{local} · 0xONI Downloader v{APP_VERSION}', '#475569')

    ui.timer(3, lambda: startup_check(), once=True)


# ─── Background cleanup timer ────────────────────────────────────
_cleanup_timer = None

def _background_cleanup():
    global _cleanup_timer
    cleanup_downloads()
    _cleanup_timer = threading.Timer(900, _background_cleanup)
    _cleanup_timer.daemon = True
    _cleanup_timer.start()

_background_cleanup()

# ─── Run ──────────────────────────────────────────────────────────
ui.run(
    title='0xONI Downloader',
    favicon='icon.ico',
    port=8765,
    host='0.0.0.0',
    storage_secret='0xoni_downloader_secret_2025'
)
