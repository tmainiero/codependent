#!/usr/bin/env python3
"""Resolve a dotted key from .claude/paths.toml to an absolute path.

Usage:
  resolve_path.py docs.conventions
  resolve_path.py tests.behavior_baseline

Prints the absolute path to stdout. Exits 0 on success, 1 if the key is
missing. Used by bash callers that need the canonical location of a doc
without hardcoding it.
"""

import os
import sys

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


def project_root() -> str:
    here = os.path.abspath(__file__)
    d = os.path.dirname(here)
    while d != "/":
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("project root not found (no .git/ ancestor)")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: resolve_path.py <section>.<key>", file=sys.stderr)
        return 2
    dotted = sys.argv[1]
    if "." not in dotted:
        print(f"key must be dotted (e.g. docs.conventions), got {dotted!r}", file=sys.stderr)
        return 2
    section, key = dotted.split(".", 1)

    root = project_root()
    toml_path = os.path.join(root, ".claude", "paths.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    try:
        rel = data[section][key]
    except KeyError:
        print(f"key {dotted!r} not found in {toml_path}", file=sys.stderr)
        return 1

    print(os.path.join(root, rel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
