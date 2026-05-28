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

            # Test runner + harness scripts (wave-open.py, apply-staged.py use
            # staging_contract → graph_contract which import pydantic).
            (python3.withPackages (ps: with ps; [ pydantic ]))
          ];
          # TeX Live is intentionally excluded — use system-wide installation
          # to avoid pulling the huge dependency into the Nix store / GC.
        };
      });

      checks = forEachSystem ({ pkgs, system }: {
        default = builtins.trace
          "WARN: install-discipline lint is wired; CORE bootstrap expected WARN classes are pending-p03-track2-effect-annotation, pending-p05-missing-* migrations, contract-owned-gaddto-macro, kernel-reset-list-raw-gaddto-macro, counter-alias-raw-let, activation-let-raw, dynamic-command-wrap-protected-edef, and unclassified-raw-install-primitive. Full callsite diagnostics are in the check build log."
          (pkgs.stdenv.mkDerivation {
          name = "codependent-tests";
          src = self;

          nativeBuildInputs = with pkgs; [
            mupdf
            qpdf
            # Checks run in the Nix build sandbox, so unlike the dev shell they
            # must declare TeX Live rather than reaching into
            # /run/current-system/sw.  Full is intentionally check-only because
            # the integration/stress fixtures exercise broad LaTeX packages.
            texlive.combined.scheme-full
            (python3.withPackages (ps: with ps; [ pydantic ]))
          ];

          buildPhase = ''
            # P02 wires the install-discipline lint now.  P03/P05 are not yet
            # landed in this branch, so their known pending source ERRORs are
            # demoted to visible WARNs for this bootstrap flake gate; parse,
            # enum, fixture, and no-rotation ERRORs remain fatal.
            python3 .claude/scripts/lint_install_discipline.py --allow-pending-core-errors
            python3 .claude/scripts/lint_wire_format_no_rotation.py
            python3 .claude/scripts/lint_wire_format_no_rotation.py --self-test
            python3 scripts/run-tests.py --check-test-index --full
          '';

          installPhase = ''
            mkdir -p $out
            touch $out/ok
          '';
        });
      });
    };
}
