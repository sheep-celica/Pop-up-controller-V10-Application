# Pop-up Controller V10 Application

Open-source PySide6 desktop application for communicating with and flashing an ESP32 on a Pop-up controller V10 over serial.
All revisions of the V10 will be supported.

Check releases for exe builds!  
https://github.com/sheep-celica/Pop-up-controller-V10-Application/releases

![Screenshot](image_examples/app_example.png)

## License

This project is licensed under `GPL-2.0-or-later`.

See [LICENSE](LICENSE) for the full license text and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled dependency notices.

## Features

- Detect and connect to the controller over serial
- Read controller build information, status, errors, manufacture data, and settings
- Send direct control commands and protected service commands
- Flash ESP32 firmware bundles from `pop_up_controller_v10_firmware_v_x.x.x.zip`
- Package a standalone Windows executable with PyInstaller and bundled `esptool`

## Further documentation

- [Documentation Index](docs/README.md)
- [Architecture Notes](docs/architecture.md)
- [Semantic Coloring Rules](docs/semantic-coloring.md)

## Development setup

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Flash bundle format

The flashing workflow expects either:

- a `pop_up_controller_v10_firmware_v_x.x.x.zip` that contains `flash_manifest.json` plus the referenced binary images, or
- an extracted bundle directory, or
- a standalone `flash_manifest.json` next to the referenced images.

The current firmware bundle in [firmware/pop_up_controller_v10_firmware_v_1.0.5.zip](firmware/pop_up_controller_v10_firmware_v_1.0.5.zip) is compatible with the built-in flashing workflow.

## Building the executable

Use the PowerShell helper script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
scripts\build_exe.ps1
```

The script:

- optionally runs the test suite first
- runs PyInstaller with the checked-in spec file
- embeds the app icon and bundles the Python `esptool` package inside the executable
- writes a versioned executable such as `popup-controller-v1.0.0.exe`
- copies `LICENSE`, `README.md`, and `THIRD_PARTY_NOTICES.md` into `dist\`
- copies the local `firmware\` directory into `dist\firmware\`
- copies available third-party license texts into `dist\third_party_licenses\`

To skip tests during a local packaging iteration:

```powershell
scripts\build_exe.ps1 -SkipTests
```

## Automated release builds

GitHub Actions now builds the release archive automatically when you publish a GitHub release.

The release workflow:

- reads the release tag such as `v1.0.13`
- injects that version into `src\popup_controller\__init__.py` for the build
- installs the project into a fresh `.venv`
- runs the packaging script on a `windows-latest` runner
- zips the `dist\` folder
- uploads the zip back to the same GitHub release as an attachment

This removes the old local version-bump flow and makes the GitHub release tag the source of truth for packaged builds.

You can also test the release build manually from the Actions tab with the `Build Release Package` workflow and a tag input.

## Distribution note

Binary distributions of this application should be shared together with the corresponding source code, or with a clear link to the public source repository, so the GPL obligations remain satisfied.

## Project layout

```text
.
|-- .github/
|-- .githooks/
|-- docs/
|-- firmware/
|-- scripts/
|-- src/
|   `-- popup_controller/
|-- tests/
|-- LICENSE
|-- THIRD_PARTY_NOTICES.md
|-- popup-controller.spec
`-- pyproject.toml
```
