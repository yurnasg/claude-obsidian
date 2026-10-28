# Supported installation modes

Resolve the installed product root from the invoking skill's own location, not
from the user-vault working directory:

```bash
PRODUCT_ROOT=/absolute/path/to/installed/claude-obsidian
CORE="$PRODUCT_ROOT/scripts/claude-obsidian.py"
test -f "$CORE"
```

## Agent Plugins 1.0 package (default cross-platform plugin)

The root `plugin.json` conforms to the Agent Plugins 1.0 standard
(`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`), bundling
`skills/` with client extension namespaces (`com.github.copilot/hooks/hooks.json`
and `extensions["com.openai"]`).

Compatible platforms support installing the package either globally or scoped
to a specific project/workspace:

- **Google Antigravity (App & IDE):** Global (`~/.gemini/config/plugins/claude-obsidian`)
  or workspace-scoped (`<workspace>/.agents/plugins/claude-obsidian`).
- **Antigravity CLI / Gemini CLI:** Global (`~/.gemini/antigravity-cli/plugins/claude-obsidian`).
- **VS Code / GitHub Copilot:** Global (`~/.copilot/installed-plugins/_direct/claude-obsidian`
  or `/plugin install`) or workspace-scoped (`chat.pluginLocations` in `.vscode/settings.json`).
- **OpenAI Codex / ChatGPT Desktop:** Global (`~/.agents/plugins/marketplace.json`)
  or project-scoped (`<workspace>/.agents/plugins/marketplace.json`).
- **Cursor:** Global (`~/.cursor/plugins/local/claude-obsidian` or User scope in Marketplace)
  or workspace-scoped (`<workspace>/.agents/plugins/claude-obsidian` or Project scope in Marketplace).

Preview and install with:

```bash
# Global plugin installation (default):
bash "$PRODUCT_ROOT/scripts/setup-multi-agent.sh" --apply

# Project-scoped plugin installation:
bash "$PRODUCT_ROOT/scripts/setup-multi-agent.sh" --workspace /path/to/project --apply
```

Mutable vault state must never resolve from `${PLUGIN_ROOT}`,
`${CLAUDE_PLUGIN_ROOT}`, or `${CURSOR_PLUGIN_ROOT}`.

## Claude marketplace plugin (default Claude Code integration)

Install the plugin through its marketplace (`.claude-plugin/plugin.json`) and
invoke namespaced skills such as `/claude-obsidian:wiki`. Plugin assets live in
an ephemeral cache. Mutable vault state must resolve from the project,
`--vault`, or workspace configuration, never `${CLAUDE_PLUGIN_ROOT}`.

## Local Claude plugin development

```bash
claude --plugin-dir /path/to/claude-obsidian
```

Skills remain namespaced. Run Claude from the user vault, not the plugin source
directory, or configure the vault explicitly.

## Portable Agent Skills (standalone skill discovery for legacy hosts)

For hosts that do not yet package plugins as a single unit (OpenCode, ZCode,
Windsurf), use `setup-multi-agent.sh` with `--host opencode`, `--host zcode`, or
`--host windsurf --workspace PATH` to link individual `skills/<name>/` directories.

## Product clone

A source clone is product/development code, not an automatically installed
plugin and not the recommended user vault. Create a separate vault:

```bash
python3 "$CORE" init /path/to/vault \
  --generated-at <ISO-UTC> --operation-id init-reviewed
python3 "$CORE" init /path/to/vault \
  --generated-at <ISO-UTC> --operation-id init-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Adopt an existing Obsidian vault non-destructively:

```bash
python3 "$CORE" adopt /path/to/vault \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed
python3 "$CORE" adopt /path/to/vault \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Both commands default to dry-run. New user vaults receive no upstream product
remote.
