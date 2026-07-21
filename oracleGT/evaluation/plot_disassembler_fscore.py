#!/usr/bin/env python3
"""Plot averaged F-score line charts for selected disassemblers and optimizations."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATASET_CHOICES = ("Instructions", "Functions", "JumpTable")
PREFERRED_DATASETS = ["Instructions", "Functions", "JumpTable"]
PREFERRED_OPTIMIZATIONS = ["O0", "O1", "O2", "O3", "Of", "Os"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate averaged F-score line plots per obfuscation for selected disassemblers "
            "with separate lines for each optimization level."
        ),
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default="all_runs",
        help="Directory containing run CSV files (default: all_runs).",
    )
    parser.add_argument(
        "--disassembler",
        "-d",
        action="append",
        required=True,
        help="Name of a disassembler to include (repeat for multiple).",
    )
    parser.add_argument(
        "--dataset",
        choices=DATASET_CHOICES,
        help="Optional dataset filter (Instructions, Functions, JumpTable).",
    )
    parser.add_argument(
        "--optimization",
        "-O",
        action="append",
        dest="optimizations",
        help="Optimization level to include (repeat for multiple, e.g., -O O0 -O O2).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        dest="max_score",
        default=None,
        help="(Deprecated, use --max-score) Only keep averaged F-scores <= this value.",
    )
    parser.add_argument(
        "--max-score",
        type=float,
        dest="max_score",
        help="Only keep averaged F-scores <= this value.",
    )
    parser.add_argument(
        "--max-top-score",
        type=float,
        dest="max_top_score",
        help=(
            "Only plot obfuscations whose best disassembler/optimization F-score "
            "is <= this value."
        ),
    )
    parser.add_argument(
        "--strip-prefix",
        default="tigress_4_0_11_gcc_8_4_0-",
        help="Prefix to remove from obfuscation names for readability.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to save the generated plot (PNG/SVG/etc.).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional plot title.",
    )
    parser.add_argument(
        "--y-min",
        type=float,
        default=0.0,
        help="Lower bound for the y-axis (default: 0.0).",
    )
    return parser.parse_args()

def shorten_obfuscation(name: str) -> str:
    return name.replace("self_modify", "sm").replace("add_opaque", "ao").replace("anti_alias_analysis", "aaa").replace("anti_taint_analysis", "ata").replace("encode_branches", "eb").replace("flatten", "f")


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator.astype(float).divide(denominator.astype(float))


def infer_optimization(csv_file: Path) -> str:
    stem = csv_file.stem
    parts = [part for part in stem.split('_') if part]
    return parts[-1] if parts else stem


def infer_dataset(csv_file: Path) -> str:
    stem = csv_file.stem.lower()
    if "instruction" in stem:
        return "Instructions"
    if "jump" in stem or "jmp" in stem:
        return "JumpTable"
    if "function" in stem:
        return "Functions"
    return "Unknown"


def load_csvs(input_path: Path, strip_prefix: str) -> pd.DataFrame:
    if input_path.is_file():
        csv_files: Sequence[Path] = [input_path]
    else:
        csv_files = sorted(input_path.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under {input_path}.")

    frames: List[pd.DataFrame] = []
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        if df.empty:
            continue
        optimization = infer_optimization(csv_file)
        dataset = infer_dataset(csv_file)

        true_pos = df["total"] - df["false_negatives"]
        precision = (safe_ratio(true_pos, true_pos + df["false_positives"]) * 100).round(2)
        recall = (safe_ratio(true_pos, true_pos + df["false_negatives"]) * 100).round(2)

        if dataset in {"Functions", "JumpTable"} and "total_compared" in df:
            zero_compares = (df["total"] > 0) & (df["total_compared"] == 0)
            precision.loc[zero_compares] = 0
            zero_targets = (df["total"] == 0) & (df["total_compared"] > 0)
            recall.loc[zero_targets] = 0
            zero_both = (df["total"] == 0) & (df["total_compared"] == 0)
            precision.loc[zero_both] = 100
            recall.loc[zero_both] = 100


        """
        no_comparisons = pd.Series(False, index=df.index)
        if dataset in {"Functions", "JumpTable"} and "total_compared" in df:
            no_comparisons = (df["total"] > 0) & (df["total_compared"] == 0)
            precision.loc[no_comparisons] = 0.0

            no_comparisons = (df["total"] == 0) & (df["total_compared"] > 0)
            recall.loc[no_comparisons] = 0.0

            no_comparisons = (df["total"] == 0) & (df["total_compared"] == 0)
            precision.loc[no_comparisons] = 1.0
            recall.loc[no_comparisons] = 1.0
        """

        denom = precision + recall
        fscore = (2 * precision * recall).divide(denom)
        #fscore = fscore.mask(denom == 0, 0.0)
        #fscore.loc[no_comparisons] = 1.0

        df = df.assign(precision=precision, recall=recall, fscore=fscore)
        if strip_prefix:
            df["obfuscation_config"] = df["obfuscation_config"].str.replace(
                strip_prefix, "", regex=False
            )
            df["obfuscation_config"] = df["obfuscation_config"].apply(shorten_obfuscation)
        df["optimization"] = optimization
        df["dataset"] = dataset
        frames.append(df)

    if not frames:
        raise RuntimeError("All CSV files were empty.")

    return pd.concat(frames, ignore_index=True)


def average_runs(data: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        data.groupby(["dataset", "optimization", "obfuscation_config", "disassembler"])[
            ["precision", "recall", "fscore"]
        ]
        .mean()
        .reset_index()
    )
    return grouped


def filter_data(
    data: pd.DataFrame,
    disassemblers: Iterable[str],
    dataset: str | None,
    optimizations: Iterable[str] | None,
    max_score: float | None,
) -> pd.DataFrame:
    filtered = data[data["disassembler"].isin(disassemblers)].copy()
    if dataset:
        filtered = filtered[filtered["dataset"] == dataset]
    if optimizations:
        opt_set = {opt for opt in optimizations}
        filtered = filtered[filtered["optimization"].isin(opt_set)]
    if max_score is not None:
        filtered = filtered[filtered["fscore"] <= max_score]
    return filtered



def build_pivot(data: pd.DataFrame, disassemblers: Sequence[str]) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    dataset_order = {name: idx for idx, name in enumerate(PREFERRED_DATASETS)}
    opt_order = {name: idx for idx, name in enumerate(PREFERRED_OPTIMIZATIONS)}

    data["dataset"] = data["dataset"].astype(str)
    data["optimization"] = data["optimization"].astype(str)
    data["dataset_sort"] = data["dataset"].map(dataset_order).fillna(len(dataset_order))
    data["opt_sort"] = data["optimization"].map(opt_order).fillna(len(opt_order))
    data["obf_sort"] = data["obfuscation_config"].astype(str).str.lower()

    data = data.sort_values(
        by=[
            "dataset_sort",
            "dataset",
            "obf_sort",
            "opt_sort",
            "optimization",
            "disassembler",
        ],
        kind="stable",
    )

    index_order = pd.MultiIndex.from_frame(
        data[["dataset", "obfuscation_config"]].drop_duplicates()
    )

    pivot = data.pivot_table(
        index=["dataset", "obfuscation_config"],
        columns=["disassembler", "optimization"],
        values="fscore",
        aggfunc="mean",
    )
    pivot = pivot.reindex(index_order)

    column_order: List[tuple[str, str]] = []
    existing_cols = set(pivot.columns)
    for dis in disassemblers:
        for opt in PREFERRED_OPTIMIZATIONS:
            col = (dis, opt)
            if col in existing_cols:
                column_order.append(col)
        extras = sorted(
            opt for (d, opt) in existing_cols if d == dis and (d, opt) not in column_order
        )
        column_order.extend((dis, opt) for opt in extras)

    if not column_order:
        raise RuntimeError("None of the requested disassembler/optimization pairs are present.")

    pivot = pivot[column_order]
    pivot.dropna(how="all", inplace=True)

    return pivot


def filter_pivot_by_top_score(pivot: pd.DataFrame, max_top_score: float) -> pd.DataFrame:
    if pivot.empty:
        return pivot

    def row_is_within_threshold(row: pd.Series) -> bool:
        row_max = row.max(skipna=True)
        if pd.isna(row_max):
            return False
        return row_max <= max_top_score

    mask = pivot.apply(row_is_within_threshold, axis=1)
    return pivot.loc[mask]


def plot_fscore(pivot: pd.DataFrame, disassemblers: Sequence[str], title: str | None, y_min: float) -> None:
    if pivot.empty:
        raise RuntimeError("No data available after filtering; nothing to plot.")

    fig, ax = plt.subplots(figsize=(14, 6))

    labels = [obfuscation for _, obfuscation in pivot.index]
    x_positions = np.arange(len(pivot))

    for dis in disassemblers:
        for opt in PREFERRED_OPTIMIZATIONS + [opt for (_, opt) in pivot.columns if opt not in PREFERRED_OPTIMIZATIONS]:
            col = (dis, opt)
            if col not in pivot.columns:
                continue
            ax.plot(
                x_positions,
                pivot[col].to_numpy(),
                marker="o",
                label=f"{dis} ({opt})",
            )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=90)
    ax.set_ylabel("Averaged F-score")
    finite_values = pivot.to_numpy().astype(float)
    finite_values = finite_values[np.isfinite(finite_values)]
    max_val = finite_values.max() if finite_values.size else y_min
    upper = max(max_val + 0.05, y_min + 0.05, 1.0)
    if upper <= y_min:
        upper = y_min + 0.05
    upper = min(1.05, upper)
    ax.set_ylim(y_min, upper)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(ncol=2, fontsize="small")

    if title:
        ax.set_title(title)

    fig.tight_layout()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)

    raw_data = load_csvs(input_path, args.strip_prefix)
    averaged = average_runs(raw_data)
    #averaged.to_csv("averaged_runs.csv", index=False)

    disassemblers = list(dict.fromkeys(args.disassembler))
    optimizations = (
        [opt for opt in args.optimizations]
        if args.optimizations is not None
        else None
    )

    filtered = filter_data(
        averaged,
        disassemblers=disassemblers,
        dataset=args.dataset,
        optimizations=optimizations,
        max_score=args.max_score,
    )

    pivot = build_pivot(filtered, disassemblers)
    if args.max_top_score is not None:
        pivot = filter_pivot_by_top_score(pivot, args.max_top_score)
    plot_fscore(pivot, disassemblers, args.title, args.y_min)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(args.output)
    else:
        plt.show()


if __name__ == "__main__":
    main()
