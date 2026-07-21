import argparse
import subprocess
import os


def main():
    parser = argparse.ArgumentParser(description="Process a C file through the entire recompilation workflow.")
    parser.add_argument("c_file", help="The C file to process.")
    parser.add_argument("--cflags", default="", help="Optional compiler flags.")
    parser.add_argument("--params", default="", help="Optional parameters for the compilation command.")
    parser.add_argument("--shared-dir", default=os.getcwd(), help="The directory to mount as /opt/shared in the Docker container.")
    parser.add_argument("--ghidra-home", default=None, help="Path to Ghidra installation inside the Docker container.")
    parser.add_argument("--java-home", default=None, help="Path to Java installation inside the Docker container.")
    parser.add_argument("--ida-path", default=None, help="Path to IDA batch executable inside the Docker container.")
    parser.add_argument("--bn-root", default=None, help="Path to Binary Ninja installation inside the Docker container.")
    parser.add_argument("--bn-license", default=None, help="Path to Binary Ninja license file inside the Docker container.")


    args = parser.parse_args()
    print("ida path:", args.ida_path)

    c_file = args.c_file
    if c_file.startswith(args.shared_dir):
        c_file = c_file.replace(args.shared_dir, "/opt/shared/", 1)

    run_pipeline(c_file, args.cflags, args.shared_dir, args.params, args.ghidra_home, args.java_home, args.ida_path, args.bn_root, args.bn_license)

def run_pipeline(c_file, cflags, shared_dir, params, ghidra_home, java_home, ida_path, bn_root, bn_license):
    print(f"Starting pipeline for {c_file} with flags '{cflags}' and params '{params}'")

    # Step 1: Compile
    binary_file = compile_file(c_file, cflags, shared_dir, params)
    if not binary_file:
        print(f"Compilation failed for {c_file}, stopping pipeline.")
        return
    

    # Step 1.1: Strip the binary
    print(f"Stripping binary {binary_file}")
    stripped_binary = strip_binary(binary_file, shared_dir)
    if not stripped_binary:
        print(f"Stripping failed for {binary_file}, stopping pipeline.")
        return


    # Step 2: Generate ground truth
    ground_truth_file = generate_ground_truth(binary_file, shared_dir)
    if not ground_truth_file:
        print(f"Ground truth generation failed for {binary_file}, stopping pipeline.")
        return

    # Step 3 & 4: Disassemble and Compare for each tool
    all_tools = {
        "radare": True,
        "bap": True,
        "angr": True,
        "ghidra": ghidra_home and java_home,
        "ghidraAggressive": ghidra_home and java_home,
        "objdump": True,
        "ida": ida_path,
        "dyninst": True,
        "ninja": bn_root and bn_license,
    }

    tools_to_run = [tool for tool, enabled in all_tools.items() if enabled]

    if not tools_to_run:
        print("No tools to run based on the provided flags.")
        print(f"Pipeline finished for {c_file}")
        return

    for tool in tools_to_run:
        print(f"--- Running tool: {tool} ---")
        disassembly_file = disassemble_file(
            stripped_binary, tool, shared_dir,
            ghidra_home=ghidra_home,
            java_home=java_home,
            ida_path=ida_path,
            bn_root=bn_root,
            bn_license=bn_license,
        )
        if disassembly_file:
            print(f"Disassembly succeeded for {stripped_binary} with {tool}, proceeding to comparison.")
            compare_results(disassembly_file, ground_truth_file, tool, shared_dir)
        else:
            print(f"Disassembly with {tool} failed for {binary_file}, skipping comparison.")
            
    print(f"Pipeline finished for {c_file}")


def strip_binary(binary_file, shared_dir):
    binary_file = binary_file.replace("/opt/shared/", shared_dir + "/")
    print(f"Stripping binary {binary_file}")

    stripped_binary = os.path.splitext(binary_file)[0] + ".strip"

    # Skip if output file already exists
    if os.path.exists(stripped_binary):
        print(f"Stripped binary {stripped_binary} already exists, skipping stripping.")
        return stripped_binary

    log_file = os.path.join(os.path.dirname(stripped_binary), f"{os.path.basename(stripped_binary)}_strip.log")
    

    subprocess_cmd = f"strip -o {stripped_binary} {binary_file}"
    with open(log_file, "w") as f:
        process = subprocess.run(subprocess_cmd.split(" "), stdout=f, stderr=subprocess.STDOUT)

    if process.returncode != 0:
        print(f"Stripping failed for {binary_file}. Check {log_file} for details.")
        return None
    else:
        print(f"Stripping succeeded for {binary_file}. Output: {stripped_binary}")
        return stripped_binary


def compile_file(c_file, cflags="", shared_dir=".", params = ""):
    print(f"Compiling {c_file}")
    output_file = os.path.splitext(c_file)[0] + ".out"

    # Skip if output file already exists
    if os.path.exists(output_file):
        print(f"Output file {output_file} already exists, skipping compilation.")
        return output_file

    log_file = os.path.join(os.path.dirname(output_file).replace("/opt/shared/", shared_dir + "/"), f"{os.path.basename(output_file)}_compile.log")

    docker_c_file = c_file
    docker_output_file = output_file
    print(docker_c_file)
    print(docker_output_file)

    # Add user-provided cflags to the command
    env_vars = f"export CFLAGS='{cflags}'"
    
    compile_command = (
        "source gcc64.rc && "
        f"{env_vars} && "
        "$CC $CFLAGS -o "
        f"'{docker_output_file}' '{docker_c_file}' {params}"
    )
    
    cmd = [
        "docker", "run",  "-m", "32g", "--rm", # "-it",
        "-v", f"{shared_dir}:/opt/shared",
        "bin2415/x86_gt:0.1",
        "/bin/bash", "-lc",
        compile_command
    ]

    with open(log_file, "w") as f:
        process = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

    if process.returncode != 0:
        print(f"Compilation failed for {c_file}. Check {log_file} for details.")
        return None
    else:
        print(f"Compilation succeeded for {c_file}. Output: {output_file}")
        return output_file

def generate_ground_truth(binary, shared_dir):
    print(f"Generating ground truth for {binary}")

    # Define the expected output file path
    ground_truth_file = os.path.join(os.path.dirname(binary), f"gtBlock_{os.path.basename(binary)}.pb")

    # Skip if output file already exists
    if os.path.exists(ground_truth_file.replace("/opt/shared/", shared_dir + "/")):
        print(f"Ground truth file {ground_truth_file} already exists, skipping generation.")
        return ground_truth_file

    log_file = os.path.join(os.path.dirname(binary).replace("/opt/shared/", shared_dir + "/"), f"{os.path.basename(binary)}_extraction.log")
    docker_binary_path = binary
    docker_binary_dir = os.path.dirname(docker_binary_path)

    cmd = [
        "docker", "run","-m", "32g",  "--rm", # "-it",
        "-v", f"{shared_dir}:/opt/shared",
        "bin2415/py_gt",
        "/bin/bash", "-c",
        (
            "pip3 install sqlalchemy pyelftools capstone protobuf==3.20.* && "
            "bash /opt/shared/run_extract_linux.sh "
            f"-d '{docker_binary_dir}' "
            "-s /opt/shared/extract_gt/extractBB.py "
            "-p gtBlock"
        )
    ]
    with open(log_file, "w") as f:
        process = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

    if process.returncode != 0:
        print(f"Ground truth generation failed for {binary}. Check {log_file} for details.")
        return None
    else:
        # The script seems to generate the file in the binary's directory.
        # We check if the file was created.
        ground_truth_file_local = ground_truth_file.replace("/opt/shared/", shared_dir + "/")
        if os.path.exists(ground_truth_file_local):
             print(f"Ground truth generation succeeded for {binary}. Output: {ground_truth_file}")
             return ground_truth_file
        else:
             print(f"Ground truth file {ground_truth_file_local} not found after execution.")
             return None


def disassemble_file(binary, tool, shared_dir, ghidra_home="/opt/ghidra_11.4.1_PUBLIC", java_home="/usr/lib/jvm/java-21-openjdk-amd64", ida_path="/opt/ida_app/", bn_root="/opt/binaryninja", bn_license="/opt/binaryninja/license.dat"):
    print(f"Disassembling {binary} with {tool}")
    output_file = os.path.join(os.path.dirname(binary), f"Block{tool[0].upper() + tool[1:]}_{os.path.basename(binary)}.pb")
    output_file = output_file.replace(".strip", "")

    # Skip if output file already exists
    if os.path.exists(output_file.replace("/opt/shared/", shared_dir + "/")):
        print(f"Disassembly file {output_file} already exists for tool {tool}, skipping disassembly.")
        return output_file
    
    if ida_path == None:
        ida_path = ""

    output_file_local = output_file.replace("/opt/shared/", shared_dir + "/")
    tool_configs = {
        "bap": {"script": "python_scripts/bap_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir], "output_file": output_file_local},
        "angr": {"script": "python_scripts/angr_updated.py", "args": [binary, "--shared-dir", shared_dir], "output_file": output_file_local},
        "ghidra": {"script": "python_scripts/ghidra_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--analyze-headless", f"{ghidra_home}/", "--java-home", java_home, "--script-path", f"{shared_dir}/disassemblers/ghidra/"], "output_file": output_file_local},
        "ghidraAggressive": {"script": "python_scripts/ghidra_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--analyze-headless", f"{ghidra_home}/", "--java-home", java_home, "--script-path", f"{shared_dir}/disassemblers/ghidra/", "--aggressive"], "output_file": output_file_local},
        "radare": {"script": "python_scripts/radare_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir], "output_file": output_file_local},
        "objdump": {"script": "python_scripts/objdump_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir], "output_file": output_file_local},
        "dyninst": {"script": "python_scripts/dyninst_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir], "output_file": output_file_local}, 
        "ida": {"script": "python_scripts/ida_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir, "-d", ida_path, "--pythonpath-prefix", ida_path + "python"], "output_file": output_file_local}, 
        "ninja": {"script": "python_scripts/ninja_updated.py", "args": [binary.replace("/opt/shared/", shared_dir + "/"), "--shared-dir", shared_dir, "--bn-root", bn_root, "--bn-license", bn_license], "output_file": output_file_local},
        # Add more tools as needed
    }

    cmd = tool_configs.get(tool)
    if not cmd:
        print(f"Tool {tool} not configured.")
        return None

    cmd_args = ["python3", cmd["script"]] + list(cmd["args"])

    log_file = os.path.join(os.path.dirname(binary).replace("/opt/shared/", shared_dir + "/"), f"{os.path.basename(binary)}_{tool}_disassemble.log")
    with open(log_file, "w") as f:
        f.write(f"Running command: {' '.join(cmd_args)}\n")
        process = subprocess.run(cmd_args, stdout=f, stderr=subprocess.STDOUT)

    if process.returncode != 0:
        print(f"Disassembly with {tool} failed for {binary}. Check {log_file} for details.")
        return None
    else:
        if "output_file" in cmd and os.path.exists(cmd["output_file"]):
             print(f"Disassembly with {tool} succeeded for {binary}. Output: {output_file}")
             return output_file
        elif "output_file" not in cmd:
             print(f"Disassembly with {tool} completed, no output file expected.")
             return "DUMMY_PATH_OK" # Special value to indicate success without output
        else:
            print(f"Disassembly output file {cmd['output_file']} not found after execution.")
            return None

def compare_results(disassembly, ground_truth, tool, shared_dir):
    print(f"Comparing {disassembly} with {ground_truth} using {tool}")

    disassembly = disassembly.replace("/opt/shared/", shared_dir + "/")
    ground_truth = ground_truth.replace("/opt/shared/", shared_dir + "/")

    # The binary file is not passed as an argument, but the compare scripts need it.
    # The compare script derives it from the ground truth file name.
    # gtBlock_basename.pb -> basename
    base_name = os.path.basename(ground_truth).replace("gtBlock_", "").replace(".pb", "")
    binary_file = os.path.join(os.path.dirname(disassembly), base_name)

    log_dir = os.path.dirname(disassembly)
    print(f"Log directory: {log_dir}")

    # Ensure dependencies are installed locally. This is done on every run to ensure
    # the environment is correct, mimicking the original Docker behavior.

    compare_scripts = ["compareFuncsIgnoreLibs.py", "compareInsts.py", "compareJmpTableIgnoreLibs.py"]

    for script in compare_scripts:
        log_file = os.path.join(log_dir, f"{script.split('.')[0]}_{tool.capitalize()}_{base_name}.log")
        print(f"Log file for {script}: {log_file}")
        if os.path.exists(log_file):
            print(f"Log file {log_file} already exists, skipping comparison with {script}.")
            continue
        
        # The compare scripts are in 'to_execute/compare' relative to the shared_dir
        compare_script_path = os.path.join(shared_dir, "compare", script)
        
        if not os.path.exists(compare_script_path):
            raise FileNotFoundError(f"Error: Comparison script not found at {compare_script_path}")
        
        cmd = [
            "python3", compare_script_path,
            "-b", binary_file,
            "-c", disassembly,
            "-g", ground_truth
        ]
        # if tool.lower() == "ida" and script == "compareJmpTable.py":
        #    cmd += ["-i", "y"]
        
        with open(log_file, "w") as f:
            f.write(f"Running command: {' '.join(cmd)}\n\n")
            process = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

        if process.returncode != 0:
            print(f"Comparison with {script} failed for {disassembly}. Check {log_file} for details.")
        else:
            print(f"Comparison with {script} succeeded for {disassembly}.")

if __name__ == "__main__":
    main()
