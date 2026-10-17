# Microsoft Clarity MCP Server (`microsoft-clarity-mcp`)

FastMCP server exposing Microsoft Clarity's Data Export API for behavioral UX analysis, rage clicks, dead clicks, quick backs, excessive scrolling, and JavaScript runtime errors.

Companion behavioral diagnostics engine to Google Analytics and Search Console for AI agents.

---

## 1. Quickstart

Run directly without installing via `uvx` (Python) or `npx` (Node):

### Via Python (`uvx`)
```bash
uvx microsoft-clarity-mcp
```

### Via Node (`npx`)
```bash
npx microsoft-clarity-mcp
```

---

## 2. MCP Client Configuration

Add to your MCP client config (`claude_desktop_config.json`, `cursor.json`, or Antigravity/OpenCode):

```json
{
  "mcpServers": {
    "microsoft-clarity": {
      "command": "uvx",
      "args": ["microsoft-clarity-mcp"],
      "env": {
        "CLARITY_API_TOKEN": "your_clarity_api_token_here"
      }
    }
  }
}
```

Or using `npx`:
```json
{
  "mcpServers": {
    "microsoft-clarity": {
      "command": "npx",
      "args": ["-y", "microsoft-clarity-mcp"],
      "env": {
        "CLARITY_API_TOKEN": "your_clarity_api_token_here"
      }
    }
  }
}
```

---

## 3. Authentication & API Tokens

Microsoft Clarity secures data export via static JWT Bearer tokens:
1. Log in to [Microsoft Clarity](https://clarity.microsoft.com).
2. Open your project dashboard.
3. Navigate to **Settings** -> **Data Export**.
4. Click **Generate new API token** (provide a name between 4 and 32 alphanumeric characters, e.g. `clarity-agent`).
5. Copy the generated token and configure `CLARITY_API_TOKEN`.

---

## 4. Rate-Limit Defense & Persistent Caching

* **Daily Quota**: Microsoft Clarity strictly allows **10 requests per project per day**.
* **Automatic Cache**: To safeguard user quota from runaway agent loops, all responses are cached locally on disk at `~/.clarity_mcp/cache.json` with a 1-hour TTL (configurable via `CLARITY_CACHE_TTL`).
* **Stale Cache Fallback**: If the daily 10-request quota is reached, the server automatically serves stale cached data with an explicit warning, ensuring your agents remain operational without hard crashing.
* **Quota Transparency**: Every tool response includes metadata detailing `calls_used_today`, `remaining_today`, and `daily_limit`.

---

## 5. Tools

| Tool | Parameters | Description |
|---|---|---|
| `get_ux_insights` | `project_id`, `num_of_days=3`, `token` | High-level behavioral friction metrics: session counts, rage clicks, dead clicks, quick backs, excessive scroll, and JS errors. |
| `get_frustration_breakdown` | `project_id`, `dimension="URL"`, `num_of_days=3`, `token` | Ranks friction severity broken down across URL paths, devices, browsers, operating systems, or countries. |
| `get_js_errors` | `project_id`, `num_of_days=3`, `token` | JavaScript runtime exceptions and error clicks grouped across browsers and operating systems. |
| `doctor` | `project_id`, `token` | Diagnostic utility checking token format, cache integrity, and remaining daily API quotas. |
| `skills_list` | *(none)* | Lists dynamic skill playbooks bundled with the server. |
| `skill_read` | `name` | Fetches operational playbooks (e.g. `ux-triage`, `setup-clarity-token`, `frustration-audit`). |
| `check_for_updates` | *(none)* | Queries PyPI for newer versions and upgrade commands. |

---

## 6. Telemetry & Privacy

This package includes anonymous usage telemetry to ensure reliability and detect runtime bugs across different client harnesses. Telemetry adheres strictly to Schema v2:
* **Opt-Out**: Strictly respects `DO_NOT_TRACK=1`, `DISABLE_TELEMETRY=1`, or `CLARITY_TELEMETRY=false`.
* **Zero PII**: No user URLs, personal identifiers, or authentication tokens are ever captured.

---

## License

MIT License. Copyright (c) 2026 Surendran B.
