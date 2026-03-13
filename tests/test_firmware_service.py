from pathlib import Path
import zipfile

from popup_controller.services.firmware_service import FirmwareService


FLASH_MANIFEST = {
    "project": "pop-up-controller-v10",
    "environment": "esp32doit-devkit-v1",
    "build_version": "1.0.4",
    "build_timestamp": "2026-03-13T21:46:11Z",
    "flash_files": [
        {"offset": "0x1000", "file": "bootloader.bin"},
        {"offset": "0x8000", "file": "partitions.bin"},
        {"offset": "0xE000", "file": "boot_app0.bin"},
        {"offset": "0x10000", "file": "firmware.bin"},
    ],
}


def _write_flash_bundle(zip_path: Path, include_command: bool = True, include_manifest: bool = True) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        if include_manifest:
            archive.writestr("flash_manifest.json", __import__("json").dumps(FLASH_MANIFEST))
        if include_command:
            archive.writestr(
                "esptool_command.txt",
                "Run this from inside the flash_bundle directory:\n"
                "python -m esptool --chip esp32 --baud 460800 write_flash "
                "0x1000 bootloader.bin 0x8000 partitions.bin 0xE000 boot_app0.bin 0x10000 firmware.bin\n",
            )
        archive.writestr("bootloader.bin", b"bootloader")
        archive.writestr("partitions.bin", b"partitions")
        archive.writestr("boot_app0.bin", b"bootapp0")
        archive.writestr("firmware.bin", b"firmware")


def test_flash_firmware_requires_port(tmp_path: Path) -> None:
    bundle_path = tmp_path / "flash_bundle.zip"
    _write_flash_bundle(bundle_path)

    service = FirmwareService(process_runner=lambda command: (0, "", ""), runtime_description="Test esptool")

    result = service.flash_firmware("", bundle_path)

    assert result.success is False
    assert "serial port" in result.message.lower()


def test_flash_firmware_uses_zip_manifest_and_command_template(tmp_path: Path) -> None:
    bundle_path = tmp_path / "flash_bundle.zip"
    _write_flash_bundle(bundle_path)
    captured: dict[str, list[str]] = {}

    def fake_runner(command: list[str]) -> tuple[int, str, str]:
        captured["command"] = list(command)
        return 0, "Hash of data verified.\nHard resetting via RTS pin...\n", ""

    service = FirmwareService(process_runner=fake_runner, runtime_description="Test esptool")

    result = service.flash_firmware("COM11", bundle_path)

    assert result.success is True
    assert "build 1.0.4" in result.message
    assert "Test esptool" in result.message

    command = captured["command"]
    assert command[:4] == ["--chip", "esp32", "--baud", "460800"]
    assert "--port" in command
    assert command[command.index("--port") + 1] == "COM11"
    assert "write_flash" in command
    assert any(part.endswith("bootloader.bin") for part in command)
    assert any(part.endswith("partitions.bin") for part in command)
    assert any(part.endswith("boot_app0.bin") for part in command)
    assert any(part.endswith("firmware.bin") for part in command)


def test_flash_firmware_reports_missing_manifest_in_zip(tmp_path: Path) -> None:
    bundle_path = tmp_path / "broken_flash_bundle.zip"
    _write_flash_bundle(bundle_path, include_manifest=False)

    service = FirmwareService(process_runner=lambda command: (0, "", ""), runtime_description="Test esptool")

    result = service.flash_firmware("COM11", bundle_path)

    assert result.success is False
    assert "flash_manifest.json" in result.message


def test_flash_firmware_reports_esptool_failure(tmp_path: Path) -> None:
    bundle_path = tmp_path / "flash_bundle.zip"
    _write_flash_bundle(bundle_path, include_command=False)

    service = FirmwareService(
        process_runner=lambda command: (2, "", "A fatal error occurred: Failed to connect to ESP32"),
        runtime_description="Test esptool",
    )

    result = service.flash_firmware("COM11", bundle_path)

    assert result.success is False
    assert "failed" in result.message.lower()
    assert "Failed to connect to ESP32" in result.message


def test_flash_firmware_reports_runner_start_failure(tmp_path: Path) -> None:
    bundle_path = tmp_path / "flash_bundle.zip"
    _write_flash_bundle(bundle_path)

    def broken_runner(command: list[str]) -> tuple[int, str, str]:
        raise RuntimeError("esptool import failed")

    service = FirmwareService(process_runner=broken_runner, runtime_description="Test esptool")

    result = service.flash_firmware("COM11", bundle_path)

    assert result.success is False
    assert "could not start" in result.message.lower()
    assert "esptool import failed" in result.message
