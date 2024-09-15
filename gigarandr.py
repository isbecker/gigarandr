#!/usr/bin/env python3

import subprocess
import os
import json

config_dir = os.path.expanduser('~/.config/gigarandr')
config_file = os.path.join(config_dir, 'config.json')
state_file = os.path.join(config_dir, 'monitor_state.json')

def ensure_config_directory():
    os.makedirs(config_dir, exist_ok=True)
    default_config = {
        "hooks": {
            "presync": ["echo 'PreSync Hook: Starting...'"],
            "sync": ["echo 'Sync Hook: Adjusting monitor settings...'"],
            "postsync": ["echo 'PostSync Hook: Clean-up operations completed.'"]
        }
    }
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(default_config, f)
    if not os.path.exists(state_file):
        with open(state_file, 'w') as f:
            json.dump({}, f)

def load_config():
    with open(config_file, 'r') as f:
        return json.load(f)

def load_state():
    with open(state_file, 'r') as f:
        return json.load(f)

def save_state(state):
    with open(state_file, 'w') as f:
        json.dump(state, f)

def run_hook(hooks, stage):
    for command in hooks.get(stage, []):
        subprocess.call(command, shell=True)

def get_monitor_capabilities(monitor):
    xrandr_output = subprocess.check_output(['xrandr', '--query']).decode()
    pattern = rf'^{monitor} connected.*?\n([\s\S]*?)(?=\n\S)'
    match = re.search(pattern, xrandr_output, re.MULTILINE)
    if match:
        modes = match.group(1)
        resolutions = []
        for line in modes.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if '+' in line or '*' in line:
                line = line.replace('+', '').replace('*', '')
            parts = line.strip().split()
            res = parts[0]
            refresh_rates = [float(r.replace('*', '').replace('+', '')) for r in parts[1:]]
            max_refresh = max(refresh_rates) if refresh_rates else None
            resolutions.append((res, max_refresh))
        # Assuming the first resolution is the highest
        if resolutions:
            return resolutions[0]
    return None

def get_connected_monitors():
    output = subprocess.check_output(['xrandr', '--query']).decode()
    return [line.split()[0] for line in output.split('\n') if ' connected' in line]

def manage_monitors(monitors, state):
    commands = ['xrandr']
    external_monitors = [m for m in monitors if not 'eDP' in m]
    laptop_monitor = [m for m in monitors if 'eDP' in m][0]  # Assuming there's exactly one laptop monitor

    if external_monitors:
        # Docked mode: external monitor above the laptop monitor
        primary_set = False
        for monitor in external_monitors:
            res_info = get_monitor_capabilities(monitor)
            if res_info:
                res, refresh_rates = res_info
                commands += ['--output', monitor, '--mode', res, '--auto', '--above', laptop_monitor]
                if not primary_set:
                    commands += ['--primary']
                    primary_set = True
        # Configure the laptop monitor
        res_info = get_monitor_capabilities(laptop_monitor)
        if res_info:
            res, refresh_rates = res_info
            commands += ['--output', laptop_monitor, '--mode', res, '--auto']
    else:
        # Mobile mode: only the laptop monitor active
        res_info = get_monitor_capabilities(laptop_monitor)
        if res_info:
            res, refresh_rates = res_info
            commands += ['--output', laptop_monitor, '--mode', res, '--auto']
        else:
            commands += ['--output', laptop_monitor, '--auto']
    
    for monitor in external_monitors:
        commands += ['--output', monitor, '--off']

    subprocess.call(commands)

def main():
    ensure_config_directory()
    config = load_config()
    state = load_state()
    hooks = config['hooks']

    run_hook(hooks, 'presync')
    monitors = get_connected_monitors()
    manage_monitors(monitors, state)
    run_hook(hooks, 'sync')
    save_state({monitor: True for monitor in monitors})
    run_hook(hooks, 'postsync')

if __name__ == '__main__':
    main()

