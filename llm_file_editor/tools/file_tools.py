"""
File Edit Tools - LangChain compatible tools for file operations.

Provides LangChain Tool decorators for:
- Viewing files (with optional line ranges)
- String replacement edits
- Line insertion
- Range deletion
- File creation
- Directory listing

These tools can be directly used with LangChain agents and chains.
"""

from typing import Optional, List, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.callbacks.manager import CallbackManagerForToolRun

from ..core.file_manager import FileManager, FileContent
from ..core.diff_engine import DiffEngine, EditCommand, EditType, DiffResult


# Pydantic models for tool input schemas

class ViewFileInput(BaseModel):
    """Input schema for viewing a file."""
    file_path: str = Field(..., description="Path to the file to view")
    start_line: Optional[int] = Field(None, description="Starting line number (0-indexed, inclusive)")
    end_line: Optional[int] = Field(None, description="Ending line number (0-indexed, exclusive)")


class StrReplaceInput(BaseModel):
    """Input schema for string replacement."""
    file_path: str = Field(..., description="Path to the file to edit")
    old_str: str = Field(..., description="The exact string to replace")
    new_str: str = Field(..., description="The replacement string")
    occurrence: int = Field(0, description="Which occurrence to replace (0=first, -1=all)")


class InsertLineInput(BaseModel):
    """Input schema for inserting text at a line."""
    file_path: str = Field(..., description="Path to the file to edit")
    insert_line: int = Field(..., description="Line number to insert at (0-indexed)")
    text: str = Field(..., description="Text to insert")


class DeleteRangeInput(BaseModel):
    """Input schema for deleting a range of lines."""
    file_path: str = Field(..., description="Path to the file to edit")
    start_line: int = Field(..., description="Starting line number (0-indexed, inclusive)")
    end_line: int = Field(..., description="Ending line number (0-indexed, exclusive)")


class CreateFileInput(BaseModel):
    """Input schema for creating a new file."""
    file_path: str = Field(..., description="Path where to create the file")
    content: str = Field("", description="Content to write to the new file")


class ListDirectoryInput(BaseModel):
    """Input schema for listing directory contents."""
    dir_path: str = Field(..., description="Path to the directory to list")
    recursive: bool = Field(False, description="Whether to list recursively")


# LangChain Tool implementations

class ViewFileTool(BaseTool):
    """Tool for viewing file contents with optional line ranges."""
    
    name: str = "view_file"
    description: str = (
        "View the contents of a file. Can optionally specify line range. "
        "Use this to inspect file content before making edits. "
        "Parameters: file_path (required), start_line (optional), end_line (optional)"
    )
    args_schema: Type[BaseModel] = ViewFileInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    
    def _run(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the view operation."""
        try:
            result = self.file_manager.view(file_path, start_line, end_line)
            
            # Format output
            output = []
            output.append(f"File: {result.path}")
            output.append(f"Lines: {result.start_line}-{result.end_line} (of {result.line_count} total)")
            output.append(f"Size: {result.size_bytes} bytes")
            if result.is_truncated:
                output.append("[Content truncated to specified range]")
            output.append("-" * 60)
            output.append(result.content)
            
            return "\n".join(output)
            
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


class StrReplaceTool(BaseTool):
    """Tool for replacing exact strings in a file."""
    
    name: str = "str_replace"
    description: str = (
        "Replace an exact string in a file with a new string. "
        "The old_str must match exactly (including whitespace). "
        "Parameters: file_path (required), old_str (required), new_str (required), occurrence (optional, 0=first, -1=all)"
    )
    args_schema: Type[BaseModel] = StrReplaceInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    diff_engine: DiffEngine = Field(default_factory=DiffEngine)
    
    def _run(
        self,
        file_path: str,
        old_str: str,
        new_str: str,
        occurrence: int = 0,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the string replacement."""
        try:
            # Read current content
            file_content = self.file_manager.view(file_path)
            
            # Apply replacement
            result = self.diff_engine.str_replace(
                file_content.content,
                old_str,
                new_str,
                occurrence
            )
            
            if not result.success:
                return f"Error: {result.error_message}"
                
            # Write back
            self.file_manager.write(file_path, result.new_content)
            
            # Format success message with diff preview
            output = []
            output.append(f"✓ Successfully replaced {result.changes_applied} occurrence(s)")
            output.append(f"File: {file_path}")
            output.append("-" * 60)
            output.append("Changes:")
            output.extend(result.diff_lines[:20])  # Show first 20 lines of diff
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


class InsertLineTool(BaseTool):
    """Tool for inserting text at a specific line."""
    
    name: str = "insert_line"
    description: str = (
        "Insert text at a specific line number in a file. "
        "Line numbers are 0-indexed. "
        "Parameters: file_path (required), insert_line (required), text (required)"
    )
    args_schema: Type[BaseModel] = InsertLineInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    diff_engine: DiffEngine = Field(default_factory=DiffEngine)
    
    def _run(
        self,
        file_path: str,
        insert_line: int,
        text: str,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the insert operation."""
        try:
            # Read current content
            file_content = self.file_manager.view(file_path)
            
            # Apply insertion
            result = self.diff_engine.insert(
                file_content.content,
                text,
                insert_line
            )
            
            if not result.success:
                return f"Error: {result.error_message}"
                
            # Write back
            self.file_manager.write(file_path, result.new_content)
            
            # Format success message
            output = []
            output.append(f"✓ Successfully inserted text at line {insert_line}")
            output.append(f"File: {file_path}")
            output.append(f"Inserted {len(text)} characters")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


class DeleteRangeTool(BaseTool):
    """Tool for deleting a range of lines."""
    
    name: str = "delete_range"
    description: str = (
        "Delete a range of lines from a file. "
        "Line numbers are 0-indexed, range is [start_line, end_line). "
        "Parameters: file_path (required), start_line (required), end_line (required)"
    )
    args_schema: Type[BaseModel] = DeleteRangeInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    diff_engine: DiffEngine = Field(default_factory=DiffEngine)
    
    def _run(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the delete operation."""
        try:
            # Read current content
            file_content = self.file_manager.view(file_path)
            
            # Apply deletion
            result = self.diff_engine.delete_range(
                file_content.content,
                start_line,
                end_line
            )
            
            if not result.success:
                return f"Error: {result.error_message}"
                
            # Write back
            self.file_manager.write(file_path, result.new_content)
            
            # Format success message
            output = []
            output.append(f"✓ Successfully deleted {result.changes_applied} line(s)")
            output.append(f"File: {file_path}")
            output.append(f"Deleted lines {start_line}-{end_line}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


class CreateFileTool(BaseTool):
    """Tool for creating new files."""
    
    name: str = "create_file"
    description: str = (
        "Create a new file with the given content. "
        "Will create parent directories if they don't exist. "
        "Parameters: file_path (required), content (optional, defaults to empty)"
    )
    args_schema: Type[BaseModel] = CreateFileInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    
    def _run(
        self,
        file_path: str,
        content: str = "",
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the create operation."""
        try:
            # Check if file already exists
            if self.file_manager.exists(file_path):
                return f"Error: File already exists: {file_path}"
                
            # Create the file
            self.file_manager.write(file_path, content)
            
            # Format success message
            output = []
            output.append(f"✓ Successfully created file")
            output.append(f"Path: {file_path}")
            output.append(f"Size: {len(content)} bytes")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


class ListDirectoryTool(BaseTool):
    """Tool for listing directory contents."""
    
    name: str = "list_directory"
    description: str = (
        "List files in a directory. "
        "Parameters: dir_path (required), recursive (optional, default False)"
    )
    args_schema: Type[BaseModel] = ListDirectoryInput
    
    file_manager: FileManager = Field(default_factory=FileManager)
    
    def _run(
        self,
        dir_path: str,
        recursive: bool = False,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the list operation."""
        try:
            files = self.file_manager.list_directory(dir_path, recursive)
            
            if not files:
                return f"Directory is empty: {dir_path}"
                
            output = []
            output.append(f"Directory: {dir_path}")
            output.append(f"Files found: {len(files)}")
            output.append("-" * 60)
            for f in files:
                output.append(f"  {f}")
                
            return "\n".join(output)
            
        except Exception as e:
            return f"Error: {str(e)}"
            
    async def _arun(self, *args, **kwargs):
        """Async implementation not provided."""
        raise NotImplementedError("Async not implemented for this tool")


# Factory function to create all tools

class FileEditTools:
    """
    Factory and container for all file editing tools.
    
    Provides easy access to all LangChain-compatible file tools
    with shared FileManager and DiffEngine instances.
    """
    
    def __init__(
        self,
        root_dir: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
        max_file_size: int = 1024 * 1024,
        sandbox_enabled: bool = True
    ):
        """
        Initialize file edit tools.
        
        Args:
            root_dir: Root directory for file operations
            allowed_extensions: Allowed file extensions
            max_file_size: Maximum file size in bytes
            sandbox_enabled: Enable path sandboxing
        """
        self.file_manager = FileManager(
            root_dir=root_dir,
            allowed_extensions=allowed_extensions,
            max_file_size=max_file_size,
            sandbox_enabled=sandbox_enabled
        )
        self.diff_engine = DiffEngine()
        
    def get_tools(self) -> List[BaseTool]:
        """Get all file editing tools as a list."""
        return [
            ViewFileTool(file_manager=self.file_manager),
            StrReplaceTool(file_manager=self.file_manager, diff_engine=self.diff_engine),
            InsertLineTool(file_manager=self.file_manager, diff_engine=self.diff_engine),
            DeleteRangeTool(file_manager=self.file_manager, diff_engine=self.diff_engine),
            CreateFileTool(file_manager=self.file_manager),
            ListDirectoryTool(file_manager=self.file_manager),
        ]
        
    def get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """Get a specific tool by name."""
        for tool in self.get_tools():
            if tool.name == name:
                return tool
        return None
