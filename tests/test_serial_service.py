from __future__ import annotations

import pytest

from popup_controller.services.serial_service import SerialConnectionError, SerialService


class _OpenConnection:
    def __init__(self, port: str) -> None:
        self.port = port
        self.is_open = True


def test_connect_to_controller_returns_probe_response(monkeypatch) -> None:
    service = SerialService()
    request_calls: list[tuple[str, dict[str, object]]] = []

    def fake_connect(port: str) -> None:
        service._serial = _OpenConnection(port)

    def fake_request_text(command: str, **kwargs) -> str:
        request_calls.append((command, kwargs))
        return "[15] Available commands:\n[15] help\n"

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "request_text", fake_request_text)

    response = service.connect_to_controller(
        "COM9",
        warmup_seconds=0.0,
        probe_window_seconds=1.2,
    )

    assert "Available commands:" in response
    assert request_calls == [
        (
            "help",
            {
                "idle_timeout_seconds": 0.35,
                "max_duration_seconds": 1.2,
                "progress_callback": None,
            },
        )
    ]
    assert service.is_connected is True
    assert service.port_name == "COM9"


def test_connect_to_controller_disconnects_when_probe_reply_is_invalid(monkeypatch) -> None:
    service = SerialService()
    disconnect_calls = 0

    def fake_connect(port: str) -> None:
        service._serial = _OpenConnection(port)

    def fake_disconnect() -> None:
        nonlocal disconnect_calls
        disconnect_calls += 1
        service._serial = None

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "disconnect", fake_disconnect)
    monkeypatch.setattr(service, "request_text", lambda command, **kwargs: "boot:0x13 SPI_FAST_FLASH_BOOT\n")

    with pytest.raises(
        SerialConnectionError,
        match="did not answer the controller probe",
    ):
        service.connect_to_controller(
            "COM9",
            warmup_seconds=0.0,
            probe_window_seconds=1.2,
        )

    assert disconnect_calls == 1
    assert service.is_connected is False
