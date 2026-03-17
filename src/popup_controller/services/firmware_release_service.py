from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_DEFAULT_RELEASE_METADATA_URL = "https://api.github.com/repos/sheep-celica/pop-up-controller-v10/releases"
_GITHUB_API_ACCEPT = "application/vnd.github+json"
_HTTP_TIMEOUT_SECONDS = 20
_VERSION_RE = re.compile(
    r"(?<!\d)(?:v(?:ersion)?[._\s-]*)?(?P<version>\d+(?:\.\d+){1,3}(?:[-+._][0-9A-Za-z]+)*)",
    re.IGNORECASE,
)
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class FirmwareReleaseInfo:
    version: str | None
    release_name: str
    tag_name: str
    asset_name: str
    download_url: str
    asset_size_bytes: int | None
    asset_sha256: str | None
    published_at: str | None
    updated_at: str | None
    html_url: str | None


@dataclass(frozen=True, slots=True)
class FirmwareDownloadResult:
    path: Path
    downloaded: bool


class FirmwareReleaseError(RuntimeError):
    pass


class FirmwareReleaseService:
    def __init__(
        self,
        release_metadata_url: str = _DEFAULT_RELEASE_METADATA_URL,
        metadata_fetcher: Callable[[str], bytes] | None = None,
        asset_fetcher: Callable[[str], bytes] | None = None,
    ) -> None:
        self._release_metadata_url = release_metadata_url
        self._metadata_fetcher = metadata_fetcher or _download_json_bytes
        self._asset_fetcher = asset_fetcher or _download_binary_bytes

    def fetch_latest_release(self) -> FirmwareReleaseInfo:
        try:
            payload = json.loads(self._metadata_fetcher(self._release_metadata_url).decode("utf-8"))
        except FirmwareReleaseError:
            raise
        except json.JSONDecodeError as exc:
            raise FirmwareReleaseError("GitHub returned invalid release metadata.") from exc

        return _parse_latest_release(payload)

    def download_release_asset(
        self,
        release: FirmwareReleaseInfo,
        destination_directory: Path,
    ) -> FirmwareDownloadResult:
        try:
            destination_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FirmwareReleaseError(f"Unable to create firmware download directory: {destination_directory}") from exc

        file_name = Path(release.asset_name).name.strip()
        if not file_name:
            raise FirmwareReleaseError("GitHub returned an invalid firmware asset name.")

        target_path = destination_directory / file_name
        if _is_cached_file_valid(target_path, release):
            return FirmwareDownloadResult(path=target_path, downloaded=False)

        try:
            asset_bytes = self._asset_fetcher(release.download_url)
        except FirmwareReleaseError:
            raise
        except Exception as exc:
            raise FirmwareReleaseError(f"Unable to download firmware asset from GitHub: {exc}") from exc

        if release.asset_size_bytes is not None and len(asset_bytes) != release.asset_size_bytes:
            raise FirmwareReleaseError(
                f"Downloaded firmware size did not match GitHub metadata for {release.asset_name}."
            )

        actual_sha256 = hashlib.sha256(asset_bytes).hexdigest()
        if release.asset_sha256 is not None and actual_sha256 != release.asset_sha256:
            raise FirmwareReleaseError(
                f"Downloaded firmware checksum did not match GitHub metadata for {release.asset_name}."
            )

        temp_path = target_path.with_name(f"{target_path.name}.download")
        try:
            temp_path.write_bytes(asset_bytes)
            temp_path.replace(target_path)
        except OSError as exc:
            raise FirmwareReleaseError(f"Unable to save firmware download to {target_path}.") from exc

        return FirmwareDownloadResult(path=target_path, downloaded=True)


def _parse_latest_release(payload: object) -> FirmwareReleaseInfo:
    if isinstance(payload, dict):
        return _release_info_from_payload(payload)

    if not isinstance(payload, list):
        raise FirmwareReleaseError("GitHub returned an unexpected release response.")

    best_release: FirmwareReleaseInfo | None = None
    best_key: tuple[object, ...] | None = None
    for entry in payload:
        if not isinstance(entry, dict) or _should_skip_release(entry):
            continue

        try:
            release = _release_info_from_payload(entry)
        except FirmwareReleaseError:
            continue

        release_key = _release_sort_key(release)
        if best_key is None or release_key > best_key:
            best_release = release
            best_key = release_key

    if best_release is None:
        raise FirmwareReleaseError("GitHub did not return any stable firmware releases with downloadable .zip assets.")

    return best_release


def _release_info_from_payload(payload: dict[object, object]) -> FirmwareReleaseInfo:
    asset = _select_zip_asset(payload.get("assets"))
    release_name = _string_or_empty(payload.get("name"))
    tag_name = _string_or_empty(payload.get("tag_name"))
    asset_name = _string_or_empty(asset.get("name"))
    version = _extract_version(release_name, tag_name, asset_name)

    return FirmwareReleaseInfo(
        version=version,
        release_name=release_name,
        tag_name=tag_name,
        asset_name=asset_name,
        download_url=_required_text(asset.get("browser_download_url"), "download URL"),
        asset_size_bytes=_int_or_none(asset.get("size")),
        asset_sha256=_parse_sha256_digest(asset.get("digest")),
        published_at=_string_or_none(payload.get("published_at")),
        updated_at=_string_or_none(payload.get("updated_at")),
        html_url=_string_or_none(payload.get("html_url")),
    )


def _release_sort_key(release: FirmwareReleaseInfo) -> tuple[object, ...]:
    return (
        release.version is not None,
        _version_key(release.version),
        release.published_at or "",
        release.updated_at or "",
        release.tag_name,
        release.asset_name,
    )


def _version_key(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()

    number_parts: list[int] = []
    for part in version.split("."):
        if part.isdigit():
            number_parts.append(int(part))
            continue

        digit_prefix = "".join(character for character in part if character.isdigit())
        if digit_prefix:
            number_parts.append(int(digit_prefix))
        break
    return tuple(number_parts)


def _should_skip_release(payload: dict[object, object]) -> bool:
    return bool(payload.get("draft")) or bool(payload.get("prerelease"))


def _select_zip_asset(assets: object) -> dict[object, object]:
    if not isinstance(assets, list):
        raise FirmwareReleaseError("GitHub release metadata did not include any downloadable assets.")

    for asset in assets:
        if not isinstance(asset, dict):
            continue

        asset_name = _string_or_none(asset.get("name"))
        if asset_name and asset_name.casefold().endswith(".zip") and _string_or_none(asset.get("browser_download_url")):
            return asset

    raise FirmwareReleaseError("GitHub release metadata did not include a downloadable .zip firmware asset.")


def _extract_version(*candidates: str) -> str | None:
    for candidate in candidates:
        match = _VERSION_RE.search(candidate)
        if not match:
            continue

        version = match.group("version")
        if candidate.casefold().endswith(".zip") and version.casefold().endswith(".zip"):
            version = version[:-4]
        return version.rstrip(".")
    return None


def _parse_sha256_digest(value: object) -> str | None:
    digest = _string_or_none(value)
    if digest is None:
        return None
    if digest.casefold().startswith(_SHA256_PREFIX):
        return digest[len(_SHA256_PREFIX) :]
    return None


def _is_cached_file_valid(path: Path, release: FirmwareReleaseInfo) -> bool:
    if not path.is_file():
        return False

    if release.asset_size_bytes is not None:
        try:
            if path.stat().st_size != release.asset_size_bytes:
                return False
        except OSError:
            return False

    if release.asset_sha256 is None:
        return False

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == release.asset_sha256
    except OSError:
        return False


def _required_text(value: object, field_name: str) -> str:
    text = _string_or_none(value)
    if text is None:
        raise FirmwareReleaseError(f"GitHub release metadata was missing the {field_name}.")
    return text


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_or_empty(value: object) -> str:
    return _string_or_none(value) or ""


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _download_json_bytes(url: str) -> bytes:
    return _download_bytes(url, accept=_GITHUB_API_ACCEPT)


def _download_binary_bytes(url: str) -> bytes:
    return _download_bytes(url)


def _download_bytes(url: str, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "popup-controller"}
    if accept:
        headers["Accept"] = accept

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            return response.read()
    except HTTPError as exc:
        raise FirmwareReleaseError(f"GitHub request failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise FirmwareReleaseError(f"Unable to reach GitHub: {reason}") from exc
