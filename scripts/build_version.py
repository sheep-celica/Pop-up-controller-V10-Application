from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_INIT_PATH = REPOSITORY_ROOT / "src" / "popup_controller" / "__init__.py"
VERSION_PATTERN = re.compile(r'^__version__ = "(?P<version>\d+\.\d+\.\d+)"$', re.MULTILINE)
TAG_PATTERN = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+)$")


class BuildVersionError(RuntimeError):
    pass


def current_version(path: Path = PACKAGE_INIT_PATH) -> str:
    text = path.read_text(encoding="utf-8-sig")
    match = VERSION_PATTERN.search(text)
    if match is None:
        raise BuildVersionError(f"Unable to locate __version__ in {path}.")
    return match.group("version")


def normalize_version(value: str) -> str:
    normalized = value.strip()
    if TAG_PATTERN.fullmatch(normalized) is None:
        raise BuildVersionError(f"Version '{value}' must look like 1.2.3 or v1.2.3.")
    return normalized.removeprefix("v")


def version_from_tag(tag: str) -> str:
    return normalize_version(tag)


def set_version(new_version: str, path: Path = PACKAGE_INIT_PATH) -> str:
    normalized_version = normalize_version(new_version)
    original_text = path.read_text(encoding="utf-8-sig")
    updated_text, replacements = VERSION_PATTERN.subn(
        lambda match: match.group(0).replace(match.group("version"), normalized_version),
        original_text,
        count=1,
    )
    if replacements != 1:
        raise BuildVersionError(f"Unable to update __version__ in {path}.")
    path.write_text(updated_text, encoding="utf-8")
    return normalized_version


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read or update the checked-in build version.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("current", help="Print the current checked-in build version.")

    set_parser = subcommands.add_parser("set", help="Write an explicit version into src/popup_controller/__init__.py.")
    set_parser.add_argument("version", help="Version to write, for example 1.2.3.")

    tag_parser = subcommands.add_parser(
        "from-tag",
        help="Write a version derived from a git/GitHub tag into src/popup_controller/__init__.py.",
    )
    tag_parser.add_argument("tag", help="Tag to convert, for example v1.2.3.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        if args.command == "current":
            print(current_version())
            return 0

        if args.command == "set":
            print(set_version(args.version))
            return 0

        if args.command == "from-tag":
            print(set_version(version_from_tag(args.tag)))
            return 0
    except BuildVersionError as exc:
        print(exc, file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
