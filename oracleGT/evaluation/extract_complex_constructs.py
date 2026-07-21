#!/usr/bin/env python3
"""Aggregate complex construct statistics from gtBlock logs into CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

# Order matters to match the LaTeX table layout.
_VALUE_CAPTURE = r"\s*(?::|=)?\s*(?:is\s+)*([\d,]+)"
_METRIC_DEFS: List[Dict[str, str]] = [
    {
        "id": "padding_bytes",
        "construct": "Data in code",
        "type": "Padding bytes",
        "pattern": rf"padding\s+cnt{_VALUE_CAPTURE}",
    },
    {
        "id": "hard_coded_bytes",
        "construct": "Data in code",
        "type": "Hard-coded bytes",
        "pattern": rf"(?:hand[-\s]*coded|handcoded)\s+bytes?{_VALUE_CAPTURE}",
    },
    {
        "id": "jump_tables",
        "construct": "Indirect Jumps",
        "type": "Jump tables",
        "pattern": rf"jump\s+tables?{_VALUE_CAPTURE}",
    },
    {
        "id": "indirect_tail_calls",
        "construct": "Indirect Jumps",
        "type": "Indirect tail-calls",
        "pattern": rf"tail\s+indirect\s+call{_VALUE_CAPTURE}",
    },
    {
        "id": "overlapping_functions",
        "construct": "Special functions",
        "type": "Overlapping functions",
        "pattern": rf"overlapping\s+functions?{_VALUE_CAPTURE}",
    },
    {
        "id": "multi_entry_functions",
        "construct": "Special functions",
        "type": "Multi-entry functions",
        "pattern": rf"multi[-\s]+entry\s+functions?{_VALUE_CAPTURE}",
    },
    {
        "id": "non_return_functions",
        "construct": "Special functions",
        "type": "Non-return functions",
        "pattern": rf"non[-\s]+return(?:ing)?\s+functions?{_VALUE_CAPTURE}",
    },
    {
        "id": "direct_tail_calls",
        "construct": "(Direct) Tail-calls",
        "type": "N/A",
        "pattern": rf"tail\s+call\s+count{_VALUE_CAPTURE}",
    },
]

# Compile regex and keep association with definition.
for metric in _METRIC_DEFS:
    metric["regex"] = re.compile(metric["pattern"], re.IGNORECASE)

_OPT_SUFFIXES = {"O0", "O1", "O2", "O3", "Os", "Of"}


def _infer_program_name(binary_name: str) -> str:
    """Heuristically derive program identifier from the binary name."""
    if "_" in binary_name:
        candidate_prog, suffix = binary_name.rsplit("_", 1)
        if suffix in _OPT_SUFFIXES and candidate_prog:
            return candidate_prog
    return binary_name


def _iter_unobfuscated_entries(input_dir: Path) -> Iterator[Tuple[str, str, Path, str]]:
    """Yield (program_key, binary_key, log_path, binary_name) tuples for unobfuscated runs."""
    for binary_entry in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        binary_name = binary_entry.name
        log_path = binary_entry / "unobfuscated" / f"gtBlock_{binary_name}.out.log"
        program_key = _infer_program_name(binary_name)
        binary_key = binary_name
        yield program_key, binary_key, log_path, binary_name


def _iter_obfuscated_entries(input_dir: Path, opt_level: str) -> Iterator[Tuple[str, str, Path, str]]:
    """Yield (program_key, binary_key, log_path, binary_name) tuples for obfuscated runs."""
    run_dir = input_dir / f"run_{opt_level}"
    if not run_dir.is_dir():
        return

    for binary_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        binary_name = binary_dir.name
        for obf_dir in sorted(p for p in binary_dir.iterdir() if p.is_dir()):
            obf_name = obf_dir.name
            log_path = obf_dir / f"gtBlock_{binary_name}.out.log"
            program_key = f"{binary_name}::{obf_name}"
            binary_key = f"{run_dir.name}::{binary_name}::{obf_name}"
            yield program_key, binary_key, log_path, binary_name


def _parse_log(log_path: Path) -> Dict[str, int]:
    """Extract all metric counts from a log file."""
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    metrics: Dict[str, int] = {}
    for metric in _METRIC_DEFS:
        match = metric["regex"].search(text)
        if match:
            value = int(match.group(1).replace(",", ""))
        else:
            value = 0
        metrics[metric["id"]] = value
    return metrics


def _collect(
    input_dir: Path, unobfuscated: bool, opt_level: str
) -> Tuple[Dict[str, Dict[str, object]], Dict[str, object], Dict[str, object]]:
    """Walk the directory tree and aggregate stats per metric."""
    summary: Dict[str, Dict[str, object]] = {}
    for metric in _METRIC_DEFS:
        summary[metric["id"]] = {
            "construct": metric["construct"],
            "type": metric["type"],
            "cases": 0,
            "programs": set(),
            "binaries": set(),
        }

    log_stats = {
        "cases": 0,
        "programs": set(),
        "binaries": set(),
    }
    compiled_stats = {
        "cases": 0,
        "programs": set(),
        "binaries": set(),
    }

    iterator: Iterable[Tuple[str, str, Path, str]]
    if unobfuscated:
        iterator = _iter_unobfuscated_entries(input_dir)
    else:
        iterator = _iter_obfuscated_entries(input_dir, opt_level) or []

    for program_key, binary_key, log_path, binary_name in iterator:
        binary_out_path = log_path.parent / f"{binary_name}.out"
        if binary_out_path.is_file():
            compiled_stats["cases"] += 1
            compiled_stats["programs"].add(program_key)
            compiled_stats["binaries"].add(binary_key)

        if not log_path.is_file():
            continue
        log_stats["cases"] += 1
        log_stats["programs"].add(program_key)
        log_stats["binaries"].add(binary_key)
        counts = _parse_log(log_path)
        for metric_id, count in counts.items():
            metric_summary = summary[metric_id]
            metric_summary["cases"] += count
            if count > 0:
                metric_summary["programs"].add(program_key)
                metric_summary["binaries"].add(binary_key)
    return summary, log_stats, compiled_stats


def _rows(
    summary: Dict[str, Dict[str, object]],
    log_stats: Dict[str, object],
    compiled_stats: Dict[str, object],
) -> List[Tuple[str, str, int, int, int]]:
    rows: List[Tuple[str, str, int, int, int]] = []
    for metric in _METRIC_DEFS:
        data = summary[metric["id"]]
        rows.append(
            (
                data["construct"],
                data["type"],
                data["cases"],
                len(data["programs"]),
                len(data["binaries"]),
            )
        )
    rows.append(
        (
            "Logs",
            "gtBlock_{binary}.out.log present",
            log_stats["cases"],
            len(log_stats["programs"]),
            len(log_stats["binaries"]),
        )
    )
    rows.append(
        (
            "Compilation",
            "{binary}.out present",
            compiled_stats["cases"],
            len(compiled_stats["programs"]),
            len(compiled_stats["binaries"]),
        )
    )
    return rows


def _write_csv(rows: Sequence[Tuple[str, str, int, int, int]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Constructs", "Types", "Cases", "Prog", "Bin"])
        writer.writerows(rows)


def _write_latex(rows: Sequence[Tuple[str, str, int, int, int]], output_path: Path) -> None:
    grouped: "OrderedDict[str, List[Tuple[str, str, int, int, int]]]" = OrderedDict()
    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    lines: List[str] = []
    lines.append(r"\begin{table}[ht]")
    lines.append(r"\centering")
    lines.append(r"  \setlength{\tabcolsep}{1.8pt}")
    lines.append(
        r"\caption{Statistics of complex constructs in our benchmark binaries. "
        r"\textit{Cases} denotes the total number of occurrences of each construct, "
        r"while \textit{Prog} and \textit{Bin} indicate the number of distinct source "
        r"programs and compiled binaries in which at least one instance appears.}"
    )
    lines.append(r"\label{tab:complex_constructs}")
    lines.append(r"\begin{tabularx}{\linewidth}{Xlrrr}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Constructs} & \textbf{Types} & \textbf{Cases} & \textbf{Prog} & \textbf{Bin} \\")
    lines.append(r"\midrule")

    first_group = True
    for construct, group_rows in grouped.items():
        if not first_group:
            lines.append(r"\midrule")
        first_group = False

        multi = len(group_rows)
        for idx, (_, type_name, cases, prog, bin_count) in enumerate(group_rows):
            cases_formatted = f"{cases:,}"
            if multi == 1:
                construct_cell = construct
            elif idx == 0:
                construct_cell = rf"\multirow{{{multi}}}{{*}}{{{construct}}}"
            else:
                construct_cell = ""

            if construct_cell:
                line = f"{construct_cell} & {type_name} & {cases_formatted} & {prog} & {bin_count} \\\\"
            else:
                line = f"    & {type_name} & {cases_formatted} & {prog} & {bin_count} \\\\"
            lines.append(line)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabularx}")
    lines.append(r"\end{table}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract complex construct statistics from gtBlock logs and emit CSV",
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Path to the directory containing per-binary folders",
    )
    parser.add_argument(
        "output_path",
        type=Path,
        help="Destination path for the generated table",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "latex"),
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--opt-level",
        choices=sorted(_OPT_SUFFIXES),
        default="O0",
        help="Optimization level to analyze in run_* layout (default: O0)",
    )
    parser.add_argument(
        "--unobfuscated",
        action="store_true",
        help="Use the legacy directory layout (binary/unobfuscated/gtBlock_*.log)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"Input directory '{args.input_dir}' does not exist or is not a directory")
    summary, log_stats, compiled_stats = _collect(args.input_dir, args.unobfuscated, args.opt_level)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = _rows(summary, log_stats, compiled_stats)
    if args.format == "latex":
        _write_latex(rows, args.output_path)
    else:
        _write_csv(rows, args.output_path)


if __name__ == "__main__":
    main()
