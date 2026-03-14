import pytest

from popup_controller.services.voltage_calibration_service import (
    VoltageCalibrationError,
    VoltageMeasurementPoint,
    fit_voltage_calibration,
)


def test_fit_voltage_calibration_calculates_linear_constants() -> None:
    result = fit_voltage_calibration(
        (
            VoltageMeasurementPoint(measured_voltage_v=12.4, controller_voltage_v=12.0),
            VoltageMeasurementPoint(measured_voltage_v=13.5, controller_voltage_v=13.0),
            VoltageMeasurementPoint(measured_voltage_v=14.6, controller_voltage_v=14.0),
        )
    )

    assert result.a == pytest.approx(1.1)
    assert result.b == pytest.approx(-0.8)
    assert result.point_count == 3
    assert result.rms_error_v == 0.0
    assert result.max_abs_error_v == 0.0
    assert result.format_a() == "1.100000"
    assert result.format_b() == "-0.800000"


def test_fit_voltage_calibration_requires_two_points() -> None:
    try:
        fit_voltage_calibration((VoltageMeasurementPoint(measured_voltage_v=12.0, controller_voltage_v=11.9),))
    except VoltageCalibrationError as exc:
        assert "at least two" in str(exc).lower()
    else:
        raise AssertionError("Expected VoltageCalibrationError")


def test_fit_voltage_calibration_requires_distinct_controller_values() -> None:
    try:
        fit_voltage_calibration(
            (
                VoltageMeasurementPoint(measured_voltage_v=12.1, controller_voltage_v=12.0),
                VoltageMeasurementPoint(measured_voltage_v=12.2, controller_voltage_v=12.0),
            )
        )
    except VoltageCalibrationError as exc:
        assert "different controller voltage" in str(exc).lower()
    else:
        raise AssertionError("Expected VoltageCalibrationError")
