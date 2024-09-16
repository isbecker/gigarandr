#!/usr/bin/env python3
"""
Gigarandr - A script to manage monitor configurations using xrandr.
"""

import sys
import subprocess
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration paths
CONFIG_DIR = Path.home() / '.config' / 'gigarandr'
CONFIG_FILE = CONFIG_DIR / 'config.json'
STATE_FILE = CONFIG_DIR / 'monitor_state.json'

# Monitor keywords
MONITOR_KEYWORDS = {'laptop', 'largest', 'smallest'}


def ensure_config_directory() -> None:
    """Ensure the configuration directory and files exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    default_config = {
        "monitors": [
            {
                "name": "laptop",
                "primary": True,
                "position": "below largest"
            },
            {
                "name": "largest",
                "position": "above laptop"
            }
        ],
        "hooks": {
            "presync": ["echo 'PreSync Hook: Starting...'"],
            "sync": ["echo 'Sync Hook: Adjusting monitor settings...'"],
            "postsync": ["echo 'PostSync Hook: Clean-up operations completed.'"]
        }
    }
    if not CONFIG_FILE.exists():
        with CONFIG_FILE.open('w') as f:
            json.dump(default_config, f, indent=4)
    if not STATE_FILE.exists():
        with STATE_FILE.open('w') as f:
            json.dump({}, f, indent=4)


def load_config() -> Dict[str, Any]:
    """Load the configuration file."""
    try:
        with CONFIG_FILE.open('r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing configuration file: {e}")
        sys.exit(1)
    except FileNotFoundError:
        logging.error("Configuration file not found.")
        sys.exit(1)


def load_state() -> Dict[str, Any]:
    """Load the saved monitor state."""
    try:
        with STATE_FILE.open('r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing state file: {e}")
        return {}
    except FileNotFoundError:
        logging.warning("State file not found. Continuing with empty state.")
        return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save the monitor state to a file."""
    try:
        with STATE_FILE.open('w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving state file: {e}")


def run_hook(hooks: Dict[str, List[str]], stage: str) -> None:
    """Run hook commands for a given stage."""
    commands = hooks.get(stage, [])
    for command in commands:
        logging.info(f"Running command: {command}")
        try:
            result = subprocess.run(command, shell=True, check=True)
            logging.debug(f"Command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {command}\nError: {e}")
        except Exception as e:
            logging.error(f"An error occurred while running command: {command}\nError: {e}")


def get_connected_monitors() -> List[Dict[str, Optional[int]]]:
    """
    Use `xrandr` to get the currently connected monitors.

    Returns:
        A list of dictionaries containing monitor names and their resolutions.
    """
    try:
        output = subprocess.check_output(['xrandr', '--query'], encoding='utf-8')
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running xrandr: {e}")
        sys.exit(1)
    monitors = []

    for line in output.splitlines():
        if " connected" in line:
            parts = line.split()
            name = parts[0]
            resolution = None
            for part in parts:
                if 'x' in part and ('+' in part or part.count('x') == 1):
                    resolution_candidate = part.split('+')[0]
                    if 'x' in resolution_candidate:
                        resolution = resolution_candidate
                        break
            if resolution:
                try:
                    width_str, height_str = resolution.split('x')
                    width = int(width_str)
                    height = int(height_str)
                except ValueError:
                    width = height = None
            else:
                width = height = None
            monitors.append({
                "name": name,
                "width": width,
                "height": height
            })

    return monitors


def resolve_monitor_keyword(monitors: List[Dict[str, Optional[int]]], keyword: str) -> Optional[str]:
    """
    Resolve a keyword like 'largest', 'smallest', 'laptop', or 'external-N' to an actual monitor name.

    Args:
        monitors: List of connected monitors with their properties.
        keyword: The keyword to resolve.

    Returns:
        The resolved monitor name or None if it cannot be resolved.
    """
    if keyword == "laptop":
        for monitor in monitors:
            if "eDP" in monitor["name"] or "LVDS" in monitor["name"]:  # Likely laptop monitor
                return monitor["name"]
    elif keyword == "largest":
        monitors_with_size = [m for m in monitors if m["width"] and m["height"]]
        if monitors_with_size:
            return max(monitors_with_size, key=lambda m: m["width"] * m["height"])["name"]
        else:
            logging.warning("No monitors with size information found for 'largest' keyword.")
    elif keyword == "smallest":
        monitors_with_size = [m for m in monitors if m["width"] and m["height"]]
        if monitors_with_size:
            return min(monitors_with_size, key=lambda m: m["width"] * m["height"])["name"]
        else:
            logging.warning("No monitors with size information found for 'smallest' keyword.")
    elif keyword.startswith("external-"):
        external_number_str = keyword.split("-", 1)[1]
        try:
            external_number = int(external_number_str)
            external_monitors = [
                m for m in monitors
                if not ("eDP" in m["name"] or "LVDS" in m["name"])
            ]
            if 0 < external_number <= len(external_monitors):
                return external_monitors[external_number - 1]["name"]
            else:
                logging.warning(f"External monitor {external_number} not found.")
        except ValueError:
            logging.error(f"Invalid external monitor number: {external_number_str}")
    else:
        # Check if the keyword matches a monitor name directly
        if any(m["name"] == keyword for m in monitors):
            return keyword
        else:
            logging.warning(f"Monitor '{keyword}' not found among connected monitors.")
    return None  # Return None if no monitor could be resolved


def manage_monitors(monitors: List[Dict[str, Optional[int]]], config: Dict[str, Any]) -> None:
    """
    Use `xrandr` to apply the configuration from the JSON file to the monitors.

    Args:
        monitors: List of connected monitors with their properties.
        config: The configuration dictionary.
    """
    commands = ['xrandr']
    monitor_configs = config.get("monitors", [])

    for monitor_config in monitor_configs:
        keyword_name = monitor_config["name"]
        name = resolve_monitor_keyword(monitors, keyword_name)
        if not name:
            logging.warning(f"Monitor '{keyword_name}' could not be resolved. Skipping.")
            continue  # Skip configuration for monitors not resolved
        commands += ["--output", name, "--auto"]
        if monitor_config.get("primary", False):
            commands += ["--primary"]
        position = monitor_config.get("position")
        if position:
            if " " in position:
                position_keyword, ref_monitor_keyword = position.split(" ", 1)
                ref_name = resolve_monitor_keyword(monitors, ref_monitor_keyword)
                if not ref_name:
                    logging.warning(
                        f"Reference monitor '{ref_monitor_keyword}' could not be resolved. "
                        f"Skipping position setting for '{name}'."
                    )
                    continue
                commands += [f"--{position_keyword}", ref_name]
            else:
                logging.warning(f"Invalid position format: '{position}'")
        refresh_rate = monitor_config.get("refresh_rate")
        if refresh_rate:
            commands += ["--rate", str(refresh_rate)]

    if len(commands) > 1:
        logging.info(f"Executing: {' '.join(commands)}")
        try:
            result = subprocess.run(
                commands,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8'
            )
            logging.debug(f"xrandr output: {result.stdout}")
            if result.stderr:
                logging.warning(f"xrandr warnings: {result.stderr}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error executing xrandr command: {e.stderr}")
            sys.exit(1)
    else:
        logging.warning("No monitor configurations to apply.")


def main() -> None:
    """Main function to manage monitor configurations."""
    ensure_config_directory()
    config = load_config()
    state = load_state()
    hooks = config.get('hooks', {})

    # PreSync Phase
    run_hook(hooks, 'presync')

    # Monitor management (Sync Phase)
    monitors = get_connected_monitors()
    if not monitors:
        logging.error("No monitors detected. Exiting.")
        sys.exit(1)
    manage_monitors(monitors, config)

    run_hook(hooks, 'sync')

    # Save the new monitor state
    save_state({monitor["name"]: True for monitor in monitors})

    # PostSync Phase
    run_hook(hooks, 'postsync')


if __name__ == '__main__':
    main()