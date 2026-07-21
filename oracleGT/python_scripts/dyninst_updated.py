import os
import subprocess
import argparse

# docker build -f docker/Dockerfile.ubuntu -t dyninst-custom:ubuntu-20.04 --build-arg version=20.04 --build-arg build_elfutils=yes .
# docker build -f docker/Dockerfile -t dyninst-own:ubuntu-20.04 --build-arg build_jobs=16 --build-arg base=dyninst-custom:ubuntu-20.04 .

# If there is no dyninst output 
# docker run -it -v ./to_execute/:/opt/shared dyninst-own:ubuntu-20.04 bash
# cd /opt/shared/disassemblers/dyninst
# make

def run_in_docker(binary_path, shared_dir):
    """
    Runs the dyninst disassembler on a given binary inside a Docker container.
    """
    
    # The path to the dyninstBlocks executable inside the Docker container.
    # This is based on the Dockerfile from Dyninst v12.3.0.
    disassembler_executable = "LD_LIBRARY_PATH=/dyninst/install/lib:$LD_LIBRARY_PATH /opt/shared/disassemblers/dyninst/dyninstBlocks"
    
    # Translate local paths to paths inside the container
    container_shared_dir = "/opt/shared"
    if not binary_path.startswith(shared_dir):
        # If the binary path is not in the shared directory, it's probably already a path inside the container.
        # This can happen because run.py sometimes passes local paths and sometimes container paths.
        # We will assume the path is already a container path.
        container_binary_path = binary_path
        output_dir = os.path.dirname(container_binary_path)
    else:
        relative_binary_path = os.path.relpath(binary_path, shared_dir)
        container_binary_path = os.path.join(container_shared_dir, relative_binary_path)
        relative_output_dir = os.path.relpath(os.path.dirname(binary_path), shared_dir)
        output_dir = os.path.join(container_shared_dir, relative_output_dir)

    
    output_prefix = "BlockDyninst_"
    base_name = os.path.basename(binary_path)
    name_without_strip = base_name
    if name_without_strip.endswith('.strip'):
        name_without_strip = name_without_strip[:-len('.strip')]
        
    output_filename = f"{output_prefix}{name_without_strip}.pb"
    container_output_file = os.path.join(output_dir, output_filename)

    print(f"Running dyninst disassembler on binary {container_binary_path} inside Docker")

    docker_image = "dyninst-own:ubuntu-20.04"
    command = [
        "docker", "run", "--rm",
        "-v", f"{shared_dir}:{container_shared_dir}",
        docker_image,
        "bash", "-c",
         f"{disassembler_executable} --binary {container_binary_path} --output {container_output_file}"
    ]
    
    print(f"Executing command: {' '.join(command)}")
    subprocess.run(command)

def main():
    """
    Processes a single binary file provided via command-line argument.
    """
    parser = argparse.ArgumentParser(description="Run Dyninst disassembler on a single binary inside a Docker container.")
    parser.add_argument("binary_path", help="Path to the binary file.")
    parser.add_argument("--shared-dir", default=os.getcwd(), help="Directory to mount as /opt/shared in the Docker container.")
    args = parser.parse_args()

    run_in_docker(args.binary_path, args.shared_dir)

if __name__ == "__main__":
    main()


