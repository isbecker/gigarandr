# gigarandr 🚀✨

Gigarandr is a monitor configuration tool inspired by autorandr, but with a twist of giga power! ⚡🔧

It magically detects and configures your monitors using xrandr, making it perfect for switching between docked and mobile modes on your laptop. 💻🔄🖥️

## Features

- **Automatic Monitor Detection**: Smartly detects connected monitors and applies configuration profiles. 🔍🖥️
- **Profile-Based Setup**: Customize different profiles to match your monitor setups. 🎛️📑
- **Hook System**: Execute pre-sync, sync, and post-sync hooks for custom commands. 🔄👉
- **Dry Run Mode**: Preview the commands without applying changes. 🧐⚙️
- **Customizable Commands**: Easily override xrandr paths and monitor details through CLI options. 🛠️🚀

### Feature Details

#### Automatic Monitor Detection

Gigarandr leverages the power of xrandr to automatically detect all connected monitors. It inspects the resolution, refresh rate, and positioning details to decide which configuration profile best fits your current setup. This means you no longer need to manually adjust your settings when docking or switching displays. 🔍🖥️

#### Profile-Based Setup

Each profile is defined in a simple JSON configuration file, allowing for easy customization. You can set up multiple profiles tailored to various setups—whether you're in the office, at home, or on the go. This makes switching between configurations seamless and efficient. 🎛️📑

#### Hook System

Before, during, and after applying monitor configurations, Gigarandr can execute custom shell commands through its hook system. This feature enables you to extend functionality, such as launching applications, adjusting brightness, or logging changes automatically. 🔄👉

#### Dry Run Mode

Dry Run Mode is a safe way to preview the xrandr command that would be executed without applying any changes to your current setup. This helps in verifying configurations and preventing potential mistakes in a live environment. 🧐⚙️

#### Customizable Commands

You can override the default xrandr binary path and adjust monitor parameters via command-line options. This allows for further flexibility, especially if you maintain multiple versions of xrandr or need to tailor settings for unique hardware configurations. 🛠️🚀

## Commands

- `gigarandr run` : Execute the monitor configuration process. 🔄
- `gigarandr run --dry-run` : Perform a dry run to preview changes without applying them. 💭
- `gigarandr show-config` : Display the current merged configuration. 📝
- `gigarandr version` : Show the installed version of gigarandr. 📌

### Command Details

#### gigarandr run

Executes the main monitor configuration process. This command:

- Reads your configuration from the default or a specified file.
- Detects connected monitors.
- Matches the monitors to a defined profile based on the number and characteristics of connected screens.
- Applies monitor settings with xrandr and runs any pre, sync, and post hooks specified.

#### gigarandr run --dry-run

Similar to `gigarandr run`, but does not execute any system changes. Instead, it displays the generated xrandr command. This is useful for verifying your configuration without affecting your display setup.

#### gigarandr show-config

Merges all configuration options, including any overrides provided via the command line, and outputs the final, effective configuration in YAML format. Use this to troubleshoot configuration issues or understand the applied settings.

#### gigarandr version

Displays the current installed version of gigarandr. It retrieves version information using Python’s importlib metadata. Use this command to verify which version of gigarandr you are running.

## Usage

Simply bind the `gigarandr run` command to your hotkey for quick switching between your different monitor setups. 🔥⌨️

### Run Command Options

- `--config, -c`: Provide a custom configuration file. Use this if you have multiple configurations.
- `--monitor-override, -m`: Override individual monitor configuration using dot notation in the format `name.field=value`. This option can be used multiple times to apply several overrides. For example, you can set the primary monitor with `laptop.primary=true` and adjust the refresh rate with `office.refresh_rate=60`.
- `--xrandr-bin`: Override the default xrandr binary path if needed.
- `--hook-presync`: Override the default presync hook commands by providing a JSON array string. For example: `--hook-presync '["echo PreSync start"]'`.
- `--hook-sync`: Override the default sync hook commands by providing a JSON array string. For example: `--hook-sync '["echo Sync in progress"]'`.
- `--hook-postsync`: Override the default postsync hook commands by providing a JSON array string. For example: `--hook-postsync '["echo PostSync complete"]'`.
- `--dry-run`: Execute a dry run by generating but not applying the xrandr command, useful for troubleshooting.

## Future Enhancements

- More flexible configuration options ⚙️
