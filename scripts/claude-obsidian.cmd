@echo off
rem Run claude-obsidian inside WSL from CMD; see scripts\claude-obsidian.ps1.
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0claude-obsidian.ps1" %*
exit /b %ERRORLEVEL%
