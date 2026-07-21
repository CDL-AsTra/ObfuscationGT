import os
import subprocess
import argparse

def main():
    """
    Runs the angr disassembler script on a single binary inside a Docker container.
    """
    parser = argparse.ArgumentParser(description="Run angr disassembler on a single binary.")
    parser.add_argument("binary_path", help="Path to the binary file.")
    parser.add_argument("--shared-dir", default=os.getcwd(), help="Directory to mount as /opt in the Docker container.")
    args = parser.parse_args()

    shared_dir = args.shared_dir
    # The binary path inside the container will be relative to /opt
    container_binary_path = args.binary_path.replace(shared_dir, "/opt/shared/")

    # The command to be executed inside the Docker container

    binary=container_binary_path

    disassembler_script="/opt/shared/disassemblers/angr/angrBlocks.py"
    output_prefix="BlockAngr_"
    output_file=os.path.join(os.path.dirname(binary), f"{output_prefix}{os.path.basename(binary).replace('.strip', '')}.pb")


    command = f"/home/angr/.venv/bin/python {disassembler_script} -b {container_binary_path} -o {output_file}"

    # The full docker command
    docker_command = [
        "docker", "run",  "--rm", 
        #"-u", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{shared_dir}:/opt/shared:rw",
        "angr/angr:9.2.166",
        "/bin/bash", "-c",
        f"{command}"
    ]
    print(f"Executing command: {' '.join(docker_command)}")
    subprocess.run(docker_command)

if __name__ == "__main__":
    main()


#   File "/opt/shared/disassemblers/angr/angrBlocks.py", line 2, in <module>
#    import angr
#ModuleNotFoundError: No module named 'angr'



# If permission error -> chmod -R a+rwx ./to_execute