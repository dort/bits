"""
Example 1: Basic Text File Operations
=====================================

Key concepts:
- open() function with modes: 'r' (read), 'w' (write), 'a' (append)
- The 'with' statement ensures files are properly closed
- read(), readline(), readlines(), and write() methods

Think of a file like a mathematical sequence: you can read it element by
element (line by line) or all at once.
"""

# -----------------------------------------------------------------------------
# WRITING TO A FILE
# -----------------------------------------------------------------------------

# 'w' mode creates a new file or overwrites existing content
# Think of it as defining a new function that replaces any previous definition
'''with open("output.txt", "w") as f:
    f.write("Hello, this is line 1\n")
    f.write("This is line 2\n")
    f.write("And line 3\n")

print("File 'output.txt' created successfully!")
'''
# -----------------------------------------------------------------------------
# READING AN ENTIRE FILE
# -----------------------------------------------------------------------------

# 'r' mode opens for reading (this is the default)
with open("01_basic_text_files.py", "r") as f:
    content = f.read()  # Returns the entire file as one string
    print("\n--- Reading entire file at once ---")
    print(content)

# -----------------------------------------------------------------------------
# READING LINE BY LINE
# -----------------------------------------------------------------------------

# This is memory-efficient for large files (like iterating through an infinite series)
with open("output.txt", "r") as f:
    print("--- Reading line by line ---")
    for i, line in enumerate(f, start=1):
        # line includes the newline character '\n'
        # strip() removes leading/trailing whitespace including '\n'
        print(f"Line {i}: {line.strip()}")

# -----------------------------------------------------------------------------
# READING INTO A LIST
# -----------------------------------------------------------------------------

with open("output.txt", "r") as f:
    lines = f.readlines()  # Returns a list of strings
    print(f"\n--- File as a list (like a vector in R^n where n={len(lines)}) ---")
    print(lines)

# -----------------------------------------------------------------------------
# APPENDING TO A FILE
# -----------------------------------------------------------------------------

# 'a' mode adds to the end without erasing existing content
# Think of it like extending a sequence: a_1, a_2, ..., a_n, a_{n+1}, ...
with open("output.txt", "a") as f:
    f.write("This line was appended!\n")

print("\n--- After appending ---")
with open("output.txt", "r") as f:
    print(f.read())

# -----------------------------------------------------------------------------
# IMPORTANT: What happens without 'with'
# -----------------------------------------------------------------------------

# The 'with' statement is equivalent to:
#
# f = open("output.txt", "r")
# try:
#     content = f.read()
# finally:
#     f.close()  # This is crucial! Unclosed files can cause data loss
#
# Always use 'with' - it's the Pythonic way and prevents resource leaks.
