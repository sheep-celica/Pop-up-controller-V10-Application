from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_INIT_PATH = REPOSITORY_ROOT / "src" / "popup_controller" / "__init__.py"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
_VERSION_PATTERN = re.compile(r'^__version__ = "(?P<version>\d+\.\d+\.\d+)"$', re.MULTILINE)
_PYPROJECT_VERSION_PATTERN = re.compile(r'^version = "(?P<version>\d+\.\d+\.\d+)"$', re.MULTILINE)


class VersioningError(RuntimeError):
    pass


def _extract_version(path: Path, pattern: re.Pattern[str]) -> str:
    text = path.read_text(encoding="utf-8-sig")
    match = pattern.search(text)
    if match is None:
        raise VersioningError(f"Unable to locate a version string in {path}.")
    return match.group("version")


def current_version() -> str:
    package_version = _extract_version(PACKAGE_INIT_PATH, _VERSION_PATTERN)
    pyproject_version = _extract_version(PYPROJECT_PATH, _PYPROJECT_VERSION_PATTERN)
    if package_version != pyproject_version:
        raise VersioningError(
            "Version mismatch between src/popup_controller/__init__.py "
            f"({package_version}) and pyproject.toml ({pyproject_version})."
        )
    return package_version


def bump_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _replace_version(path: Path, pattern: re.Pattern[str], new_version: str) -> None:
    original_text = path.read_text(encoding="utf-8-sig")
    updated_text, replacements = pattern.subn(lambda _: _.group(0).replace(_.group("version"), new_version), original_text, count=1)
    if replacements != 1:
        raise VersioningError(f"Unable to update version in {path}.")
    path.write_text(updated_text, encoding="utf-8")


def set_version(new_version: str) -> None:
    _replace_version(PACKAGE_INIT_PATH, _VERSION_PATTERN, new_version)
    _replace_version(PYPROJECT_PATH, _PYPROJECT_VERSION_PATTERN, new_version)


def stage_version_files() -> None:
    subprocess.run(
        [
            "git",
            "add",
            "--",
            str(PACKAGE_INIT_PATH.relative_to(REPOSITORY_ROOT)),
            str(PYPROJECT_PATH.relative_to(REPOSITORY_ROOT)),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read or bump the application version.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("current", help="Print the current synchronized version.")

    bump_parser = subcommands.add_parser("bump", help="Increment the patch version.")
    bump_parser.add_argument("--stage", action="store_true", help="Stage the modified version files with git add.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        if args.command == "current":
            print(current_version())
            return 0

        if args.command == "bump":
            new_version = bump_patch(current_version())
            set_version(new_version)
            if args.stage:
                stage_version_files()
            print(new_version)
            return 0
    except VersioningError as exc:
        print(exc, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Git command failed while staging version files: {exc}", file=sys.stderr)
        return exc.returncode or 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
