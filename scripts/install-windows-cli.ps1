param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$CodezznRepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$CodezznCliRoot = Join-Path $CodezznRepoRoot 'cli'
$CodezznNodeCommand = Get-Command node.exe -ErrorAction Stop
$CodezznNpmCommand = Get-Command npm.cmd -ErrorAction Stop
$CodezznNodeMajor = [int]((& $CodezznNodeCommand.Source -p 'parseInt(process.versions.node)') | Select-Object -Last 1)
if ($CodezznNodeMajor -lt 20) { throw 'Codezzn CLI requires Node.js 20 or later. Existing Node was not modified.' }
if (!(Test-Path -LiteralPath (Join-Path $CodezznCliRoot 'package.json'))) { throw 'CLI package not found in this repository.' }
& $CodezznNodeCommand.Source (Join-Path $CodezznCliRoot 'bin/codezzn.js') --help
if ($LASTEXITCODE -ne 0) { throw 'CLI self-check failed. No global installation was performed.' }
if ($CheckOnly) { return }
$CodezznExistingCommand = Get-Command codezzn.cmd -ErrorAction SilentlyContinue
if ($CodezznExistingCommand) {
    Write-Host "Existing codezzn command: $($CodezznExistingCommand.Source)"
    Write-Host 'The local Codezzn CLI package will update this npm command; other commands are not changed.'
    $CodezznInstallAnswer = Read-Host 'Continue? [y/N]'
    if ($CodezznInstallAnswer -notin @('y', 'Y')) { return }
}
# Local package only, no lifecycle scripts or external dependency downloads.
& $CodezznNpmCommand.Source install --global --offline --ignore-scripts --no-audit --no-fund $CodezznCliRoot
if ($LASTEXITCODE -ne 0) { throw 'npm installation failed. Use node cli/bin/codezzn.js instead.' }
Write-Host 'Installed Codezzn CLI. Run codezzn --help in PowerShell or Windows Terminal.'
Write-Host 'If npm global bin is not in PATH, use its codezzn.cmd directly; this installer does not change machine PATH.'
