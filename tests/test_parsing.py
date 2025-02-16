import sys
from pathlib import Path

# Adjust the module search path to include the parent directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import subprocess
import textwrap
from hypothesis import given, strategies as st, settings, HealthCheck

# Import the function to test
from gigarandr import get_connected_monitors
import gigarandr  # Added to set global variable

# Updated fake xrandr output with two connected monitors:
SAMPLE_OUTPUT = textwrap.dedent("""\
    Screen 0: minimum 8 x 8, current 4480 x 1440, maximum 32767 x 32767
    DVI-D-0 disconnected primary (normal left inverted right x axis y axis)
    HDMI-0 disconnected (normal left inverted right x axis y axis)
    DP-0 disconnected (normal left inverted right x axis y axis)
    DP-1 disconnected (normal left inverted right x axis y axis)
    DP-2 connected 2560x1440+0+0 (normal left inverted right x axis y axis) 597mm x 336mm
      2560x1440     59.95 + 165.00*  160.00   155.00   143.97   120.00
      1920x1080    119.88   100.00    60.00    59.94    50.00
    DP-3 disconnected (normal left inverted right x axis y axis)
    DP-4 connected 1920x1080+2560+360 (normal left inverted right x axis y axis) 531mm x 299mm
      1920x1080     60.00 + 144.00*  119.98    99.93    84.90    59.94    50.00
      1680x1050     59.95
      1440x900      59.89
      1280x1024     75.02    60.02
""")


def fake_check_output(args, encoding):
    return SAMPLE_OUTPUT


def test_get_connected_monitors(monkeypatch):
    # Set XRANDR_BIN to a dummy value for testing.
    gigarandr.XRANDR_BIN = "xrandr"
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    monitors = get_connected_monitors()
    # Expecting 2 connected monitors: DP-2 and DP-4
    assert len(monitors) == 2

    dp2 = next((m for m in monitors if m["name"] == "DP-2"), None)
    assert dp2 is not None
    assert dp2["width"] == 2560
    assert dp2["height"] == 1440
    # Highest refresh rate in DP-2 mode line is 165.00
    assert dp2["default_refresh_rate"] == 165.00

    dp4 = next((m for m in monitors if m["name"] == "DP-4"), None)
    assert dp4 is not None
    assert dp4["width"] == 1920
    assert dp4["height"] == 1080
    # Highest refresh rate in DP-4 mode line is 144.00
    assert dp4["default_refresh_rate"] == 144.00


def fake_no_mode_output(args, encoding):
    # Simulate a connected monitor with no mode lines following
    return textwrap.dedent("""\
        Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
        DP-0 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 531mm x 299mm
    """)


def test_no_mode_line(monkeypatch):
    # Set XRANDR_BIN for testing.
    gigarandr.XRANDR_BIN = "xrandr"
    monkeypatch.setattr(subprocess, "check_output", fake_no_mode_output)
    monitors = get_connected_monitors()
    assert len(monitors) == 1
    monitor = monitors[0]
    assert monitor["name"] == "DP-0"
    assert monitor["width"] == 1920
    assert monitor["height"] == 1080
    assert monitor["default_refresh_rate"] is None


@given(input_text=st.text())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_random_output_no_connected(input_text, monkeypatch):
    # Set XRANDR_BIN for testing.
    gigarandr.XRANDR_BIN = "xrandr"
    # If no ' connected' is present, the parser should return an empty list.
    monkeypatch.setattr(subprocess, "check_output", lambda args, encoding: input_text)
    monitors = get_connected_monitors()
    if " connected" not in input_text:
        assert monitors == []
