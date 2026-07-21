
# This is a wrapper to make protobuf work with Jython
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Try to import protobuf
try:
    from google.protobuf import descriptor
    from google.protobuf import message
    print("Successfully imported protobuf")
except ImportError as e:
    print(f"Failed to import protobuf: {e}")
    sys.exit(1)
