#!/usr/bin/env python3
"""
Gigarandr - A script to manage monitor configurations using xrandr.
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import os
import yaml
import typer
import re
from loguru import logger

from omegaconf import OmegaConf, DictConfig, ListConfig
from dataclasses import dataclass, field

logger.add(sys.stderr, colorize=True, level="DEBUG", format="<green>{time}</green> <level>{message}</level>")

app = typer.Typer()

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gigarandr"
)
DEFAULT_CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "monitor_state.json"


@dataclass
class MonitorConfig:
    """Represents a single monitor configuration."""
    name: Optional[str] = None
    primary: bool = False
    position: Optional[str] = None
    refresh_rate: Optional[Union[int, float]] = None
    role: Optional[str] = None


@dataclass
class HooksConfig:
    """Defines presync, sync, and postsync command hooks."""
    presync: List[str] = field(
        default_factory=lambda: ["echo 'PreSync Hook: Starting...'"]
    )
    sync: List[str] = field(
        default_factory=lambda: ["echo 'Sync Hook: Adjusting monitor settings...'"]
    )
    postsync: List[str] = field(
        default_factory=lambda: ["echo 'PostSync Hook: Clean-up operations completed.'"]
    )


@dataclass
class ProfileConfig:
    """Encapsulates a set of monitors forming a configuration profile."""
    monitors: Dict[str, MonitorConfig] = field(default_factory=dict)
    name: Optional[str] = None


@dataclass
class AppConfig:
    """Holds the main application configuration with default profiles."""
    monitors: Dict[str, MonitorConfig] = field(
        default_factory=lambda: {
            "laptop": MonitorConfig(primary=True, position="below largest"),
            "largest": MonitorConfig(position="above laptop"),
        }
    )
    hooks: HooksConfig = field(default_factory=HooksConfig)
    xrandr_bin: str = "xrandr"
    profiles: List[ProfileConfig] = field(
        default_factory=lambda: [
            ProfileConfig(monitors={
                "laptop": MonitorConfig(primary=True, position="below largest"),
                "largest": MonitorConfig(position="above laptop")
            })
        ]
    )


def ensure_config_directory(config_dir: Optional[Path] = None, config_file: Optional[Path] = None, state_file: Optional[Path] = None) -> None:
    """Ensure configuration directory and empty config/state files exist."""
    config_dir = config_dir or CONFIG_DIR
    config_file = config_file or DEFAULT_CONFIG_FILE
    state_file = state_file or STATE_FILE

    config_dir.mkdir(parents=True, exist_ok=True)
    default_conf = OmegaConf.structured(AppConfig())
    if not config_file.exists():
        with config_file.open("w") as f:
            f.write(OmegaConf.to_yaml(default_conf))
    if not state_file.exists():
        with state_file.open("w") as f:
            json.dump({}, f, indent=4)


def load_config() -> Union[DictConfig, ListConfig]:
    """Load the configuration file using OmegaConf."""
    try:
        return OmegaConf.load(DEFAULT_CONFIG_FILE)
    except Exception as e:
        logger.error(f"Error loading configuration file: {e}")
        sys.exit(1)


def load_state() -> Dict[str, Any]:
    """Load the saved monitor state from JSON."""
    try:
        with STATE_FILE.open("r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing state file: {e}")
        return {}
    except FileNotFoundError:
        logger.warning("State file not found. Continuing with empty state.")
        return {}


def save_state(state: Dict[str, Any]) -> None:
    """Write the current monitor state to disk as JSON."""
    try:
        json_module = __import__('json')
        with STATE_FILE.open("w") as f:
            json_module.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving state file: {e}")
        raise e


def match_profile(config, connected_monitors: List[Dict[str, Optional[int]]]):
    """Match connected monitors against a known profile by monitor count."""
    profiles = config.get("profiles", [])
    for profile in profiles:
        profile_monitors = profile.get("monitors", {})
        if len(profile_monitors) == len(connected_monitors):
            return profile
    return None


class GigarandrApp:
    """Core application logic for building and applying xrandr commands."""
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.xrandr_bin = config.get("xrandr_bin", "xrandr")
        self.hooks = config.get("hooks", {})
        self.dry_run = False

    def build_xrandr_command(
        self, profile, connected_monitors: List[Dict[str, Optional[int]]]
    ) -> List[str]:
        resolved_mapping = self.resolve_monitors(profile, connected_monitors)
        full_graph = self.build_full_graph(profile)
        graph_mapping = {k: v[1] for k, v in full_graph.items()}
        cycle_nodes = self.detect_cycles(graph_mapping)
        if cycle_nodes:
            logger.warning(f"Cycle detected in monitor positioning for monitors: {cycle_nodes}. Resolving by keeping first encountered edge.")
            processed = set()
            cycle_graph = {}
            for key, (flag, ref) in full_graph.items():
                if key in cycle_nodes and ref in cycle_nodes and full_graph.get(ref, (None, None))[1] == key:
                    # bidirectional cycle edge
                    if key not in processed and ref not in processed:
                        cycle_graph[key] = (flag, ref)
                        processed.add(key)
                    # skip additional edge
                else:
                    cycle_graph[key] = (flag, ref)
            full_graph = cycle_graph
        cmd_args = self.build_command_segments(profile, connected_monitors, resolved_mapping, full_graph)
        logger.debug(f"Generated xrandr command: {cmd_args}")
        return cmd_args

    def resolve_monitors(self, profile, connected_monitors: List[Dict[str, Optional[int]]]) -> Dict[str, str]:
        monitors = profile.get("monitors", {})
        resolved_mapping = {}
        for m_key, mon in monitors.items():
            resolved = None
            if (mon.get("name") and any(cm["name"] == mon["name"] for cm in connected_monitors)):
                resolved = mon["name"]
            elif mon.get("role") == "largest":
                resolved = self.resolve_monitor_keyword(connected_monitors, "largest")
            elif (mon.get("role") and any(cm["name"] == mon["role"] for cm in connected_monitors)):
                resolved = mon["role"]
            elif mon.get("refresh_rate") is not None:
                desired_rate = float(mon["refresh_rate"])
                for cm in connected_monitors:
                    if (cm.get("default_refresh_rate") is not None and abs(cm["default_refresh_rate"] - desired_rate) < 0.1):
                        resolved = cm["name"]
                        break
            if not resolved:
                resolved = self.resolve_monitor_keyword(connected_monitors, m_key)
            if resolved:
                resolved_mapping[m_key] = resolved
        return resolved_mapping

    def build_full_graph(self, profile) -> Dict[str, Tuple[str, str]]:
        monitors = profile.get("monitors", {})
        full_graph = {}
        for monitor_key, monitor in monitors.items():
            pos = monitor.get("position")
            if pos:
                m_rel = re.match(r"^(left-of|right-of|above|below|same-as)\s+(\S+)$", pos.strip())
                if m_rel:
                    flag, ref_key = m_rel.groups()
                    full_graph[monitor_key] = (flag, ref_key)
        return full_graph

    def detect_cycles(self, graph: Dict[str, str]) -> set:
        cycle_nodes = set()
        def dfs(node, visited, stack):
            if node in stack:
                cycle_nodes.update(stack)
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            if node in graph:
                dfs(graph[node], visited, stack)
            stack.remove(node)
        visited = set()
        for n in graph:
            dfs(n, visited, set())
        return cycle_nodes

    def build_command_segments(
        self, profile, connected_monitors: List[Dict[str, Optional[int]]], 
        resolved_mapping: Dict[str, str], full_graph: Dict[str, Tuple[str, str]]
    ) -> List[str]:
        monitors = profile.get("monitors", {})
        cmd_args = [self.xrandr_bin]
        for monitor_key, monitor in monitors.items():
            resolved_name = resolved_mapping.get(monitor_key)
            if not resolved_name:
                logger.warning(f"Monitor {monitor_key} not resolved.")
                continue

            segment = ["--output", resolved_name]
            if monitor_key in full_graph:
                rel, dst = full_graph[monitor_key]
                ref_name = resolved_mapping.get(dst) or self.resolve_monitor_keyword(connected_monitors, dst)
                if ref_name:
                    segment += [f"--{rel}", ref_name]
                else:
                    logger.warning(f"Reference monitor '{dst}' not found.")

            monitor_info = next((m for m in connected_monitors if m["name"] == resolved_name), None)
            if monitor_info and monitor_info["width"] and monitor_info["height"]:
                mode_str = f"{monitor_info['width']}x{monitor_info['height']}"
                segment += ["--mode", mode_str]
                refresh_rate = monitor.get("refresh_rate") or monitor_info.get("default_refresh_rate")
                logger.debug(f"Monitor {resolved_name}: mode {mode_str}, refresh rate {refresh_rate}")
                if refresh_rate:
                    segment += ["--rate", f"{refresh_rate:.2f}"]
            else:
                segment += ["--mode", "unknown"]
            if monitor.get("primary", False):
                segment += ["--primary"]

            cmd_args += segment
        return cmd_args

    def get_connected_monitors(self) -> List[Dict[str, Optional[int]]]:
        try:
            output = subprocess.check_output([self.xrandr_bin, "--query"], encoding="utf-8")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {self.xrandr_bin}: {e}")
            sys.exit(1)
        monitors = []
        lines = output.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if " connected" in line:
                parts = line.split()
                name = parts[0]
                resolution = None
                for token in parts:
                    if "x" in token and ("+" in token):
                        resolution_candidate = token.split("+")[0]
                        if "x" in resolution_candidate:
                            resolution = resolution_candidate
                            break
                if resolution:
                    try:
                        width_str, height_str = resolution.split("x")
                        width = int(width_str)
                        height = int(height_str)
                    except ValueError:
                        width = height = None
                else:
                    width = height = None
                max_refresh = None
                j = i + 1
                while j < len(lines) and lines[j].startswith(" "):
                    tokens = lines[j].strip().split()
                    if tokens and tokens[0] == resolution:
                        for token in tokens[1:]:
                            try:
                                val = float(token.strip("*+"))
                                if (max_refresh is None) or (val > max_refresh):
                                    max_refresh = val
                            except ValueError:
                                continue
                        break
                    j += 1
                monitors.append({
                    "name": name,
                    "width": width,
                    "height": height,
                    "default_refresh_rate": max_refresh,
                })
            i += 1
        return monitors

    def resolve_monitor_keyword(self, connected_monitors: List[Dict[str, Any]], keyword: str) -> Optional[str]:
        if (keyword.lower() == "largest"):
            best_monitor = None
            best_area = 0
            for m in connected_monitors:
                if m["width"] and m["height"]:
                    area = m["width"] * m["height"]
                    if area > best_area:
                        best_area = area
                        best_monitor = m["name"]
            if best_monitor:
                return best_monitor
        if keyword.lower() == "laptop":
            for monitor in connected_monitors:
                if re.match(r"^(eDP|LVDS)", monitor["name"]):
                    return monitor["name"]
        for monitor in connected_monitors:
            if keyword.lower() in monitor["name"].lower():
                return monitor["name"]
            if "role" in monitor and monitor["role"] and keyword.lower() in monitor["role"].lower():
                return monitor["name"]
        return None

    def run(self) -> None:
        if self.dry_run:
            logger.info("Dry run: skipping hook execution and state save.")
            connected_monitors = self.get_connected_monitors()
            matched_profile = match_profile(self.config, connected_monitors)
            if matched_profile:
                command = self.build_xrandr_command(matched_profile, connected_monitors)
                logger.info("Dry run xrandr command: " + " ".join(command))
            else:
                logger.info("No matching profile found for dry run.")
            raise SystemExit()
        self.run_hook("presync")
        connected_monitors = self.get_connected_monitors()
        matched_profile = match_profile(self.config, connected_monitors)
        if matched_profile:
            profile_name = matched_profile.get("name") or "default"
            logger.info(f"Matched profile: {profile_name}")
            self.apply_profile(matched_profile, connected_monitors)
        else:
            logger.info(
                f"No matching profile found for {len(connected_monitors)} monitors."
            )
        self.run_hook("sync")
        save_state({monitor["name"]: True for monitor in connected_monitors})
        self.run_hook("postsync")

    def run_hook(self, hook_name: str) -> None:
        commands = self.hooks.get(hook_name, [])
        for cmd in commands:
            logger.info(f"Executing {hook_name} hook: {cmd}")
            try:
                subprocess.check_call(cmd, shell=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error executing {hook_name} hook: {cmd} => {e}")

    def apply_profile(self, profile, connected_monitors: List[Dict[str, Optional[int]]]) -> None:
        command = self.build_xrandr_command(profile, connected_monitors)
        logger.info("Applying xrandr command: " + " ".join(command))
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error executing xrandr command: {command} => {e}")


def get_connected_monitors():
    temp_app = GigarandrApp(load_config())
    return temp_app.get_connected_monitors()


def show_config() -> None:
    """Load and merge the configuration file with CLI overrides and output as YAML."""
    merged_conf = merge_config()
    yaml_str = yaml.dump(merged_conf, sort_keys=False, default_flow_style=False)
    print(yaml_str)
    sys.exit(0)


def merge_config(config_file: Optional[Path] = None) -> AppConfig:
    """Merge and return the configuration from file, applying any needed updates."""
    ensure_config_directory()
    cf = config_file if config_file is not None else DEFAULT_CONFIG_FILE
    if not cf.exists() or cf.stat().st_size == 0:
        logger.warning(f"Configuration file {cf} does not exist or is empty. Initializing with default values.")
        default_conf = OmegaConf.structured(AppConfig())
        try:
            with cf.open("w") as f:
                f.write(OmegaConf.to_yaml(default_conf))
        except Exception as e:
            logger.warning(f"Could not write default config to {cf}: {e}")
        return default_conf
    base_conf = OmegaConf.load(str(cf))
    if "profiles" in base_conf:
        for idx, profile in enumerate(base_conf.profiles):
            monitors = profile.get("monitors", {})
            for key in monitors:
                if not monitors[key].get("name"):
                    monitors[key]["name"] = key
            base_conf.profiles[idx].monitors = monitors
    container_conf = OmegaConf.to_container(base_conf, resolve=True)
    try:
        with cf.open("w") as f:
            json.dump(container_conf, f, indent=4)
    except Exception as e:
        logger.warning(f"Could not write merged config to file {cf}: {e}")
    return OmegaConf.create(container_conf)


def merge_monitor_override(conf_monitors: Dict[str, Any], override: str) -> None:
    """Merge a JSON-based monitor override into the existing monitor config."""
    try:
        monitor_data = json.loads(override)
        if not isinstance(monitor_data, dict):
            logger.error(f"Invalid monitor override JSON: {override}")
            return
    except json.JSONDecodeError:
        logger.error(f"Invalid monitor override JSON: {override}")
        return
    name = monitor_data.get("name")
    if not name:
        logger.error("Monitor override must have a 'name' key.")
        return
    existing = conf_monitors.get(name, {})
    existing.update(monitor_data)
    conf_monitors[name] = existing


def merge_monitor_path(conf_monitors: Dict[str, Any], override: str) -> None:
    """Merge a dot-notation override (like 'office.primary=true') into monitor config."""
    if '=' not in override:
        logger.error(f"Invalid monitor override format (missing '='): {override}")
        return
    key_path, value_str = override.split('=', 1)
    if '.' not in key_path:
        logger.error(f"Invalid monitor override format (missing '.'): {override}")
        return
    monitor_name, field = key_path.split('.', 1)
    if value_str.lower() in ['true', 'false']:
        value = (value_str.lower() == 'true')
    else:
        try:
            value = int(value_str)
        except ValueError:
            try:
                value = float(value_str)
            except ValueError:
                value = value_str
    existing = conf_monitors.get(monitor_name, {})
    existing[field] = value
    conf_monitors[monitor_name] = existing


@app.command()
def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a custom configuration file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True
    ),
    xrandr_bin: Optional[str] = typer.Option(
        None, help="Override xrandr binary path."
    ),
    monitor_override: List[str] = typer.Option(
        None,
        "--monitor-override",
        "-m",
        help="Override individual monitor configuration using dot notation in the format 'name.field=value'. Can be used multiple times."
    ),
    hook_presync: Optional[str] = typer.Option(
        None, help="Override presync hook commands as a JSON array string."
    ),
    hook_sync: Optional[str] = typer.Option(
        None, help="Override sync hook commands as a JSON array string."
    ),
    hook_postsync: Optional[str] = typer.Option(
        None, help="Override postsync hook commands as a JSON array string."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Perform a dry run without executing xrandr commands."
    )
) -> None:
    """Run gigarandr with full configuration overrides."""
    merged_conf = merge_config(config)
    
    if xrandr_bin:
        merged_conf.xrandr_bin = xrandr_bin

    if monitor_override:
        if merged_conf.get("profiles") and merged_conf.profiles:
            for override in monitor_override:
                merge_monitor_path(merged_conf.profiles[0].monitors, override)
        else:
            for override in monitor_override:
                merge_monitor_path(merged_conf.monitors, override)

    if hook_presync:
        try:
            merged_conf.hooks.presync = json.loads(hook_presync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_presync")
    if hook_sync:
        try:
            merged_conf.hooks.sync = json.loads(hook_sync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_sync")
    if hook_postsync:
        try:
            merged_conf.hooks.postsync = json.loads(hook_postsync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_postsync")
    
    container_conf = OmegaConf.to_container(merged_conf, resolve=True)
    cf = config if config is not None else DEFAULT_CONFIG_FILE
    with cf.open("w") as f:
        json.dump(container_conf, f, indent=4)
    
    app_instance = GigarandrApp(merged_conf)
    app_instance.dry_run = dry_run
    app_instance.run()


@app.command(name="show-config")
def show_config_cmd(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a custom configuration file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    xrandr_bin: Optional[str] = typer.Option(
        None, help="Override xrandr binary path."
    ),
    monitor_override: List[str] = typer.Option(
        None,
        "--monitor-override",
        "-m",
        help="Override individual monitor configuration using dot notation in the format 'name.field=value'. Can be used multiple times."
    ),
    hook_presync: Optional[str] = typer.Option(
        None, help="Override presync hook commands as a JSON array string."
    ),
    hook_sync: Optional[str] = typer.Option(
        None, help="Override sync hook commands as a JSON array string."
    ),
    hook_postsync: Optional[str] = typer.Option(
        None, help="Override postsync hook commands as a JSON array string."
    ),
) -> None:
    """Display the merged configuration with overrides applied."""
    merged_conf = merge_config(config)
    if xrandr_bin:
        merged_conf.xrandr_bin = xrandr_bin
    if monitor_override:
        if merged_conf.get("profiles") and merged_conf.profiles:
            for override in monitor_override:
                merge_monitor_path(merged_conf.profiles[0].monitors, override)
        else:
            for override in monitor_override:
                merge_monitor_path(merged_conf.monitors, override)
    if hook_presync:
        try:
            merged_conf.hooks.presync = json.loads(hook_presync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_presync")
    if hook_sync:
        try:
            merged_conf.hooks.sync = json.loads(hook_sync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_sync")
    if hook_postsync:
        try:
            merged_conf.hooks.postsync = json.loads(hook_postsync)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for hook_postsync")
    
    primary_profile = merged_conf.profiles[0] if merged_conf.get("profiles") and merged_conf.profiles else {}
    monitors_conf = primary_profile.get("monitors", {}) if primary_profile else {}
    temp_app = GigarandrApp(merged_conf)
    connected = temp_app.get_connected_monitors()
    mapping = {}
    unmatched = []
    for key, monitor in monitors_conf.items():
        resolved = None
        if monitor.get("name") and any(m["name"] == monitor["name"] for m in connected):
            resolved = monitor["name"]
        elif monitor.get("refresh_rate") is not None:
            desired_rate = float(monitor["refresh_rate"])
            for m in connected:
                if m.get("default_refresh_rate") is not None and abs(m["default_refresh_rate"] - desired_rate) < 0.1:
                    resolved = m["name"]
                    break
        if not resolved:
            resolved = temp_app.resolve_monitor_keyword(connected, key)
        if resolved:
            info = next((m for m in connected if m["name"] == resolved), {})
            mapping[key] = {"resolved_to": resolved, "details": info}
        else:
            unmatched.append(key)
    
    output = {
        "merged_config": OmegaConf.to_container(merged_conf, resolve=True),
        "xrandr_monitors": connected,
        "monitor_mapping": mapping,
        "unmatched_monitors": unmatched,
    }
    typer.echo(yaml.dump(output, sort_keys=False, default_flow_style=False))
    raise typer.Exit()


@logger.catch
def main():
    """Main entry point to run the Typer CLI with loguru exception catching."""
    app()


if __name__ == "__main__":
    main()
