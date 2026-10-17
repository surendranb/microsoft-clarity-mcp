# SPDX-License-Identifier: MIT
"""Persistent on-disk cache & rate-limit tracking for Microsoft Clarity MCP.

Microsoft Clarity strictly enforces a quota of 10 requests per project per day.
This module maintains:
1. Daily request counters per project per UTC date.
2. Response caching with configurable TTL (default 1 hour / 3600s) to absorb
   repeated agent queries and guard the user's quota.
3. Stale cache fallback if the daily quota is exhausted.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DAILY_REQUEST_LIMIT = 10
DEFAULT_CACHE_TTL = 3600  # 1 hour in seconds

_CACHE_LOCK = threading.Lock()


def get_cache_path() -> Path:
    """Resolve the cache file path honoring environment overrides."""
    if os.environ.get("CLARITY_CACHE_PATH"):
        return Path(os.environ["CLARITY_CACHE_PATH"])
    cache_dir = Path(os.environ.get("CLARITY_CACHE_DIR", Path.home() / ".clarity_mcp"))
    return cache_dir / "cache.json"


def get_default_ttl() -> int:
    """Get the default cache TTL in seconds."""
    try:
        return int(os.environ.get("CLARITY_CACHE_TTL", str(DEFAULT_CACHE_TTL)))
    except ValueError:
        return DEFAULT_CACHE_TTL


def get_today_utc() -> str:
    """Get current UTC date string YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_cache_file() -> Dict[str, Any]:
    path = get_cache_path()
    if not path.exists():
        return {"calls": {}, "entries": {}}
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return {"calls": {}, "entries": {}}
        data = json.loads(content)
        if not isinstance(data, dict):
            return {"calls": {}, "entries": {}}
        data.setdefault("calls", {})
        data.setdefault("entries", {})
        return data
    except Exception:
        return {"calls": {}, "entries": {}}


def _write_cache_file(data: Dict[str, Any]) -> None:
    path = get_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        # Fallback direct write
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def make_cache_key(
    project_id: str,
    endpoint: str = "project-live-insights",
    num_of_days: int = 3,
    dimensions: Optional[List[str]] = None,
) -> str:
    """Generate a canonical cache key."""
    dims = ",".join(sorted(d.strip() for d in (dimensions or []) if d and d.strip()))
    return f"{project_id.strip()}:{endpoint}:{num_of_days}:{dims}"


def get_daily_usage(project_id: str, date_str: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve daily call count and remaining quota for a project."""
    target_date = date_str or get_today_utc()
    with _CACHE_LOCK:
        data = _read_cache_file()
        project_calls = data.get("calls", {}).get(project_id, {})
        calls = project_calls.get(target_date, 0)

    remaining = max(0, DAILY_REQUEST_LIMIT - calls)
    return {
        "project_id": project_id,
        "date_utc": target_date,
        "calls_used": calls,
        "remaining_quota": remaining,
        "daily_limit": DAILY_REQUEST_LIMIT,
        "quota_exhausted": calls >= DAILY_REQUEST_LIMIT,
    }


def record_api_call(project_id: str, date_str: Optional[str] = None) -> int:
    """Increment the daily call counter for a project and persist it."""
    target_date = date_str or get_today_utc()
    with _CACHE_LOCK:
        data = _read_cache_file()
        project_calls = data.setdefault("calls", {}).setdefault(project_id, {})
        new_count = project_calls.get(target_date, 0) + 1
        project_calls[target_date] = new_count
        _write_cache_file(data)
        return new_count


def is_quota_exhausted(project_id: str, date_str: Optional[str] = None) -> bool:
    """Check if the daily quota is already exhausted."""
    usage = get_daily_usage(project_id, date_str)
    return usage["quota_exhausted"]


def get_cached_data(
    key: str,
    ttl: Optional[int] = None,
    allow_stale: bool = False,
) -> Tuple[Optional[Any], bool, Optional[str]]:
    """Retrieve cached data for a key.

    Returns:
        (data, is_stale, cached_at_utc)
        If not found or expired (and allow_stale is False), data is None.
        If found and still within TTL, is_stale is False.
        If found but past TTL, and allow_stale is True, is_stale is True.
    """
    effective_ttl = ttl if ttl is not None else get_default_ttl()
    now = time.time()

    with _CACHE_LOCK:
        data = _read_cache_file()
        entry = data.get("entries", {}).get(key)

    if not entry:
        return None, False, None

    cached_ts = entry.get("timestamp", 0)
    cached_at = entry.get("cached_at_utc")
    entry_ttl = entry.get("ttl", effective_ttl)
    payload = entry.get("data")

    age = now - cached_ts
    if age <= entry_ttl:
        return payload, False, cached_at

    if allow_stale:
        return payload, True, cached_at

    return None, False, None


def set_cached_data(key: str, payload: Any, ttl: Optional[int] = None) -> None:
    """Store data in cache."""
    effective_ttl = ttl if ttl is not None else get_default_ttl()
    now_ts = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    with _CACHE_LOCK:
        data = _read_cache_file()
        data.setdefault("entries", {})[key] = {
            "timestamp": now_ts,
            "cached_at_utc": now_iso,
            "ttl": effective_ttl,
            "data": payload,
        }
        _write_cache_file(data)


def clear_cache() -> None:
    """Wipe cache file (used primarily for tests)."""
    with _CACHE_LOCK:
        path = get_cache_path()
        if path.exists():
            path.unlink()
