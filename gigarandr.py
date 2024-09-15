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
        },
        "bar_name": "mybar"
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

def get_connected_monitors():
    output = subprocess.check_output(['xrandr', '--query']).decode()
    return [line.split()[0] for line in output.split('\n') if ' connected' in line]

def manage_monitors(monitors, state):
    commands = ['xrandr']
    for monitor in monitors:
        commands += ['--output', monitor, '--auto']
    for monitor in state:
        if monitor not in monitors:
            commands += ['--output', monitor, '--off']
    subprocess.call(commands)

def main():
    ensure_config_directory()
    config = load_config()
    state = load_state()
    hooks = config['hooks']
    bar_name = config['bar_name']

    run_hook(hooks, 'presync')
    monitors = get_connected_monitors()
    manage_monitors(monitors, state)
    run_hook(hooks, 'sync')
    launch_polybar(monitors, bar_name)
    save_state({monitor: True for monitor in monitors})
    run_hook(hooks, 'postsync')

if __name__ == '__main__':
    main()

