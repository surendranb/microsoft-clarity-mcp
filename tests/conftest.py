# SPDX-License-Identifier: MIT
"""Deterministic test fixtures covering Surendran's actual Clarity projects."""

import json
import os
import pytest
from pathlib import Path

# Deterministic fixtures for Surendran's actual Clarity projects
PROJECT_SURENDRANB = "yz5idaioq2"      # surendranb.com
PROJECT_FREEINFERENCE = "yz5j1y2n6n"   # freeinference.dev
PROJECT_BUILDITWITHAI = "yz5jgqt3e3"   # builditwithai.xyz

ALL_PROJECT_IDS = [PROJECT_SURENDRANB, PROJECT_FREEINFERENCE, PROJECT_BUILDITWITHAI]


def create_mock_clarity_data(project_id: str, dimension: str | None = None) -> list:
    """Generate realistic deterministic Clarity API payloads."""
    # Seed values based on project
    if project_id == PROJECT_SURENDRANB:
        sessions = 1250
        bots = 85
        users = 1120
        rage_count = 18
        dead_count = 35
        quick_backs = 12
        excessive_scroll = 22
        js_errors = 4
    elif project_id == PROJECT_FREEINFERENCE:
        sessions = 4800
        bots = 310
        users = 4200
        rage_count = 45
        dead_count = 92
        quick_backs = 28
        excessive_scroll = 54
        js_errors = 0
    else:  # PROJECT_BUILDITWITHAI
        sessions = 820
        bots = 40
        users = 750
        rage_count = 8
        dead_count = 14
        quick_backs = 5
        excessive_scroll = 11
        js_errors = 2

    if dimension == "URL":
        return [
            {
                "metricName": "Traffic",
                "information": [
                    {"URL": "/home", "totalSessionCount": str(int(sessions * 0.5)), "subTotal": str(int(sessions * 0.5))},
                    {"URL": "/pricing", "totalSessionCount": str(int(sessions * 0.3)), "subTotal": str(int(sessions * 0.3))},
                    {"URL": "/docs", "totalSessionCount": str(int(sessions * 0.2)), "subTotal": str(int(sessions * 0.2))},
                ],
            },
            {
                "metricName": "Rage Click Count",
                "information": [
                    {"URL": "/pricing", "totalSessionCount": str(int(rage_count * 0.7)), "subTotal": str(rage_count)},
                    {"URL": "/home", "totalSessionCount": str(int(rage_count * 0.3)), "subTotal": str(int(rage_count * 0.3))},
                ],
            },
            {
                "metricName": "Dead Click Count",
                "information": [
                    {"URL": "/docs", "totalSessionCount": str(int(dead_count * 0.6)), "subTotal": str(dead_count)},
                    {"URL": "/home", "totalSessionCount": str(int(dead_count * 0.4)), "subTotal": str(int(dead_count * 0.4))},
                ],
            },
        ]

    if dimension in ("Device", "Browser", "OS"):
        dim_key = dimension
        vals = ["Desktop", "Mobile", "Tablet"] if dimension == "Device" else (
            ["Chrome", "Safari", "Firefox"] if dimension == "Browser" else ["Windows", "macOS", "iOS", "Android"]
        )
        return [
            {
                "metricName": "Traffic",
                "information": [{dim_key: v, "totalSessionCount": str(sessions // len(vals))} for v in vals],
            },
            {
                "metricName": "Rage Click Count",
                "information": [{dim_key: vals[0], "totalSessionCount": str(rage_count), "subTotal": str(rage_count)}],
            },
            {
                "metricName": "Dead Click Count",
                "information": [{dim_key: vals[1], "totalSessionCount": str(dead_count), "subTotal": str(dead_count)}],
            },
        ]

    if dimension == "Browser,OS" or dimension == "multi_dim":
        return [
            {
                "metricName": "Script Error Count",
                "information": [
                    {"Browser": "Safari", "OS": "iOS", "totalSessionCount": str(js_errors), "subTotal": str(js_errors * 3)},
                    {"Browser": "Chrome", "OS": "Windows", "totalSessionCount": "1", "subTotal": "2"},
                ],
            },
            {
                "metricName": "Error Click Count",
                "information": [
                    {"Browser": "Safari", "OS": "iOS", "totalSessionCount": "2", "subTotal": "4"},
                ],
            },
        ]

    # Default Top-Level
    return [
        {
            "metricName": "Traffic",
            "information": [
                {
                    "totalSessionCount": str(sessions),
                    "totalBotSessionCount": str(bots),
                    "distantUserCount": str(users),
                    "PagesPerSessionPercentage": 2.45,
                }
            ],
        },
        {
            "metricName": "Rage Click Count",
            "information": [{"totalSessionCount": str(int(rage_count * 0.8)), "subTotal": str(rage_count)}],
        },
        {
            "metricName": "Dead Click Count",
            "information": [{"totalSessionCount": str(int(dead_count * 0.85)), "subTotal": str(dead_count)}],
        },
        {
            "metricName": "Quickback Click",
            "information": [{"totalSessionCount": str(quick_backs), "subTotal": str(quick_backs)}],
        },
        {
            "metricName": "Excessive Scroll",
            "information": [{"totalSessionCount": str(excessive_scroll), "subTotal": str(excessive_scroll)}],
        },
        {
            "metricName": "Script Error Count",
            "information": [{"totalSessionCount": str(js_errors), "subTotal": str(js_errors * 2)}],
        },
        {
            "metricName": "Error Click Count",
            "information": [{"totalSessionCount": str(max(0, js_errors - 1)), "subTotal": str(js_errors)}],
        },
    ]


@pytest.fixture(autouse=True)
def isolate_test_cache(tmp_path, monkeypatch):
    """Ensure every test runs with an isolated cache file."""
    cache_file = tmp_path / "test_cache.json"
    monkeypatch.setenv("CLARITY_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("CLARITY_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("CLARITY_TELEMETRY", "false")
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    monkeypatch.setenv("CLARITY_API_TOKEN", "mock_valid_token_xyz_123456789")
    yield cache_file
