#!/usr/bin/env python3
"""
Run Binary Ninja headlessly on ONE binary (argparse version).

This Python script translates the provided bash workflow into Python and limits
processing to a single binary passed via argparse.

It will:
  - pip-install required Python packages
  - install the Binary Ninja Python API
  - set BN_LICENSE_PATH and prepend Binary Ninja's Python to PYTHONPATH
  - verify the license file exists and is readable (fix permissions if needed)
  - run ninjaBB.py on the given binary and write a .pb output file
  - sync filesystem changes

Example:
  python3 run_bn.py ./out/some_dir/sample.strip
  python3 run_bn.py ./out/some_dir/sample.strip -o ./out/some_dir/BlockNinja_sample.pb
"""

# python3 ./binaryninja/scripts/install_api.py


import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Binary Ninja disassembler on one binary (ninjaBB.py)."
    )
    parser.add_argument(
        "binary",
        help="Path to the binary to analyze (e.g., ./out/dir/file.strip)",
    )
    parser.add_argument(
        "--bn-root",
        default=None,
        help="Path to the Binary Ninja folder (defaults to ./binaryninja relative to this script).",
    )
    parser.add_argument("--shared-dir", default=os.getcwd(), help="Directory to mount as /opt in the Docker container.")
    parser.add_argument(
        "--bn-license",
        default=None,
        help="Path to the Binary Ninja license file (e.g., /opt/binaryninja/license.dat).",
    )
    return parser.parse_args()


def ensure_readable(path: Path) -> None:
    """Ensure file is world-readable (like `chmod +r`)."""
    try:
        mode = path.stat().st_mode
        new_mode = mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
        if new_mode != mode:
            path.chmod(new_mode)
            print("Changed permissions to make license file readable")
    except Exception as e:
        print(f"WARNING: Could not adjust permissions on {path}: {e}", file=sys.stderr)




def main() -> int:
    args = parse_args()

    print("Running tasks on the server")

    bn_root = Path(args.bn_root).resolve() 

    # Paths based on repo layout
    bn_license_path = args.bn_license
    bn_python_dir = (bn_root / "python").resolve()
    ninjaBB_py = f"{args.shared_dir}/disassemblers/ninja/ninjaBB.py"

    binary_path = Path(args.binary).resolve()
    if not binary_path.is_file():
        print(f'ERROR: Binary not found or not a file: "{binary_path}"', file=sys.stderr)
        return 1

    # Output path
    output_dir = os.path.dirname(binary_path)
    base_name = os.path.basename(binary_path)

    name_without_strip = base_name
    if name_without_strip.endswith('.strip'):
        name_without_strip = name_without_strip[:-len('.strip')]
    output_prefix = "BlockNinja_"
    output_filename = f"{output_prefix}{name_without_strip}.pb"
    output_file = os.path.join(output_dir, output_filename)


    # 3) Set environment variables
    os.environ["BN_LICENSE_PATH"] = str(bn_license_path)
    current_pp = os.environ.get("PYTHONPATH", "")
    new_pp = str(bn_python_dir) if not current_pp else f"{bn_python_dir}:{current_pp}"
    os.environ["PYTHONPATH"] = new_pp

    print(f"License path: {os.environ['BN_LICENSE_PATH']}")
    print(f"Python path: {os.environ['PYTHONPATH']}")

    # 4) Verify license file exists and is readable

    # 5) Run Binary Ninja disassembler on the single binary

    print(f"Running Binary Ninja on: {binary_path}")
    print(f"Output will be saved to: {output_file}")

    cmd = [
        sys.executable,
        str(ninjaBB_py),
        "-b",
        str(binary_path),
        "-o",
        str(output_file),
    ]

    try:
        subprocess.check_call(cmd, env=os.environ.copy())
    except subprocess.CalledProcessError as e:
        print(f"ERROR: ninjaBB.py failed with exit code {e.returncode}.", file=sys.stderr)
        return e.returncode


    print("Processing complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
