#!/usr/bin/env python3
"""Normalize qpdf JSON output to strip volatile PDF fields.

Volatile fields removed:
  - trailer /ID (document identifier hash, changes every compile)
  - Info object /CreationDate, /ModDate (timestamps)
  - Info object /Producer, /Creator (tool versions)
  - qpdf[0] maxobjectid (may shift with object count changes)

Usage:
  python3 scripts/normalize-pdf-json.py input.pdf
  python3 scripts/normalize-pdf-json.py input.pdf --output out.json

Outputs normalized JSON to stdout (or --output file) suitable for diffing.
The normalization is stable: two PDFs compiled from the same source in the
same Nix environment are byte-identical, so normalized JSON will also be
identical. This script is the safety net for cross-environment comparisons
(different TeX Live versions, different machines).
"""
import json
import subprocess
import sys
import argparse

# Volatile Info dictionary keys (PDF name objects)
VOLATILE_INFO_KEYS = {"/CreationDate", "/ModDate", "/Producer", "/Creator"}


def run_qpdf_json(pdf_path: str) -> dict:
    result = subprocess.run(
        ["qpdf", "--json", pdf_path],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def strip_volatile_qpdf(data: dict) -> dict:
    """Return a copy of qpdf JSON with all volatile fields removed."""
    data = json.loads(json.dumps(data))  # deep copy via round-trip

    qpdf_arr = data.get("qpdf")
    if not isinstance(qpdf_arr, list) or len(qpdf_arr) < 2:
        return data

    header, obj_dict = qpdf_arr[0], qpdf_arr[1]

    # Remove maxobjectid from header — it changes when object count shifts
    header.pop("maxobjectid", None)

    if not isinstance(obj_dict, dict):
        return data

    for key, entry in obj_dict.items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue

        # Strip /ID from trailer
        if key == "trailer":
            value.pop("/ID", None)
            continue

        # Strip volatile fields from any Info dictionary
        for vk in VOLATILE_INFO_KEYS:
            value.pop(vk, None)

    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", help="Input PDF file path")
    parser.add_argument("--output", "-o", help="Write JSON to this file (default: stdout)")
    args = parser.parse_args()

    raw = run_qpdf_json(args.pdf)
    normalized = strip_volatile_qpdf(raw)
    out = json.dumps(normalized, indent=2, sort_keys=True)

    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
            f.write("\n")
    else:
        print(out)


if __name__ == "__main__":
    main()
