# Third-Party Notices

The packaged application bundles open-source components. Their upstream projects and declared licenses are listed here for convenience.

## Direct runtime dependencies

- PySide6 6.10.2
  - Declared license: `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
  - Home page: <https://pyside.org>
- pyserial 3.5
  - Declared license: `BSD`
  - Home page: <https://github.com/pyserial/pyserial>
- esptool 5.2.0
  - Declared license: `GPLv2+`
  - Home page: <https://github.com/espressif/esptool/>

## esptool transitive runtime dependencies

The bundled `esptool` package also pulls in these Python packages at build time:

- bitstring
- click
- cryptography
- intelhex
- PyYAML
- reedsolo
- rich_click

Their exact versions are resolved in the build environment used to create the executable.

## Build-time tooling included in the executable stub

- PyInstaller 6.19.0
  - Declared license: `GPLv2-or-later with a special exception`
  - Home page: <https://pyinstaller.org>

## Included license texts

The build script copies available upstream license files into `dist\third_party_licenses\` for the bundled packages that ship them in the local Python environment.

## Distribution note

This repository is licensed as `GPL-2.0-or-later` so that the bundled flashing workflow remains compatible with the bundled `esptool` dependency.
