---
name: setup-clarity-token
description: "This guide walks through generating and configuring an API token for Microsoft Clarity Data Export."
---

# Setting Up Microsoft Clarity API Token

This guide walks through generating and configuring an API token for Microsoft Clarity Data Export.

## Prerequisites
* Admin access to the target Microsoft Clarity project.
* A Clarity project ID (e.g., `yz5idaioq2`).

## Token Generation Steps
1. Navigate to [Microsoft Clarity](https://clarity.microsoft.com) and log in.
2. Select your project from the dashboard.
3. In the top navigation, click **Settings**.
4. In the left sidebar, click **Data Export**.
5. Click **Generate new API token**.
6. Provide a descriptive token name:
   * Length: 4 to 32 characters.
   * Allowed characters: Alphanumeric (`A-Z`, `a-z`, `0-9`), hyphens (`-`), underscores (`_`), and periods (`.`).
   * No spaces or symbols like `@`, `#`, `$`.
   * Example: `clarity-mcp-agent`.
7. Click **Generate** and copy the resulting Bearer token immediately (it will not be shown again).

## Environment Configuration
Set the token in your shell or agent environment:

```bash
export CLARITY_API_TOKEN="your_jwt_token_here"
```

Alternatively, pass `token="your_jwt_token_here"` directly to any tool call.

## Rate Limits & Quotas
* Microsoft Clarity enforces a strict quota of **10 requests per project per day**.
* Lookback periods are restricted to `1`, `2`, or `3` days (last 24, 48, or 72 hours).
* The MCP server includes an automatic on-disk cache (`~/.clarity_mcp/cache.json`) with a 1-hour TTL. Repeated queries by AI agents will hit the cache and will NOT consume your daily quota.
* If your quota is reached, the server will serve stale cached data where available to keep agents operational.
