"""Utility functions for the LLM file editor."""

from typing import List, Optional


def format_diff_for_display(diff_lines: List[str], max_lines: int = 50) -> str:
    """Format diff lines for display."""
    if not diff_lines:
        return "No changes"
    
    output = []
    for i, line in enumerate(diff_lines[:max_lines]):
        if line.startswith('+'):
            output.append(f"\033[92m{line}\033[0m")  # Green for additions
        elif line.startswith('-'):
            output.append(f"\033[91m{line}\033[0m")  # Red for deletions
        elif line.startswith('@'):
            output.append(f"\033[94m{line}\033[0m")  # Blue for hunk headers
        else:
            output.append(line)
            
    if len(diff_lines) > max_lines:
        output.append(f"... and {len(diff_lines) - max_lines} more lines")
        
    return "\n".join(output)
