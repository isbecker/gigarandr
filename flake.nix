{
  description = "Flake for gigarandr dev";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    devenv.url = "github:cachix/devenv";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix_hammer_overrides.url = "github:TyberiusPrime/uv2nix_hammer_overrides";
    uv2nix_hammer_overrides.inputs.nixpkgs.follows = "nixpkgs";
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs =
    inputs@{ flake-parts
    , nixpkgs
    , uv2nix
    , uv2nix_hammer_overrides
    , pyproject-nix
    , pyproject-build-systems
    , ...
    }:
    let
      inherit (nixpkgs) lib;

      # Load a uv workspace from a workspace root.
      # Uv2nix treats all uv projects as workspace projects.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Create package overlay from workspace.
      overlay = workspace.mkPyprojectOverlay {
        # Prefer prebuilt binary wheels as a package source.
        # Sdists are less likely to "just work" because of the metadata missing from uv.lock.
        # Binary wheels are more likely to, but may still require overrides for library dependencies.
        sourcePreference = "wheel"; # or sourcePreference = "sdist";
        # Optionally customise PEP 508 environment
        # environ = {
        #   platform_release = "5.10.65";
        # };
      };

      # Extend generated overlay with build fixups
      #
      # Uv2nix can only work with what it has, and uv.lock is missing essential metadata to perform some builds.
      # This is an additional overlay implementing build fixups.
      # See:
      # - https://pyproject-nix.github.io/uv2nix/FAQ.html
      pyprojectOverrides = pkgs.lib.composeExtensions (uv2nix_hammer_overrides.overrides pkgs) (
        # use uv2nix_hammer_overrides.overrides_debug
        #   to see which versions were matched to which overrides
        #  use uv2nix_hammer_overrides.overrides_strict / overrides_strict_debug
        #  to use only overrides exactly matching your python package versions

        _final: _prev: {
          # place additional overlays here.
          #a_pkg = prev.a_pkg.overrideAttrs (old: nativeBuildInputs = old.nativeBuildInputs ++ [pkgs.someBuildTool] ++ (final.resolveBuildSystems { setuptools = [];});
        }
      );

      # This example is only using x86_64-linux
      pkgs = nixpkgs.legacyPackages.x86_64-linux;

      # Use Python 3.12 from nixpkgs
      python = pkgs.python312;

      # Construct package set
      pythonSet =
        # Use base package set from pyproject.nix builders
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
              pyprojectOverrides
            ]
          );

    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.devenv.flakeModule
      ];
      systems = [ "x86_64-linux" "i686-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      perSystem = { config, self', inputs', pkgs, system, lib, ... }: {
        packages.default = pythonSet.mkVirtualEnv "gigarandr" workspace.deps.default;

        apps.${system} = {
          default = {
            type = "app";
            program = "${self'.packages.${system}.default}/bin/gigarandr";
          };
        };

        devenv.shells.default = {
          name = "gigarandr";

          devcontainer.enable = true;

          languages = {
            python = {
              enable = true;
              uv = {
                enable = true;
                sync = {
                  enable = true;
                };
              };
            };
          };

          pre-commit.hooks = {
            treefmt = {
              package = pkgs.treefmt2;
              enable = true;
              settings = {
                formatters = with pkgs; [
                  nixpkgs-fmt
                  ruff
                  mdformat
                  taplo
                  biome
                ];
              };
            };
          };
          packages = with pkgs; [
            config.packages.default
            just
          ];
        };
      };
    };
}

