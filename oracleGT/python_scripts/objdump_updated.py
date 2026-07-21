import os
import subprocess
import argparse

def objdump_disassembler_script(binary_path, shared_dir):
    """
    Runs the objdump disassembler script on a given binary.
    """
    disassembler_script = os.path.join(shared_dir, "disassemblers", "objdump", "objdumpBB.py")
    output_prefix = "BlockObjdump_"

    if not os.path.isfile(binary_path):
        print(f"Error: Binary file not found at {binary_path}")
        return

    print(f"Running disassembler script on binary {binary_path}")
    output_dir = os.path.dirname(binary_path)
    base_name = os.path.basename(binary_path)

    name_without_strip = base_name
    if name_without_strip.endswith('.strip'):
        name_without_strip = name_without_strip[:-len('.strip')]

    output_filename = f"{output_prefix}{name_without_strip}.pb"
    output_file = os.path.join(output_dir, output_filename)

    command = ["python3", disassembler_script, "-b", binary_path, "-o", output_file]
    subprocess.run(command)

def main():
    """
    Processes a single binary file provided via command-line argument.
    """
    parser = argparse.ArgumentParser(description="Run objdump disassembler on a single binary.")
    parser.add_argument("binary_path", help="Path to the binary file.")
    parser.add_argument("--shared-dir", default=os.getcwd(), help="Directory to mount as /opt in the Docker container.")
    args = parser.parse_args()

    objdump_disassembler_script(args.binary_path, args.shared_dir)

if __name__ == "__main__":
    main()
