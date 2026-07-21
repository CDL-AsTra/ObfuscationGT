import os
import re
import csv
import argparse


RUN_DIRECTORY_NAMES = [
    "run_O0_new",
#    "run_O1",
#    "run_O2",
#    "run_O3",
#    "run_Os",
#    "run_Of",
]


VALID_TYPES = ["functions", "instructions", "JumpTables"]


TYPE_FIELDNAMES = {
    "functions": [
        'file', 'disassembler', 'obfuscation_config',
        'total', 'total_compared',
        'false_positives', 'false_negatives',
        'precision', 'recall'
    ],
    "instructions": [
        'file', 'disassembler', 'obfuscation_config',
        'total', 'false_positives',
        'false_negatives', 'padding_instructions',
        'precision', 'recall'
    ],
    "JumpTables": [
        'file', 'disassembler', 'obfuscation_config',
        'total', 'total_compared',
        'false_positives', 'false_negatives',
        'wrong_successor'
    ],
}


TYPE_OUTPUT_FILENAMES = {
    "functions": "functions.csv",
    "instructions": "instructions.csv",
    "JumpTables": "jump_tables.csv",
}


def collect_run_directories(parent_directories, run_names=None):
    """Collect run directories (run_O*) that exist under the given parents."""
    if not parent_directories:
        return []

    run_names = run_names or RUN_DIRECTORY_NAMES
    collected = []
    seen = set()

    for parent in parent_directories:
        parent_abs = os.path.abspath(parent)
        parent_label = os.path.basename(parent_abs.rstrip(os.sep))
        for run_name in run_names:
            candidate = os.path.join(parent, run_name)
            if os.path.isdir(candidate) and candidate not in seen:
                collected.append((run_name, candidate, parent_label))
                seen.add(candidate)

    return collected


def process_log_files(directory, rows, type):
    post_fix = ""

    if type == "functions":
        post_fix = "Funcs"
    elif type == "instructions":
        post_fix = "Insts"
    elif type == "JumpTables":
        post_fix = "JmpTableIgnoreLibs"


    for root, _, files in os.walk(directory):
        for file in files:
            if 'compare'+ post_fix in file and file.endswith('.log'):
                disassembler_pattern = re.compile(r'compare' + post_fix + r'_(\w+)_')
                disassembler_match = disassembler_pattern.search(file)
                disassembler = disassembler_match.group(1) if disassembler_match else 'Unknown'
                obfuscation_config = os.path.basename(root)
                log_path = os.path.join(root, file)

                try:
                    with open(log_path, 'r') as f:
                        content = f.read()
                except OSError:
                    continue

                def grab_int(pattern):
                    m = re.search(pattern, content)
                    return int(m.group(1)) if m else None

                def grab_float(pattern):
                    m = re.search(pattern, content)
                    return float(m.group(1)) if m else None
                if type == "instructions":
                    rows.append({
                        'file': file,
                        'disassembler': disassembler,
                        'obfuscation_config': obfuscation_config,
                        'total': grab_int(r'The total instruction number is (\d+)'),
                        'false_positives': grab_int(r'Instruction false positive number is (\d+)'),
                        'false_negatives': grab_int(r'Instruction false negative number is (\d+)'),
                        'padding_instructions': grab_int(r'Padding byte instructions number is (\d+)'),
                        'precision': grab_float(r'Precision ([0-9.]+)'),
                        'recall': grab_float(r'Recall ([0-9.]+)')
                    })
                elif type == "functions":
                    rows.append({
                        'file': file,
                        'disassembler': disassembler,
                        'obfuscation_config': obfuscation_config,
                        'total': grab_int(r'The total Functions in ground truth is (\d+)'),
                        "total_compared": grab_int(r'The total Functions in compared is (\d+)'),
                        'false_positives': grab_int(r'False positive number is (\d+)'),
                        'false_negatives': grab_int(r'False negative number is (\d+)'),
                        'precision': grab_float(r'Precision ([0-9.]+)'),
                        'recall': grab_float(r'Recall ([0-9.]+)')
                    })
                else:  # JumpTables
                    rows.append({
                        'file': file,
                        'disassembler': disassembler,
                        'obfuscation_config': obfuscation_config,
                        'total': grab_int(r':The total jump table in ground truth is (\d+)'),
                        "total_compared": grab_int(r'The total jump table in compared is (\d+)'),
                        'false_positives': grab_int(r'False positive number is (\d+)'),
                        'false_negatives': grab_int(r'False negative number is (\d+)'),
                        'wrong_successor': grab_int(r'Wrong successors number is (\d+)'),
                    })

def main():
    parser = argparse.ArgumentParser(description='Extract instruction comparison metrics from log files.')
    parser.add_argument('-b', '--base-directories', nargs='+', default=[],
                        help='One or more directories to traverse; can be used with parent directories')
    parser.add_argument('-p', '--parent-directories', nargs='+', default=[],
                        help='Parent directories containing run_O* folders (run_O0, run_O1, run_O2, run_O3, run_Os, run_Of)')
    parser.add_argument('-o', '--output-csv', required=True,
                        help='Path to output CSV file or directory (for all types)')
    parser.add_argument('-t', '--type', choices=VALID_TYPES + ['all'], default=None,
                        help='Type to process (defaults to all when parent directories are provided)')
    args = parser.parse_args()

    explicit_directories = list(args.base_directories)
    parent_run_entries = collect_run_directories(args.parent_directories)

    if not explicit_directories and not parent_run_entries:
        parser.error('No valid directories found to process.')

    if args.type is None:
        if parent_run_entries:
            selected_types = list(VALID_TYPES)
        else:
            parser.error('Type is required when parent directories are not provided.')
    elif args.type == 'all':
        selected_types = list(VALID_TYPES)
    else:
        selected_types = [args.type]

    requires_directory_output = len(selected_types) > 1 or bool(parent_run_entries)

    if requires_directory_output:
        output_dir = args.output_csv
        if os.path.exists(output_dir):
            if not os.path.isdir(output_dir):
                parser.error('When producing multiple outputs, --output-csv must point to a directory.')
        else:
            os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = None

    def write_rows(destination, fieldnames, rows):
        with open(destination, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def base_suffix_from_run(run_name):
        return run_name[4:] if run_name.startswith('run_') else run_name

    for type_name in selected_types:
        fieldnames = TYPE_FIELDNAMES[type_name]

        if parent_run_entries:
            prefix = TYPE_OUTPUT_FILENAMES[type_name][:-4]
            base_counts = {}
            for run_name, _, _ in parent_run_entries:
                suffix = base_suffix_from_run(run_name)
                base_counts[suffix] = base_counts.get(suffix, 0) + 1

            used_final_suffixes = set()

            for run_name, run_path, parent_label in parent_run_entries:
                rows = []
                process_log_files(run_path, rows, type_name)

                suffix = base_suffix_from_run(run_name)
                if base_counts.get(suffix, 0) > 1:
                    suffix = f"{suffix}_{parent_label}" if parent_label else f"{suffix}_1"

                final_suffix = suffix
                duplicate_index = 1
                while final_suffix in used_final_suffixes:
                    duplicate_index += 1
                    final_suffix = f"{suffix}_{duplicate_index}"

                used_final_suffixes.add(final_suffix)

                output_file = os.path.join(output_dir, f"{prefix}_{final_suffix}.csv")
                write_rows(output_file, fieldnames, rows)

        if explicit_directories:
            rows = []
            for directory in explicit_directories:
                process_log_files(directory, rows, type_name)

            if requires_directory_output:
                output_file = os.path.join(output_dir, TYPE_OUTPUT_FILENAMES[type_name])
            else:
                output_file = args.output_csv

            write_rows(output_file, fieldnames, rows)

if __name__ == '__main__':
    main()
