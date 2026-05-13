"""
core/fonts.py — Cross-platform Devanagari font management

Ensures a Devanagari-capable font is always available for:
  - PIL text rendering (intro/outro title cards)
  - FFmpeg subtitle burning (hard-coded captions)

Strategy:
  1. Search system fonts (Windows registry, Linux paths)
  2. If no Devanagari font found, auto-download Noto Sans Devanagari
  3. Cache downloaded fonts in project directory for offline reuse
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# ── Font cache directory ─────────────────────────────────────────────────

def _font_cache_dir() -> Path:
    """Get or create the font cache directory inside the project."""
    # Use project-level fonts/ directory so it persists and is portable
    base = Path(__file__).parent.parent
    cache = base / "fonts"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


# ── System font discovery ───────────────────────────────────────────────

def _find_system_devanagari_font() -> Path:
    """
    Find a system font that supports Devanagari script.
    Returns the path to the font file, or empty Path() if none found.
    """
    # Windows: check registry for Devanagari fonts
    if sys.platform == "win32" or os.name == "nt":
        font = _find_windows_devanagari_font()
        if font and font.exists():
            return font

        # Direct path checks (try both system and per-user font directories)
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        system_fonts_dir = Path(sys_root) / "Fonts"
        
        # Per-user fonts directory (Windows 10+)
        user_profile = os.environ.get("USERPROFILE", "")
        user_fonts_dir = Path(user_profile) / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" if user_profile else None
        
        candidates = [
            # Devanagari fonts (highest priority)
            "Mangal.ttf", "mangal.ttf", "MANGAL.TTF",
            "Nirmala.ttf", "nirmala.ttf", "NIRMALA.TTF",
            "Nirmalab.ttf", "nirmalab.ttf", "NIRMALAB.TTF",
            "Nirmalas.ttf", "nirmalas.ttf", "NIRMALAS.TTF",
            # Unicode fonts with Devanagari support
            "Arialuni.ttf", "ARIALUNI.TTF", "arialuni.ttf",
            "seguiemj.ttf", "SEGUIEMJ.TTF",  # Segoe UI Emoji (has broad Unicode)
            "segoeui.ttf", "SEGOEUI.TTF",    # Segoe UI (limited Devanagari)
        ]
        
        # Check system fonts directory
        for fname in candidates:
            p = system_fonts_dir / fname
            if p.exists():
                return p
        
        # Check per-user fonts directory
        if user_fonts_dir and user_fonts_dir.exists():
            for fname in candidates:
                p = user_fonts_dir / fname
                if p.exists():
                    return p
        
        # Try globbing the Windows Fonts directory for any .ttf with "mangal" or "nirmala" in name
        try:
            for p in system_fonts_dir.glob("*angal*"):
                if p.suffix.lower() in (".ttf", ".ttc"):
                    return p
            for p in system_fonts_dir.glob("*irmala*"):
                if p.suffix.lower() in (".ttf", ".ttc"):
                    return p
        except Exception:
            pass

    # Linux: check standard font directories
    linux_dirs = [
        "/usr/share/fonts/truetype/freefont",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/truetype/chinese",
        "/usr/share/fonts/truetype/liberation",
    ]
    linux_fonts = [
        "FreeSans.ttf", "FreeSansBold.ttf",
        "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
        "NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf",
    ]
    for d in linux_dirs:
        if os.path.isdir(d):
            for fname in linux_fonts:
                p = Path(d) / fname
                if p.exists():
                    return p

    # macOS
    mac_paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for p in mac_paths:
        if Path(p).exists():
            return Path(p)

    return Path()


def _find_windows_devanagari_font() -> Path:
    """Use Windows registry to find Devanagari-capable fonts."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        )
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        fonts_dir = Path(sys_root) / "Fonts"

        # Keywords that indicate Devanagari support
        devanagari_keywords = ["mangal", "nirmala", "devanagari", "noto sans devanagari"]

        for i in range(winreg.QueryInfoKey(key)[1]):
            try:
                name, value, _ = winreg.EnumValue(key, i)
                name_lower = name.lower()
                for kw in devanagari_keywords:
                    if kw in name_lower:
                        # value is the font filename (relative to Fonts dir or absolute)
                        font_path = Path(value)
                        if not font_path.is_absolute():
                            font_path = fonts_dir / value
                        if font_path.exists():
                            return font_path
            except OSError:
                break
    except Exception:
        pass
    return Path()


# ── Font download (Noto Sans Devanagari) ────────────────────────────────

# Multiple download sources for reliability
# Noto Sans Devanagari supports Hindi, Marathi, and other Devanagari scripts
# Also supports Latin, so it works as a universal font for all languages
_FONT_DOWNLOAD_URLS = [
    # Source 1: GitHub raw (static weight, most compatible with PIL)
    ("NotoSansDevanagari-Regular.ttf",
     "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Regular.ttf"),
    ("NotoSansDevanagari-Bold.ttf",
     "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Bold.ttf"),
    # Source 2: GitHub raw (variable font — may not work with older PIL)
    ("NotoSansDevanagari-VF.ttf",
     "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"),
    # Source 3: Noto Sans (supports Latin + some Devanagari via fallback)
    ("NotoSans-VF.ttf",
     "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"),
    # Source 4: CDN mirrors
    ("NotoSansDevanagari-Regular.ttf",
     "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosansdevanagari/static/NotoSansDevanagari-Regular.ttf"),
    ("NotoSansDevanagari-Bold.ttf",
     "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosansdevanagari/static/NotoSansDevanagari-Bold.ttf"),
]


def _download_font(name: str, url: str, target: Path, timeout: int = 30) -> bool:
    """Download a font file from URL to target path."""
    try:
        print(f"    Downloading {name}...")
        import socket
        # Use urlopen with timeout, then save manually (urlretrieve doesn't support timeout)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            if len(data) > 1000:
                target.write_bytes(data)
                return True
        target.unlink(missing_ok=True)
    except Exception as e:
        print(f"    Download failed for {name}: {e}")
        target.unlink(missing_ok=True)
    return False


def ensure_devanagari_font() -> Path:
    """
    Ensure a Devanagari-capable font is available.
    Returns the path to the regular-weight font file.

    Priority:
      1. Already cached in project fonts/ directory
      2. System font with Devanagari support
      3. Downloaded Noto Sans Devanagari
      4. Downloaded Noto Sans (fallback)
    """
    cache = _font_cache_dir()

    # Check if we already have a cached/project font. The repo ships variable
    # Noto Devanagari and Nirmala fonts, so prefer them before going online.
    for fname in [
        "NotoSansDevanagari-Regular.ttf",
        "NotoSansDevanagari-VF.ttf",
        "Nirmala.ttc",
        "Mangal.ttf",
        "NotoSans-Regular.ttf",
        "NotoSans-VF.ttf",
    ]:
        cached = cache / fname
        if cached.exists() and cached.stat().st_size > 1000:
            return cached

    # Try system fonts
    system_font = _find_system_devanagari_font()
    if system_font and system_font.exists():
        # Copy system font to cache for consistent access
        try:
            import shutil
            cached = cache / system_font.name
            if not cached.exists():
                shutil.copy2(system_font, cached)
            return cached
        except Exception:
            return system_font

    # Download fonts — try all sources until we get a working one
    print("    No Devanagari font found on system. Downloading Noto Sans Devanagari...")
    for name, url in _FONT_DOWNLOAD_URLS:
        target = cache / name
        if target.exists() and target.stat().st_size > 1000:
            # Already downloaded successfully
            continue
        # Skip if we already tried this filename (different URL for same file)
        if target.exists() and target.stat().st_size <= 1000:
            target.unlink(missing_ok=True)
        _download_font(name, url, target)

    # Check if download succeeded — try in priority order
    for fname in ["NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-VF.ttf",
                   "NotoSans-VF.ttf"]:
        cached = cache / fname
        if cached.exists() and cached.stat().st_size > 1000:
            return cached

    # Last resort: return empty path (will use default font)
    print("    WARNING: Could not download Devanagari font. Text may show as boxes.")
    return Path()


def ensure_devanagari_font_bold() -> Path:
    """Ensure a bold-weight Devanagari font is available."""
    cache = _font_cache_dir()

    # Check cache
    for fname in [
        "NotoSansDevanagari-Bold.ttf",
        "NotoSansDevanagari-VF.ttf",
        "Nirmalab.ttf",
        "Nirmala.ttc",
        "Mangal.ttf",
    ]:
        cached = cache / fname
        if cached.exists() and cached.stat().st_size > 1000:
            return cached

    # Try system fonts (look for bold variants)
    if sys.platform == "win32" or os.name == "nt":
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        fonts_dir = Path(sys_root) / "Fonts"
        for fname in ["Mangal.ttf", "Nirmalab.ttf", "nirmalab.ttf"]:
            p = fonts_dir / fname
            if p.exists():
                return p

    # Download
    for name, url in _FONT_DOWNLOAD_URLS:
        target = cache / name
        if target.exists() and target.stat().st_size > 1000:
            continue
        if target.exists() and target.stat().st_size <= 1000:
            target.unlink(missing_ok=True)
        _download_font(name, url, target)

    # Check for bold font
    bold = cache / "NotoSansDevanagari-Bold.ttf"
    if bold.exists() and bold.stat().st_size > 1000:
        return bold

    # If no bold found, use regular (same font, different weight)
    regular = ensure_devanagari_font()
    if regular and regular.exists():
        return regular

    return Path()


# ── PIL Font Loader ─────────────────────────────────────────────────────

def get_pil_font(size: int, bold: bool = False):
    """
    Get a PIL ImageFont that supports Devanagari (Hindi/Marathi),
    Latin, and common Unicode scripts.

    Uses cached/downloaded font first, then falls back to system fonts.
    """
    from PIL import ImageFont

    # Try cached/downloaded Devanagari font first
    if bold:
        font_path = ensure_devanagari_font_bold()
    else:
        font_path = ensure_devanagari_font()

    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except (IOError, OSError):
            pass

    # Fall back to system font paths
    candidates = _system_font_paths(bold)
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue

    # Last resort: PIL default (may show boxes for Devanagari)
    return ImageFont.load_default()


def _system_font_paths(bold: bool = False) -> list[str]:
    """Get a list of system font file paths to try."""
    paths = []

    if sys.platform == "win32" or os.name == "nt":
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        fd = Path(sys_root) / "Fonts"
        paths = [
            str(fd / ("arialbd.ttf" if bold else "arial.ttf")),
            str(fd / "Mangal.ttf"),
            str(fd / "mangal.ttf"),
            str(fd / "Nirmala.ttf"),
            str(fd / "nirmala.ttf"),
            str(fd / "Nirmalab.ttf"),
            str(fd / "Arialuni.ttf"),
        ]
    else:
        paths = [
            f"/usr/share/fonts/truetype/freefont/{'FreeSansBold.ttf' if bold else 'FreeSans.ttf'}",
            f"/usr/share/fonts/truetype/dejavu/{'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'}",
            f"/usr/share/fonts/truetype/chinese/{'NotoSansSC-Bold.ttf' if bold else 'NotoSansSC-Regular.ttf'}",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    return paths


# ── FFmpeg Font Helpers ─────────────────────────────────────────────────

def get_ffmpeg_font_dir() -> str:
    """
    Get the directory containing the best Devanagari-capable font for FFmpeg.
    Returns an absolute path string, or empty string if not found.
    """
    # Check cached/downloaded font first
    cache = _font_cache_dir()
    # Check if any TTF files exist in the cache
    for fname in [
        "NotoSansDevanagari-Regular.ttf",
        "NotoSansDevanagari-Bold.ttf",
        "NotoSansDevanagari-VF.ttf",
        "Nirmala.ttc",
        "Nirmala.ttf",
        "Mangal.ttf",
        "NotoSans-Regular.ttf",
        "NotoSans-VF.ttf",
    ]:
        if (cache / fname).exists():
            return str(cache)

    # Check system font directories
    font_path = _find_system_devanagari_font()
    if font_path and font_path.exists():
        return str(font_path.parent)

    return ""


def get_ffmpeg_font_name(language: str = "en") -> str:
    """
    Get the best font name for FFmpeg subtitle rendering.
    For Hindi/Marathi, must use a font with Devanagari support.
    """
    if language in ("hi", "mr"):
        # Check if we have a cached/downloaded font
        cache = _font_cache_dir()
        if (cache / "Nirmala.ttc").exists() or (cache / "Nirmala.ttf").exists():
            return "Nirmala UI"
        if (
            (cache / "NotoSansDevanagari-Regular.ttf").exists()
            or (cache / "NotoSansDevanagari-Bold.ttf").exists()
            or (cache / "NotoSansDevanagari-VF.ttf").exists()
        ):
            return "Noto Sans Devanagari"
        if (cache / "Mangal.ttf").exists():
            return "Mangal"
        if (cache / "NotoSans-Regular.ttf").exists() or (cache / "NotoSans-VF.ttf").exists():
            return "Noto Sans"

        # System fonts
        if sys.platform == "win32" or os.name == "nt":
            return "Mangal"  # Built-in Windows Devanagari font

        # Linux
        font_dir = "/usr/share/fonts/truetype/freefont"
        if os.path.isdir(font_dir) and os.path.isfile(os.path.join(font_dir, "FreeSans.ttf")):
            return "FreeSans"
        if os.path.isdir("/usr/share/fonts/truetype/dejavu"):
            return "DejaVu Sans"

        return "NotoSansDevanagari-Regular"  # Best guess if downloaded

    return "Arial"


def find_ffmpeg_binary() -> str:
    """Find the FFmpeg binary path."""
    import shutil
    # Check common Windows location first
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for path in candidates:
        if Path(path).exists():
            return str(path)
    # Check PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"
