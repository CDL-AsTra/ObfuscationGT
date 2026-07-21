import os
import subprocess
import argparse

# sudo apt-get install opam m4 pkg-config libgmp-dev zlib1g-dev
# opam init
# opam switch create 4.14.0   # or latest stable OCaml
# eval $(opam env)
# opam install bap --no-depexts


# # docker build -f python_scripts/bap/Dockerfile -t bap:2.5.0 .

# docker save -o bap-docker.tar bap:2.5.0
# docker load -i bap-docker.tar

def bap_disassembler_script(binary_path, shared_dir):
    """
    Runs the BAP disassembler script on a given binary.
    """

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

    
    output_prefix = "BlockBap_"
    base_name = os.path.basename(binary_path)
    name_without_strip = base_name
    if name_without_strip.endswith('.strip'):
        name_without_strip = name_without_strip[:-len('.strip')]
        
    output_filename = f"{output_prefix}{name_without_strip}.pb"
    container_output_file = os.path.join(output_dir, output_filename)


    disassembler_script = os.path.join(container_shared_dir, "disassemblers", "bap", "bapBB.py")


    docker_image = "bap:2.5.0"
    command = [
        "docker", "run", "--rm",
        "-v", f"{shared_dir}:{container_shared_dir}",
        docker_image,
        "bash", "-c",
         f"python3 {disassembler_script} --binary {container_binary_path} --output {container_output_file}"
    ]
    
    print(f"Executing command: {' '.join(command)}")
    subprocess.run(command)



def main():
    """
    Processes a single binary file provided via command-line argument.
    """
    parser = argparse.ArgumentParser(description="Run BAP disassembler on a single binary.")
    parser.add_argument("binary_path", help="Path to the binary file.")
    parser.add_argument("--shared-dir", default=os.getcwd(), help="The shared directory.")
    args = parser.parse_args()

    bap_disassembler_script(args.binary_path, args.shared_dir)

if __name__ == "__main__":
    main()
