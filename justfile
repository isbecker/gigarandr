default:
  {{ just_executable() }} -f {{ justfile() }} --list

test:
  uv run --active pytest tests/

update:
  nix flake update
  uv sync --upgrade

run *args:
  uv run --active gigarandr.py run {{ args }}

alias up:=update