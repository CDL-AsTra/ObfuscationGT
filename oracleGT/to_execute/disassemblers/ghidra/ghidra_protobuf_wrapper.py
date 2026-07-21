#!/usr/bin/env python

# Add the minimal_protobuf directory to the Python path
import sys
import os

# Add our minimal protobuf directory to the path
sys.path.insert(0, '/home/')

# Import the original ghidraBB script
from ghidraBB import *

# This is the main entry point that Ghidra will call
if __name__ == '__main__':
    # Call the main function from ghidraBB.py
    # Assuming it has a main() function or that the script will execute when imported
    try:
        if 'main' in globals():
            main()
    except Exception as e:
        print(f"Error in ghidra_protobuf_wrapper.py: {e}")
        import traceback
        traceback.print_exc()
