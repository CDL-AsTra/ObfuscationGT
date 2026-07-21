#!/usr/bin/env python3
"""Generate the LaTeX precision/recall table for a given optimization level."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple

import pandas as pd

DATASET_CONFIG = [
    ("instructions", "Instruction"),
    ("functions", "Function"),
    ("jump_tables", "Jump Table"),
]

DISASSEMBLER_ORDER = [
    ("Angr", r"\angr"),
    ("Bap", r"\bap"),
    ("Dyninst", r"\dyninst"),
    ("Ghidra", r"\ghidra"),
    ("Ida", r"\ida"),
    ("Ninja", "B. Ninja"),
    ("Objdump", r"\objdump"),
    ("Radare", r"\radare"),
 #           ("Ghidraaggressive", r"\ghidraaggressive"),

]

DISASSEMBLER_ALIASES = {
    "Angr": "Angr",
    "Bap": "Bap",
    "Dyninst": "Dyninst",
    "Ghidra": "Ghidra",
    "Ida": "Ida",
    "Ninja": "Ninja",
    "Objdump": "Objdump",
    "Radare": "Radare",
    "Ghidraaggressive": "Ghidraaggressive",
}

DISPLAY_METRIC_OVERRIDES = {
    "functions": {"Objdump"},
    "jump_tables": {"Objdump", "Bap"},
}

OBFUSCATION_ORDER = [
    "unobfuscated",
    "add_opaque_bug",
    "add_opaque_call",
    "add_opaque_junk",
    "add_opaque_question",
    "add_opaque_true",
    "anti_alias_analysis_001",
    "anti_taint_analysis",
    "anti_taint_analysis_argv",
    "anti_taint_analysis_sysCalls",
    "encode_branches_branchFuns",
    "encode_branches_goto2nopSled",
    "flatten_call",
    "flatten_goto",
    "flatten_indirect",
    "flatten_switch",
    "self_modify_arithmetic",
    "self_modify_comparisons",
    "self_modify_indirectBranch",
    "virtualize_binary",
    "virtualize_call",
    "virtualize_direct",
    "virtualize_ifnest",
    "virtualize_indirect",
    "virtualize_interpolation",
    "virtualize_linear",
    "virtualize_switch",
]

VARIANT_SUFFIXES = {"array", "env", "list", "stack", "text", "clobber"}
OBFUSCATION_SET = set(OBFUSCATION_ORDER)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate per-run CSV files for a specific optimization level and emit "
            "the LaTeX table of average precision/recall values."
        )
    )
    parser.add_argument(
        "--olevel",
        required=True,
        help="Optimization level to load (e.g., O0, O1, O2, O3, Of, Os).",
    )
    parser.add_argument(
        "--runs-dir",
        default="all_runs",
        type=Path,
        help="Directory containing the run CSV files (default: all_runs).",
    )
    parser.add_argument(
        "--strip-prefix",
        default="tigress_4_0_11_gcc_8_4_0-",
        help="Prefix to remove from obfuscation names before grouping.",
    )
    parser.add_argument(
        "--highlight-threshold",
        type=float,
        default=90.0,
        help="Highlight values below this percentage using \\textcolor{red}{...}.",
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=2,
        help="Number of decimal places to keep for non-integer percentages.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file. Defaults to stdout.",
    )
    parser.add_argument(
        "--relative-to-unobfuscated",
        action="store_true",
        help=(
            "Display obfuscation rows as differences relative to the unobfuscated "
            "baseline for each disassembler/metric column."
        ),
    )
    parser.add_argument(
        "--delta-color-threshold",
        type=float,
        default=None,
        help=(
            "Color values based on their change relative to the unobfuscated baseline "
            "when the relative table option is disabled. Specify the minimum "
            "percentage-point change needed to color the value."
        ),
    )
    return parser.parse_args()


def normalize_obfuscation(name: str, suffixes: Iterable[str]) -> str:
    parts = name.split("_")
    while parts and parts[-1] in suffixes:
        parts = parts[:-1]
    return "_".join(parts)


def canonical_obfuscation(name: str, suffixes: Iterable[str]) -> str | None:
    """Map a raw obfuscation configuration name to a known base."""
    normalized = normalize_obfuscation(name, suffixes)
    if normalized in OBFUSCATION_SET:
        return normalized
    for base in OBFUSCATION_ORDER:
        if normalized.startswith(f"{base}_"):
            return base
    return None


def latex_escape(text: str) -> str:
    return text.replace("_", r"\_")


def format_value(
    value: float | None,
    decimals: int,
    highlight_threshold: float,
    enable_highlight: bool = True,
) -> str:
    if value is None or pd.isna(value):
        return "--"

    percent = value * 100.0
    if math.isclose(percent, 100.0, rel_tol=1e-9, abs_tol=1e-9):
        formatted = "100"
    else:
        formatted = f"{percent:.{decimals}f}"

    if enable_highlight and percent < highlight_threshold:
        return rf"\textcolor{{red}}{{{formatted}}}"
    return formatted


def format_difference(
    value: float | None, baseline: float | None, decimals: int
) -> str:
    if (
        value is None
        or baseline is None
        or pd.isna(value)
        or pd.isna(baseline)
    ):
        return "--"

    diff = (value - baseline) * 100.0
    if math.isclose(diff, 0.0, rel_tol=1e-9, abs_tol=1e-9):
        diff = 0.0
    return f"{diff:+.{decimals}f}"


def apply_delta_coloring(
    formatted: str,
    value: float | None,
    baseline: float | None,
    delta_threshold: float | None,
) -> str:
    if (
        delta_threshold is None
        or value is None
        or baseline is None
        or pd.isna(value)
        or pd.isna(baseline)
    ):
        return formatted

    diff = (value - baseline) * 100.0
    if diff <= -delta_threshold:
        return rf"\textcolor{{red}}{{{formatted}}}"
    if diff >= delta_threshold:
        return rf"\textcolor{{green}}{{{formatted}}}"
    return formatted


def compute_metrics(df: pd.DataFrame, dataset_key: str) -> Tuple[pd.Series, pd.Series]:
    if {"precision", "recall"}.issubset(df.columns):
        return df["precision"].astype(float), df["recall"].astype(float)

    true_positives = df["total"] - df["false_negatives"]
    precision = true_positives.astype(float).divide(
        (true_positives + df["false_positives"]).astype(float).where(
            (true_positives + df["false_positives"]) != 0
        )
    )
    recall = true_positives.astype(float).divide(
        (true_positives + df["false_negatives"]).astype(float).where(
            (true_positives + df["false_negatives"]) != 0
        )
    )

    if dataset_key in {"functions", "jump_tables"} and "total_compared" in df:
        no_precision = (df["total"] > 0) & (df["total_compared"] == 0)
        precision.loc[no_precision] = 0.0

        no_recall = (df["total"] == 0) & (df["total_compared"] > 0)
        recall.loc[no_recall] = 0.0

        both_zero = (df["total"] == 0) & (df["total_compared"] == 0)
        precision.loc[both_zero] = 1.0
        recall.loc[both_zero] = 1.0

    return precision, recall


def load_dataset(
    csv_path: Path,
    strip_prefix: str,
    dataset_key: str,
) -> Dict[Tuple[str, str], Tuple[float, float]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV file: {csv_path}")

    df = pd.read_csv(csv_path)
    if df.empty:
        return {}

    precision, recall = compute_metrics(df, dataset_key)
    obfuscation = df["obfuscation_config"]
    if strip_prefix:
        obfuscation = obfuscation.str.replace(strip_prefix, "", regex=False)

    df = df.assign(
        precision=precision,
        recall=recall,
        obfuscation=obfuscation.map(
            lambda name: canonical_obfuscation(name, VARIANT_SUFFIXES)
        ),
        disassembler=df["disassembler"].map(DISASSEMBLER_ALIASES),
    )

    df = df.dropna(subset=["obfuscation", "disassembler"])

    grouped = (
        df.groupby(["obfuscation", "disassembler"])[["precision", "recall"]]
        .mean()
        .reset_index()
    )

    result: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for _, row in grouped.iterrows():
        key = (row["obfuscation"], row["disassembler"])
        result[key] = (float(row["precision"]), float(row["recall"]))

    overrides = DISPLAY_METRIC_OVERRIDES.get(dataset_key, set())
    if overrides:
        for obfuscation in OBFUSCATION_ORDER:
            for disassembler in overrides:
                result[(obfuscation, disassembler)] = (math.nan, math.nan)
    return result


def render_dataset_section(
    dataset_label: str,
    stats: Dict[Tuple[str, str], Tuple[float, float]],
    decimals: int,
    highlight_threshold: float,
    relative_to_unobfuscated: bool,
    delta_color_threshold: float | None,
) -> list[str]:
    lines: list[str] = []
    total_rows = len(OBFUSCATION_ORDER)
    multirow = (
        f"    \\multirow{{{total_rows}}}{{*}}{{"
        f"\\rotatebox[origin=c]{{90}}{{\\textbf{{{dataset_label}}}}}}}"
    )

    baseline_by_disassembler: Dict[str, Tuple[float, float]] = {}
    needs_baseline = relative_to_unobfuscated or delta_color_threshold is not None
    if needs_baseline:
        for disassembler, _ in DISASSEMBLER_ORDER:
            baseline_by_disassembler[disassembler] = stats.get(
                ("unobfuscated", disassembler), (math.nan, math.nan)
            )

    for idx, obf in enumerate(OBFUSCATION_ORDER):
        prefix = multirow if idx == 0 else "    "
        row_cells = [latex_escape(obf)]
        for disassembler, _ in DISASSEMBLER_ORDER:
            precision, recall = stats.get((obf, disassembler), (math.nan, math.nan))
            if relative_to_unobfuscated and obf != "unobfuscated":
                baseline_prec, baseline_rec = baseline_by_disassembler.get(
                    disassembler, (math.nan, math.nan)
                )
                row_cells.append(
                    format_difference(precision, baseline_prec, decimals)
                )
                row_cells.append(
                    format_difference(recall, baseline_rec, decimals)
                )
            else:
                apply_highlight = not (
                    delta_color_threshold is not None
                    and not relative_to_unobfuscated
                )
                formatted_prec = format_value(
                    precision,
                    decimals,
                    highlight_threshold,
                    enable_highlight=apply_highlight,
                )
                formatted_rec = format_value(
                    recall,
                    decimals,
                    highlight_threshold,
                    enable_highlight=apply_highlight,
                )
                if (
                    delta_color_threshold is not None
                    and not relative_to_unobfuscated
                    and obf != "unobfuscated"
                ):
                    baseline_prec, baseline_rec = baseline_by_disassembler.get(
                        disassembler, (math.nan, math.nan)
                    )
                    formatted_prec = apply_delta_coloring(
                        formatted_prec,
                        precision,
                        baseline_prec,
                        delta_color_threshold,
                    )
                    formatted_rec = apply_delta_coloring(
                        formatted_rec,
                        recall,
                        baseline_rec,
                        delta_color_threshold,
                    )
                row_cells.append(formatted_prec)
                row_cells.append(formatted_rec)
        row_content = " & ".join(row_cells)
        lines.append(f"{prefix} & {row_content} \\\\")
    return lines


def build_table(
    data: Dict[str, Dict[Tuple[str, str], Tuple[float, float]]],
    decimals: int,
    highlight_threshold: float,
    relative_to_unobfuscated: bool,
    delta_color_threshold: float | None,
) -> str:
    header = [
        r"\begin{table*}[!htbp]",
        r"  \centering",
        r"  \setlength{\tabcolsep}{1.5pt}",
        r"  \scriptsize",
        r" \caption{Average precision and recall, by obfuscation technique and disassembler.}",
        r"\label{tab:prec_recall_grouped}",
        r"  \begin{tabularx}{\textwidth}{lXrrrrrrrrrrrrrrrr}",
        r"    \toprule",
        r"    & \emph{\textbf{}}                & \multicolumn{2}{c}{\textbf{\angr}} & "
        r"\multicolumn{2}{c}{\textbf{\bap}} & \multicolumn{2}{c}{\textbf{\dyninst}} & "
        r"\multicolumn{2}{c}{\textbf{\ghidra}} & \multicolumn{2}{c}{\textbf{\ida}} & "
        r"\multicolumn{2}{c}{\textbf{B. Ninja}} & \multicolumn{2}{c}{\textbf{\objdump}} & "
        r"\multicolumn{2}{c}{\textbf{\radare}} \\",
        r"    & \textbf{Obfuscation}            & \textbf{Prec.}                     & "
        r"\textbf{Rec.}                     & \textbf{Prec.}                        & "
        r"\textbf{Rec.}                        & \textbf{Prec.}                    & "
        r"\textbf{Rec.}                         & \textbf{Prec.}                        & "
        r"\textbf{Rec.}                        & \textbf{Prec.}         & \textbf{Rec.}          & "
        r"\textbf{Prec.} & \textbf{Rec.}          & \textbf{Prec.}         & \textbf{Rec.} & "
        r"\textbf{Prec.}         & \textbf{Rec.}          \\",
    ]

    body: list[str] = []
    for dataset_key, dataset_label in DATASET_CONFIG:
        body.append(r"    \midrule")
        stats = data.get(dataset_key, {})
        body.extend(
            render_dataset_section(
                dataset_label,
                stats,
                decimals,
                highlight_threshold,
                relative_to_unobfuscated,
                delta_color_threshold,
            )
        )

    footer = [
        r"",
        r"    \bottomrule",
        r"  \end{tabularx}",
        r"\end{table*}",
    ]

    return "\n".join(header + body + footer)


def main() -> None:
    args = parse_args()
    data: Dict[str, Dict[Tuple[str, str], Tuple[float, float]]] = {}
    for dataset_name, _ in DATASET_CONFIG:
        csv_file = args.runs_dir / f"{dataset_name}_{args.olevel}_new.csv"
        stats = load_dataset(csv_file, args.strip_prefix, dataset_name)
        data[dataset_name] = stats

    latex_table = build_table(
        data,
        args.decimals,
        args.highlight_threshold,
        args.relative_to_unobfuscated,
        args.delta_color_threshold,
    )
    if args.output:
        args.output.write_text(latex_table + "\n", encoding="utf-8")
    else:
        print(latex_table)


if __name__ == "__main__":
    main()
