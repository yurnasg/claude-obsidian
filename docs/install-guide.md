# Install claude-obsidian

claude-obsidian has two independent parts:

1. the product package (shipped by default as an **Agent Plugins 1.0** package
   (`plugin.json`) and a **Claude Code plugin** (`.claude-plugin/plugin.json`),
   bundling portable Agent Skills (`skills/`), core (`claude_obsidian/`), and
   templates);
2. a user-owned Obsidian vault containing mutable knowledge.

Do not use an installed plugin cache as the vault. A source clone is suitable
for development, but a normal user vault should be a separate directory.

## Requirements

- Python 3.11 or newer
- an [Agent Plugins 1.0](https://agent-plugins.org) client (VS Code / GitHub
  Copilot, Cursor, ChatGPT, Codex), Claude Code, or an [Agent Skills](https://agentskills.io)
  compatible host
- Obsidian when you want its visual editor
- Standard Python (everything runs natively via standard-library subcommands without requiring Bash or external build tools)
- Git only for source development, release builds, or explicit checkpoints
- On Windows: native NTFS support for inspection and writes; WSL is completely optional (see the [Windows and cross-platform guide](windows-wsl.md))

## Agent Plugins 1.0 (Default Cross-Platform Package)

The repository root ships a canonical `plugin.json` conforming to
`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`, alongside
`skills/`, `com.github.copilot/hooks/hooks.json`, and `extensions["com.openai"]`.

Compatible platforms support installing the package **globally** (available
across all projects on the workstation) or **per-workspace / project** (active
only when working in that directory):

### Summary of Installation Locations

| Platform / Client | Workspace / Project Scope | Global Scope |
|---|---|---|
| **Google Antigravity (App & IDE)** | `<workspace>/.agents/plugins/claude-obsidian` | `~/.gemini/config/plugins/claude-obsidian` |
| **Antigravity CLI / Gemini CLI** | — | `~/.gemini/antigravity-cli/plugins/claude-obsidian` |
| **VS Code / GitHub Copilot** | `.vscode/settings.json` (`chat.pluginLocations`) | `~/.copilot/installed-plugins/_direct/claude-obsidian` |
| **OpenAI Codex / ChatGPT** | `<workspace>/.agents/plugins/marketplace.json` | `~/.agents/plugins/marketplace.json` |
| **Cursor** | `<workspace>/.agents/plugins/claude-obsidian` | `~/.cursor/plugins/local/claude-obsidian` |

### Installing via `setup-multi-agent.sh`

The installer manages these package links safely without overwriting foreign files:

- **Global installation (default):**
  Installs user-level Agent Plugins links for Copilot, Antigravity, Antigravity CLI,
  and Codex:
  ```bash
  bash scripts/setup-multi-agent.sh
  bash scripts/setup-multi-agent.sh --apply
  ```

- **Project-scoped installation (`--workspace PATH`):**
  Installs the plugin confined to a specific project workspace:
  ```bash
  # Install into current project (.agents/plugins/claude-obsidian):
  bash scripts/setup-multi-agent.sh --host antigravity --workspace "$PWD" --apply
  bash scripts/setup-multi-agent.sh --host codex --workspace "$PWD" --apply
  bash scripts/setup-multi-agent.sh --host cursor --workspace "$PWD" --apply
  ```

- **Check readiness without writing:**
  ```bash
  bash scripts/setup-multi-agent.sh --check
  ```

### Platform-Specific Native Setup

- **VS Code and GitHub Copilot:**
  Install directly from the repository in VS Code (`Chat: Install Plugin From Source`
  or `/plugin install https://github.com/AgriciDaniel/claude-obsidian`), or register a
  workspace checkout in `.vscode/settings.json`:
  ```json
  {
    "chat.pluginLocations": {
      "/absolute/path/to/claude-obsidian": true
    }
  }
  ```

- **Cursor:**
  In **Customize -> Plugins**, click **Install** and choose between **Project Scope**
  or **User Scope**, or clone/link into `~/.cursor/plugins/local/claude-obsidian`.

- **OpenAI Codex / ChatGPT:**
  Add a marketplace entry pointing to the plugin in `$REPO_ROOT/.agents/plugins/marketplace.json`
  (project) or `~/.agents/plugins/marketplace.json` (global).

## Claude Code Plugin (Default Claude Integration)

Add the public catalog and install the namespaced plugin:

```bash
claude plugin marketplace add AgriciDaniel/claude-obsidian
claude plugin install claude-obsidian@agricidaniel-claude-obsidian
claude plugin list
```

Upgrading from 2.x or 3.0.0? See [Upgrade and rollback](#upgrade-and-rollback).

A private development tree that holds contributor-vault state has no
`.claude-plugin/marketplace.json`; it can contain contributor-vault state and
must not be added as a marketplace. The deterministic release builder injects
that manifest only into its audited output. The public default branch must be
promoted from the extracted audited artifact before these marketplace commands
are advertised for a new version.

Invoke skills as `/claude-obsidian:wiki`,
`/claude-obsidian:wiki-ingest`, and `/claude-obsidian:save`.

The plugin cache contains read-only product assets. Run Claude from the user
vault, set `CLAUDE_OBSIDIAN_VAULT`, or pass `--vault` to portable commands.

### Local Claude plugin development

From a product clone:

```bash
claude --plugin-dir <product-repository>
```

This mode is for testing uninstalled changes. Skills remain namespaced. It does
not convert the product repository into a user vault.

## Portable Agent Skills hosts (legacy hosts)

For hosts that do not yet package plugins as a single unit (OpenCode, ZCode,
Windsurf), link each canonical `skills/<name>/` directory into the host's direct
`<skill-root>/<name>/SKILL.md` layout:

```bash
# OpenCode (user-level):
python3 scripts/claude-obsidian.py setup-multi-agent --host opencode --apply

# ZCode (user-level):
python3 scripts/claude-obsidian.py setup-multi-agent --host zcode --apply

# Windsurf (workspace-scoped):
python3 scripts/claude-obsidian.py setup-multi-agent --host windsurf --workspace <workspace> --apply
```

(The shell script `bash scripts/setup-multi-agent.sh` remains supported as a backward-compatible shim).

Manual per-skill link locations:

```text
OpenCode:            ~/.config/opencode/skills/<name>    -> <product-repository>/skills/<name>
ZCode:               ~/.zcode/skills/<name>              -> <product-repository>/skills/<name>
Windsurf:            <workspace>/.windsurf/skills/<name> -> <product-repository>/skills/<name>
```

## Create a new vault

Review the initialization plan first:

```bash
python3 scripts/claude-obsidian.py init <new-vault> \
  --generated-at <ISO-UTC> --operation-id init-reviewed
```

Apply the same operation only after the destination and changed paths look
correct:

```bash
python3 scripts/claude-obsidian.py init <new-vault> \
  --generated-at <ISO-UTC> --operation-id init-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

The generated vault contains:

- `.gitignore`, privacy-safe defaults excluding `.vault-meta/` runtime state,
  Obsidian workspace state, and live `.mcp.json` launch configuration;
- `.claude-obsidian.json`, workspace identity and vault selection;
- `inbox/`, visible source intake;
- `.raw/`, immutable source payloads and legacy delta manifest;
- `wiki/`, index, log, hot cache, overview, and generated notes;
- `.obsidian/`, minimal non-destructive Obsidian defaults;
- `.vault-meta/`, ignored runtime state created when needed.

Initialization does not add an upstream Git remote or install community
plugins. Open the new directory through Obsidian's vault picker.

## Adopt an existing vault

Adoption scans an existing Obsidian directory and proposes only missing product
metadata and foundation files:

```bash
python3 scripts/claude-obsidian.py adopt <existing-vault> \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed
python3 scripts/claude-obsidian.py adopt <existing-vault> \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

It preserves existing notes and Obsidian JSON. `--force` is intentionally
separate and should be used only after inspecting replacement targets.

For older claude-obsidian layouts, add provenance ledgers and workspace config
with an additive migration:

```bash
python3 scripts/claude-obsidian.py migrate --vault <existing-vault> \
  --generated-at <ISO-UTC> --operation-id migrate-reviewed
python3 scripts/claude-obsidian.py migrate --vault <existing-vault> \
  --generated-at <ISO-UTC> --operation-id migrate-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Migration is idempotent, does not infer claims from prose, and leaves the
legacy `.raw/.manifest.json` byte-for-byte unchanged.

## Vault selection

Mutable commands use this precedence:

1. `--vault <path>`
2. `CLAUDE_OBSIDIAN_VAULT`
3. nearest `.claude-obsidian.json`
4. nearest unambiguous initialized vault from the current directory

If selection fails, the command exits without mutation. The product/plugin root
is rejected as an implicit vault.

Verify a selected vault:

```bash
python3 scripts/claude-obsidian.py doctor --vault <vault>
python3 scripts/claude-obsidian.py contracts --verify --vault <vault>
```

Doctor checks metadata directory safety and write/search permissions without
creating files. A missing `.vault-meta` is ready only when the vault directory
permits its creation. Readiness is a point-in-time diagnostic; transactions
still recheck paths, conflicts and permissions before applying changes.

## Optional configuration

The portable filesystem transport always remains available. Detect an active,
supported Obsidian CLI without persisting a snapshot:

```bash
bash scripts/detect-transport.sh --peek --vault <vault>
```

Optional extensions are explicit and vault-scoped:

```bash
bash scripts/setup-mode.sh --vault <vault>
bash scripts/setup-retrieve.sh --vault <vault>
bash scripts/setup-dragonscale.sh --vault <vault>
```

Read each script's preview before applying. Retrieval may use local BM25 alone;
model-based contextual prefixes or remote endpoints require explicit egress
consent. Optional tools such as Ollama and defuddle are capability-detected.

## First operation

Place a source in `inbox/`. Inspect the byte-capture plan:

```bash
python3 scripts/claude-obsidian.py capture plan --vault <vault>
```

Create immutable content-addressed copies only when the plan is correct:

```bash
python3 scripts/claude-obsidian.py capture apply --vault <vault> \
  --generated-at <ISO-UTC> --operation-id capture-reviewed
python3 scripts/claude-obsidian.py capture apply --vault <vault> \
  --generated-at <ISO-UTC> --operation-id capture-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Then invoke the host's `wiki-ingest` skill. Image, PDF, and EPUB semantic
extraction is not built into the core; those formats currently receive bounded
metadata unless a separately configured adapter is explicitly approved.

## Upgrade and rollback

The Claude plugin is `claude-obsidian`, and its commands are
`/claude-obsidian:*`. From 2.x, update it as usual:

```bash
claude plugin marketplace update agricidaniel-claude-obsidian
claude plugin update claude-obsidian@agricidaniel-claude-obsidian
```

Version 3.0.0 alone was named `agricidaniel-obsidian`. If you installed it,
the marketplace `renames` map moves you back, then you install once:

```bash
claude plugin marketplace update agricidaniel-claude-obsidian
claude plugin install claude-obsidian@agricidaniel-claude-obsidian
```

Restart Claude Code after either path. Managed settings that name
`agricidaniel-obsidian` need an administrator change. See the
[namespace migration](namespace-migration.md) for verification and rollback.

Upgrade product code independently from the user vault. Before a migration or
large ingest, make a normal backup or snapshot. Knowledge writes are journaled;
run recovery after an interrupted operation:

```bash
python3 scripts/claude-obsidian.py transaction recover --vault <vault>
```

Recovery conservatively preserves stale or foreign lock identities. Only after
confirming no writer is active may an operator add `--force-stale-lock`.

Git history is optional and never automatic. To checkpoint exactly one
completed transaction:

```bash
python3 scripts/claude-obsidian.py checkpoint <operation-id> --vault <vault> \
  --as-of YYYY-MM-DD
```

Checkpointing uses a temporary index, verifies exact Git blob bytes, refuses
pre-existing staged state, and resumes an interrupted ref/index finalization
from its vault-local pending record.

## Uninstall

Remove the host integration, not the vault:

```bash
claude plugin uninstall claude-obsidian@agricidaniel-claude-obsidian
claude plugin marketplace remove agricidaniel-claude-obsidian
```

For portable hosts, remove only the per-skill links that the installer reported.
User notes, sources, ledgers, and Obsidian settings remain untouched.

## Troubleshooting

| Symptom | Check |
|---|---|
| Skill is not discovered | Confirm `<host-skill-root>/<name>/SKILL.md` resolves to the matching product skill; rerun installer `--check`. |
| Command says no vault selected | Run from the vault, pass `--vault`, or set `CLAUDE_OBSIDIAN_VAULT`. |
| Plugin-root refusal | Select a separate user vault; plugin cache writes are unsupported. |
| Transaction conflict / exit 75 | Another operation is active or a target changed; reread, rebuild, and inspect a new bundle. |
| Obsidian CLI is unavailable | Use filesystem reads; start/update Obsidian before retrying CLI transport. |
| Capture adapter is not implemented | Inspect `capture adapters`; configure a separate runner only with explicit consent. |
| Writes refused with `UNSAFE_VAULT_IDENTITY` on Windows | The vault is on an unsupported FAT/exFAT or network share; move it to an NTFS drive (see the [Windows guide](windows-wsl.md)). |
| Native dry-run approval fails across boundary with `PLAN_CHANGED` | Approval hashes bind the reviewing environment; redo the dry-run in the environment running the apply ([details](windows-wsl.md#wsl-troubleshooting)). |

Run `python scripts/claude-obsidian.py test` (or `make test`) in the product repository when developing or packaging changes.
