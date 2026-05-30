"""
Diff Engine - Generate and apply precise diff patches.

Provides functionality for:
- String replacement with exact matching
- Line insertion at specific positions
- Range deletion
- Unified diff generation and parsing
- Safe patch application with validation
"""

import difflib
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum


class EditType(Enum):
    """Types of edit operations."""
    STR_REPLACE = "str_replace"
    INSERT = "insert"
    DELETE = "delete"
    CREATE = "create"


@dataclass
class EditCommand:
    """Represents a single edit command."""
    edit_type: EditType
    file_path: str
    old_str: Optional[str] = None
    new_str: Optional[str] = None
    insert_line: Optional[int] = None  # For insert operations
    start_line: Optional[int] = None   # For delete range
    end_line: Optional[int] = None     # For delete range
    content: Optional[str] = None      # For create operations


@dataclass
class DiffResult:
    """Result of applying a diff operation."""
    success: bool
    original_content: str
    new_content: str
    changes_applied: int
    error_message: Optional[str] = None
    diff_lines: List[str] = None
    
    def __post_init__(self):
        if self.diff_lines is None:
            self.diff_lines = []


class DiffEngine:
    """
    Engine for generating and applying precise diff patches.
    
    Supports multiple edit strategies:
    - Exact string replacement
    - Line-based insertion
    - Range deletion
    - Multi-match handling with disambiguation
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize the diff engine.
        
        Args:
            strict_mode: If True, require exact matches for replacements
        """
        self.strict_mode = strict_mode
        
    def str_replace(
        self,
        content: str,
        old_str: str,
        new_str: str,
        occurrence: int = 0
    ) -> DiffResult:
        """
        Replace a string in content with new string.
        
        Args:
            content: Original file content
            old_str: String to replace
            new_str: Replacement string
            occurrence: Which occurrence to replace (0 = first, -1 = all)
            
        Returns:
            DiffResult with success status and changes
        """
        if not old_str:
            return DiffResult(
                success=False,
                original_content=content,
                new_content=content,
                changes_applied=0,
                error_message="old_str cannot be empty"
            )
            
        # Find all occurrences
        occurrences = []
        start = 0
        while True:
            pos = content.find(old_str, start)
            if pos == -1:
                break
            occurrences.append(pos)
            start = pos + 1
            
        if not occurrences:
            return DiffResult(
                success=False,
                original_content=content,
                new_content=content,
                changes_applied=0,
                error_message=f"String not found: {repr(old_str[:50])}..."
            )
            
        # Determine which occurrences to replace
        if occurrence == -1:
            # Replace all
            new_content = content.replace(old_str, new_str)
            changes = len(occurrences)
        else:
            # Replace specific occurrence
            if occurrence >= len(occurrences):
                return DiffResult(
                    success=False,
                    original_content=content,
                    new_content=content,
                    changes_applied=0,
                    error_message=f"Only {len(occurrences)} occurrences found, requested {occurrence}"
                )
                
            pos = occurrences[occurrence]
            new_content = content[:pos] + new_str + content[pos + len(old_str):]
            changes = 1
            
        # Generate diff
        diff_lines = self._generate_diff(content, new_content)
        
        return DiffResult(
            success=True,
            original_content=content,
            new_content=new_content,
            changes_applied=changes,
            diff_lines=diff_lines
        )
        
    def insert(
        self,
        content: str,
        text: str,
        line_number: int
    ) -> DiffResult:
        """
        Insert text at a specific line number.
        
        Args:
            content: Original file content
            text: Text to insert
            line_number: Line number to insert at (0-indexed)
            
        Returns:
            DiffResult with success status and changes
        """
        lines = content.splitlines(keepends=True)
        
        # Handle edge cases
        if line_number < 0:
            line_number = 0
        if line_number > len(lines):
            line_number = len(lines)
            
        # Ensure text ends with newline if inserting in middle
        if text and not text.endswith('\n') and line_number < len(lines):
            text += '\n'
            
        # Insert the text
        lines.insert(line_number, text)
        new_content = ''.join(lines)
        
        # Handle case where original didn't end with newline
        if content and not content.endswith('\n') and line_number == len(lines) - 1:
            new_content = new_content.rstrip('\n')
            
        diff_lines = self._generate_diff(content, new_content)
        
        return DiffResult(
            success=True,
            original_content=content,
            new_content=new_content,
            changes_applied=1,
            diff_lines=diff_lines
        )
        
    def delete_range(
        self,
        content: str,
        start_line: int,
        end_line: int
    ) -> DiffResult:
        """
        Delete a range of lines from content.
        
        Args:
            content: Original file content
            start_line: Starting line number (0-indexed, inclusive)
            end_line: Ending line number (0-indexed, exclusive)
            
        Returns:
            DiffResult with success status and changes
        """
        lines = content.splitlines(keepends=True)
        
        # Validate range
        if start_line < 0:
            start_line = 0
        if end_line > len(lines):
            end_line = len(lines)
        if start_line >= end_line:
            return DiffResult(
                success=False,
                original_content=content,
                new_content=content,
                changes_applied=0,
                error_message=f"Invalid line range: {start_line}-{end_line}"
            )
            
        deleted_lines = lines[start_line:end_line]
        deleted_count = len(deleted_lines)
        
        # Delete the lines
        new_lines = lines[:start_line] + lines[end_line:]
        new_content = ''.join(new_lines)
        
        diff_lines = self._generate_diff(content, new_content)
        
        return DiffResult(
            success=True,
            original_content=content,
            new_content=new_content,
            changes_applied=deleted_count,
            diff_lines=diff_lines
        )
        
    def create(self, content: str = "") -> DiffResult:
        """
        Create new file content.
        
        Args:
            content: Content for the new file
            
        Returns:
            DiffResult representing creation
        """
        return DiffResult(
            success=True,
            original_content="",
            new_content=content,
            changes_applied=1,
            diff_lines=self._generate_diff("", content)
        )
        
    def _generate_diff(self, old_content: str, new_content: str) -> List[str]:
        """Generate unified diff between two strings."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile='original',
            tofile='modified',
            n=3  # Context lines
        )
        
        return list(diff)
        
    def generate_patch(self, old_content: str, new_content: str, 
                      old_path: str = 'a/file', new_path: str = 'b/file') -> str:
        """
        Generate a standard unified diff patch.
        
        Args:
            old_content: Original content
            new_content: Modified content
            old_path: Path label for original file
            new_path: Path label for modified file
            
        Returns:
            Unified diff patch as string
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path,
            tofile=new_path,
            n=3
        )
        
        return ''.join(diff)
        
    def validate_edit_command(self, command: EditCommand, content: str) -> Tuple[bool, str]:
        """
        Validate an edit command before applying.
        
        Args:
            command: EditCommand to validate
            content: Current file content
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if command.edit_type == EditType.STR_REPLACE:
            if not command.old_str:
                return False, "old_str is required for str_replace"
            if command.new_str is None:
                return False, "new_str is required for str_replace"
            if command.old_str not in content:
                return False, f"old_str not found in content"
                
        elif command.edit_type == EditType.INSERT:
            if command.insert_line is None:
                return False, "insert_line is required for insert"
            if command.new_str is None:
                return False, "new_str (text) is required for insert"
                
        elif command.edit_type == EditType.DELETE:
            if command.start_line is None or command.end_line is None:
                return False, "start_line and end_line required for delete"
                
        elif command.edit_type == EditType.CREATE:
            if command.content is None:
                return False, "content is required for create"
                
        return True, ""
        
    def apply_command(self, command: EditCommand, content: str) -> DiffResult:
        """
        Apply an edit command to content.
        
        Args:
            command: EditCommand to apply
            content: Current file content
            
        Returns:
            DiffResult with the outcome
        """
        # Validate first
        is_valid, error = self.validate_edit_command(command, content)
        if not is_valid:
            return DiffResult(
                success=False,
                original_content=content,
                new_content=content,
                changes_applied=0,
                error_message=error
            )
            
        # Apply based on type
        if command.edit_type == EditType.STR_REPLACE:
            return self.str_replace(content, command.old_str, command.new_str)
        elif command.edit_type == EditType.INSERT:
            return self.insert(content, command.new_str, command.insert_line)
        elif command.edit_type == EditType.DELETE:
            return self.delete_range(content, command.start_line, command.end_line)
        elif command.edit_type == EditType.CREATE:
            return self.create(command.content)
        else:
            return DiffResult(
                success=False,
                original_content=content,
                new_content=content,
                changes_applied=0,
                error_message=f"Unknown edit type: {command.edit_type}"
            )
