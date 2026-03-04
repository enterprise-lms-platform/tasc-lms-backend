"""
Pure helpers for external video embedding (YouTube, Vimeo, Loom).
Uses only stdlib urllib.parse; no Django/DRF imports.
"""

from urllib.parse import urlparse, parse_qs
import re


def _is_https(url: str) -> bool:
    """Return True if URL uses https scheme."""
    try:
        parsed = urlparse(url)
        return parsed.scheme == 'https'
    except Exception:
        return False


def detect_provider(url: str) -> str | None:
    """
    Detect video provider from URL. Returns lowercase provider name or None.
    Only https URLs are accepted.
    """
    if not url or not isinstance(url, str):
        return None
    if not _is_https(url):
        return None

    parsed = urlparse(url)
    host = (parsed.netloc or '').lower()

    if 'youtube.com' in host or 'youtu.be' in host:
        return 'youtube'
    if 'vimeo.com' in host:
        return 'vimeo'
    if 'loom.com' in host:
        return 'loom'
    return None


def to_embed_url(url: str) -> str | None:
    """
    Convert a watch/share URL to an embed URL.
    Returns None for unknown providers or non-https URLs.
    """
    if not url or not isinstance(url, str):
        return None
    if not _is_https(url):
        return None

    parsed = urlparse(url)
    host = (parsed.netloc or '').lower()
    path = (parsed.path or '').strip('/')

    # YouTube
    if 'youtube.com' in host:
        qs = parse_qs(parsed.query)
        vid = (qs.get('v') or [None])[0]
        if vid:
            return f'https://www.youtube.com/embed/{vid}'
    if 'youtu.be' in host:
        vid = path.split('/')[0] if path else None
        if vid:
            return f'https://www.youtube.com/embed/{vid}'

    # Vimeo: https://vimeo.com/123456789 -> https://player.vimeo.com/video/123456789
    if 'vimeo.com' in host:
        video_id = path.split('/')[0] if path else None
        if video_id and re.match(r'^\d+$', video_id):
            return f'https://player.vimeo.com/video/{video_id}'

    # Loom: https://www.loom.com/share/ID -> https://www.loom.com/embed/ID
    if 'loom.com' in host:
        parts = path.split('/')
        try:
            share_idx = parts.index('share')
        except ValueError:
            return None
        if share_idx + 1 < len(parts):
            embed_id = parts[share_idx + 1]
            if embed_id:
                return f'https://www.loom.com/embed/{embed_id}'
    return None


def validate_external_video_url(url: str) -> tuple[str, str]:
    """
    Validate external video URL and return (provider, embed_url).
    Raises ValueError if URL is invalid or provider is unsupported.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise ValueError("external_video_url is required.")
    if not _is_https(url):
        raise ValueError("Only https URLs are allowed.")

    provider = detect_provider(url)
    embed_url = to_embed_url(url)

    if not provider or not embed_url:
        raise ValueError(
            "Unsupported video provider. Allowed: YouTube, Vimeo, Loom."
        )
    return provider, embed_url
