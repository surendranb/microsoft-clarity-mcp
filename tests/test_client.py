# SPDX-License-Identifier: MIT
"""Unit tests for ClarityClient, error absorption, and deterministic project fixtures."""

import pytest
import requests
from unittest.mock import MagicMock

from microsoft_clarity_mcp.cache import record_api_call
from microsoft_clarity_mcp.client import (
    ClarityClient,
    normalize_dimension,
    resolve_token,
    validate_request_params,
)
from tests.conftest import (
    ALL_PROJECT_IDS,
    PROJECT_BUILDITWITHAI,
    PROJECT_FREEINFERENCE,
    PROJECT_SURENDRANB,
    create_mock_clarity_data,
)


def test_normalize_dimension():
    assert normalize_dimension("url") == "URL"
    assert normalize_dimension("URL") == "URL"
    assert normalize_dimension("device") == "Device"
    assert normalize_dimension("Device") == "Device"
    assert normalize_dimension("browser") == "Browser"
    assert normalize_dimension("os") == "OS"
    assert normalize_dimension("country") == "Country/Region"
    assert normalize_dimension("Country/Region") == "Country/Region"
    assert normalize_dimension("Source") == "Source"

    with pytest.raises(ValueError) as excinfo:
        normalize_dimension("invalid_dim")
    assert "[INPUT_FIXABLE]" in str(excinfo.value)


def test_validate_request_params():
    validate_request_params(PROJECT_SURENDRANB, 1)
    validate_request_params(PROJECT_FREEINFERENCE, 2)
    validate_request_params(PROJECT_BUILDITWITHAI, 3)

    with pytest.raises(ValueError) as exc:
        validate_request_params("", 3)
    assert "[INPUT_FIXABLE]" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        validate_request_params(PROJECT_SURENDRANB, 0)
    assert "[INPUT_FIXABLE]" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        validate_request_params(PROJECT_SURENDRANB, 4)
    assert "[INPUT_FIXABLE]" in str(exc.value)


def test_resolve_token(monkeypatch):
    # 1. Direct argument takes priority
    assert resolve_token("explicit_token") == "explicit_token"

    # 2. Environment variable fallback
    monkeypatch.setenv("CLARITY_API_TOKEN", "env_token_123")
    assert resolve_token(None) == "env_token_123"

    # 3. Missing token raises ENVIRONMENT_FIXABLE
    monkeypatch.delenv("CLARITY_API_TOKEN", raising=False)
    monkeypatch.delenv("CLARITY_TOKEN", raising=False)
    with pytest.raises(ValueError) as exc:
        resolve_token(None)
    assert "[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]" in str(exc.value)


@pytest.mark.parametrize("pid", ALL_PROJECT_IDS)
def test_fetch_live_insights_mocked_success(pid):
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_data = create_mock_clarity_data(pid)
    mock_resp.json.return_value = mock_data
    mock_session.get.return_value = mock_resp

    client = ClarityClient(session=mock_session)
    res = client.fetch_live_insights(project_id=pid, num_of_days=3)

    assert res["project_id"] == pid
    assert res["data_source"] == "live_api"
    assert res["daily_calls_used"] == 1
    assert res["remaining_daily_requests"] == 9
    assert res["raw_data"] == mock_data
    assert mock_session.get.call_count == 1

    # Second call should hit the cache!
    res_cached = client.fetch_live_insights(project_id=pid, num_of_days=3)
    assert res_cached["data_source"] == "cache"
    assert res_cached["daily_calls_used"] == 1
    assert res_cached["remaining_daily_requests"] == 9
    assert mock_session.get.call_count == 1  # No additional HTTP request made


def test_auth_error_absorption():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_session.get.return_value = mock_resp

    client = ClarityClient(session=mock_session)
    with pytest.raises(PermissionError) as exc:
        client.fetch_live_insights(project_id=PROJECT_SURENDRANB, num_of_days=3)
    assert "[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]" in str(exc.value)


def test_bad_request_error_absorption():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Invalid date range"
    mock_session.get.return_value = mock_resp

    client = ClarityClient(session=mock_session)
    with pytest.raises(ValueError) as exc:
        client.fetch_live_insights(project_id=PROJECT_SURENDRANB, num_of_days=3)
    assert "[INPUT_FIXABLE]" in str(exc.value)


def test_rate_limit_429_absorption():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_session.get.return_value = mock_resp

    client = ClarityClient(session=mock_session)
    with pytest.raises(RuntimeError) as exc:
        client.fetch_live_insights(project_id=PROJECT_SURENDRANB, num_of_days=3)
    assert "[TRANSIENT]" in str(exc.value)
    assert "daily request limit reached" in str(exc.value)


def test_rate_limit_guard_blocks_11th_call():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = create_mock_clarity_data(PROJECT_SURENDRANB)
    mock_session.get.return_value = mock_resp

    client = ClarityClient(session=mock_session)
    pid = PROJECT_SURENDRANB

    # Pre-exhaust the quota to 10 calls
    for _ in range(10):
        record_api_call(pid)

    # Attempting a fresh call without cache should be blocked by rate limit guard
    with pytest.raises(RuntimeError) as exc:
        client.fetch_live_insights(project_id=pid, num_of_days=1, dimensions=["URL"])
    assert "[TRANSIENT]" in str(exc.value)
    assert "daily request limit reached" in str(exc.value)
    assert mock_session.get.call_count == 0  # Guard completely prevented network call!
