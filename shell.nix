# Development shell for semtex.sty testing.
# Usage: nix-shell   (or `nix develop` once flake.nix lands)
#
# Provides PDF analysis tools needed by TEST-PDF-STEXT / TEST-PDF-OBJECTS
# directives in the test runner.  Without these, structural PDF assertions
# are skipped gracefully.
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = with pkgs; [
    # TeX engine (tests use system texlive-full for now)
    # texlive.combined.scheme-full

    # PDF analysis tools for structural assertions
    mupdf      # mutool: stext extraction (positions/fonts), object dump, link counting
    qpdf       # fallback link counting, PDF inspection

    # Test runner
    python3
  ];
}
