[CmdletBinding()]
param(
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = (Resolve-Path (Join-Path $scriptDirectory '..')).Path
$pythonExe = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$specFile = Join-Path $repositoryRoot 'popup-controller.spec'
$distDirectory = Join-Path $repositoryRoot 'dist'
$licenseOutputDirectory = Join-Path $distDirectory 'third_party_licenses'

function Copy-LicenseDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Pattern,
        [Parameter(Mandatory = $true)]
        [string]$DestinationName
    )

    $match = Get-ChildItem -Path $Pattern -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $match) {
        return
    }

    $destinationPath = Join-Path $licenseOutputDirectory $DestinationName
    if (Test-Path $destinationPath) {
        Remove-Item $destinationPath -Recurse -Force
    }

    Copy-Item $match.FullName $destinationPath -Recurse -Force
}

function Copy-LicenseFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$DestinationName
    )

    if (-not (Test-Path $Path)) {
        return
    }

    Copy-Item $Path (Join-Path $licenseOutputDirectory $DestinationName) -Force
}

Push-Location $repositoryRoot
try {
    if (-not (Test-Path $pythonExe)) {
        throw "Expected virtual environment interpreter at $pythonExe"
    }

    if (-not (Test-Path $specFile)) {
        throw "PyInstaller spec file not found at $specFile"
    }

    if (-not $SkipTests) {
        Write-Host 'Running test suite before packaging...'
        & $pythonExe -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw 'Tests failed. Packaging stopped.'
        }
    }

    Write-Host 'Building standalone executable with PyInstaller...'
    & $pythonExe -m PyInstaller --clean --noconfirm $specFile
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller build failed.'
    }

    New-Item -ItemType Directory -Path $licenseOutputDirectory -Force | Out-Null

    foreach ($fileName in @('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md')) {
        Copy-Item (Join-Path $repositoryRoot $fileName) $distDirectory -Force
    }

    $firmwareSource = Join-Path $repositoryRoot 'firmware'
    $firmwareDestination = Join-Path $distDirectory 'firmware'
    if (Test-Path $firmwareSource) {
        if (Test-Path $firmwareDestination) {
            Remove-Item $firmwareDestination -Recurse -Force
        }
        Copy-Item $firmwareSource $firmwareDestination -Recurse -Force
    }

    Copy-LicenseDirectory -Pattern (Join-Path $repositoryRoot '.venv\Lib\site-packages\esptool-*.dist-info\licenses') -DestinationName 'esptool'
    Copy-LicenseDirectory -Pattern (Join-Path $repositoryRoot '.venv\Lib\site-packages\pyinstaller-*.dist-info\licenses') -DestinationName 'pyinstaller'
    Copy-LicenseDirectory -Pattern (Join-Path $repositoryRoot '.venv\Lib\site-packages\pyside6-*.dist-info\licenses') -DestinationName 'pyside6'
    Copy-LicenseDirectory -Pattern (Join-Path $repositoryRoot '.venv\Lib\site-packages\pyside6_addons-*.dist-info\licenses') -DestinationName 'pyside6_addons'
    Copy-LicenseDirectory -Pattern (Join-Path $repositoryRoot '.venv\Lib\site-packages\pyside6_essentials-*.dist-info\licenses') -DestinationName 'pyside6_essentials'

    $stubFlasherLicenseDirectory = Join-Path $licenseOutputDirectory 'esptool_stub_flasher'
    New-Item -ItemType Directory -Path $stubFlasherLicenseDirectory -Force | Out-Null
    Copy-LicenseFile -Path (Join-Path $repositoryRoot '.venv\Lib\site-packages\esptool\targets\stub_flasher\2\LICENSE-APACHE') -DestinationName 'esptool_stub_flasher\LICENSE-APACHE'
    Copy-LicenseFile -Path (Join-Path $repositoryRoot '.venv\Lib\site-packages\esptool\targets\stub_flasher\2\LICENSE-MIT') -DestinationName 'esptool_stub_flasher\LICENSE-MIT'

    $exePath = Join-Path $distDirectory 'popup-controller.exe'
    if (-not (Test-Path $exePath)) {
        throw "Build completed but executable was not found at $exePath"
    }

    Write-Host "Build complete: $exePath"
    Write-Host "Support files copied to: $distDirectory"
}
finally {
    Pop-Location
}
