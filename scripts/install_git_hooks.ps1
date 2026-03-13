[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = (Resolve-Path (Join-Path $scriptDirectory '..')).Path

Push-Location $repositoryRoot
try {
    git config core.hooksPath .githooks
    Write-Host 'Git hooks path configured to use .githooks'
}
finally {
    Pop-Location
}
