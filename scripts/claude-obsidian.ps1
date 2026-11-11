<#
.SYNOPSIS
Run the claude-obsidian portable core inside WSL from a native Windows shell.

.DESCRIPTION
Native Windows refuses vault mutation (UNSUPPORTED_PLATFORM) because it lacks
directory-descriptor confinement. This wrapper forwards every command, including
read-only inspection and dry-runs, to one WSL distribution. Approval hashes bind
to the environment that produced the dry-run, so reviewing and applying through
the same wrapper and distribution keeps them replayable.

Arguments pass through unchanged except recognised Windows paths:

  C:\path or C:/path              ->  <mount-root>c/path   (default /mnt/c/path)
  --option=C:\path                ->  --option=<mount-root>c/path
  \\wsl.localhost\<distro>\path   ->  /path
  \\wsl$\<distro>\path            ->  /path

Relative paths are resolved by WSL from the converted current directory; write
them with forward slashes.

Environment:
  CLAUDE_OBSIDIAN_WSL_DISTRO      WSL distribution to run in. When unset, a
                                  distribution named by a \\wsl.localhost path is
                                  used; otherwise the WSL default distribution.
                                  Pin it when more than one distribution exists.
  CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT  automount root inside WSL (default /mnt/).
  CLAUDE_OBSIDIAN_WSL_PYTHON      interpreter inside WSL (default python3).
  CLAUDE_OBSIDIAN_WSL_EXE         path to wsl.exe (default: resolved from PATH).
  CLAUDE_OBSIDIAN_VAULT           forwarded into WSL after path conversion.
  CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND=1
                                  print the wsl.exe argv as JSON and exit
                                  without running anything.

Windows PowerShell 5.1 drops empty-string arguments and mangles embedded double
quotes when calling native programs; use PowerShell 7.3+ for such arguments.
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:PathDistros = New-Object System.Collections.Generic.List[string]

function Stop-Wrapper([string]$Message) {
    [Console]::Error.WriteLine("ERR WSL_WRAPPER: $Message")
    exit 2
}

function Get-MountRoot {
    $root = $env:CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT
    if ([string]::IsNullOrEmpty($root)) { $root = '/mnt/' }
    if (-not $root.StartsWith('/')) {
        Stop-Wrapper "CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT must be an absolute POSIX path: $root"
    }
    if (-not $root.EndsWith('/')) { $root += '/' }
    return $root
}

[void](Get-MountRoot)

# Return the WSL form of a recognised Windows path, or $null when the value is
# not one. Records the distribution named by \\wsl.localhost / \\wsl$ paths.
function ConvertTo-WslPath([string]$Value) {
    if ($Value -match '^([A-Za-z]):[\\/](.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = $Matches[2] -replace '\\', '/'
        return (Get-MountRoot) + $drive + '/' + $rest
    }
    if ($Value -match '^(?:\\\\|//)(?:wsl\.localhost|wsl\$)[\\/]([^\\/]+)(?:[\\/](.*))?$') {
        $distro = $Matches[1]
        $rest = ''
        if ($Matches.ContainsKey(2) -and $null -ne $Matches[2]) {
            $rest = $Matches[2] -replace '\\', '/'
        }
        $script:PathDistros.Add($distro)
        return '/' + $rest
    }
    return $null
}

function Convert-Argument([string]$Value) {
    $converted = ConvertTo-WslPath $Value
    if ($null -ne $converted) { return $converted }
    if ($Value -match '^(--?[A-Za-z0-9][A-Za-z0-9_-]*=)(.+)$') {
        $prefix = $Matches[1]
        $candidate = $Matches[2]
        $converted = ConvertTo-WslPath $candidate
        if ($null -ne $converted) { return $prefix + $converted }
    }
    return $Value
}

function Resolve-RequiredPath([string]$Value, [string]$Label) {
    if ($Value.StartsWith('/')) { return $Value }
    $converted = ConvertTo-WslPath $Value
    if ($null -eq $converted) {
        Stop-Wrapper "$Label is not reachable from WSL: $Value (use a drive path or \\wsl.localhost\<distro>\...)"
    }
    return $converted
}

function Resolve-WslExecutable([bool]$AllowMissing) {
    $configured = $env:CLAUDE_OBSIDIAN_WSL_EXE
    if (-not [string]::IsNullOrEmpty($configured)) {
        if (Test-Path -LiteralPath $configured -PathType Leaf) { return $configured }
        if ($AllowMissing) { return $configured }
        Stop-Wrapper "CLAUDE_OBSIDIAN_WSL_EXE does not exist: $configured"
    }
    $command = Get-Command 'wsl.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) { return $command.Path }
    if ($AllowMissing) { return 'wsl.exe' }
    Stop-Wrapper 'wsl.exe was not found; install WSL first (see docs/windows-wsl.md)'
}

$printOnly = $env:CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND -eq '1'

$core = Join-Path $PSScriptRoot 'claude-obsidian.py'
if (-not (Test-Path -LiteralPath $core -PathType Leaf)) {
    Stop-Wrapper "portable core not found next to this wrapper: $core"
}
$coreInWsl = Resolve-RequiredPath $core 'product directory'

$workingDirectory = (Get-Location -PSProvider FileSystem).ProviderPath
$workingDirectoryInWsl = Resolve-RequiredPath $workingDirectory 'current directory'

$forwarded = New-Object System.Collections.Generic.List[string]
$i = 0
while ($i -lt $args.Count) {
    $argument = [string]$args[$i]
    if ($argument -match '^(--?[A-Za-z0-9][A-Za-z0-9_-]*=)([A-Za-z])$' -and ($i + 1) -lt $args.Count) {
        $next = [string]$args[$i + 1]
        if ($next -match '^[\\/]') {
            $argument = $Matches[1] + $Matches[2] + ':' + $next
            $i++
        }
    }
    $forwarded.Add((Convert-Argument $argument))
    $i++
}

$vaultInWsl = $null
if (-not [string]::IsNullOrEmpty($env:CLAUDE_OBSIDIAN_VAULT)) {
    $vaultInWsl = Convert-Argument $env:CLAUDE_OBSIDIAN_VAULT
}

$referenced = @($script:PathDistros | Sort-Object -Unique)
if ($referenced.Count -gt 1) {
    Stop-Wrapper ("paths reference more than one WSL distribution: " + ($referenced -join ', '))
}

$distro = $env:CLAUDE_OBSIDIAN_WSL_DISTRO
if ([string]::IsNullOrEmpty($distro)) {
    if ($referenced.Count -eq 1) { $distro = $referenced[0] }
} else {
    if ($distro -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        Stop-Wrapper "CLAUDE_OBSIDIAN_WSL_DISTRO is not a valid distribution name: $distro"
    }
    if ($referenced.Count -eq 1 -and
        -not [string]::Equals($distro, $referenced[0], [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Wrapper ("CLAUDE_OBSIDIAN_WSL_DISTRO is '$distro' but a path points into '" +
            $referenced[0] + "'; review and apply in one distribution")
    }
}

$python = $env:CLAUDE_OBSIDIAN_WSL_PYTHON
if ([string]::IsNullOrEmpty($python)) { $python = 'python3' }

$wslArguments = New-Object System.Collections.Generic.List[string]
if (-not [string]::IsNullOrEmpty($distro)) {
    $wslArguments.Add('-d')
    $wslArguments.Add($distro)
}
$wslArguments.Add('--cd')
$wslArguments.Add($workingDirectoryInWsl)
$wslArguments.Add('-e')
$wslArguments.Add('env')
$wslArguments.Add('PYTHONDONTWRITEBYTECODE=1')
if ($null -ne $vaultInWsl) { $wslArguments.Add("CLAUDE_OBSIDIAN_VAULT=$vaultInWsl") }
$wslArguments.Add($python)
$wslArguments.Add($coreInWsl)
foreach ($argument in $forwarded) { $wslArguments.Add($argument) }

$wsl = Resolve-WslExecutable $printOnly

if ($printOnly) {
    $argv = @($wsl) + $wslArguments.ToArray()
    Write-Output (ConvertTo-Json -InputObject $argv -Compress)
    exit 0
}

& $wsl @($wslArguments.ToArray())
exit $LASTEXITCODE
