#!/usr/bin/env python3
"""
Probe codependent's per-atom dictionary backref path at synthetic scale.

The generated document contains 10,000 tracked theorems followed by 10,000
``\\cref`` references back to those theorems.  Stable later passes exercise the
csname families used by the dictionary-only architecture:

* ``\\codep@brcount@<key>``
* ``\\codep@brnode@<key>@<k>``
* ``\\codep@rendered@<key>``
* ``\\codep@rlflag@<key>``
* ``\\codep@anchor@<key>``

Run from the repository root:

    python3 scripts/scale-probe-dictionary.py

All TeX engine invocations are made through ``nix develop --command``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WAVE_DIR = PROJECT_ROOT / ".claude" / "comms" / "waves" / "W05-D"
PROBE_DIR = WAVE_DIR / "scale-probe"
METRICS_PATH = WAVE_DIR / "scale-probe-metrics.json"
SCALING_DOC = PROJECT_ROOT / "docs" / "SCALING.md"
TEXBUILD_DIR = PROJECT_ROOT / "texbuild"

DEFAULT_ATOMS = 10_000
DEFAULT_PASSES = 3
DEFAULT_ENGINES = ("pdflatex", "lualatex", "xelatex")
DEFAULT_POOL_SIZE_RETRY = 9_000_000
DEFAULT_EXTRA_MEM_RETRY = 5_000_000

CAPACITY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"TeX capacity exceeded",
        r"hash[_ ]?extra",
        r"hash size",
        r"pool[_ ]?size",
        r"pool size",
        r"main memory size",
        r"csname",
        r"No room for a new",
    ]
]

MAIN_MEMORY_PATTERNS = [
    re.compile(
        r"(?P<used>[0-9,]+)\s+words of memory out of\s+(?P<limit>[0-9,]+)"
    ),
    re.compile(
        r"(?P<node>[0-9,]+),(?P<token>[0-9,]+)\s+"
        r"words of node,token memory allocated",
        re.IGNORECASE,
    ),
]

STRING_POOL_PATTERN = re.compile(
    r"(?P<used>[0-9,]+)\s+string characters out of\s+(?P<limit>[0-9,]+)",
    re.IGNORECASE,
)
CSNAME_PATTERN = re.compile(
    r"(?P<used>[0-9,]+)\s+multiletter control sequences out of\s+"
    r"(?P<base>[0-9,]+)\+(?P<extra>[0-9,]+)",
    re.IGNORECASE,
)


def _chunked(items: Iterable[str], per_line: int) -> Iterable[list[str]]:
    chunk: list[str] = []
    for item in items:
        chunk.append(item)
        if len(chunk) == per_line:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _tex_label(index: int) -> str:
    return f"thm:{index}"


def _probe_source(atom_count: int) -> str:
    theorem_blocks = "\n".join(
        (
            "\\begin{theorem}"
            f"\\label{{{_tex_label(index)}}}"
            "x."
            "\\end{theorem}"
        )
        for index in range(1, atom_count + 1)
    )
    ref_lines = "\n".join(
        " ".join(f"\\cref{{{label}}}." for label in labels)
        for labels in _chunked((_tex_label(i) for i in range(1, atom_count + 1)), 8)
    )
    return f"""\\documentclass{{article}}
\\tracingstats=1
\\usepackage{{amsthm}}
\\newtheorem{{theorem}}{{Theorem}}[section]
\\usepackage[hypertexnames=false]{{hyperref}}
\\usepackage{{cleveref}}
\\usepackage[paragraphs=off,backref-style=inline]{{codependent}}
\\codeptrack{{theorem}}
\\pagestyle{{empty}}

\\begin{{document}}
\\section{{Tracked atoms}}
{theorem_blocks}

\\section{{Cross references}}
{ref_lines}
\\end{{document}}
"""


def write_probe_tex(atom_count: int) -> Path:
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = PROBE_DIR / f"scale-probe-dictionary-{atom_count}.tex"
    tex_path.write_text(_probe_source(atom_count), encoding="utf-8")
    return tex_path


def _engine_jobname(engine: str, atom_count: int, attempt: str) -> str:
    return f"scale-probe-dictionary-{atom_count}-{engine}-{attempt}"


def _cleanup_engine_outputs(jobname: str) -> None:
    for suffix in (".aux", ".cdp", ".log", ".out", ".pdf", ".fls", ".fdb_latexmk"):
        path = TEXBUILD_DIR / f"{jobname}{suffix}"
        if path.exists():
            path.unlink()


def run_engine_attempt(
    engine: str,
    tex_path: Path,
    atom_count: int,
    passes: int,
    attempt: str,
    env_updates: dict[str, str],
) -> dict:
    TEXBUILD_DIR.mkdir(parents=True, exist_ok=True)
    jobname = _engine_jobname(engine, atom_count, attempt)
    _cleanup_engine_outputs(jobname)

    pass_results: list[dict] = []
    start = time.perf_counter()
    exit_code = 0
    combined_output = ""
    command = [
        "nix",
        "develop",
        "--command",
    ]
    if env_updates:
        command.extend(
            ["env", *[f"{key}={value}" for key, value in sorted(env_updates.items())]]
        )
    command.extend(
        [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-draftmode",
        f"-jobname={jobname}",
        "-output-directory=texbuild",
        str(tex_path),
        ]
    )

    for pass_index in range(1, passes + 1):
        pass_start = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            errors="replace",
        )
        pass_seconds = time.perf_counter() - pass_start
        combined_output += result.stdout + "\n" + result.stderr + "\n"
        pass_results.append(
            {
                "pass": pass_index,
                "exit_code": result.returncode,
                "wall_clock_seconds": round(pass_seconds, 3),
            }
        )
        exit_code = result.returncode
        if result.returncode != 0:
            break

    wall_seconds = time.perf_counter() - start
    log_path = TEXBUILD_DIR / f"{jobname}.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    diagnostics_text = combined_output + "\n" + log_text
    capacity_events = find_capacity_events(diagnostics_text)
    memory = parse_main_memory(log_text)
    string_pool = parse_string_pool(log_text)
    csnames = parse_csnames(log_text)

    return {
        "engine": engine,
        "attempt": attempt,
        "env": env_updates,
        "atom_count": atom_count,
        "reference_count": atom_count,
        "passes_requested": passes,
        "passes_completed": len(pass_results),
        "exit_code": exit_code,
        "wall_clock_seconds": round(wall_seconds, 3),
        "main_memory_words": memory["used"],
        "main_memory_limit_words": memory["limit"],
        "main_memory_source": memory["source"],
        "string_characters": string_pool["used"],
        "string_characters_limit": string_pool["limit"],
        "multiletter_control_sequences": csnames["used"],
        "multiletter_control_sequences_limit": csnames["limit"],
        "capacity_events": capacity_events,
        "log_path": str(log_path.relative_to(PROJECT_ROOT)),
        "pass_results": pass_results,
    }


def run_engine(
    engine: str,
    tex_path: Path,
    atom_count: int,
    passes: int,
    pool_size_retry: int,
    extra_mem_retry: int,
) -> dict:
    default = run_engine_attempt(engine, tex_path, atom_count, passes, "default", {})
    attempts = [default]
    final = default
    if (
        default["exit_code"] != 0
        and pool_size_retry > 0
        and any("pool" in event.lower() for event in default["capacity_events"])
    ):
        retry = run_engine_attempt(
            engine,
            tex_path,
            atom_count,
            passes,
            f"pool{pool_size_retry}",
            {"pool_size": str(pool_size_retry)},
        )
        attempts.append(retry)
        final = retry
    if final["exit_code"] != 0 and extra_mem_retry > 0:
        events = " ".join(final["capacity_events"]).lower()
        if "main memory" in events:
            retry = run_engine_attempt(
                engine,
                tex_path,
                atom_count,
                passes,
                f"pool{pool_size_retry}-mem{extra_mem_retry}",
                {
                    "extra_mem_bot": str(extra_mem_retry),
                    "extra_mem_top": str(extra_mem_retry),
                    "pool_size": str(pool_size_retry),
                },
            )
            attempts.append(retry)
            final = retry
    result = dict(final)
    result["attempts"] = attempts
    result["retried_after_capacity_error"] = len(attempts) > 1
    result["prior_capacity_events"] = [
        event
        for attempt in attempts[:-1]
        for event in attempt["capacity_events"]
    ]
    return result


def parse_int(text: str) -> int:
    return int(text.replace(",", ""))


def parse_main_memory(log_text: str) -> dict:
    candidates: list[dict] = []
    for pattern in MAIN_MEMORY_PATTERNS:
        for match in pattern.finditer(log_text):
            if "node" in match.groupdict():
                used = parse_int(match.group("node")) + parse_int(match.group("token"))
                candidate = {
                    "used": used,
                    "limit": None,
                    "source": match.group(0).strip(),
                }
            else:
                candidate = {
                    "used": parse_int(match.group("used")),
                    "limit": parse_int(match.group("limit")),
                    "source": match.group(0).strip(),
                }
            candidates.append(candidate)
    if not candidates:
        return {"used": None, "limit": None, "source": None}
    return max(candidates, key=lambda item: item["used"])


def parse_string_pool(log_text: str) -> dict:
    matches = [
        {"used": parse_int(match.group("used")), "limit": parse_int(match.group("limit"))}
        for match in STRING_POOL_PATTERN.finditer(log_text)
    ]
    if not matches:
        return {"used": None, "limit": None}
    return max(matches, key=lambda item: item["used"])


def parse_csnames(log_text: str) -> dict:
    matches = [
        {
            "used": parse_int(match.group("used")),
            "limit": parse_int(match.group("base")) + parse_int(match.group("extra")),
        }
        for match in CSNAME_PATTERN.finditer(log_text)
    ]
    if not matches:
        return {"used": None, "limit": None}
    return max(matches, key=lambda item: item["used"])


def find_capacity_events(text: str) -> list[str]:
    events: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and any(pattern.search(stripped) for pattern in CAPACITY_PATTERNS):
            if stripped not in events:
                events.append(stripped)
    return events


def write_metrics(metrics: dict) -> None:
    WAVE_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_existing_metrics() -> dict | None:
    if not METRICS_PATH.exists():
        return None
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def reusable_result(
    existing: dict | None,
    engine: str,
    atom_count: int,
    passes: int,
) -> dict | None:
    if existing is None or existing.get("atom_count") != atom_count:
        return None
    for result in existing.get("engines", []):
        if (
            result.get("engine") == engine
            and result.get("passes_requested") == passes
            and _status(result) == "PASS"
        ):
            reused = dict(result)
            reused["reused_from_metrics"] = True
            return reused
    return None


def _status(engine_result: dict) -> str:
    if engine_result["exit_code"] == 0 and not engine_result["capacity_events"]:
        return "PASS"
    if engine_result["exit_code"] == 0:
        return "WARN"
    return "FAIL"


def _config(engine_result: dict) -> str:
    if not engine_result["env"]:
        return "default"
    return ", ".join(f"{key}={value}" for key, value in sorted(engine_result["env"].items()))


def _format_memory(engine_result: dict) -> str:
    used = engine_result["main_memory_words"]
    limit = engine_result["main_memory_limit_words"]
    if used is None:
        return "not reported"
    if limit is None:
        return f"{used:,}"
    return f"{used:,} / {limit:,}"


def _recommendation(results: list[dict]) -> str:
    passing = [result for result in results if _status(result) == "PASS"]
    default_passing = [result["engine"] for result in passing if not result["env"]]
    tuned_passing = [result["engine"] for result in passing if result["env"]]
    if len(default_passing) == len(results):
        return (
            "All probed engines completed the 10k-atom document with default "
            "TeX Live/Nix settings and no detected capacity errors."
        )
    if default_passing and tuned_passing:
        return (
            "Use "
            + ", ".join(default_passing)
            + " for 10k-atom documents under default settings. "
            + ", ".join(tuned_passing)
            + " also completed the probe, but only after the TeX capacity "
            "variables shown in the config column were raised."
        )
    if default_passing:
        return (
            "Use "
            + ", ".join(default_passing)
            + " for 10k-atom documents under default settings; investigate "
            "capacity flags for the failing engines before relying on them."
        )
    if tuned_passing:
        return (
            "All passing engines required raised TeX capacity variables; no "
            "probed engine is recommended for 10k-atom documents under the "
            "default settings."
        )
    return "No probed engine completed the 10k-atom document safely."


def _render_scaling_section(metrics: dict) -> str:
    results = metrics["engines"]
    generated_at = metrics["generated_at"]
    atom_count = metrics["atom_count"]
    lines = [
        "## W05-D dictionary scale probe",
        "",
        f"Generated: {generated_at}",
        "",
        (
            f"Synthetic document: {atom_count:,} tracked theorem atoms followed "
            f"by {atom_count:,} `\\cref` references.  The probe is designed to "
            "exercise the dictionary csname families "
            "`\\codep@brcount@<key>`, `\\codep@brnode@<key>@<k>`, "
            "`\\codep@rendered@<key>`, `\\codep@rlflag@<key>`, and "
            "`\\codep@anchor@<key>`."
        ),
        "",
        "| Engine | Config | Status | Exit | Passes | Wall seconds | main_memory words | string pool | csnames | Capacity events |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        events = "<br>".join(f"`{event}`" for event in result["capacity_events"]) or "none"
        lines.append(
            "| {engine} | {config} | {status} | {exit_code} | {passes_completed}/{passes_requested} "
            "| {wall_clock_seconds:.3f} | {memory} | {string_pool} | {csnames} | {events} |".format(
                engine=result["engine"],
                config=_config(result),
                status=_status(result),
                exit_code=result["exit_code"],
                passes_completed=result["passes_completed"],
                passes_requested=result["passes_requested"],
                wall_clock_seconds=result["wall_clock_seconds"],
                memory=_format_memory(result),
                string_pool=_format_limit(
                    result["string_characters"], result["string_characters_limit"]
                ),
                csnames=_format_limit(
                    result["multiletter_control_sequences"],
                    result["multiletter_control_sequences_limit"],
                ),
                events=events,
            )
        )
    lines.extend(
        [
            "",
            "Capacity assessment:",
            "",
        ]
    )
    if all(not result["capacity_events"] for result in results):
        lines.append(
            "- No `hash_extra`, `pool_size`, `csname_size`, or other TeX capacity "
            "exhaustion events were detected in the final successful engine logs."
        )
    else:
        for result in results:
            if result["capacity_events"]:
                lines.append(
                    f"- {result['engine']} reported: "
                    + "; ".join(f"`{event}`" for event in result["capacity_events"])
                )
    for result in results:
        if result.get("prior_capacity_events"):
            lines.append(
                f"- {result['engine']} default-config probe hit "
                + "; ".join(f"`{event}`" for event in result["prior_capacity_events"])
                + f"; the recorded final pass used `{_config(result)}`."
            )
    lines.extend(
        [
            f"- Recommendation: {_recommendation(results)}",
            "- No `--hash-extra` or `--main-memory` flags were required.  Engines "
            "that hit the default string-pool ceiling were retried with the "
            "`pool_size` kpathsea variable shown in the config column.",
            "",
            f"Raw JSON metrics: `{METRICS_PATH.relative_to(PROJECT_ROOT)}` (gitignored).",
            "",
        ]
    )
    return "\n".join(lines)


def _format_limit(used: int | None, limit: int | None) -> str:
    if used is None:
        return "not reported"
    if limit is None:
        return f"{used:,}"
    return f"{used:,} / {limit:,}"


def update_scaling_doc(metrics: dict) -> None:
    section = _render_scaling_section(metrics)
    start_marker = "## W05-D dictionary scale probe"
    if SCALING_DOC.exists():
        existing = SCALING_DOC.read_text(encoding="utf-8")
        if start_marker in existing:
            prefix = existing.split(start_marker, 1)[0].rstrip()
            text = prefix + "\n\n" + section + "\n"
        else:
            text = existing.rstrip() + "\n\n" + section + "\n"
    else:
        text = "# Scaling notes\n\n" + section + "\n"
    SCALING_DOC.write_text(text, encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atoms", type=int, default=DEFAULT_ATOMS)
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    parser.add_argument(
        "--engine",
        action="append",
        choices=DEFAULT_ENGINES,
        help="Engine to run; may be repeated. Defaults to all three engines.",
    )
    parser.add_argument(
        "--skip-doc",
        action="store_true",
        help="Write metrics JSON only; do not update docs/SCALING.md.",
    )
    parser.add_argument(
        "--pool-size-retry",
        type=int,
        default=DEFAULT_POOL_SIZE_RETRY,
        help=(
            "Retry an engine with this pool_size if its default run hits the "
            "string-pool ceiling. Use 0 to disable."
        ),
    )
    parser.add_argument(
        "--extra-mem-retry",
        type=int,
        default=DEFAULT_EXTRA_MEM_RETRY,
        help=(
            "Retry with extra_mem_top/bot at this value if a pool-size retry "
            "reaches main_memory. Use 0 to disable."
        ),
    )
    parser.add_argument(
        "--reuse-existing-success",
        action="store_true",
        help="Reuse passing engine results already present in the metrics JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    engines = args.engine or list(DEFAULT_ENGINES)
    tex_path = write_probe_tex(args.atoms)
    existing = read_existing_metrics() if args.reuse_existing_success else None
    results = []
    for engine in engines:
        reused = reusable_result(existing, engine, args.atoms, args.passes)
        if reused is not None:
            results.append(reused)
            continue
        results.append(
            run_engine(
                engine,
                tex_path,
                args.atoms,
                args.passes,
                args.pool_size_retry,
                args.extra_mem_retry,
            )
        )
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "atom_count": args.atoms,
        "reference_count": args.atoms,
        "tex_path": str(tex_path.relative_to(PROJECT_ROOT)),
        "engines": results,
    }
    write_metrics(metrics)
    if not args.skip_doc:
        update_scaling_doc(metrics)

    for result in results:
        print(
            f"{result['engine']}: {_status(result)} exit={result['exit_code']} "
            f"config={_config(result)} "
            f"main_memory={_format_memory(result)} "
            f"wall={result['wall_clock_seconds']:.3f}s"
        )
    print(f"metrics: {METRICS_PATH.relative_to(PROJECT_ROOT)}")
    if not args.skip_doc:
        print(f"summary: {SCALING_DOC.relative_to(PROJECT_ROOT)}")
    return 0 if all(_status(result) == "PASS" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
