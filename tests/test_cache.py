# SPDX-License-Identifier: MIT
"""Unit tests for cache and rate limit defense."""

import time
from microsoft_clarity_mcp.cache import (
    DAILY_REQUEST_LIMIT,
    clear_cache,
    get_cached_data,
    get_daily_usage,
    is_quota_exhausted,
    make_cache_key,
    record_api_call,
    set_cached_data,
)
from tests.conftest import PROJECT_SURENDRANB


def test_make_cache_key_consistency():
    k1 = make_cache_key(PROJECT_SURENDRANB, "project-live-insights", 3, ["URL", "Device"])
    k2 = make_cache_key(PROJECT_SURENDRANB, "project-live-insights", 3, ["Device", "URL"])
    assert k1 == k2
    assert "yz5idaioq2:project-live-insights:3:Device,URL" == k1


def test_cache_miss_initially():
    key = make_cache_key(PROJECT_SURENDRANB, num_of_days=3)
    data, is_stale, cached_at = get_cached_data(key)
    assert data is None
    assert is_stale is False
    assert cached_at is None


def test_cache_hit_within_ttl():
    key = make_cache_key(PROJECT_SURENDRANB, num_of_days=3)
    mock_payload = [{"metricName": "Traffic", "information": [{"sessions": "100"}]}]
    set_cached_data(key, mock_payload, ttl=3600)

    data, is_stale, cached_at = get_cached_data(key, ttl=3600)
    assert data == mock_payload
    assert is_stale is False
    assert cached_at is not None


def test_cache_expiration_and_stale_fallback():
    key = make_cache_key(PROJECT_SURENDRANB, num_of_days=1)
    mock_payload = {"test": 123}
    # Set with 0-second TTL
    set_cached_data(key, mock_payload, ttl=0)
    time.sleep(0.01)

    # Normal fetch should expire
    data, is_stale, _ = get_cached_data(key, ttl=0, allow_stale=False)
    assert data is None

    # Stale fetch should return data with is_stale=True
    data, is_stale, cached_at = get_cached_data(key, ttl=0, allow_stale=True)
    assert data == mock_payload
    assert is_stale is True
    assert cached_at is not None


def test_daily_quota_counter_and_limit():
    pid = PROJECT_SURENDRANB
    usage = get_daily_usage(pid)
    assert usage["calls_used"] == 0
    assert usage["remaining_quota"] == DAILY_REQUEST_LIMIT
    assert usage["quota_exhausted"] is False

    # Make 5 calls
    for i in range(1, 6):
        cnt = record_api_call(pid)
        assert cnt == i

    usage = get_daily_usage(pid)
    assert usage["calls_used"] == 5
    assert usage["remaining_quota"] == 5
    assert is_quota_exhausted(pid) is False

    # Make remaining 5 calls to hit 10
    for i in range(6, 11):
        record_api_call(pid)

    usage = get_daily_usage(pid)
    assert usage["calls_used"] == 10
    assert usage["remaining_quota"] == 0
    assert is_quota_exhausted(pid) is True
    assert usage["quota_exhausted"] is True


def test_clear_cache():
    pid = PROJECT_SURENDRANB
    key = make_cache_key(pid, num_of_days=3)
    set_cached_data(key, {"sample": "data"})
    record_api_call(pid)

    clear_cache()

    data, _, _ = get_cached_data(key)
    assert data is None
    usage = get_daily_usage(pid)
    assert usage["calls_used"] == 0
