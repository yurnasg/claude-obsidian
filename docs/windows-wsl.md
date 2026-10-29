# Windows and cross-platform guide

claude-obsidian supports native Windows, Linux, and macOS with full read and write
capabilities. This guide covers how platform isolation works, native Windows
support, and how to work across the Windows/WSL boundary when desired.

## Platform support

| Capability | Linux / macOS / WSL | Native Windows (NTFS) |
|---|---|---|
| Inspection, dry-run previews, retrieval | Yes | Yes |
| Vault writes (`transaction apply`, `init`, `adopt`, `migrate`, `capture apply`, `mode set`) | Yes (POSIX dirfd confinement) | Yes (Atomic path confinement) |
| Git checkpoints (`checkpoint`) | Yes | Yes |
| Setup and multi-agent linking (`setup-multi-agent`) | Yes (`python3 scripts/claude-obsidian.py`) | Yes (`python scripts/claude-obsidian.py`) |
| Unified test runner (`claude-obsidian test`) | Yes | Yes |
| Claude Code hooks (`SessionStart`, `Stop`) | Yes (works out of the box) | Yes (requires `python3` or `python` on `PATH`) |

Vaults must live on a filesystem with stable file identity: NTFS is fine, but
FAT/exFAT volumes (typical USB sticks) and some network shares are refused with
`UNSAFE_VAULT_IDENTITY`: move the vault to NTFS or work inside a native filesystem.

## Claude Code hooks and python3 on Windows

`hooks/hooks.json` spawns each hook using the [Claude Code exec-form command
hook](https://code.claude.com/docs/en/hooks): `"command": "python3"` with an
`args` array. Claude Code resolves `python3` as an executable on `PATH` and
spawns it directly; there is no shell, so no `.bat` shim, alias function, or
shell profile is consulted.

WSL and most Linux and macOS Python installs provide a `python3` on `PATH` by
default, so hooks work there without extra setup. Native Windows commonly does
not:

- python.org installer: installs `python.exe`, not `python3.exe`. Either add
  a `python3.exe` shim earlier on `PATH` than the interpreter, install a
  distribution that provides `python3.exe`, or run Claude Code from WSL so
  hooks resolve the WSL `python3`.
- Microsoft Store Python: the `python3` app execution alias can be a stub
  that opens the Store instead of running Python. Disable the `python3` app
  execution alias in Windows Settings, then install Python from python.org
  or WSL and confirm the real interpreter is on `PATH`.

When `python3` cannot be resolved, Claude Code fails to spawn the hook
process, so claude-obsidian's own code never runs and cannot emit a
diagnostic. SessionStart context and Stop recovery warnings are both silently
absent in that case; the rest of claude-obsidian (skills and the CLI) is
unaffected, since only the optional hook path depends on `python3`.

## Confinement and mutation architecture

Mutation safety requires that target files and directories cannot be redirected by
concurrent hostile symlink replacement or directory swapping during a write:

- **POSIX hosts (Linux, macOS, WSL)**: Confinement binds to open directory descriptors
  (`dir_fd` / `openat`). The vault root and runtime directories stay pinned for the whole write.
- **Native Windows (NTFS)**: Confinement uses strict path resolution (`assert_within`),
  name-surrogate rejection (symlinks and volume junctions), Win32 process liveness verification
  (`OpenProcess`), and atomic replacement (`os.replace` via `MoveFileExW(..., MOVEFILE_REPLACE_EXISTING)`).

Both models guarantee crash-safety, atomic rollbacks, and tamper resistance without
requiring WSL or POSIX emulators on Windows.

## WSL troubleshooting

WSL being "installed" does not always mean WSL is working. Symptoms and checks,
roughly in the order worth trying:

| Symptom | Check |
|---|---|
| `wsl --install` completed but `wsl --status` or `wsl -l -v` hangs indefinitely | This field-reported hang has no confirmed cause. Follow Microsoft's WSL hang diagnosis and reporting flow below. |
| `wsl` reports a kernel or version error | Run `wsl --update`, then `wsl --shutdown`, then retry. |
| WSL worked before and stopped after an update or software change | Do not assume a cause. Update Windows and WSL, then follow Microsoft's WSL troubleshooting flow. |
| Approval hash from a native dry-run fails inside WSL with `PLAN_CHANGED` | By design: the approval hash binds the reviewing environment's filesystem identity. Run the dry-run review inside WSL when the apply will happen there; a natively produced `approved_plan_sha256` cannot be replayed from WSL. |
| Writes fail with `UNSAFE_VAULT_IDENTITY` mentioning stable file identity | The vault sits on FAT/exFAT or an unsupported network share. Move it to NTFS, or keep it inside the WSL filesystem. |

WSL troubleshooting checklist:

1. Start with Microsoft's official
   [WSL troubleshooting guide](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting).
2. Confirm virtualization is enabled in BIOS/UEFI and that both "Virtual
   Machine Platform" and "Windows Subsystem for Linux" are enabled. Reboot
   after enabling either feature.
3. Run `wsl --update` from an elevated prompt, then `wsl --shutdown`, and retry
   `wsl --status`.
4. Confirm the hypervisor launch setting is enabled. If a third-party
   hypervisor is installed, use a current version that supports Hyper-V or
   temporarily turn it off while diagnosing the conflict.
5. If WSL still hangs, follow Microsoft's
   [WSL hang data-collection steps](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting-guide#wsl-hangs)
   and file the resulting report with the WSL project. Do not attribute the
   hang to a specific cause without supporting diagnostics.

## Working across the boundary (optional WSL integration)

Native Windows is fully supported for all commands and workflows. If you prefer or already maintain
a Linux-based vault inside a WSL distribution, you can work across the boundary: because approval
hashes bind to the environment that produced them, do the reviewed dry-run in the same environment
that will run the apply.

### Windows-to-WSL wrapper (`scripts/claude-obsidian.ps1` and `scripts/claude-obsidian.cmd`)

When running an agent host on native Windows (PowerShell or `cmd.exe`) targeting a WSL vault,
use the Windows-to-WSL wrapper so both the reviewed dry-run and the subsequent `--apply`
run inside the same POSIX WSL environment:

```powershell
# PowerShell: dry-run and apply inside WSL from native Windows
.\scripts\claude-obsidian.ps1 init C:\vaults\notes
.\scripts\claude-obsidian.ps1 init C:\vaults\notes --apply --approved-plan-sha256 <PLAN_SHA256>
```

```cmd
REM cmd.exe equivalent
scripts\claude-obsidian.cmd status --vault C:\vaults\notes
```

The wrapper handles cross-boundary translation and multi-distro safety:

- **Path translation**: converts Windows drive paths (`C:\...`, `--vault=C:\...`)
  and WSL UNC paths (`\\wsl.localhost\<distro>\...`, `\\wsl$\<distro>\...`) to
  POSIX paths inside WSL, and forwards a converted `CLAUDE_OBSIDIAN_VAULT` via
  `WSLENV=CLAUDE_OBSIDIAN_VAULT/u`.
- **Single-distro pinning**: resolves one target WSL distribution per
  invocation in order:
  1. `CLAUDE_OBSIDIAN_WSL_DISTRO` (recommended when multiple WSL distros are
     installed)
  2. Distro inferred from a `\\wsl.localhost\<distro>\...` or
     `\\wsl$\<distro>\...` path in the command working directory,
     `CLAUDE_OBSIDIAN_VAULT`, or CLI arguments
  3. Default WSL distribution from `wsl.exe --status` / `wsl.exe -l -v`
- **Fail-closed on distro mismatch**: if paths or `CLAUDE_OBSIDIAN_WSL_DISTRO`
  reference two different WSL distributions in the same command, the wrapper
  aborts before invoking Python.

