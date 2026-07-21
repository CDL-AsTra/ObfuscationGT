#!/usr/bin/env python3
"""
Run a Ghidra Python script via **PyGhidra (CPython 3)** on a single binary.

Example:
  python disassemble_with_ghidra.py /path/to/binary.strip \
      --ghidra-install /oracleGT/ghidra_11.4.2_PUBLIC \
      --script-path /opt/shared/x86-sok/disassemblers/ghidra \
      --post-script ghidraBB.py
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4


def remove_suffix(text: str, suffix: str) -> str:
    return text[:-len(suffix)] if text.endswith(suffix) else text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Disassemble a single binary with Ghidra using PyGhidra (CPython 3)."
    )
    parser.add_argument("binary", type=Path, help="Path to the input binary (e.g., file.strip).")
    parser.add_argument("--analyze-headless", type=Path, default=None,
                        help="Path to Ghidra install dir (sets GHIDRA_INSTALL_DIR).")
    parser.add_argument("--script-path", type=Path, required=True,
                        help="Directory containing your Ghidra script.")
    parser.add_argument("--post-script", default="ghidraBB.py",
                        help="Script filename to run (default: ghidraBB.py).")
    parser.add_argument("--project-name", default="temp_project",
                        help='Ghidra project name (default: "temp_project").')
    parser.add_argument("--java-home", type=Path, default=None,
                        help="Optional JAVA_HOME; set if JPype needs help finding libjvm.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output.")
    parser.add_argument("--aggressive", "-a", action="store_true", default=None)
    args = parser.parse_args()

    # Validate inputs
    binary_path: Path = args.binary
    if not binary_path.is_file():
        print(f"error: binary not found: {binary_path}", file=sys.stderr)
        return 1
    if not args.script_path.is_dir():
        print(f"error: script-path is not a directory: {args.script_path}", file=sys.stderr)
        return 1
    script_file = args.script_path / args.post_script
    if not script_file.is_file():
        print(f"error: post script not found: {script_file}", file=sys.stderr)
        return 1

    # Compute output paths (same names as your original)
    out_dir = binary_path.parent
    base_name = remove_suffix(binary_path.name, ".strip")
    if not args.aggressive:
        ghidra_out_path = out_dir / f"BlockGhidra_{base_name}.pb"
        ghidra_stat_out_path = out_dir / f"Stat_ghidra_{base_name}.log"
    else:
        ghidra_out_path = out_dir / f"BlockGhidraAggressive_{base_name}.pb"
        ghidra_stat_out_path = out_dir / f"Stat_ghidraAggressive_{base_name}.log"

    # Environment visible to the script (ghidraBB.py)
    os.environ["GHIDRA_OUT_PATH"] = str(ghidra_out_path)
    os.environ["GHIDRA_STAT_OUT_PATH"] = str(ghidra_stat_out_path)

    if args.analyze_headless:
        os.environ["GHIDRA_INSTALL_DIR"] = str(args.analyze_headless)
    if args.java_home:
        # Helpful for JPype to find libjvm; harmless if already set up
        os.environ["JAVA_HOME"] = str(args.java_home)
        os.environ["PATH"] = str(args.java_home / "bin") + os.pathsep + os.environ.get("PATH", "")

    try:
        import pyghidra  # requires: pip install pyghidra
    except ImportError:
        print("error: pyghidra is not installed. Run: pip install pyghidra", file=sys.stderr)
        return 1

    # Project naming / temp dir
    project_name = args.project_name
    if project_name == "temp_project":
        project_name = f"ghidra_proj_{uuid4().hex[:12]}"
        if args.verbose:
            print(f"Using random project name: {project_name}")

    # Create a temporary project location (optionally keep it)
    td = tempfile.TemporaryDirectory(prefix="ghidra_proj_")
    project_dir = Path(td.name)

    if args.verbose:
        print("Running with PyGhidra (CPython 3)...")
        print(f"  GHIDRA_INSTALL_DIR={os.environ.get('GHIDRA_INSTALL_DIR', '(unset)')}")
        print(f"  Project dir: {project_dir}")
        print(f"  Project name: {project_name}")
        print(f"  Script: {script_file}")
        print(f"  GHIDRA_OUT_PATH={os.environ['GHIDRA_OUT_PATH']}")
        print(f"  GHIDRA_STAT_OUT_PATH={os.environ['GHIDRA_STAT_OUT_PATH']}")

    # Run the script against the binary using PyGhidra
    try:
        # See pyghidra.run_script signature in official docs.
        args_to_set = []
        if args.aggressive:
            print("Running Ghidra in aggressive mode.")
            args_to_set.append("--aggressive-mode")

        pyghidra.run_script(
            str(binary_path),
            str(script_file),
            project_location=project_dir,
            project_name=project_name,
            script_args=args_to_set,         # add args to forward to your ghidra script if needed
            verbose=args.verbose,
            analyze=False, # We will handle analysis in the script
            nested_project_location=True,
            install_dir=Path(os.environ["GHIDRA_INSTALL_DIR"]) if "GHIDRA_INSTALL_DIR" in os.environ else None,
        )
    except Exception as e:
        print(f"error: PyGhidra run failed: {e}", file=sys.stderr)
        # Keep temp dir on failure for inspection
        return 1

    print(f"Ghidra disassembly completed for {binary_path}.")
    print(f"Output protobuf: {ghidra_out_path}")
    print(f"Stats log:       {ghidra_stat_out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
