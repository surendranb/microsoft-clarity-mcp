# SPDX-License-Identifier: MIT
"""Lifecycle boot events: server_first_install / package_download / mcp_started."""
import importlib

from microsoft_clarity_mcp import telemetry as T


def _fresh(monkeypatch, tmp_path):
    """Reload the module with HOME pinned to a temp dir (fresh identity)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("DO_NOT_TRACK", "MCP_TELEMETRY_OPT_OUT", "DISABLE_TELEMETRY", "NO_TELEMETRY", "CLARITY_TELEMETRY"):
        monkeypatch.delenv(var, raising=False)
    return importlib.reload(T)


def _capture(monkeypatch, mod):
    sent = []
    monkeypatch.setattr(mod, "_send_event_sync", lambda e: sent.append(e))
    return sent


def test_first_boot_emits_install_download_and_start(monkeypatch, tmp_path):
    mod = _fresh(monkeypatch, tmp_path)
    sent = _capture(monkeypatch, mod)
    mod.announce_and_fire_boot_events()
    mod.track_event("mcp_started", {})
    mod.flush_and_close()
    assert [e["event"] for e in sent] == [
        "server_first_install",
        "package_download",
        "mcp_started",
    ]
    assert sent[0]["properties"]["first_install_version"] == mod.MCP_SERVER_VERSION
    assert sent[1]["properties"]["first_download"] is True
    assert sent[2]["properties"]["session_id"].startswith("sess_")


def test_second_boot_emits_start_only(monkeypatch, tmp_path):
    mod = _fresh(monkeypatch, tmp_path)
    mod.announce_and_fire_boot_events()
    mod.flush_and_close()
    mod = importlib.reload(mod)  # same HOME: identity + version file already exist
    sent = _capture(monkeypatch, mod)
    mod.announce_and_fire_boot_events()
    mod.track_event("mcp_started", {})
    mod.flush_and_close()
    assert [e["event"] for e in sent] == ["mcp_started"]


def test_opt_out_emits_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    mod = importlib.reload(T)
    sent = _capture(monkeypatch, mod)
    mod.announce_and_fire_boot_events()
    mod.track_event("mcp_started", {})
    mod.flush_and_close()
    assert sent == []
