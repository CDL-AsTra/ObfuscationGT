#!/usr/bin/env python3
"""Generate an obfuscation summary table from evaluation CSV files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate run CSV files and print a table of per-obfuscation "
            "precision/recall scores for each disassembler."
        )
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default="all_runs",
        help="Directory containing run CSV files (default: all_runs).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Only keep obfuscations where any precision or recall falls below this value.",
    )
    parser.add_argument(
        "--strip-prefix",
        default="tigress_4_0_11_gcc_8_4_0-",
        help=(
            "String prefix to drop from obfuscation names. "
            "Pass an empty string to keep the original values."
        ),
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=2,
        help="Number of decimal places when displaying metrics.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="If set, only display the first N rows after sorting.",
    )
    parser.add_argument(
        "--format",
        choices=("plain", "markdown", "csv", "latex"),
        default="csv",
        help="Output format for the table (default: csv).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional file path to write the formatted table.",
    )
    return parser.parse_args()


def find_csv_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    return sorted(p for p in path.glob("*.csv") if p.is_file())


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return numerator / denominator with NaNs when denominator is 0."""
    denominator = denominator.replace(0, np.nan)
    return numerator.astype(float).divide(denominator.astype(float))


def infer_optimization(csv_file: Path) -> str:
    """Best-effort extraction of the optimization level from the CSV filename."""
    stem = csv_file.stem
    parts = [part for part in stem.split('_') if part]
    return parts[-1] if parts else stem


def infer_dataset(csv_file: Path) -> str:
    """Infer the dataset type (instructions/functions/jump table) from the filename."""
    stem = csv_file.stem.lower()
    if "instruction" in stem:
        return "Instructions"
    if "jump" in stem or "jmp" in stem:
        return "JumpTable"
    if "function" in stem:
        return "Functions"
    return "Unknown"


def load_runs(csv_files: Iterable[Path], strip_prefix: str | None) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        if df.empty:
            continue

        optimization = infer_optimization(csv_file)
        dataset = infer_dataset(csv_file)

        true_positives = df["total"] - df["false_negatives"]
        precision = safe_ratio(true_positives, true_positives + df["false_positives"])
        recall = safe_ratio(true_positives, true_positives + df["false_negatives"])

        if dataset in {"Functions", "JumpTable"} and "total_compared" in df:
            no_comparisons = (df["total"] > 0) & (df["total_compared"] == 0)
            precision.loc[no_comparisons] = 0.0
            no_comparisons = (df["total"] == 0) & (df["total_compared"] > 0)
            recall.loc[no_comparisons] = 0.0
            
            no_comparisons = (df["total"] == 0) & (df["total_compared"] == 0)
            precision.loc[no_comparisons] = 1.0
            recall.loc[no_comparisons] = 1.0

        df = df.assign(precision=precision, recall=recall)
        if strip_prefix:
            df["obfuscation_config"] = df["obfuscation_config"].str.replace(
                strip_prefix, "", regex=False
            )
        df["optimization"] = optimization
        df["dataset"] = dataset
        frames.append(df)

    if not frames:
        raise RuntimeError("No non-empty CSV files found under the provided path.")

    return pd.concat(frames, ignore_index=True)





def build_summary_table(
    data: pd.DataFrame, threshold: float, decimals: int
) -> pd.DataFrame:
    grouped = (
        data.groupby(["dataset", "optimization", "obfuscation_config", "disassembler"])[
            ["precision", "recall"]
        ]
        .mean()
        .reset_index()
    )

    pivot = grouped.pivot(
        index=["dataset", "optimization", "obfuscation_config"],
        columns="disassembler",
        values=["precision", "recall"],
    )

    if pivot.empty:
        return pd.DataFrame()

    precision_values = pivot.xs("precision", axis=1, level=0)
    recall_values = pivot.xs("recall", axis=1, level=0)

    below_threshold = (precision_values.lt(threshold) | recall_values.lt(threshold)).fillna(False)
    pivot = pivot.loc[below_threshold.any(axis=1)]

    if pivot.empty:
        return pd.DataFrame()

    preferred_order = ["O0", "O1", "O2", "O3", "Of", "Os"]
    preferred_datasets = ["Instructions", "Functions", "JumpTable"]
    dataset_order = {name: idx for idx, name in enumerate(preferred_datasets)}
    optimization_order = {opt: idx for idx, opt in enumerate(preferred_order)}

    combined_metrics = pd.concat([precision_values, recall_values], axis=1)
    combined_metrics = combined_metrics.loc[pivot.index]
    row_scores = combined_metrics.min(axis=1)

    def sort_key(idx):
        dataset, optimization, obfuscation = idx
        return (
            dataset_order.get(dataset, len(dataset_order)),
            dataset,
            optimization_order.get(optimization, len(preferred_order)),
            optimization,
            row_scores[idx],
            obfuscation,
        )

    sorted_index = sorted(pivot.index, key=sort_key)
    pivot = pivot.loc[sorted_index]

    excluded_tools = {"Radare_linear", "linear_bap"}
    disassemblers = sorted(
        tool for tool in data["disassembler"].unique() if tool not in excluded_tools
    )
    ordered_columns = pd.MultiIndex.from_product(
        [disassemblers, ["precision", "recall"]]
    )

    table = pivot.swaplevel(axis=1).sort_index(axis=1, level=0)
    table = table.reindex(columns=ordered_columns)

    def fmt(value: float) -> str:
        if pd.isna(value):
            return "NA"
        return f"{value:.{decimals}f}"

    formatted = table.map(fmt)
    formatted.index.set_names(["Dataset", "Optimization", "Obfuscation"], inplace=True)

    return formatted



def output_table(
    table: pd.DataFrame, output_format: str, output_path: Path | None
) -> None:
    if table.empty:
        message = "No obfuscation techniques met the filter criteria."
        if output_path:
            output_path.write_text(message + "\n")
        else:
            print(message)
        return

    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        if output_format == "plain":
            rendered = table.to_string()
            if output_path:
                output_path.write_text(rendered + "\n")
            else:
                print(rendered)
            return

        if output_format == "latex":
            rendered = table.to_latex(
                index=True,
                escape=False,
                multicolumn=True,
                multicolumn_format="c",
            )
            if output_path:
                output_path.write_text(rendered + "\n")
            else:
                print(rendered)
            return

        if output_format == "markdown":
            export = table.reset_index()
            export.columns = [
                "_".join(str(part) for part in col if str(part))
                for col in export.columns.to_flat_index()
            ]
            try:
                rendered = export.to_markdown(index=False)
            except ImportError as exc:
                raise SystemExit(
                    "Markdown output requires tabulate to be installed."
                ) from exc
            if output_path:
                output_path.write_text(rendered + "\n")
            else:
                print(rendered)
            return

        # CSV output retains the MultiIndex column structure for multi-row headers.
        if output_path:
            table.to_csv(output_path)
        else:
            table.to_csv(sys.stdout)



def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)
    csv_files = find_csv_files(input_path)
    data = load_runs(csv_files, args.strip_prefix if args.strip_prefix else None)
    summary = build_summary_table(data, args.threshold, args.decimals)

    if args.limit is not None and args.limit > 0:
        summary = summary.head(args.limit)

    output_table(summary, args.format, args.output)


if __name__ == "__main__":
    main()
