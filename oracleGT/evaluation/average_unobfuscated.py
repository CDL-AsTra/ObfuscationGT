#!/usr/bin/env python3
"""Produce average precision/recall tables for unobfuscated binaries."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

DATASET_FILES: Mapping[str, str] = {
    "Instructions": "instructions_{opt}_new.csv",
    "Functions": "functions_{opt}_new.csv",
    "JumpTable": "jump_tables_{opt}_new.csv",
}

DATASET_LABELS: Mapping[str, str] = {
    "Instructions": "Instructions",
    "Functions": "Functions",
    "JumpTable": "JumpTable",
}

DATASET_SYNONYMS: Mapping[str, str] = {
    "instructions": "Instructions",
    "instruction": "Instructions",
    "inst": "Instructions",
    "functions": "Functions",
    "function": "Functions",
    "funcs": "Functions",
    "jumptable": "JumpTable",
    "jump_table": "JumpTable",
    "jump tables": "JumpTable",
    "jump": "JumpTable",
}

DISASSEMBLER_ORDER: List[str] = [
    "Angr",
    "Bap",
    "Dyninst",
    "Ghidra",
    "Ida",
    "Ninja",
    "Objdump",
    "Radare",
]

DISASSEMBLER_LABELS: Mapping[str, str] = {
    "Angr": r"\angr",
    "Bap": r"\bap",
    "Dyninst": r"\dyninst",
    "Ghidra": r"\ghidra",
    "Ida": r"\ida",
    "Ninja": r"\ninja",
    "Objdump": r"\objdump",
    "Radare": r"\radare",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute per-disassembler precision/recall averages for unobfuscated binaries "
            "and emit a LaTeX-ready table."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("all_runs"),
        help="Directory that contains the raw CSV files (default: all_runs).",
    )
    parser.add_argument(
        "-O",
        "--optimization",
        default="O2",
        help="Optimization level to analyze (e.g. O0, O2).",
    )
    parser.add_argument(
        "--format",
        choices=("latex", "markdown", "csv"),
        default="latex",
        help="Output format for the aggregated table (default: latex).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional file to write; prints to stdout when omitted.",
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=2,
        help="Number of decimal places for rendered percentages (default: 2).",
    )
    parser.add_argument(
        "--oracle-csv",
        type=Path,
        help=(
            "Optional CSV with OracleGT reference numbers. "
            "Expected columns: disassembler,dataset,precision,recall."
        ),
    )
    return parser.parse_args()


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator.astype(float).divide(denominator.astype(float))


def normalize_dataset_name(name: str) -> str:
    key = name.strip().lower()
    return DATASET_SYNONYMS.get(key, name.strip().title())


def compute_metrics(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    df = df.copy()
    for column in ("total", "total_compared", "false_positives", "false_negatives"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    true_pos = df["total"] - df["false_negatives"]
    precision = safe_ratio(true_pos, true_pos + df["false_positives"])
    recall = safe_ratio(true_pos, true_pos + df["false_negatives"])

    if dataset in {"Functions", "JumpTable"} and "total_compared" in df.columns:
        zero_compares = (df["total"] > 0) & (df["total_compared"] == 0)
        zero_targets = (df["total"] == 0) & (df["total_compared"] > 0)
        zero_both = (df["total"] == 0) & (df["total_compared"] == 0)
        precision.loc[zero_compares] = 0.0
        recall.loc[zero_targets] = 0.0
        precision.loc[zero_both] = 1.0
        recall.loc[zero_both] = 1.0

    df["precision"] = precision.fillna(0.0)
    df["recall"] = recall.fillna(0.0)
    return df


def load_unobfuscated_metrics(csv_path: Path, dataset: str) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing dataset file: {csv_path}")
    df = pd.read_csv(csv_path)
    if df.empty:
        return pd.DataFrame(columns=["precision", "recall"])

    mask = df["obfuscation_config"].astype(str).str.strip().str.lower() == "unobfuscated"
    df = df.loc[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=["precision", "recall"])

    df = compute_metrics(df, dataset)
    grouped = df.groupby("disassembler")[["precision", "recall"]].mean()
    return grouped


def load_oracle_metrics(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"disassembler", "dataset", "precision", "recall"}
    missing = required - set(df.columns)
    if missing:
        missing_fields = ", ".join(sorted(missing))
        raise ValueError(f"Oracle CSV missing required columns: {missing_fields}")
    df["dataset"] = df["dataset"].astype(str).map(normalize_dataset_name)
    df["precision"] = pd.to_numeric(df["precision"], errors="coerce")
    df["recall"] = pd.to_numeric(df["recall"], errors="coerce")
    return (
        df.set_index(["disassembler", "dataset"])[["precision", "recall"]]
        .sort_index()
    )


def to_percentage(value: float) -> float:
    if pd.isna(value):
        return np.nan
    if 0.0 <= value <= 1.0:
        return value * 100.0
    return value


def build_table_records(
    our_metrics: Mapping[str, pd.DataFrame],
    oracle_metrics: Optional[pd.DataFrame],
) -> pd.DataFrame:
    records: List[Dict[str, object]] = []
    for disassembler in DISASSEMBLER_ORDER:
        for dataset in DATASET_FILES:
            our_precision = np.nan
            our_recall = np.nan
            dataset_df = our_metrics.get(dataset)
            if dataset_df is not None and disassembler in dataset_df.index:
                our_precision = to_percentage(dataset_df.loc[disassembler, "precision"])
                our_recall = to_percentage(dataset_df.loc[disassembler, "recall"])

            oracle_precision = np.nan
            oracle_recall = np.nan
            if oracle_metrics is not None:
                idx = (disassembler, dataset)
                if idx in oracle_metrics.index:
                    oracle_precision = to_percentage(
                        oracle_metrics.loc[idx, "precision"]
                    )
                    oracle_recall = to_percentage(
                        oracle_metrics.loc[idx, "recall"]
                    )

            records.append(
                {
                    "disassembler": disassembler,
                    "dataset": dataset,
                    "our_precision": our_precision,
                    "our_recall": our_recall,
                    "oracle_precision": oracle_precision,
                    "oracle_recall": oracle_recall,
                }
            )
    return pd.DataFrame.from_records(records)


def format_value(value: float, decimals: int) -> str:
    if pd.isna(value):
        return "--"
    return f"{value:.{decimals}f}"


def render_latex(table: pd.DataFrame, decimals: int) -> str:
    lines: List[str] = [
        r"\begin{tabularx}{\linewidth}{Xlrr|rr}",
        r"\toprule",
        r"&   & \multicolumn{2}{c}{\textbf{Our paper}} & "
        r"\multicolumn{2}{c}{\textbf{OracleGT}} \\",
        r"\cmidrule(lr){3-4} \cmidrule(lr){5-6}",
        r"\textbf{} & \textbf{Type} & \textbf{Prec} & \textbf{Rec} & "
        r"\textbf{Prec} & \textbf{Rec} \\",
        r"\midrule",
    ]

    for disassembler in DISASSEMBLER_ORDER:
        label = DISASSEMBLER_LABELS.get(disassembler, rf"\texttt{{{disassembler}}}")
        block = table[table["disassembler"] == disassembler]
        for idx, dataset in enumerate(DATASET_FILES):
            dataset_label = DATASET_LABELS[dataset]
            row = block[block["dataset"] == dataset]
            our_prec = format_value(row["our_precision"].iloc[0], decimals) if not row.empty else "--"
            our_rec = format_value(row["our_recall"].iloc[0], decimals) if not row.empty else "--"
            oracle_prec = format_value(row["oracle_precision"].iloc[0], decimals) if not row.empty else "--"
            oracle_rec = format_value(row["oracle_recall"].iloc[0], decimals) if not row.empty else "--"

            multirow = (
                rf"\multirow{{3}}{{*}}{{\textbf{{{label}}}}}"
                if idx == 0
                else ""
            )
            lines.append(
                f"{multirow:20s} & {dataset_label:<13} & "
                f"{our_prec:>8} & {our_rec:>8} & {oracle_prec:>8} & {oracle_rec:>8} \\\\"
            )
        lines.append(r"\midrule")

    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabularx}")
    return "\n".join(lines)


def render_markdown(table: pd.DataFrame, decimals: int) -> str:
    pivot = (
        table.set_index(["disassembler", "dataset"])[
            ["our_precision", "our_recall", "oracle_precision", "oracle_recall"]
        ]
        .sort_index()
    )
    formatted = pivot.applymap(lambda v: format_value(v, decimals))
    return formatted.to_markdown()


def render_csv(table: pd.DataFrame, decimals: int) -> str:
    formatted = table.copy()
    for column in ("our_precision", "our_recall", "oracle_precision", "oracle_recall"):
        formatted[column] = formatted[column].map(
            lambda v: format_value(v, decimals) if not pd.isna(v) else ""
        )
    return formatted.to_csv(index=False)


def render_table(table: pd.DataFrame, fmt: str, decimals: int) -> str:
    if fmt == "latex":
        return render_latex(table, decimals)
    if fmt == "markdown":
        return render_markdown(table, decimals)
    if fmt == "csv":
        return render_csv(table, decimals)
    raise ValueError(f"Unsupported format: {fmt}")


def main() -> None:
    args = parse_args()
    opt = args.optimization
    input_dir = args.input_dir

    our_metrics: Dict[str, pd.DataFrame] = {}
    for dataset, pattern in DATASET_FILES.items():
        csv_path = input_dir / pattern.format(opt=opt)
        our_metrics[dataset] = load_unobfuscated_metrics(csv_path, dataset)

    oracle_metrics = load_oracle_metrics(args.oracle_csv) if args.oracle_csv else None
    table = build_table_records(our_metrics, oracle_metrics)
    rendered = render_table(table, args.format, args.decimals)

    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
