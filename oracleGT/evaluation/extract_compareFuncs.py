import os
import re
import csv

# Base directories for obfuscated and unobfuscated files
base_directories = ['run_O0/']
print(f"Base directories: {base_directories}")

# Regex to extract the disassembler name from the log file name
disassembler_pattern = re.compile(r'compareFuncs_(\w+)_')

# CSV output file for logs
csv_file_funcs = 'coreutils_log_summary_func.csv'

# List to hold extracted data
data_funcs = []

# Function to process the log files and extract data
def process_log_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Process `compareFuncs_*` logs
            if 'compareFuncs' in file and file.endswith('.log'):
                disassembler_match = disassembler_pattern.search(file)
                if disassembler_match:
                    disassembler = disassembler_match.group(1)
                else:
                    disassembler = 'Unknown'

                # Set obfuscation config based on the directory structure
                obfuscation_config = os.path.basename(root)

                log_path = os.path.join(root, file)

                with open(log_path, 'r') as f:
                    content = f.read()

                    total_functions_match = re.search(r'The total Functions in ground truth is (\d+)', content)
                    total_functions = int(total_functions_match.group(1)) if total_functions_match else 0

                    compared_functions_match = re.search(r'The total Functions in compared is (\d+)', content)
                    compared_functions = int(compared_functions_match.group(1)) if compared_functions_match else 0

                    false_positives_match = re.search(r'False positive number is (\d+)', content)
                    false_positives = int(false_positives_match.group(1)) if false_positives_match else 0

                    false_negatives_match = re.search(r'False negative number is (\d+)', content)
                    false_negatives = int(false_negatives_match.group(1)) if false_negatives_match else 0

                    precision_match = re.search(r'Precision ([0-9.]+)', content)
                    precision = float(precision_match.group(1)) if precision_match else 0.0

                    recall_match = re.search(r'Recall ([0-9.]+)', content)
                    recall = float(recall_match.group(1)) if recall_match else 0.0

                    # Append the extracted data to the list
                    data_funcs.append({
                        'file': file,
                        'disassembler': disassembler,
                        'obfuscation_config': obfuscation_config,
                        'total_functions': total_functions,
                        'compared_functions': compared_functions,
                        'false_positives': false_positives,
                        'false_negatives': false_negatives,
                        'precision': precision,
                        'recall': recall
                    })

# Traverse both base directories and process log files
for base_directory in base_directories:
    process_log_files(base_directory)

# Write the data to a CSV file
with open(csv_file_funcs, 'w', newline='') as csvfile:
    fieldnames = [
        'file', 'disassembler', 'obfuscation_config',
        'total_functions', 'compared_functions',
        'false_positives', 'false_negatives',
        'precision', 'recall'
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    writer.writeheader()
    writer.writerows(data_funcs)

print(f"Data extracted and saved to {csv_file_funcs}")

