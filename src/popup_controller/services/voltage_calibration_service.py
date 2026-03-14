from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence


class VoltageCalibrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VoltageMeasurementPoint:
    measured_voltage_v: float
    controller_voltage_v: float

    @property
    def error_voltage_v(self) -> float:
        return self.measured_voltage_v - self.controller_voltage_v


@dataclass(frozen=True, slots=True)
class VoltageCalibrationResult:
    a: float
    b: float
    point_count: int
    rms_error_v: float
    max_abs_error_v: float

    def format_a(self, decimals: int = 6) -> str:
        return f"{self.a:.{decimals}f}"

    def format_b(self, decimals: int = 6) -> str:
        return f"{self.b:.{decimals}f}"


def fit_voltage_calibration(points: Sequence[VoltageMeasurementPoint]) -> VoltageCalibrationResult:
    if len(points) < 2:
        raise VoltageCalibrationError("Add at least two measurement points before calculating calibration constants.")

    x_values = [point.controller_voltage_v for point in points]
    y_values = [point.measured_voltage_v for point in points]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    denominator = sum((x_value - x_mean) ** 2 for x_value in x_values)
    if denominator == 0:
        raise VoltageCalibrationError(
            "Use at least two points with different controller voltage readings to calculate calibration constants."
        )

    numerator = sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in zip(x_values, y_values))
    a = numerator / denominator
    b = y_mean - (a * x_mean)

    fitted_errors = [y_value - ((a * x_value) + b) for x_value, y_value in zip(x_values, y_values)]
    rms_error_v = sqrt(sum(error * error for error in fitted_errors) / len(fitted_errors))
    max_abs_error_v = max(abs(error) for error in fitted_errors)

    return VoltageCalibrationResult(
        a=a,
        b=b,
        point_count=len(points),
        rms_error_v=rms_error_v,
        max_abs_error_v=max_abs_error_v,
    )
