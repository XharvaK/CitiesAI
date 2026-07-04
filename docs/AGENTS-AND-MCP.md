# Agents and MCP (Cursor)

CitiesAI works without Cursor. For Cursor users, combine **Cities2-MCP** with the **cities2-advisor** skill.

## Cities2-MCP

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cities2-mcp": {
      "command": "uvx",
      "args": ["cities2-mcp"],
      "env": {
        "CITIES2_GAME_DIR": "C:\\path\\to\\Content",
        "CITIES2_LOCALE_COK": "C:\\path\\to\\Content\\Cities2_Data\\Content\\Game\\Locale.cok"
      }
    }
  }
}
```

Replace paths for your install (Steam or Game Pass). Run `citiesai setup` to detect them.

## cities2-advisor skill

Copy [skills/cities2-advisor/SKILL.md](../skills/cities2-advisor/SKILL.md) to:

- Cursor: `~/.cursor/skills/cities2-advisor/SKILL.md` or your skills manifest path
- Claude Code: `~/.claude/skills/cities2-advisor/SKILL.md`

## Prompt bundle without LLM

```powershell
citiesai ask "why is traffic bad downtown?" --no-llm
```

Paste the output into any agent that has CS2 wiki access, or pair with Cities2-MCP tools in Cursor.

## cities2-knowledge

For general mechanics (no city export), use the upstream `cities2-knowledge` skill from Cities2-MCP documentation.
