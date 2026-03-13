from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import shlex
import tempfile
import traceback
import zipfile


_MANIFEST_FILE_NAME = "flash_manifest.json"
_COMMAND_FILE_NAME = "esptool_command.txt"
_DEFAULT_CHIP = "esp32"
_DEFAULT_BAUDRATE = 460800
_COMMAND_LINE_RE = re.compile(r"^.*esptool.*$", re.IGNORECASE)
_BUNDLED_RUNTIME_DESCRIPTION = "bundled esptool"


@dataclass(frozen=True, slots=True)
class FlashResult:
    success: bool
    message: str


@dataclass(frozen=True, slots=True)
class FlashFile:
    offset: str
    file_name: str
    path: Path


@dataclass(frozen=True, slots=True)
class FlashBundle:
    source_path: Path
    build_version: str | None
    build_timestamp: str | None
    default_chip: str
    default_baudrate: int
    flash_files: tuple[FlashFile, ...]
    command_line: str | None


class FlashBundleError(RuntimeError):
    pass


class FirmwareService:
    def __init__(
        self,
        process_runner: Callable[[Sequence[str]], tuple[int, str, str]] | None = None,
        runtime_description: str = _BUNDLED_RUNTIME_DESCRIPTION,
    ) -> None:
        self._process_runner = process_runner or _run_esptool
        self._runtime_description = runtime_description

    def flash_firmware(self, port: str, firmware_path: Path) -> FlashResult:
        if not port:
            return FlashResult(False, "Select a serial port before flashing firmware.")

        if str(firmware_path).strip() in {"", "."}:
            return FlashResult(False, "Select a firmware bundle before flashing.")

        if not firmware_path.exists():
            return FlashResult(False, f"Firmware bundle not found: {firmware_path}")

        try:
            with _prepare_flash_bundle(firmware_path) as bundle:
                exit_code, stdout, stderr = self._process_runner(self._build_flash_arguments(bundle, port))
        except FlashBundleError as exc:
            return FlashResult(False, str(exc))
        except Exception as exc:
            return FlashResult(
                False,
                f"Firmware flash could not start using {self._runtime_description}: {exc}",
            )

        output_summary = _summarize_process_output(stdout, stderr)
        bundle_description = _describe_bundle(bundle)
        if exit_code != 0:
            message = f"Firmware flash failed for {bundle_description} on {port}."
            if output_summary:
                message = f"{message} {output_summary}"
            return FlashResult(False, message)

        message = f"Flashed {bundle_description} to {port} using {self._runtime_description}."
        if output_summary:
            message = f"{message} {output_summary}"
        return FlashResult(True, message)

    def _build_flash_arguments(self, bundle: FlashBundle, port: str) -> list[str]:
        if bundle.command_line:
            command_arguments = _build_arguments_from_command_line(bundle.command_line, bundle.flash_files, port)
            if command_arguments:
                return command_arguments

        command_arguments = [
            "--chip",
            bundle.default_chip,
            "--port",
            port,
            "--baud",
            str(bundle.default_baudrate),
            "write_flash",
        ]
        for flash_file in bundle.flash_files:
            command_arguments.extend((flash_file.offset, str(flash_file.path)))
        return command_arguments


@contextmanager
def _prepare_flash_bundle(firmware_path: Path) -> Iterator[FlashBundle]:
    normalized_path = firmware_path.resolve()

    if normalized_path.is_dir():
        manifest_path = _find_manifest_path(normalized_path)
        yield _load_flash_bundle(manifest_path, normalized_path)
        return

    if normalized_path.name.casefold() == _MANIFEST_FILE_NAME:
        yield _load_flash_bundle(normalized_path, normalized_path)
        return

    if normalized_path.suffix.casefold() != ".zip":
        raise FlashBundleError(
            "Select a flash bundle .zip, an extracted flash bundle directory, or a flash_manifest.json file."
        )

    try:
        with tempfile.TemporaryDirectory(prefix="popup-controller-flash-") as temp_dir:
            extraction_root = Path(temp_dir)
            with zipfile.ZipFile(normalized_path) as archive:
                archive.extractall(extraction_root)
            manifest_path = _find_manifest_path(extraction_root)
            yield _load_flash_bundle(manifest_path, normalized_path)
    except zipfile.BadZipFile as exc:
        raise FlashBundleError(f"Invalid flash bundle zip: {normalized_path}") from exc


def _find_manifest_path(root: Path) -> Path:
    candidates = sorted(root.rglob(_MANIFEST_FILE_NAME))
    if not candidates:
        raise FlashBundleError(f"No {_MANIFEST_FILE_NAME} file was found in {root}.")
    if len(candidates) > 1:
        raise FlashBundleError(f"Multiple {_MANIFEST_FILE_NAME} files were found in {root}.")
    return candidates[0]


def _load_flash_bundle(manifest_path: Path, source_path: Path) -> FlashBundle:
    try:
        raw_manifest = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FlashBundleError(f"Unable to read flash manifest: {manifest_path}") from exc

    try:
        manifest = json.loads(raw_manifest)
    except json.JSONDecodeError as exc:
        raise FlashBundleError(f"Invalid flash manifest JSON: {manifest_path}") from exc

    flash_entries = manifest.get("flash_files")
    if not isinstance(flash_entries, list) or not flash_entries:
        raise FlashBundleError("Flash manifest does not list any flash files.")

    flash_files: list[FlashFile] = []
    for entry in flash_entries:
        if not isinstance(entry, dict):
            raise FlashBundleError("Flash manifest contains an invalid flash_files entry.")

        offset = str(entry.get("offset", "")).strip()
        file_name = str(entry.get("file", "")).strip()
        if not offset or not file_name:
            raise FlashBundleError("Each flash_files entry must define both offset and file.")

        file_path = manifest_path.parent / file_name
        if not file_path.is_file():
            raise FlashBundleError(f"Flash file listed in manifest is missing: {file_name}")

        flash_files.append(FlashFile(offset=offset, file_name=file_name, path=file_path))

    command_line = _read_optional_command_line(manifest_path.parent / _COMMAND_FILE_NAME)
    default_chip = _string_or_none(manifest.get("chip")) or _parse_command_flag(command_line, "--chip") or _DEFAULT_CHIP
    default_baudrate = _parse_manifest_baudrate(manifest) or _parse_baudrate(command_line) or _DEFAULT_BAUDRATE

    return FlashBundle(
        source_path=source_path,
        build_version=_string_or_none(manifest.get("build_version")),
        build_timestamp=_string_or_none(manifest.get("build_timestamp")),
        default_chip=default_chip,
        default_baudrate=default_baudrate,
        flash_files=tuple(flash_files),
        command_line=command_line,
    )


def _read_optional_command_line(command_path: Path) -> str | None:
    if not command_path.is_file():
        return None

    try:
        text = command_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _COMMAND_LINE_RE.match(stripped) and "write_flash" in stripped:
            return stripped
    return None


def _parse_manifest_baudrate(manifest: dict[object, object]) -> int | None:
    for key in ("baudrate", "baud"):
        value = manifest.get(key)
        if value is None:
            continue
        try:
            return int(str(value).strip())
        except ValueError:
            return None
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_command_flag(command_line: str | None, flag: str) -> str | None:
    if not command_line:
        return None

    tokens = shlex.split(command_line, posix=True)
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            value = tokens[index + 1].strip()
            return value or None
    return None


def _parse_baudrate(command_line: str | None) -> int | None:
    value = _parse_command_flag(command_line, "--baud")
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def _build_arguments_from_command_line(
    command_line: str,
    flash_files: tuple[FlashFile, ...],
    port: str,
) -> list[str]:
    tokens = shlex.split(command_line, posix=True)
    if not tokens:
        return []

    argument_start = _find_argument_start(tokens)
    arguments = tokens[argument_start:]
    if not arguments or "write_flash" not in arguments:
        return []

    if "--port" not in arguments:
        write_flash_index = arguments.index("write_flash")
        arguments = [*arguments[:write_flash_index], "--port", port, *arguments[write_flash_index:]]

    file_lookup = {flash_file.file_name: str(flash_file.path) for flash_file in flash_files}
    return [file_lookup.get(argument, argument) for argument in arguments]


def _find_argument_start(tokens: list[str]) -> int:
    for index, token in enumerate(tokens):
        normalized = Path(token).name.casefold()
        if normalized in {"esptool", "esptool.py"}:
            return index + 1
    return 0


def _run_esptool(arguments: Sequence[str]) -> tuple[int, str, str]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 0

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            import esptool

            esptool.main(list(arguments))
        except SystemExit as exc:
            exit_code = _coerce_exit_code(exc.code)
        except Exception:
            exit_code = 1
            traceback.print_exc(file=stderr_buffer)

    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _coerce_exit_code(code: object) -> int:
    if code in (None, 0, False):
        return 0
    if isinstance(code, int):
        return code
    return 1


def _describe_bundle(bundle: FlashBundle) -> str:
    version = bundle.build_version
    timestamp = bundle.build_timestamp
    if version and timestamp:
        return f"build {version} ({timestamp})"
    if version:
        return f"build {version}"
    if timestamp:
        return f"firmware built at {timestamp}"
    return bundle.source_path.name


def _summarize_process_output(stdout: str, stderr: str) -> str:
    lines = [line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1]
