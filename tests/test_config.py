import sys
from pathlib import Path

# Adjust the module search path to include the parent directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pathlib import Path
import pytest

from gigarandr import ensure_config_directory, load_config, load_state
import gigarandr


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    # Set HOME to a temporary directory
    temp_home_dir = tmp_path / "home"
    temp_home_dir.mkdir()
    monkeypatch.setenv("HOME", str(temp_home_dir))
    # Override config paths in gigarandr module to use the temporary home.
    gigarandr.CONFIG_DIR = Path(temp_home_dir) / ".config" / "gigarandr"
    gigarandr.CONFIG_FILE = gigarandr.CONFIG_DIR / "config.json"
    gigarandr.STATE_FILE = gigarandr.CONFIG_DIR / "monitor_state.json"
    return temp_home_dir


def test_ensure_config_directory(temp_home):
    # Calling ensure_config_directory should create config and state files in our temporary config directory.
    config_dir = Path.home() / ".config" / "gigarandr"
    config_file = config_dir / "config.json"
    state_file = config_dir / "monitor_state.json"
    ensure_config_directory(config_dir=config_dir, config_file=config_file, state_file=state_file)

    assert config_dir.exists()
    assert config_file.exists()
    assert state_file.exists()


def test_load_default_config(temp_home):
    config_dir = Path.home() / ".config" / "gigarandr"
    config_file = config_dir / "config.json"
    state_file = config_dir / "monitor_state.json"
    ensure_config_directory(config_dir=config_dir, config_file=config_file, state_file=state_file)
    config = load_config()
    # Check that default keys exist.
    assert "profiles" in config
    assert "hooks" in config
    assert config.get("xrandr_bin") == "/usr/bin/xrandr"
    # Check that the first profile contains the "monitors" key.
    assert "monitors" in config["profiles"][0]


def test_load_empty_state(temp_home):
    # First, create config files.
    ensure_config_directory()
    state_file = Path.home() / ".config" / "gigarandr" / "monitor_state.json"
    # Remove state file to simulate missing state.
    if state_file.exists():
        state_file.unlink()
    state = load_state()
    # When file is missing, load_state should return an empty dict.
    assert state == {}
