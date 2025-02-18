import sys
from pathlib import Path

# Adjust the module search path to include the parent directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pathlib import Path
import pytest
import json
import tempfile
from loguru import logger
from hypothesis import given, strategies as st, settings, HealthCheck
import os
from omegaconf import OmegaConf

from gigarandr import ensure_config_directory, load_config, GigarandrApp, merge_config, AppConfig
import gigarandr


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    # Set HOME to a temporary directory
    temp_home_dir = tmp_path / "home"
    temp_home_dir.mkdir()
    monkeypatch.setenv("HOME", str(temp_home_dir))
    gigarandr.CONFIG_DIR = Path(temp_home_dir) / ".config" / "gigarandr"
    gigarandr.CONFIG_FILE = gigarandr.CONFIG_DIR / "config.json"
    gigarandr.STATE_FILE = gigarandr.CONFIG_DIR / "monitor_state.json"
    return temp_home_dir


@pytest.fixture(autouse=True)
def configure_logger(caplog):
    caplog.set_level("ERROR", logger="gigarandr")
    logger.add(caplog.handler, format="{message}", level="ERROR")


@pytest.fixture
def config(temp_home):
    ensure_config_directory()
    return load_config()


@given(st.builds(Path))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ensure_config_directory_creates_files(temp_home, config_dir):
    """
    Test that ensure_config_directory creates config and state files in the temporary config directory.
    """
    config_file = config_dir / "config.json"
    state_file = config_dir / "monitor_state.json"
    ensure_config_directory(config_dir=config_dir, config_file=config_file, state_file=state_file)

    assert config_dir.exists()
    assert config_file.exists()
    assert state_file.exists()


@given(st.builds(gigarandr.load_config))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_load_default_config_contains_keys(temp_home, config):
    """
    Test that load_config loads the default configuration with the expected keys.
    """
    config_dir = Path.home() / ".config" / "gigarandr"
    config_file = config_dir / "config.json"
    state_file = config_dir / "monitor_state.json"
    ensure_config_directory(config_dir=config_dir, config_file=config_file, state_file=state_file)
    assert "profiles" in config
    assert "hooks" in config
    assert config.get("xrandr_bin") == "/usr/bin/xrandr"
    assert "monitors" in config["profiles"][0]


@given(st.builds(gigarandr.load_state))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_load_empty_state_returns_empty_dict(temp_home, state):
    """
    Test that load_state returns an empty dictionary when the state file is missing.
    """
    ensure_config_directory()
    state_file = Path.home() / ".config" / "gigarandr" / "monitor_state.json"
    if state_file.exists():
        state_file.unlink()
    assert state == {}


@given(state=st.dictionaries(keys=st.text(), values=st.booleans()))
def test_save_state_saves_correctly(state):
    """
    Test that save_state correctly saves the state to a file.
    """
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_path = Path(temp_file.name)
    gigarandr.STATE_FILE = temp_file_path
    gigarandr.save_state(state)
    with temp_file_path.open("r") as f:
        saved_state = json.load(f)
    assert saved_state == state
    temp_file_path.unlink()


@given(st.builds(gigarandr.load_config))
def test_match_profile_with_sample_config(config):
    """
    Test that match_profile correctly matches the profile based on connected monitors.
    """
    connected_monitors = [
        {"name": "DP-2", "width": 2560, "height": 1440, "default_refresh_rate": 165.00},
        {"name": "DP-4", "width": 1920, "height": 1080, "default_refresh_rate": 144.00}
    ]
    profile = gigarandr.match_profile(config, connected_monitors)
    assert profile is not None
    assert "monitors" in profile
    assert len(profile["monitors"]) == 2


@given(st.builds(gigarandr.load_config))
def test_resolve_monitor_keyword_with_sample_config(config):
    """
    Test that resolve_monitor_keyword correctly resolves monitor keywords.
    """
    connected_monitors = [
        {"name": "eDP-1", "width": 1920, "height": 1080},
        {"name": "DP-2", "width": 2560, "height": 1440},
        {"name": "DP-4", "width": 1920, "height": 1080}
    ]
    app = gigarandr.GigarandrApp(config)
    largest = app.resolve_monitor_keyword(connected_monitors, "largest")
    assert largest == "DP-2"
    laptop = app.resolve_monitor_keyword(connected_monitors, "laptop")
    assert laptop == "eDP-1"


@given(invalid_override=st.text())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_merge_monitor_path_with_invalid_format(config, invalid_override, caplog):
    """
    Test that merge_monitor_path logs an error for invalid override formats.
    """
    monitors = config.get("monitors", {})
    gigarandr.merge_monitor_path(monitors, invalid_override)
    assert "Invalid monitor override format" in caplog.text


@given(invalid_override=st.text())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_merge_monitor_override_with_invalid_json(config, invalid_override, caplog):
    """
    Test that merge_monitor_override logs an error for invalid JSON overrides.
    """
    monitors = config.get("monitors", {})
    gigarandr.merge_monitor_override(monitors, invalid_override)
    assert "Invalid monitor override JSON" in caplog.text


@given(st.builds(gigarandr.load_config))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_gigarandr_app_dry_run_executes_correctly(monkeypatch, config):
    """
    Test that GigarandrApp runs correctly in dry run mode without exceptions.
    """
    app = GigarandrApp(config)
    app.dry_run = True
    monkeypatch.setattr(app, "get_connected_monitors", lambda: [
        {"name": "DP-2", "width": 2560, "height": 1440, "default_refresh_rate": 165.00},
        {"name": "DP-4", "width": 1920, "height": 1080, "default_refresh_rate": 144.00}
    ])
    monkeypatch.setattr(app, "run_hook", lambda x: None)
    monkeypatch.setattr(app, "apply_profile", lambda x, y: None)
    with pytest.raises(SystemExit):
        app.run()
    # No assertion needed, just ensuring no exceptions are raised


def test_merge_config_non_writable(tmp_path):
    # Create a temporary config file with default configuration
    config_file = tmp_path / "config.json"
    default_conf = OmegaConf.structured(AppConfig())
    config_file.write_text(OmegaConf.to_yaml(default_conf))

    # Make the config file read-only
    os.chmod(config_file, 0o444)  

    # Call merge_config with the read-only config file
    # It should not crash and should return a valid configuration
    cfg = merge_config(config_file)
    # Verify that the returned configuration has the expected keys
    assert hasattr(cfg, 'monitors')
    
    # Cleanup: Change permissions back for deletion (if necessary)
    os.chmod(config_file, 0o666)
