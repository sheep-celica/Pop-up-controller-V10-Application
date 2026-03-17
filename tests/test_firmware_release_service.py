import hashlib
import json
from pathlib import Path

import pytest

from popup_controller.services.firmware_release_service import (
    FirmwareReleaseError,
    FirmwareReleaseInfo,
    FirmwareReleaseService,
)


RELEASE_ASSET_BYTES = b"flash bundle bytes"
RELEASE_ASSET_DIGEST = hashlib.sha256(RELEASE_ASSET_BYTES).hexdigest()


def _release_payload(
    version: str,
    *,
    tag_name: str | None = None,
    release_name: str | None = None,
    published_at: str = "2026-03-15T17:57:58Z",
    prerelease: bool = False,
    draft: bool = False,
) -> dict[str, object]:
    normalized_tag_name = tag_name or f"v{version}"
    normalized_release_name = release_name or f"Firmware version {version}"
    return {
        "name": normalized_release_name,
        "tag_name": normalized_tag_name,
        "published_at": published_at,
        "updated_at": published_at,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": f"https://github.com/sheep-celica/pop-up-controller-v10/releases/tag/{normalized_tag_name}",
        "assets": [
            {
                "name": f"pop_up_controller_v10_firmware_v_{version}.zip",
                "browser_download_url": (
                    "https://github.com/sheep-celica/pop-up-controller-v10/releases/download/"
                    f"{normalized_tag_name}/pop_up_controller_v10_firmware_v_{version}.zip"
                ),
                "size": len(RELEASE_ASSET_BYTES),
                "digest": f"sha256:{RELEASE_ASSET_DIGEST}",
            }
        ],
    }


def test_fetch_latest_release_parses_version_from_single_release_payload() -> None:
    payload = _release_payload("1.0.9")
    service = FirmwareReleaseService(metadata_fetcher=lambda url: json.dumps(payload).encode("utf-8"))

    release = service.fetch_latest_release()

    assert release.version == "1.0.9"
    assert release.tag_name == "v1.0.9"
    assert release.asset_name == "pop_up_controller_v10_firmware_v_1.0.9.zip"
    assert release.download_url.endswith("pop_up_controller_v10_firmware_v_1.0.9.zip")
    assert release.asset_sha256 == RELEASE_ASSET_DIGEST


def test_fetch_latest_release_selects_highest_version_from_release_list() -> None:
    payload = [
        _release_payload("1.0.9", published_at="2026-03-15T17:57:58Z"),
        _release_payload("1.0.12", published_at="2026-03-17T21:13:16Z"),
    ]
    service = FirmwareReleaseService(metadata_fetcher=lambda url: json.dumps(payload).encode("utf-8"))

    release = service.fetch_latest_release()

    assert release.version == "1.0.12"
    assert release.tag_name == "v1.0.12"
    assert release.asset_name == "pop_up_controller_v10_firmware_v_1.0.12.zip"


def test_fetch_latest_release_ignores_prerelease_when_stable_release_exists() -> None:
    payload = [
        _release_payload("1.0.13", published_at="2026-03-18T08:00:00Z", prerelease=True),
        _release_payload("1.0.12", published_at="2026-03-17T21:13:16Z"),
    ]
    service = FirmwareReleaseService(metadata_fetcher=lambda url: json.dumps(payload).encode("utf-8"))

    release = service.fetch_latest_release()

    assert release.version == "1.0.12"


def test_fetch_latest_release_supports_tag_names_with_dot_after_v() -> None:
    payload = _release_payload("1.0.12", tag_name="v.1.0.12", release_name="Firmware version 1.0.12")
    service = FirmwareReleaseService(metadata_fetcher=lambda url: json.dumps(payload).encode("utf-8"))

    release = service.fetch_latest_release()

    assert release.version == "1.0.12"
    assert release.tag_name == "v.1.0.12"


def test_fetch_latest_release_requires_zip_asset() -> None:
    payload = _release_payload("1.0.9")
    payload["assets"] = [{"name": "notes.txt", "browser_download_url": "https://example.invalid/notes.txt"}]
    service = FirmwareReleaseService(metadata_fetcher=lambda url: json.dumps(payload).encode("utf-8"))

    with pytest.raises(FirmwareReleaseError, match=".zip"):
        service.fetch_latest_release()


def test_download_release_asset_saves_file_and_reuses_valid_cache(tmp_path: Path) -> None:
    download_calls: list[str] = []

    def fake_asset_fetcher(url: str) -> bytes:
        download_calls.append(url)
        return RELEASE_ASSET_BYTES

    release = FirmwareReleaseInfo(
        version="1.0.12",
        release_name="Firmware version 1.0.12",
        tag_name="v1.0.12",
        asset_name="pop_up_controller_v10_firmware_v_1.0.12.zip",
        download_url="https://example.invalid/firmware.zip",
        asset_size_bytes=len(RELEASE_ASSET_BYTES),
        asset_sha256=RELEASE_ASSET_DIGEST,
        published_at="2026-03-17T21:13:16Z",
        updated_at="2026-03-17T21:13:16Z",
        html_url="https://example.invalid/releases/tag/v1.0.12",
    )
    service = FirmwareReleaseService(asset_fetcher=fake_asset_fetcher)

    first_result = service.download_release_asset(release, tmp_path)
    second_result = service.download_release_asset(release, tmp_path)

    assert first_result.downloaded is True
    assert second_result.downloaded is False
    assert first_result.path.read_bytes() == RELEASE_ASSET_BYTES
    assert second_result.path == first_result.path
    assert download_calls == ["https://example.invalid/firmware.zip"]
