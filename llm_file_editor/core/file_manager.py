"""
File Manager - Core file operations with safety checks.

Handles viewing, reading, and writing files with support for:
- Partial file viewing (line ranges)
- Context chunking for large files
- Safety validation before writes
- Version control integration points
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import hashlib


@dataclass
class FileContent:
    """Represents file content with metadata."""
    path: str
    content: str
    line_count: int
    size_bytes: int
    hash: str
    is_truncated: bool = False
    start_line: int = 0
    end_line: int = 0


class FileManager:
    """
    Safe file manager for LLM-based editing operations.
    
    Provides controlled access to file system operations with:
    - Path validation and sandboxing
    - Line-range based viewing for context management
    - Content hashing for change detection
    - Atomic write operations
    """
    
    DEFAULT_MAX_FILE_SIZE = 1024 * 1024  # 1MB default max file size
    DEFAULT_CONTEXT_LINES = 100  # Default lines to show in context
    
    def __init__(
        self,
        root_dir: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        sandbox_enabled: bool = True
    ):
        """
        Initialize the file manager.
        
        Args:
            root_dir: Root directory for file operations (sandbox base)
            allowed_extensions: List of allowed file extensions (e.g., ['.py', '.txt'])
            max_file_size: Maximum file size in bytes that can be read
            sandbox_enabled: Whether to enable path sandboxing
        """
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd()
        self.allowed_extensions = allowed_extensions
        self.max_file_size = max_file_size
        self.sandbox_enabled = sandbox_enabled
        
    def _validate_path(self, file_path: str) -> Path:
        """
        Validate and resolve file path within sandbox.
        
        Args:
            file_path: Path to validate
            
        Returns:
            Resolved Path object
            
        Raises:
            ValueError: If path is outside sandbox or has disallowed extension
        """
        path = Path(file_path)
        
        # Resolve to absolute path
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (self.root_dir / path).resolve()
            
        # Check sandbox constraint
        if self.sandbox_enabled:
            try:
                resolved.relative_to(self.root_dir)
            except ValueError:
                raise ValueError(
                    f"Path '{file_path}' is outside sandbox root '{self.root_dir}'"
                )
                
        # Check extension whitelist
        if self.allowed_extensions:
            ext = resolved.suffix.lower()
            if ext not in [e.lower() for e in self.allowed_extensions]:
                raise ValueError(
                    f"File extension '{ext}' not in allowed list: {self.allowed_extensions}"
                )
                
        return resolved
        
    def view(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> FileContent:
        """
        View file content, optionally with line range.
        
        Args:
            file_path: Path to the file
            start_line: Starting line number (0-indexed), inclusive
            end_line: Ending line number (0-indexed), exclusive
            
        Returns:
            FileContent object with file metadata and content
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path validation fails
        """
        resolved_path = self._validate_path(file_path)
        
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
            
        # Check file size
        file_size = resolved_path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds maximum allowed ({self.max_file_size} bytes)"
            )
            
        # Read file content
        try:
            content = resolved_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            raise ValueError(f"File is not valid UTF-8 text: {file_path}")
            
        lines = content.splitlines()
        total_lines = len(lines)
        
        # Apply line range if specified
        is_truncated = False
        actual_start = 0
        actual_end = total_lines
        
        if start_line is not None or end_line is not None:
            is_truncated = True
            actual_start = max(0, start_line if start_line is not None else 0)
            actual_end = min(total_lines, end_line if end_line is not None else total_lines)
            lines = lines[actual_start:actual_end]
            content = '\n'.join(lines)
            
        return FileContent(
            path=str(resolved_path),
            content=content,
            line_count=len(lines),
            size_bytes=len(content.encode('utf-8')),
            hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
            is_truncated=is_truncated,
            start_line=actual_start,
            end_line=actual_end
        )
        
    def write(self, file_path: str, content: str, create_parents: bool = True) -> FileContent:
        """
        Write content to file atomically.
        
        Args:
            file_path: Path to the file
            content: Content to write
            create_parents: Whether to create parent directories if they don't exist
            
        Returns:
            FileContent object with updated metadata
            
        Raises:
            ValueError: If path validation fails
        """
        resolved_path = self._validate_path(file_path)
        
        # Create parent directories if needed
        if create_parents:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
        # Write atomically using temp file
        temp_path = resolved_path.with_suffix(resolved_path.suffix + '.tmp')
        try:
            temp_path.write_text(content, encoding='utf-8')
            temp_path.replace(resolved_path)
        except Exception as e:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise e
            
        return self.view(str(resolved_path))
        
    def exists(self, file_path: str) -> bool:
        """Check if file exists within sandbox."""
        try:
            resolved = self._validate_path(file_path)
            return resolved.exists() and resolved.is_file()
        except ValueError:
            return False
            
    def delete(self, file_path: str) -> bool:
        """
        Delete a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if deleted, False if file didn't exist
            
        Raises:
            ValueError: If path validation fails
        """
        resolved_path = self._validate_path(file_path)
        
        if not resolved_path.exists():
            return False
            
        resolved_path.unlink()
        return True
        
    def list_directory(self, dir_path: str, recursive: bool = False) -> List[str]:
        """
        List files in a directory.
        
        Args:
            dir_path: Path to the directory
            recursive: Whether to list recursively
            
        Returns:
            List of relative file paths
        """
        resolved_path = self._validate_path(dir_path)
        
        if not resolved_path.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")
            
        if not resolved_path.is_dir():
            raise ValueError(f"Path is not a directory: {dir_path}")
            
        files = []
        if recursive:
            for item in resolved_path.rglob('*'):
                if item.is_file():
                    files.append(str(item.relative_to(self.root_dir)))
        else:
            for item in resolved_path.iterdir():
                if item.is_file():
                    files.append(str(item.relative_to(self.root_dir)))
                    
        return sorted(files)
        
    def get_relative_path(self, file_path: str) -> str:
        """Get path relative to root directory."""
        resolved = self._validate_path(file_path)
        return str(resolved.relative_to(self.root_dir))
