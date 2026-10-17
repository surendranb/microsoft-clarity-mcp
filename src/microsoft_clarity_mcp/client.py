# SPDX-License-Identifier: MIT
"""Microsoft Clarity API client with error absorption, rate-limit defense, and caching."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from microsoft_clarity_mcp.cache import (
    DAILY_REQUEST_LIMIT,
    get_cached_data,
    get_daily_usage,
    is_quota_exhausted,
    make_cache_key,
    record_api_call,
    set_cached_data,
)

CLARITY_API_BASE_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

VALID_DIMENSIONS = {
    "url": "URL",
    "device": "Device",
    "browser": "Browser",
    "os": "OS",
    "country": "Country/Region",
    "country/region": "Country/Region",
    "source": "Source",
    "medium": "Medium",
    "campaign": "Campaign",
    "channel": "Channel",
}

KNOWN_PROJECTS = {
    "surendranb.com": "yz5idaioq2",
    "freeinference.dev": "yz5j1y2n6n",
    "builditwithai.xyz": "yz5jgqt3e3",
}


def normalize_dimension(dimension: str) -> str:
    """Normalize user input to canonical Microsoft Clarity dimension name."""
    cleaned = dimension.strip().lower()
    if cleaned in VALID_DIMENSIONS:
        return VALID_DIMENSIONS[cleaned]
    # Check if exact title-case match
    for canonical in VALID_DIMENSIONS.values():
        if dimension.strip() == canonical:
            return canonical
    valid_list = ", ".join(sorted(set(VALID_DIMENSIONS.values())))
    raise ValueError(
        f"[INPUT_FIXABLE] Invalid dimension '{dimension}'. Supported dimensions are: {valid_list}."
    )


def resolve_token(token: Optional[str] = None) -> str:
    """Resolve API token from argument or environment variables."""
    if token and token.strip():
        return token.strip()
    env_token = os.environ.get("CLARITY_API_TOKEN") or os.environ.get("CLARITY_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()
    raise ValueError(
        "[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN] Missing Microsoft Clarity API Token.\n"
        "To generate an API token:\n"
        "1. Open your project on https://clarity.microsoft.com\n"
        "2. Navigate to Settings -> Data Export\n"
        "3. Click 'Generate new API token' and copy the token\n"
        "4. Set environment variable CLARITY_API_TOKEN=<token> or pass token parameter directly."
    )


def validate_request_params(project_id: str, num_of_days: int) -> None:
    """Validate project ID and lookback days."""
    if not project_id or not project_id.strip():
        known_str = ", ".join(f"{domain} ({pid})" for domain, pid in KNOWN_PROJECTS.items())
        raise ValueError(
            f"[INPUT_FIXABLE] project_id is required. Known projects: {known_str}."
        )
    if num_of_days not in (1, 2, 3):
        raise ValueError(
            f"[INPUT_FIXABLE] num_of_days must be 1, 2, or 3 (representing last 24h, 48h, or 72h). Received: {num_of_days}."
        )


class ClarityClient:
    """Client for Microsoft Clarity Data Export API with defensive caching."""

    def __init__(self, base_url: str = CLARITY_API_BASE_URL, session: Optional[requests.Session] = None):
        self.base_url = base_url
        self.session = session or requests.Session()

    def fetch_live_insights(
        self,
        project_id: str,
        num_of_days: int = 3,
        dimensions: Optional[List[str]] = None,
        token: Optional[str] = None,
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Fetch live insights with rate-limit defense and on-disk caching."""
        validate_request_params(project_id, num_of_days)
        api_token = resolve_token(token)

        normalized_dims: List[str] = []
        if dimensions:
            normalized_dims = [normalize_dimension(d) for d in dimensions if d and d.strip()]

        cache_key = make_cache_key(project_id, "project-live-insights", num_of_days, normalized_dims)
        usage = get_daily_usage(project_id)

        # 1. Check fresh cache
        if not force_refresh:
            cached_payload, is_stale, cached_at = get_cached_data(cache_key, ttl=ttl, allow_stale=False)
            if cached_payload is not None:
                return {
                    "project_id": project_id,
                    "num_of_days": num_of_days,
                    "dimensions": normalized_dims,
                    "data_source": "cache",
                    "cached_at_utc": cached_at,
                    "daily_calls_used": usage["calls_used"],
                    "remaining_daily_requests": usage["remaining_quota"],
                    "daily_limit": DAILY_REQUEST_LIMIT,
                    "raw_data": cached_payload,
                }

        # 2. Check if daily quota is exhausted
        if is_quota_exhausted(project_id):
            cached_payload, is_stale, cached_at = get_cached_data(cache_key, ttl=ttl, allow_stale=True)
            if cached_payload is not None:
                return {
                    "project_id": project_id,
                    "num_of_days": num_of_days,
                    "dimensions": normalized_dims,
                    "data_source": "stale_cache",
                    "warning": (
                        f"[WARNING: DAILY QUOTA EXHAUSTED] {usage['calls_used']}/{DAILY_REQUEST_LIMIT} "
                        f"requests used today for project '{project_id}'. Serving cached data from {cached_at} UTC."
                    ),
                    "cached_at_utc": cached_at,
                    "daily_calls_used": usage["calls_used"],
                    "remaining_daily_requests": 0,
                    "daily_limit": DAILY_REQUEST_LIMIT,
                    "raw_data": cached_payload,
                }
            raise RuntimeError(
                f"[TRANSIENT] Microsoft Clarity daily request limit reached "
                f"({DAILY_REQUEST_LIMIT}/{DAILY_REQUEST_LIMIT} requests used today for project '{project_id}'). "
                f"Quota resets at 00:00 UTC. No cached data available for this query."
            )

        # 3. Perform Live HTTP request
        params: Dict[str, str] = {"numOfDays": str(num_of_days)}
        for idx, dim in enumerate(normalized_dims[:3], start=1):
            params[f"dimension{idx}"] = dim

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "microsoft-clarity-mcp/0.1.0",
        }

        try:
            resp = self.session.get(self.base_url, params=params, headers=headers, timeout=15.0)
        except requests.RequestException as exc:
            # Network failure: check for stale cache fallback
            cached_payload, _, cached_at = get_cached_data(cache_key, ttl=ttl, allow_stale=True)
            if cached_payload is not None:
                return {
                    "project_id": project_id,
                    "num_of_days": num_of_days,
                    "dimensions": normalized_dims,
                    "data_source": "stale_cache",
                    "warning": f"[WARNING: NETWORK FAILURE] Request failed ({exc}); serving stale cached data.",
                    "cached_at_utc": cached_at,
                    "daily_calls_used": usage["calls_used"],
                    "remaining_daily_requests": usage["remaining_quota"],
                    "daily_limit": DAILY_REQUEST_LIMIT,
                    "raw_data": cached_payload,
                }
            raise RuntimeError(
                f"[TRANSIENT] Failed to connect to Microsoft Clarity API: {exc}. Please retry."
            )

        # 4. Handle HTTP responses
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(
                    f"[TRANSIENT] Received invalid JSON from Microsoft Clarity API: {e} (content: {resp.text[:200]})"
                )

            # Record call and cache payload
            calls_used = record_api_call(project_id)
            set_cached_data(cache_key, data, ttl=ttl)
            remaining = max(0, DAILY_REQUEST_LIMIT - calls_used)

            return {
                "project_id": project_id,
                "num_of_days": num_of_days,
                "dimensions": normalized_dims,
                "data_source": "live_api",
                "daily_calls_used": calls_used,
                "remaining_daily_requests": remaining,
                "daily_limit": DAILY_REQUEST_LIMIT,
                "raw_data": data,
            }

        if resp.status_code in (401, 403):
            raise PermissionError(
                f"[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN] Authentication failed (HTTP {resp.status_code}): "
                f"Invalid or expired Microsoft Clarity API token for project '{project_id}'.\n"
                f"To generate a valid token:\n"
                f"1. Open https://clarity.microsoft.com\n"
                f"2. Go to Settings -> Data Export\n"
                f"3. Click 'Generate new API token'\n"
                f"4. Export CLARITY_API_TOKEN=<token>"
            )

        if resp.status_code == 400:
            raise ValueError(
                f"[INPUT_FIXABLE] Bad request to Microsoft Clarity API (HTTP 400): {resp.text}. "
                f"Check num_of_days ({num_of_days}) and dimensions ({normalized_dims})."
            )

        if resp.status_code == 429:
            # Force quota to limit
            while get_daily_usage(project_id)["calls_used"] < DAILY_REQUEST_LIMIT:
                record_api_call(project_id)
            cached_payload, _, cached_at = get_cached_data(cache_key, ttl=ttl, allow_stale=True)
            if cached_payload is not None:
                return {
                    "project_id": project_id,
                    "num_of_days": num_of_days,
                    "dimensions": normalized_dims,
                    "data_source": "stale_cache",
                    "warning": f"[WARNING: 429 RATE LIMIT EXCEEDED] Serving cached data from {cached_at} UTC.",
                    "cached_at_utc": cached_at,
                    "daily_calls_used": DAILY_REQUEST_LIMIT,
                    "remaining_daily_requests": 0,
                    "daily_limit": DAILY_REQUEST_LIMIT,
                    "raw_data": cached_payload,
                }
            raise RuntimeError(
                f"[TRANSIENT] Microsoft Clarity daily request limit reached (HTTP 429: 10 requests/day per project). "
                f"Quota resets at 00:00 UTC."
            )

        raise RuntimeError(
            f"[TRANSIENT] Microsoft Clarity API returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
