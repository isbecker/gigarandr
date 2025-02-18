import gigarandr
import pytest
from unittest.mock import patch, mock_open
import subprocess
import json
from gigarandr import load_config, load_state, match_profile, GigarandrApp, get_connected_monitors, merge_config
from pathlib import Path
from typer.testing import CliRunner

runner = CliRunner()

@pytest.fixture
def config():
    return load_config()

@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
         "profiles": [{
              "name": "default",
              "monitors": {
                  "165hz": {
                      "position": "left-of 144hz",
                      "name": "165hz",
                      "refresh_rate": 165.0,
                      "role": "largest"
                  },
                  "144hz": {
                      "position": "right-of 165hz",
                      "name": "144hz",
                      "refresh_rate": 144.0
                  }
              }
         }],
         "hooks": {"presync":[], "sync":[], "postsync":[]},
         "xrandr_bin": "/usr/bin/xrandr"
    }))
    return config_file

# Test for load_config with exception
@patch("gigarandr.OmegaConf.load", side_effect=Exception("Load error"))
def test_load_config_exception(mock_load):
    with pytest.raises(SystemExit):
        load_config()

# Test for load_state with JSONDecodeError
@patch("builtins.open", new_callable=mock_open, read_data="{invalid_json}")
def test_load_state_json_decode_error(mock_file):
    with patch("gigarandr.json.load", side_effect=json.JSONDecodeError("Expecting value", "", 0)):
        state = load_state()
        assert state == {}

# Test for load_state with FileNotFoundError
@patch("builtins.open", side_effect=FileNotFoundError)
def test_load_state_file_not_found(mock_file):
    state = load_state()
    assert state == {}

# Test for save_state with exception
@patch("json.dump", side_effect=Exception("Save error"))
@patch("builtins.open", new_callable=mock_open)
def test_save_state_exception(mock_file, mock_json_dump):
    with pytest.raises(Exception, match="Save error"):
        gigarandr.save_state({"test": True})

# Test for match_profile with no profiles
@patch("gigarandr.load_config", return_value={"profiles": []})
def test_match_profile_no_profiles(mock_config):
    config = load_config()
    profile = match_profile(config, [])
    assert profile is None

# Test for run_hook with exception
@patch("subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_run_hook_exception(mock_check_call):
    app = GigarandrApp(load_config())
    app.hooks = {"testhook": ["cmd"]}
    app.run_hook("testhook")
    # No assertion needed, just ensuring no exceptions are raised

# Test for apply_profile with exception
@patch("subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_apply_profile_exception(mock_check_call):
    app = GigarandrApp(load_config())
    profile = {"monitors": {}}
    app.apply_profile(profile, [])
    # No assertion needed, just ensuring no exceptions are raised

# Test for run method with no matching profile
@patch("gigarandr.GigarandrApp.get_connected_monitors", return_value=[])
def test_run_no_matching_profile(mock_get_connected_monitors):
    app = GigarandrApp(load_config())
    app.run()
    # No assertion needed, just ensuring no exceptions are raised

# Test for get_connected_monitors with subprocess.CalledProcessError
@patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_get_connected_monitors_called_process_error(mock_check_output):
    with pytest.raises(SystemExit):
        get_connected_monitors()

# Test for build_xrandr_command with no resolution or refresh rate
def test_build_xrandr_command_no_resolution_or_refresh_rate():
    app = GigarandrApp(load_config())
    connected_monitors = [
        {"name": "DP-2", "width": None, "height": None, "default_refresh_rate": None},
        {"name": "DP-4", "width": None, "height": None, "default_refresh_rate": None}
    ]
    profile = gigarandr.match_profile(load_config(), connected_monitors)
    command = app.build_xrandr_command(profile, connected_monitors)
    assert "--mode" not in command
    assert "--rate" not in command

# Test for build_xrandr_command with cycle in monitor positions
def test_build_xrandr_command_with_cycle():
    app = GigarandrApp(load_config())
    connected_monitors = [
        {"name": "DP-2", "width": 2560, "height": 1440, "default_refresh_rate": 165.00},
        {"name": "DP-4", "width": 1920, "height": 1080, "default_refresh_rate": 144.00}
    ]
    profile = {
        "monitors": {
            "DP-2": {"position": "left-of DP-4"},
            "DP-4": {"position": "right-of DP-2"}
        }
    }
    command = app.build_xrandr_command(profile, connected_monitors)
    assert "--left-of" in command
    assert "--right-of" not in command

# Test for run_hook with subprocess.CalledProcessError
@patch("subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_run_hook_called_process_error(mock_check_call):
    app = GigarandrApp(load_config())
    app.hooks = {"testhook": ["cmd"]}
    app.run_hook("testhook")
    # No assertion needed, just ensuring no exceptions are raised

# Test for apply_profile with xrandr command failure
@patch("subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_apply_profile_xrandr_command_failure(mock_check_call):
    app = GigarandrApp(load_config())
    profile = {"monitors": {}}
    app.apply_profile(profile, [])
    # No assertion needed, just ensuring no exceptions are raised

# Test for merge_monitor_override with invalid JSON
def test_merge_monitor_override_invalid_json(config, caplog):
    monitors = config.get("monitors", {})
    invalid_override = "{invalid_json}"
    gigarandr.merge_monitor_override(monitors, invalid_override)
    assert "Invalid monitor override JSON" in caplog.text

# Test for merge_monitor_path with invalid format
def test_merge_monitor_path_invalid_format(config, caplog):
    monitors = config.get("monitors", {})
    invalid_override = "invalid_format"
    gigarandr.merge_monitor_path(monitors, invalid_override)
    assert "Invalid monitor override format" in caplog.text

def test_merge_config_writable(temp_config):
    # Ensure merge_config writes config correctly when file is writable
    cfg = merge_config(temp_config)
    assert "profiles" in cfg

def test_run_config_unwritable(tmp_path: Path):
    # Create a temporary config file and remove write permissions to simulate an unwritable file
    config_file = tmp_path / "unwritable_config.json"
    config_file.write_text(json.dumps({"profiles": []}))
    # Remove write permission
    config_file.chmod(0o444)
    # merge_config should log a warning but proceed without crashing
    cfg = merge_config(config_file)
    assert cfg is not None
    # Optionally, we can check that the profile remains unchanged
    assert cfg.get("profiles", []) == []

def test_version_known_version(monkeypatch):
    """Test version command returns known version when package is found."""
    import importlib.metadata
    def fake_version(pkg):
        return "1.0.0"
    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    result = runner.invoke(gigarandr.app, ["version"])
    assert result.exit_code == 0
    assert "gigarandr version: 1.0.0" in result.output


def test_version_unknown(monkeypatch):
    """Test version command returns 'unknown' when package is not found."""
    import importlib.metadata
    from importlib.metadata import PackageNotFoundError
    def fake_version(pkg):
        raise PackageNotFoundError
    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    result = runner.invoke(gigarandr.app, ["version"])
    assert result.exit_code == 0
    assert "gigarandr version: unknown" in result.output

def test_turn_off_disconnected_monitors(monkeypatch):
    import subprocess
    import gigarandr

    # Simulate previous monitor state with DP-2 and DP-4 active
    monkeypatch.setattr(gigarandr, "load_state", lambda: {"DP-2": True, "DP-4": True})

    captured_cmd = None
    def fake_check_call(cmd, *args, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    captured_state = None
    def fake_save_state(state):
        nonlocal captured_state
        captured_state = state
    monkeypatch.setattr(gigarandr, "save_state", fake_save_state)

    # Initialize app with current configuration
    app = gigarandr.GigarandrApp(gigarandr.load_config())
    # Simulate current connected monitors only including DP-2
    connected_monitors = [{"name": "DP-2", "width": 1920, "height": 1080, "default_refresh_rate": 60.0}]

    app.turn_off_disconnected_monitors(connected_monitors)

    # Expect that DP-4 has been turned off
    expected_cmd = [app.xrandr_bin, "--output", "DP-4", "--off"]
    assert captured_cmd == expected_cmd
    
    # Also, the saved state should be updated to only include DP-2
    assert captured_state == {"DP-2": True}
