# SPDX-License-Identifier: MIT
"""FastMCP server for Microsoft Clarity: behavioral UX diagnostics, rage clicks, dead clicks, quick backs, excessive scroll, and JS errors."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer(
        "microsoft-clarity-mcp",
        title="Microsoft Clarity MCP Server",
        version="0.1.0",
        website_url="https://github.com/surendranb/microsoft-clarity-mcp",
    )
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("microsoft-clarity-mcp")
    except ImportError:
        # Fallback dummy for direct script inspection if mcp is not installed
        class DummyMCP:
            def tool(self, *args, **kwargs):
                def dec(fn):
                    return fn
                return dec
            def run(self):
                pass
        mcp = DummyMCP()

from microsoft_clarity_mcp.cache import (
    DAILY_REQUEST_LIMIT,
    get_cache_path,
    get_daily_usage,
    get_default_ttl,
    is_quota_exhausted,
)
from microsoft_clarity_mcp.client import (
    KNOWN_PROJECTS,
    ClarityClient,
    normalize_dimension,
    resolve_token,
)
from microsoft_clarity_mcp.skills import list_available_skills, read_skill_content
from microsoft_clarity_mcp.telemetry import (
    MCP_SERVER_VERSION,
    classify_exception,
    track_event,
    track_tool_call,
)

# ---------------------------------------------------------------------------
# Universal fleet update checker (async, non-blocking, 24h TTL, 7d re-nudge)
# ---------------------------------------------------------------------------
_FLEET_CACHE_FILE = Path.home() / ".cache" / "mcp_fleet_updates.json"
_UPDATE_CHECK_TTL = 86400  # 24 hours


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        clean = re.sub(r"[^\d.]", "", str(v))
        parts = [int(p) for p in clean.split(".") if p.isdigit()]
        return tuple(parts) if parts else (0,)
    except Exception:
        return (0,)


def check_server_update(package_name: str, current_version: str, force_check: bool = False) -> dict:
    """Checks PyPI for latest version and returns update status and instructions."""
    now = time.time()
    cache = {}
    if _FLEET_CACHE_FILE.exists():
        try:
            cache = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    entry = cache.get(package_name, {})
    last_check = entry.get("last_checked", 0)
    latest_version = entry.get("latest_version", current_version)

    if force_check or (now - last_check > _UPDATE_CHECK_TTL):
        try:
            req = urllib.request.Request(
                f"https://pypi.org/pypi/{package_name}/json",
                headers={"User-Agent": f"{package_name}/{current_version}"},
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    latest_version = data.get("info", {}).get("version", current_version)
                    cache[package_name] = {"latest_version": latest_version, "last_checked": now}
                    _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    _FLEET_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        except Exception:
            pass

    cur_tuple = _parse_version(current_version)
    lat_tuple = _parse_version(latest_version)
    is_outdated = lat_tuple > cur_tuple

    return {
        "package": package_name,
        "current_version": current_version,
        "latest_version": latest_version,
        "is_outdated": is_outdated,
        "upgrade_command": f"uvx --upgrade {package_name}" if is_outdated else None,
    }


def get_upgrade_nudge(package_name: str, current_version: str) -> str:
    """Returns in-band upgrade directive if outdated, else empty string."""
    try:
        status = check_server_update(package_name, current_version)
        if status.get("is_outdated"):
            lat = status.get("latest_version")
            return f"\n\n[NOTICE: Update available for {package_name}: {current_version} -> {lat}. Run: {status.get('upgrade_command')}]"
    except Exception:
        pass
    return ""


# Shared client instance
client = ClarityClient()


def _extract_metric_map(raw_data: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Index raw Clarity metric blocks by metricName."""
    metrics: Dict[str, List[Dict[str, Any]]] = {}
    if not isinstance(raw_data, list):
        return metrics
    for block in raw_data:
        if isinstance(block, dict):
            name = block.get("metricName") or block.get("name")
            info = block.get("information") or block.get("data") or []
            if name and isinstance(info, list):
                metrics[str(name)] = info
    return metrics


# ---------------------------------------------------------------------------
# MCP Tool: get_ux_insights
# ---------------------------------------------------------------------------
@mcp.tool()
def get_ux_insights(
    project_id: str,
    num_of_days: int = 3,
    token: Optional[str] = None,
) -> str:
    """Retrieve high-level UX insights, frustration rates, and technical health for a Clarity project.

    Args:
        project_id: Microsoft Clarity Project ID (e.g., 'yz5idaioq2').
        num_of_days: Lookback window in days (1, 2, or 3 days; defaults to 3).
        token: Optional Clarity API token. If omitted, uses CLARITY_API_TOKEN environment variable.

    Returns:
        Structured JSON summary of session overview, rage clicks, dead clicks,
        quick backs, excessive scrolling, JS errors, and quota status.
    """
    t0 = time.perf_counter()
    tool_name = "get_ux_insights"

    try:
        res = client.fetch_live_insights(
            project_id=project_id,
            num_of_days=num_of_days,
            token=token,
        )
        raw_data = res.get("raw_data", [])
        metric_map = _extract_metric_map(raw_data)

        # 1. Traffic & Sessions
        traffic_info = metric_map.get("Traffic", [{}])
        total_sessions = 0
        total_bots = 0
        distinct_users = 0
        pages_per_session = 0.0

        for item in traffic_info:
            try:
                total_sessions += int(item.get("totalSessionCount", 0))
            except (ValueError, TypeError):
                pass
            try:
                total_bots += int(item.get("totalBotSessionCount", 0))
            except (ValueError, TypeError):
                pass
            try:
                distinct_users += int(item.get("distantUserCount", 0))
            except (ValueError, TypeError):
                pass
            if "PagesPerSessionPercentage" in item:
                try:
                    pages_per_session = float(item["PagesPerSessionPercentage"])
                except (ValueError, TypeError):
                    pass

        # 2. Frustration Signals Helper
        def _get_metric_counts(metric_name: str) -> Dict[str, Any]:
            items = metric_map.get(metric_name, [])
            sessions = 0
            sub_total = 0
            for it in items:
                try:
                    sessions += int(it.get("totalSessionCount", 0))
                except (ValueError, TypeError):
                    pass
                try:
                    sub_total += int(it.get("subTotal", it.get("value", 0)))
                except (ValueError, TypeError):
                    pass
            pct = (sessions / total_sessions * 100) if total_sessions > 0 else 0.0
            return {
                "sessions_affected": sessions,
                "percentage_of_sessions": round(pct, 2),
                "total_count": sub_total if sub_total > 0 else sessions,
            }

        rage_clicks = _get_metric_counts("Rage Click Count")
        dead_clicks = _get_metric_counts("Dead Click Count")
        quick_backs = _get_metric_counts("Quickback Click")
        excessive_scroll = _get_metric_counts("Excessive Scroll")

        # 3. Technical Health
        script_errors = _get_metric_counts("Script Error Count")
        error_clicks = _get_metric_counts("Error Click Count")

        # 4. Engagement & Scroll
        engagement_items = metric_map.get("Engagement Time", [{}])
        scroll_items = metric_map.get("Scroll Depth", [{}])

        output_data = {
            "project_id": project_id,
            "lookback_days": num_of_days,
            "data_source": res.get("data_source"),
            "cached_at_utc": res.get("cached_at_utc"),
            "quota": {
                "daily_limit": res.get("daily_limit", DAILY_REQUEST_LIMIT),
                "calls_used_today": res.get("daily_calls_used", 0),
                "remaining_today": res.get("remaining_daily_requests", 0),
            },
            "session_overview": {
                "total_sessions": total_sessions,
                "bot_sessions": total_bots,
                "distinct_users": distinct_users,
                "pages_per_session": pages_per_session,
            },
            "frustration_metrics": {
                "rage_clicks": rage_clicks,
                "dead_clicks": dead_clicks,
                "quick_backs": quick_backs,
                "excessive_scroll": excessive_scroll,
            },
            "technical_health": {
                "script_errors": script_errors,
                "error_clicks": error_clicks,
            },
            "raw_metric_names": list(metric_map.keys()),
        }

        if "warning" in res:
            output_data["warning"] = res["warning"]

        duration_ms = (time.perf_counter() - t0) * 1000
        out_str = json.dumps(output_data, indent=2) + get_upgrade_nudge("microsoft-clarity-mcp", MCP_SERVER_VERSION)
        track_tool_call(tool_name, duration_ms, status="success", rows_returned=len(metric_map), result_chars=len(out_str))
        return out_str

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        err_cat = classify_exception(exc)
        err_msg = str(exc)
        track_tool_call(tool_name, duration_ms, status="error", error_category=err_cat, error_message=err_msg)
        return err_msg


# ---------------------------------------------------------------------------
# MCP Tool: get_frustration_breakdown
# ---------------------------------------------------------------------------
@mcp.tool()
def get_frustration_breakdown(
    project_id: str,
    dimension: str = "URL",
    num_of_days: int = 3,
    token: Optional[str] = None,
) -> str:
    """Break down user frustration metrics (rage clicks, dead clicks, quick backs) across a specific dimension.

    Args:
        project_id: Microsoft Clarity Project ID.
        dimension: Breakdown dimension: 'URL', 'Device', 'Browser', 'OS', or 'Country/Region'. Defaults to 'URL'.
        num_of_days: Lookback window in days (1, 2, or 3; defaults to 3).
        token: Optional Clarity API token.

    Returns:
        Structured JSON ranking dimension values by user frustration severity.
    """
    t0 = time.perf_counter()
    tool_name = "get_frustration_breakdown"

    try:
        norm_dim = normalize_dimension(dimension)
        res = client.fetch_live_insights(
            project_id=project_id,
            num_of_days=num_of_days,
            dimensions=[norm_dim],
            token=token,
        )
        raw_data = res.get("raw_data", [])
        metric_map = _extract_metric_map(raw_data)

        # Dimension value aggregation map
        dim_stats: Dict[str, Dict[str, Any]] = {}

        def _record_dim_metric(m_name: str, field_name: str):
            for entry in metric_map.get(m_name, []):
                # Locate dimension key in entry
                val = entry.get(norm_dim) or entry.get("dimension1") or entry.get("dimension") or "Unknown"
                val = str(val)
                stats = dim_stats.setdefault(
                    val,
                    {
                        norm_dim: val,
                        "rage_clicks": 0,
                        "dead_clicks": 0,
                        "quick_backs": 0,
                        "excessive_scroll": 0,
                        "script_errors": 0,
                        "sessions": 0,
                    },
                )
                try:
                    count = int(entry.get("subTotal", entry.get("totalSessionCount", entry.get("value", 0))))
                    stats[field_name] += count
                except (ValueError, TypeError):
                    pass

        # Parse metrics
        _record_dim_metric("Rage Click Count", "rage_clicks")
        _record_dim_metric("Dead Click Count", "dead_clicks")
        _record_dim_metric("Quickback Click", "quick_backs")
        _record_dim_metric("Excessive Scroll", "excessive_scroll")
        _record_dim_metric("Script Error Count", "script_errors")
        _record_dim_metric("Traffic", "sessions")

        # Rank by total frustration (rage + dead clicks)
        ranked = sorted(
            dim_stats.values(),
            key=lambda x: x["rage_clicks"] + x["dead_clicks"] + x["script_errors"],
            reverse=True,
        )

        output_data = {
            "project_id": project_id,
            "dimension": norm_dim,
            "lookback_days": num_of_days,
            "data_source": res.get("data_source"),
            "cached_at_utc": res.get("cached_at_utc"),
            "quota": {
                "daily_limit": res.get("daily_limit", DAILY_REQUEST_LIMIT),
                "calls_used_today": res.get("daily_calls_used", 0),
                "remaining_today": res.get("remaining_daily_requests", 0),
            },
            "total_segments": len(ranked),
            "breakdown": ranked,
        }

        if "warning" in res:
            output_data["warning"] = res["warning"]

        duration_ms = (time.perf_counter() - t0) * 1000
        out_str = json.dumps(output_data, indent=2) + get_upgrade_nudge("microsoft-clarity-mcp", MCP_SERVER_VERSION)
        track_tool_call(tool_name, duration_ms, status="success", rows_returned=len(ranked), result_chars=len(out_str))
        return out_str

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        err_cat = classify_exception(exc)
        err_msg = str(exc)
        track_tool_call(tool_name, duration_ms, status="error", error_category=err_cat, error_message=err_msg)
        return err_msg


# ---------------------------------------------------------------------------
# MCP Tool: get_js_errors
# ---------------------------------------------------------------------------
@mcp.tool()
def get_js_errors(
    project_id: str,
    num_of_days: int = 3,
    token: Optional[str] = None,
) -> str:
    """Analyze JavaScript errors and unhandled exceptions across browsers and operating systems.

    Args:
        project_id: Microsoft Clarity Project ID.
        num_of_days: Lookback window in days (1, 2, or 3; defaults to 3).
        token: Optional Clarity API token.

    Returns:
        Structured JSON breakdown of JavaScript script errors and error clicks by Browser and OS.
    """
    t0 = time.perf_counter()
    tool_name = "get_js_errors"

    try:
        # Request Browser and OS dimensions in a single call to conserve daily quota
        res = client.fetch_live_insights(
            project_id=project_id,
            num_of_days=num_of_days,
            dimensions=["Browser", "OS"],
            token=token,
        )
        raw_data = res.get("raw_data", [])
        metric_map = _extract_metric_map(raw_data)

        error_items = metric_map.get("Script Error Count", [])
        click_error_items = metric_map.get("Error Click Count", [])

        by_browser: Dict[str, Dict[str, int]] = {}
        by_os: Dict[str, Dict[str, int]] = {}
        total_errors = 0
        total_error_sessions = 0

        for item in error_items:
            browser = str(item.get("Browser") or item.get("dimension1") or "Unknown")
            os_name = str(item.get("OS") or item.get("dimension2") or "Unknown")
            try:
                count = int(item.get("subTotal", item.get("value", 0)))
            except (ValueError, TypeError):
                count = 0
            try:
                sessions = int(item.get("totalSessionCount", 0))
            except (ValueError, TypeError):
                sessions = 0

            total_errors += count
            total_error_sessions += sessions

            b_stat = by_browser.setdefault(browser, {"errors": 0, "sessions_affected": 0})
            b_stat["errors"] += count
            b_stat["sessions_affected"] += sessions

            os_stat = by_os.setdefault(os_name, {"errors": 0, "sessions_affected": 0})
            os_stat["errors"] += count
            os_stat["sessions_affected"] += sessions

        output_data = {
            "project_id": project_id,
            "lookback_days": num_of_days,
            "data_source": res.get("data_source"),
            "cached_at_utc": res.get("cached_at_utc"),
            "quota": {
                "daily_limit": res.get("daily_limit", DAILY_REQUEST_LIMIT),
                "calls_used_today": res.get("daily_calls_used", 0),
                "remaining_today": res.get("remaining_daily_requests", 0),
            },
            "summary": {
                "total_script_errors": total_errors,
                "sessions_with_errors": total_error_sessions,
                "error_clicks_reported": len(click_error_items),
            },
            "errors_by_browser": sorted(
                [{"browser": k, **v} for k, v in by_browser.items()],
                key=lambda x: x["errors"],
                reverse=True,
            ),
            "errors_by_os": sorted(
                [{"os": k, **v} for k, v in by_os.items()],
                key=lambda x: x["errors"],
                reverse=True,
            ),
        }

        if "warning" in res:
            output_data["warning"] = res["warning"]

        duration_ms = (time.perf_counter() - t0) * 1000
        out_str = json.dumps(output_data, indent=2) + get_upgrade_nudge("microsoft-clarity-mcp", MCP_SERVER_VERSION)
        track_tool_call(tool_name, duration_ms, status="success", rows_returned=len(by_browser), result_chars=len(out_str))
        return out_str

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        err_cat = classify_exception(exc)
        err_msg = str(exc)
        track_tool_call(tool_name, duration_ms, status="error", error_category=err_cat, error_message=err_msg)
        return err_msg


# ---------------------------------------------------------------------------
# MCP Tool: doctor
# ---------------------------------------------------------------------------
@mcp.tool()
def doctor(
    project_id: Optional[str] = None,
    token: Optional[str] = None,
) -> str:
    """Validate Microsoft Clarity credentials, project configurations, on-disk cache, and remaining daily request quota."""
    t0 = time.perf_counter()
    tool_name = "doctor"

    try:
        # Check Token
        token_found = False
        token_source = "none"
        masked_token = None

        if token and token.strip():
            token_found = True
            token_source = "parameter"
            t_str = token.strip()
            masked_token = f"{t_str[:4]}...{t_str[-4:]}" if len(t_str) > 8 else "***"
        else:
            env_tok = os.environ.get("CLARITY_API_TOKEN") or os.environ.get("CLARITY_TOKEN")
            if env_tok and env_tok.strip():
                token_found = True
                token_source = "environment (CLARITY_API_TOKEN)"
                t_str = env_tok.strip()
                masked_token = f"{t_str[:4]}...{t_str[-4:]}" if len(t_str) > 8 else "***"

        # Check Cache File
        cache_path = get_cache_path()
        cache_exists = cache_path.exists()
        cache_size_bytes = cache_path.stat().st_size if cache_exists else 0
        cache_ttl = get_default_ttl()

        # Quotas
        projects_to_check = [project_id] if project_id else list(KNOWN_PROJECTS.values())
        quota_reports = []
        for pid in projects_to_check:
            usage = get_daily_usage(pid)
            quota_reports.append(usage)

        report = {
            "status": "HEALTHY" if token_found else "ACTION_REQUIRED",
            "token": {
                "configured": token_found,
                "source": token_source,
                "preview": masked_token,
            },
            "cache": {
                "path": str(cache_path),
                "exists": cache_exists,
                "size_bytes": cache_size_bytes,
                "default_ttl_seconds": cache_ttl,
            },
            "daily_quota": quota_reports,
            "known_projects": KNOWN_PROJECTS,
        }

        if not token_found:
            report["guidance"] = (
                "[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN] Missing Microsoft Clarity API Token.\n"
                "To generate a valid token:\n"
                "1. Open https://clarity.microsoft.com and sign in\n"
                "2. Navigate to your project -> Settings -> Data Export\n"
                "3. Click 'Generate new API token' and copy the generated token\n"
                "4. Set environment variable CLARITY_API_TOKEN=<token> or pass token parameter directly."
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        out_str = json.dumps(report, indent=2) + get_upgrade_nudge("microsoft-clarity-mcp", MCP_SERVER_VERSION)
        track_tool_call(tool_name, duration_ms, status="success" if token_found else "warning", result_chars=len(out_str))
        return out_str

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        err_cat = classify_exception(exc)
        err_msg = str(exc)
        track_tool_call(tool_name, duration_ms, status="error", error_category=err_cat, error_message=err_msg)
        return err_msg


# ---------------------------------------------------------------------------
# Dynamic Skills Layer (Fleet v2 Standard §4)
# ---------------------------------------------------------------------------
@mcp.tool()
def skills_list() -> str:
    """List available dynamic skill playbooks bundled with microsoft-clarity-mcp."""
    t0 = time.perf_counter()
    skills = list_available_skills()
    track_event("skill_read", {"action": "skills_list", "count": len(skills)})
    res = {
        "skills": skills,
        "source": "github+local",
        "description": "Call skill_read(name='<skill_name>') to load any playbook.",
    }
    duration_ms = (time.perf_counter() - t0) * 1000
    out_str = json.dumps(res, indent=2)
    track_tool_call("skills_list", duration_ms, status="success", rows_returned=len(skills), result_chars=len(out_str))
    return out_str


@mcp.tool()
def skill_read(name: str) -> str:
    """Load a dynamic skill playbook by name from GitHub (with local fallback).

    Args:
        name: Skill name (e.g., 'ux-triage', 'setup-clarity-token', 'frustration-audit').
    """
    t0 = time.perf_counter()
    content, ok = read_skill_content(name)
    duration_ms = (time.perf_counter() - t0) * 1000
    if ok:
        track_tool_call("skill_read", duration_ms, status="success", result_chars=len(content))
        return content
    else:
        track_tool_call("skill_read", duration_ms, status="error", error_category="NotFoundError", error_message=content)
        return content


# ---------------------------------------------------------------------------
# MCP Tool: check_for_updates
# ---------------------------------------------------------------------------
@mcp.tool()
def check_for_updates() -> str:
    """Check PyPI for newer versions of microsoft-clarity-mcp and get upgrade instructions."""
    res = check_server_update("microsoft-clarity-mcp", MCP_SERVER_VERSION, force_check=True)
    return json.dumps(res, indent=2)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
