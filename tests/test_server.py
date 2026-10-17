# SPDX-License-Identifier: MIT
"""Unit tests for FastMCP server tools in microsoft_clarity_mcp.server."""

import json
import pytest
from unittest.mock import MagicMock, patch

from microsoft_clarity_mcp.server import (
    check_for_updates,
    client,
    doctor,
    get_frustration_breakdown,
    get_js_errors,
    get_ux_insights,
    skill_read,
    skills_list,
)
from tests.conftest import (
    ALL_PROJECT_IDS,
    PROJECT_BUILDITWITHAI,
    PROJECT_FREEINFERENCE,
    PROJECT_SURENDRANB,
    create_mock_clarity_data,
)


@pytest.mark.parametrize("pid", ALL_PROJECT_IDS)
def test_get_ux_insights_tool(pid):
    mock_data = create_mock_clarity_data(pid)
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data
        mock_get.return_value = mock_resp

        out = get_ux_insights(project_id=pid, num_of_days=3)
        assert not out.startswith("[INPUT_FIXABLE]")
        assert not out.startswith("[ENVIRONMENT_FIXABLE")
        assert not out.startswith("[TRANSIENT]")

        data = json.loads(out)
        assert data["project_id"] == pid
        assert data["lookback_days"] == 3
        assert data["data_source"] == "live_api"
        assert "session_overview" in data
        assert "frustration_metrics" in data
        assert "rage_clicks" in data["frustration_metrics"]
        assert "dead_clicks" in data["frustration_metrics"]
        assert "quick_backs" in data["frustration_metrics"]
        assert "excessive_scroll" in data["frustration_metrics"]
        assert "technical_health" in data
        assert "quota" in data
        assert data["quota"]["calls_used_today"] == 1
        assert data["quota"]["remaining_today"] == 9


def test_get_ux_insights_cache_hit():
    pid = PROJECT_SURENDRANB
    mock_data = create_mock_clarity_data(pid)
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data
        mock_get.return_value = mock_resp

        # First call: live API
        out1 = get_ux_insights(project_id=pid, num_of_days=3)
        d1 = json.loads(out1)
        assert d1["data_source"] == "live_api"
        assert mock_get.call_count == 1

        # Second call: cache hit!
        out2 = get_ux_insights(project_id=pid, num_of_days=3)
        d2 = json.loads(out2)
        assert d2["data_source"] == "cache"
        assert mock_get.call_count == 1  # No extra HTTP call made


def test_get_frustration_breakdown_tool():
    pid = PROJECT_FREEINFERENCE
    mock_data = create_mock_clarity_data(pid, dimension="URL")
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data
        mock_get.return_value = mock_resp

        out = get_frustration_breakdown(project_id=pid, dimension="URL", num_of_days=2)
        data = json.loads(out)
        assert data["project_id"] == pid
        assert data["dimension"] == "URL"
        assert data["lookback_days"] == 2
        assert "breakdown" in data
        assert len(data["breakdown"]) > 0
        first_item = data["breakdown"][0]
        assert "rage_clicks" in first_item
        assert "dead_clicks" in first_item


def test_get_frustration_breakdown_invalid_dimension():
    out = get_frustration_breakdown(project_id=PROJECT_SURENDRANB, dimension="non_existent_dim")
    assert "[INPUT_FIXABLE]" in out
    assert "Invalid dimension" in out


def test_get_js_errors_tool():
    pid = PROJECT_BUILDITWITHAI
    mock_data = create_mock_clarity_data(pid, dimension="multi_dim")
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data
        mock_get.return_value = mock_resp

        out = get_js_errors(project_id=pid, num_of_days=3)
        data = json.loads(out)
        assert data["project_id"] == pid
        assert "summary" in data
        assert "errors_by_browser" in data
        assert "errors_by_os" in data
        assert data["summary"]["total_script_errors"] > 0


def test_doctor_healthy(monkeypatch):
    monkeypatch.setenv("CLARITY_API_TOKEN", "valid_secret_token_1234")
    out = doctor(project_id=PROJECT_SURENDRANB)
    data = json.loads(out)
    assert data["status"] == "HEALTHY"
    assert data["token"]["configured"] is True
    assert data["cache"]["exists"] is not None
    assert len(data["daily_quota"]) >= 1
    assert data["daily_quota"][0]["project_id"] == PROJECT_SURENDRANB


def test_doctor_missing_token(monkeypatch):
    monkeypatch.delenv("CLARITY_API_TOKEN", raising=False)
    monkeypatch.delenv("CLARITY_TOKEN", raising=False)
    out = doctor(token=None)
    data = json.loads(out)
    assert data["status"] == "ACTION_REQUIRED"
    assert data["token"]["configured"] is False
    assert "[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]" in data["guidance"]


def test_skills_list_and_read():
    # 1. List skills
    list_out = skills_list()
    data = json.loads(list_out)
    assert "skills" in data
    assert "ux-triage" in data["skills"]
    assert "setup-clarity-token" in data["skills"]
    assert "frustration-audit" in data["skills"]

    # 2. Read existing skills
    for s_name in ["ux-triage", "setup-clarity-token", "frustration-audit"]:
        content = skill_read(name=s_name)
        assert not content.startswith("[INPUT_FIXABLE]")
        assert len(content) > 100

    # 3. Read unknown skill
    bad = skill_read(name="unknown-skill-xyz")
    assert "[INPUT_FIXABLE]" in bad
    assert "Unknown skill" in bad


def test_check_for_updates():
    out = check_for_updates()
    data = json.loads(out)
    assert data["package"] == "microsoft-clarity-mcp"
    assert "current_version" in data
