# Setting Up Microsoft Clarity MCP Server

This guide walks through generating and configuring an API token and project ID for Microsoft Clarity Data Export API.

Official Microsoft Clarity Documentation: [Clarity Data Export API](https://learn.microsoft.com/en-us/clarity/data-export-api/)

---

## 1. Prerequisites
* A Microsoft Clarity account with admin access to the target project.
* Your Clarity Project ID (a 10-character alphanumeric string like `yz5idaioq2`, visible in your project URL: `https://clarity.microsoft.com/projects/view/<projectId>/dashboard`).

---

## 2. Token Generation Steps (2 Minutes)

1. Log in to [Microsoft Clarity Dashboard](https://clarity.microsoft.com).
2. Select your project from the projects list.
3. In the top navigation bar, click **Settings**.
4. In the left sidebar, click **Data Export**.
5. Click **Generate new API token**.
6. Provide a descriptive token name:
   * Length: 4 to 32 characters.
   * Allowed characters: Alphanumeric (`A-Z`, `a-z`, `0-9`), hyphens (`-`), underscores (`_`), and periods (`.`).
   * No spaces or symbols like `@`, `#`, `$`.
   * Example: `clarity-mcp-agent`.
7. Click **Generate** and copy the resulting JWT Bearer token immediately (Clarity will not show it again).

---

## 3. Configuring Your MCP Client

### Environment Variables
Configure the following environment variables:
* `CLARITY_API_TOKEN`: Your JWT Bearer token generated above.
* `CLARITY_PROJECT_ID`: (Optional default) Target project ID so you don't need to pass it to every tool call.

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "microsoft-clarity": {
      "command": "uvx",
      "args": ["microsoft-clarity-mcp"],
      "env": {
        "CLARITY_API_TOKEN": "eyJhbGciOi...",
        "CLARITY_PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "microsoft-clarity": {
      "command": "uvx",
      "args": ["microsoft-clarity-mcp"],
      "env": {
        "CLARITY_API_TOKEN": "eyJhbGciOi...",
        "CLARITY_PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

### Command Line / CLI Testing
```bash
export CLARITY_API_TOKEN="eyJhbGciOi..."
export CLARITY_PROJECT_ID="your_project_id"
uvx microsoft-clarity-mcp
```

---

## 4. Rate Limits & Quotas
* **Daily Quota**: Microsoft Clarity enforces a strict limit of **10 requests per project per day**.
* **Lookback Periods**: Allowed values are `1`, `2`, or `3` days (last 24, 48, or 72 hours).
* **Automatic Disk Caching**: The MCP server caches responses locally in `~/.clarity_mcp/cache.json` with a 1-hour TTL. Repeated queries by AI agents hit the cache and do NOT consume your daily 10-call quota.
* **Stale Cache Fallback**: If you hit the 10-call daily quota, the server automatically serves stale cached data where available to keep agents operational.

---

## 5. Troubleshooting & Error Codes

| Error | Cause | Remediation |
|---|---|---|
| `401 Unauthorized` | Invalid or expired token | Generate a fresh API token in Clarity Settings > Data Export. |
| `403 Forbidden` | Token does not have access to specified project | Ensure the token was generated in the matching project workspace. |
| `404 Not Found` | Project ID is invalid | Check project URL: `https://clarity.microsoft.com/projects/view/<projectId>/dashboard`. |
| `429 Too Many Requests` | Daily quota of 10 requests exceeded | Wait for daily quota reset at 00:00 UTC or rely on local disk cache. |
| `Invalid Date Range` | Requested `numOfDays` is outside 1-3 | Clarity only allows 1, 2, or 3 days of historical data. |
