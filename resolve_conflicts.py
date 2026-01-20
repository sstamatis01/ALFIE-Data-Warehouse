#!/usr/bin/env python3
"""
Script to resolve merge conflicts by keeping HEAD version
Removes everything from """
import os
import re
from pathlib import Path

def resolve_conflicts_in_file(filepath):
    """Resolve conflicts in a single file by keeping HEAD version"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Check if file has conflicts
        if '=======' not in content:
            return False
        
        # Pattern to match conflict blocks: <<<<<<< HEAD ... ======= ... >>>>>>>
        # We want to keep everything before ======= and remove everything from ======= to >>>>>>>
        lines = content.split('\n')
        new_lines = []
        skip_until_end = False
        
        for i, line in enumerate(lines):
            if line.strip().startswith('<<<<<<< HEAD'):
                # Remove the <<<<<<< HEAD line
                continue
            elif line.strip() == '=======':
                # Start skipping from here
                skip_until_end = True
                continue
            elif line.strip().startswith('>>>>>>>'):
                # Stop skipping
                skip_until_end = False
                continue
            elif not skip_until_end:
                # Keep this line
                new_lines.append(line)
        
        new_content = '\n'.join(new_lines)
        
        # Only write if content changed
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Find and resolve all conflicts"""
    repo_root = Path(__file__).parent
    resolved_count = 0
    
    # Find all Python files
    for py_file in repo_root.rglob('*.py'):
        if resolve_conflicts_in_file(py_file):
            resolved_count += 1
            print(f"Resolved: {py_file}")
    
    print(f"\nTotal files resolved: {resolved_count}")

if __name__ == '__main__':
    main()
