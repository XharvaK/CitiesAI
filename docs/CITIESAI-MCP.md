# CitiesAI MCP server

Expose live city state to Cursor, Claude Desktop, or any MCP client.

## Run

```powershell
citiesai mcp
```

Or add to `%USERPROFILE%\.cursor\mcp.json`:

```json
{
  "mcpServers": {
    "citiesai": {
      "command": "citiesai-mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `get_city_brief` | Markdown city brief from `latest.json` |
| `get_metric_group` | Raw export group (e.g. `mobility`, `workforce`) |
| `detect_issues` | Rule-based city pressures |
| `get_history` | Persistent SQLite historian |
| `get_report_card` | Domain letter grades |
| `get_forecasts` | Trend projections and alerts |

Requires a loaded city with CS2 Data Export producing `latest.json`.
