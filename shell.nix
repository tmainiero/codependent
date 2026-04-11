# Flake-compat shim — allows `nix-shell` to work without flakes.
# The canonical shell definition lives in flake.nix (devShells.default).
let
  flake = builtins.getFlake (toString ./.);
  system = builtins.currentSystem;
in
  flake.devShells.${system}.default
