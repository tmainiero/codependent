{
  description = "codependent — LaTeX package for automatic semantic dependency tracking";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSystem = f: nixpkgs.lib.genAttrs supportedSystems (system: f {
        pkgs = nixpkgs.legacyPackages.${system};
        inherit system;
      });
    in
    {
      devShells = forEachSystem ({ pkgs, ... }: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            # PDF analysis tools for TEST-PDF-STEXT / TEST-PDF-OBJECTS directives
            mupdf    # mutool: stext extraction (positions/fonts), object dump, link counting
            qpdf     # fallback link counting, PDF inspection

            # Test runner
            python3
          ];
          # TeX Live is intentionally excluded — use system-wide installation
          # to avoid pulling the huge dependency into the Nix store / GC.
        };
      });

      checks = forEachSystem ({ pkgs, system }: {
        default = pkgs.stdenv.mkDerivation {
          name = "codependent-tests";
          src = self;

          # Allow access to system pdflatex (texlive not in flake).
          __noChroot = true;

          nativeBuildInputs = with pkgs; [
            mupdf
            qpdf
            python3
          ];

          # Make system PATH available so pdflatex is reachable.
          buildPhase = ''
            export PATH="/run/current-system/sw/bin:$PATH"
            python3 testfiles/run-tests.py
          '';

          installPhase = ''
            mkdir -p $out
            touch $out/ok
          '';
        };
      });
    };
}
