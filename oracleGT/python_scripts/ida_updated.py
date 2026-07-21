
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run IDA Pro headlessly on a single binary using runIDAScript.py."
    )
    parser.add_argument(
        "binary",
        help="Path to the binary to analyze",
    )
    parser.add_argument(
        "-d",
        "--idat",
        default="/opt/ida_app/idat",
        help="Path to IDA batch executable (default: /opt/ida_app/idat)",
    )
    parser.add_argument("--shared-dir", default=os.getcwd(), help="Directory to mount as /opt in the Docker container.")

    parser.add_argument(
        "--pythonpath-prefix",
        default="/opt/ida_app/python",
        help='Prefix to add to PYTHONPATH for IDA\'s Python (default: "/opt/ida_app/python")',
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("Running tasks on the server")
    print("Installing necessary Python packages...")  # (placeholder message to mirror bash script)

    # Ensure PYTHONPATH includes IDA's Python
    if args.pythonpath_prefix:
        current_pp = os.environ.get("PYTHONPATH", "")
        new_pp = (
            args.pythonpath_prefix
            if not current_pp
            else f"{args.pythonpath_prefix}:{current_pp}"
        )
        os.environ["PYTHONPATH"] = new_pp
    
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # Avoid Qt errors if no display


    # Defaults for ida script and runner, relative to this file to avoid CWD issues
    ida_script = f"{args.shared_dir}/disassemblers/ida/idaBlocks.py"
    runner = f"{args.shared_dir}/disassemblers/ida/runIDAScript.py"
    binary_path = Path(args.binary).resolve()
    idat_path = Path(args.idat).resolve()

    output_dir = os.path.dirname(binary_path)
    base_name = os.path.basename(binary_path)

    name_without_strip = base_name
    if name_without_strip.endswith('.strip'):
        name_without_strip = name_without_strip[:-len('.strip')]
    output_prefix = "BlockIda_"

    output_filename = f"{output_prefix}{name_without_strip}.pb"
    output_file = os.path.join(output_dir, output_filename)

    # Basic validations
    errs = []
    if not binary_path.is_file():
        errs.append(f'Binary not found or not a file: "{binary_path}"')
    if not idat_path.exists():
        errs.append(f'IDA executable not found: "{idat_path}"')
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Optional: verify python is available (use current interpreter)
    py = sys.executable or shutil.which("python3")
    if not py:
        print('ERROR: Could not locate a Python interpreter to run "runIDAScript.py".', file=sys.stderr)
        return 1

    print(f'Running disassembler script on binary "{binary_path}"')

    cmd = [
        py,
        str(runner),
        "-d",
        str(idat_path),
        "-b",
        str(binary_path),
        "-s",
        str(ida_script),
    ]
    print(" ".join(cmd))
    try:
        completed = subprocess.run(cmd,  stderr=subprocess.STDOUT, check=True)
        candidate_file = os.path.join(output_dir, f"Block-idaBlocks-{base_name}.pb")
        if os.path.isfile(candidate_file):
            try:
                os.replace(candidate_file, output_file)
            except OSError as e:
                print(f'ERROR: Failed to rename "{candidate_file}" to "{output_file}": {e}', file=sys.stderr)
                return 1
        return completed.returncode
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Disassembler run failed with exit code {exc.returncode}.", file=sys.stderr)
        return exc.returncode
    except FileNotFoundError as exc:
        print(f"ERROR: Failed to execute runner: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    main()



