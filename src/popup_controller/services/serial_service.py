from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

import serial
from serial import SerialException
from serial.tools import list_ports


@dataclass(frozen=True, slots=True)
class SerialPortInfo:
    device: str
    description: str


class SerialConnectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ControllerDetectionResult:
    port: SerialPortInfo
    response: str


class SerialService:
    def __init__(
        self,
        baudrate: int = 115200,
        timeout_seconds: float = 0.1,
        command_terminator: bytes = b"\n",
    ) -> None:
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.command_terminator = command_terminator
        self._serial: serial.Serial | None = None
        self._read_buffer = ""

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    @property
    def port_name(self) -> str | None:
        if not self._serial:
            return None
        return self._serial.port

    def available_ports(self) -> list[SerialPortInfo]:
        ports = sorted(list_ports.comports(), key=lambda port: port.device)
        return [
            SerialPortInfo(
                device=port.device,
                description=port.description or "Serial device",
            )
            for port in ports
        ]

    def find_controller_port(
        self,
        probe_command: str = "help",
        expected_response_fragment: str = "Available commands:",
        warmup_seconds: float = 1.5,
        probe_window_seconds: float = 1.2,
    ) -> ControllerDetectionResult | None:
        if self.is_connected:
            raise SerialConnectionError("Disconnect before searching for the controller.")

        for port_info in self.available_ports():
            response = self._probe_port(
                port=port_info.device,
                probe_command=probe_command,
                warmup_seconds=warmup_seconds,
                probe_window_seconds=probe_window_seconds,
            )
            if expected_response_fragment in response:
                return ControllerDetectionResult(port=port_info, response=response)

        return None

    def connect(self, port: str) -> None:
        if self.is_connected and self.port_name == port:
            return

        if self.is_connected:
            self.disconnect()

        try:
            self._serial = self._open_port(port)
            self._read_buffer = ""
        except SerialException as exc:
            raise SerialConnectionError(f"Unable to open {port}: {exc}") from exc

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()

        self._serial = None
        self._read_buffer = ""

    def send_command(self, command: str) -> None:
        if not self.is_connected or not self._serial:
            raise SerialConnectionError("No serial connection is currently open.")

        payload = command.rstrip("\r\n").encode("utf-8") + self.command_terminator

        try:
            self._serial.write(payload)
            self._serial.flush()
        except SerialException as exc:
            raise SerialConnectionError(f"Unable to send command: {exc}") from exc

    def request_text(
        self,
        command: str,
        idle_timeout_seconds: float = 0.35,
        max_duration_seconds: float = 2.5,
        clear_input_buffer: bool = True,
        progress_callback: Callable[[], None] | None = None,
    ) -> str:
        if not self.is_connected or not self._serial:
            raise SerialConnectionError("No serial connection is currently open.")

        try:
            if clear_input_buffer:
                self._serial.reset_input_buffer()
                self._read_buffer = ""

            self.send_command(command)
            return self._read_until_idle(
                self._serial,
                idle_timeout_seconds=idle_timeout_seconds,
                max_duration_seconds=max_duration_seconds,
                progress_callback=progress_callback,
            )
        except SerialException as exc:
            raise SerialConnectionError(f"Unable to request controller data: {exc}") from exc

    def read_available(self) -> list[str]:
        if not self.is_connected or not self._serial:
            return []

        try:
            pending_bytes = self._serial.in_waiting
            if pending_bytes <= 0:
                return []

            raw = self._serial.read(pending_bytes)
        except SerialException as exc:
            raise SerialConnectionError(f"Unable to read from serial port: {exc}") from exc

        if not raw:
            return []

        normalized = self._normalize_text(raw.decode("utf-8", errors="replace"))
        self._read_buffer += normalized

        lines = self._read_buffer.split("\n")
        self._read_buffer = lines.pop()
        return [line.strip() for line in lines if line.strip()]

    def _open_port(self, port: str) -> serial.Serial:
        connection = serial.Serial()
        connection.port = port
        connection.baudrate = self.baudrate
        connection.timeout = self.timeout_seconds
        connection.write_timeout = self.timeout_seconds
        connection.rtscts = False
        connection.dsrdtr = False
        connection.xonxoff = False
        connection.dtr = False
        connection.rts = False
        connection.open()
        return connection

    def _probe_port(
        self,
        port: str,
        probe_command: str,
        warmup_seconds: float,
        probe_window_seconds: float,
    ) -> str:
        try:
            connection = self._open_port(port)
        except SerialException:
            return ""

        try:
            time.sleep(max(0.0, warmup_seconds))
            connection.reset_input_buffer()

            payload = probe_command.rstrip("\r\n").encode("utf-8") + self.command_terminator
            connection.write(payload)
            connection.flush()
            return self._read_text(connection, probe_window_seconds)
        except SerialException:
            return ""
        finally:
            if connection.is_open:
                connection.close()

    def _read_text(self, connection: serial.Serial, duration_seconds: float) -> str:
        deadline = time.monotonic() + max(0.0, duration_seconds)
        chunks: list[str] = []

        while time.monotonic() < deadline:
            waiting = connection.in_waiting
            if waiting > 0:
                raw = connection.read(waiting)
                if raw:
                    chunks.append(raw.decode("utf-8", errors="replace"))
                continue

            time.sleep(min(self.timeout_seconds, 0.05))

        return self._normalize_text("".join(chunks))

    def _read_until_idle(
        self,
        connection: serial.Serial,
        idle_timeout_seconds: float,
        max_duration_seconds: float,
        progress_callback: Callable[[], None] | None = None,
    ) -> str:
        deadline = time.monotonic() + max(0.0, max_duration_seconds)
        chunks: list[str] = []
        last_data_at: float | None = None

        while time.monotonic() < deadline:
            waiting = connection.in_waiting
            if waiting > 0:
                raw = connection.read(waiting)
                if raw:
                    chunks.append(raw.decode("utf-8", errors="replace"))
                    last_data_at = time.monotonic()
                if progress_callback is not None:
                    progress_callback()
                continue

            if last_data_at is not None and (time.monotonic() - last_data_at) >= max(0.0, idle_timeout_seconds):
                break

            if progress_callback is not None:
                progress_callback()
            time.sleep(min(self.timeout_seconds, 0.05))

        return self._normalize_text("".join(chunks))

    def _normalize_text(self, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")