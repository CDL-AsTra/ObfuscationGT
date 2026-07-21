#!/usr/bin/env python3
"""Compute average F-scores per obfuscation across all runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd

DATASET_CHOICES = ("Instructions", "Functions", "JumpTable")
DEFAULT_PREFIX = "tigress_4_0_11_gcc_8_4_0-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate evaluation CSV files and report the average F-score per "
            "obfuscation technique across optimizations, disassemblers, and binaries."
        )
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default="all_runs",
        help="Directory containing run CSV files or a single CSV file (default: all_runs).",
    )
    parser.add_argument(
        "--dataset",
        "-D",
        action="append",
        dest="datasets",
        choices=DATASET_CHOICES,
        help="Optional dataset filter; repeat to include multiple datasets.",
    )
    parser.add_argument(
        "--disassembler",
        "-d",
        action="append",
        dest="disassemblers",
        help="Optional disassembler filter; repeat to include multiple disassemblers.",
    )
    parser.add_argument(
        "--optimization",
        "-O",
        action="append",
        dest="optimizations",
        help="Optional optimization filter (e.g. -O O0 -O O2).",
    )
    parser.add_argument(
        "--strip-prefix",
        default=DEFAULT_PREFIX,
        help="Prefix to remove from obfuscation names for readability.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=("csv", "markdown", "plain"),
        default="csv",
        help="Output format for the aggregated table (default: csv).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional output file path. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=3,
        help="Number of decimal places to display for F-scores (default: 3).",
    )
    return parser.parse_args()


def find_csv_files(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    files = sorted(p for p in input_path.glob("*.csv") if p.is_file())
    if not files:
        raise FileNotFoundError(f"No CSV files found under {input_path}")
    return files


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator.astype(float).divide(denominator.astype(float))


def infer_optimization(csv_file: Path) -> str:
    parts = [part for part in csv_file.stem.split("_") if part]
    return parts[-1] if parts else csv_file.stem


def infer_dataset(csv_file: Path) -> str:
    stem = csv_file.stem.lower()
    if "instruction" in stem:
        return "Instructions"
    if "jump" in stem or "jmp" in stem:
        return "JumpTable"
    if "function" in stem:
        return "Functions"
    return "Unknown"


def normalize_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)


def load_runs(csv_files: Iterable[Path], strip_prefix: str) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        if df.empty:
            continue

        normalize_numeric(df, ("total", "total_compared", "false_positives", "false_negatives"))

        optimization = infer_optimization(csv_file)
        dataset = infer_dataset(csv_file)

        true_pos = df["total"] - df["false_negatives"]
        fp = df["false_positives"]
        fn = df["false_negatives"]

        precision = safe_ratio(true_pos, true_pos + fp)
        recall = safe_ratio(true_pos, true_pos + fn)

        if dataset in {"Functions", "JumpTable"} and "total_compared" in df:
            zero_compares = (df["total"] > 0) & (df["total_compared"] == 0)
            precision.loc[zero_compares] = 0.0
            zero_targets = (df["total"] == 0) & (df["total_compared"] > 0)
            recall.loc[zero_targets] = 0.0
            zero_both = (df["total"] == 0) & (df["total_compared"] == 0)
            precision.loc[zero_both] = 1.0
            recall.loc[zero_both] = 1.0
        elif "total_compared" not in df:
            print(df)

        denom = precision + recall
        fscore = (2 * precision * recall).divide(denom)
        fscore = fscore.fillna(0.0)

        df = df.assign(precision=precision.fillna(0.0), recall=recall.fillna(0.0), fscore=fscore)
        df["optimization"] = optimization
        df["dataset"] = dataset
        if strip_prefix:
            df["obfuscation_config"] = df["obfuscation_config"].str.replace(strip_prefix, "", regex=False)
        frames.append(df)

    if not frames:
        raise RuntimeError("All CSV files were empty.")

    return pd.concat(frames, ignore_index=True)


def filter_runs(
    data: pd.DataFrame,
    datasets: Iterable[str] | None,
    disassemblers: Iterable[str] | None,
    optimizations: Iterable[str] | None,
) -> pd.DataFrame:
    filtered = data
    if datasets:
        dataset_set = {name for name in datasets}
        filtered = filtered[filtered["dataset"].isin(dataset_set)]
    if disassemblers:
        disassembler_set = {name for name in disassemblers}
        filtered = filtered[filtered["disassembler"].isin(disassembler_set)]
    if optimizations:
        optimization_set = {name for name in optimizations}
        filtered = filtered[filtered["optimization"].isin(optimization_set)]
    return filtered


def aggregate_fscore(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(columns=["obfuscation_config", "avg_fscore"])
    grouped = (
        data.groupby("obfuscation_config")["fscore"].mean().reset_index(name="avg_fscore")
    )
    grouped = grouped.sort_values(["avg_fscore", "obfuscation_config"], ascending=[False, True])
    return grouped


def format_output(table: pd.DataFrame, fmt: str, decimals: int) -> str:
    display = table.copy()
    display["avg_fscore"] = display["avg_fscore"].round(decimals)
    if fmt == "csv":
        return display.to_csv(index=False)
    if fmt == "markdown":
        return display.to_markdown(index=False)
    return display.to_string(index=False)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)
    csv_files = find_csv_files(input_path)
    runs = load_runs(csv_files, args.strip_prefix)
    filtered = filter_runs(runs, args.datasets, args.disassemblers, args.optimizations)

    table = aggregate_fscore(filtered)
    if table.empty:
        raise SystemExit("No data left after applying filters.")

    output_text = format_output(table, args.format, args.decimals)
    if args.output:
        args.output.write_text(output_text)
    else:
        print(output_text, end="" if args.format == "csv" else "\n")


if __name__ == "__main__":
    main()
