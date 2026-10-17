# SPDX-License-Identifier: MIT
"""Dynamic skills layer for microsoft-clarity-mcp: fetches from GitHub with local fallback."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

SKILLS_REPO_URL = "https://raw.githubusercontent.com/surendranb/microsoft-clarity-mcp/main/skills"

# Registry of bundled starter skills
_BUNDLED_SKILLS: Dict[str, str] = {
    "ux-triage": "UX Friction Triage: Diagnose rage clicks, dead clicks, quick backs, and JS errors.",
    "setup-clarity-token": "Setup Clarity Token: Guide to generating and configuring Microsoft Clarity API tokens.",
    "frustration-audit": "Behavioral UX Audit: Framework for systematic frustration index and conversion friction auditing.",
}


def get_local_skills_dir() -> Path:
    """Find the local skills directory."""
    # Check package root (repo root) or src-relative
    candidates = [
        Path(__file__).parent.parent.parent / "skills",
        Path(__file__).parent / "skills",
        Path.cwd() / "skills",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return candidates[0]


def list_available_skills() -> List[str]:
    """Return sorted list of available skill names."""
    skills = set(_BUNDLED_SKILLS.keys())
    local_dir = get_local_skills_dir()
    if local_dir.exists():
        for p in local_dir.glob("*.md"):
            skills.add(p.stem)
    return sorted(skills)


def read_skill_content(name: str) -> Tuple[str, bool]:
    """Read a skill by name, trying GitHub first then local fallback.

    Returns:
        (content, success)
    """
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
    if not safe_name:
        return "[INPUT_FIXABLE] Skill name cannot be empty. Call skills_list to view available skills.", False

    # 1. Try remote GitHub fetch
    remote_url = f"{SKILLS_REPO_URL}/{safe_name}.md"
    try:
        req = urllib.request.Request(
            remote_url,
            headers={"User-Agent": "microsoft-clarity-mcp/0.1.0"},
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8", "replace"), True
    except Exception:
        pass

    # 2. Local fallback
    local_path = get_local_skills_dir() / f"{safe_name}.md"
    if local_path.exists():
        try:
            return local_path.read_text(encoding="utf-8"), True
        except Exception as exc:
            return f"[INPUT_FIXABLE] Failed to read local skill '{safe_name}': {exc}", False

    available = ", ".join(list_available_skills())
    return (
        f"[INPUT_FIXABLE] Unknown skill '{name}'. Available skills: {available}. "
        "Call skills_list() to see descriptions.",
        False,
    )
