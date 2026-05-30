"""
Unit tests for the LLM file editor.

Run with: pytest tests/
"""

import pytest
import tempfile
import os
from pathlib import Path

from llm_file_editor.core.file_manager import FileManager, FileContent
from llm_file_editor.core.diff_engine import DiffEngine, EditCommand, EditType, DiffResult
from llm_file_editor.security.access_control import AccessControl, Role, Permission, AccessPolicy
from llm_file_editor.security.audit_logger import AuditLogger, ActionType


class TestFileManager:
    """Tests for FileManager class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
            
    @pytest.fixture
    def file_manager(self, temp_dir):
        """Create a FileManager instance."""
        return FileManager(root_dir=temp_dir)
        
    def test_create_and_view_file(self, file_manager, temp_dir):
        """Test creating and viewing a file."""
        # Create a file
        content = "Hello, World!\nThis is a test file."
        result = file_manager.write("test.txt", content)
        
        assert result.path.endswith("test.txt")
        assert result.content == content
        assert result.line_count == 2
        
        # View the file
        viewed = file_manager.view("test.txt")
        assert viewed.content == content
        
    def test_view_with_line_range(self, file_manager, temp_dir):
        """Test viewing file with line range."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        file_manager.write("test.txt", content)
        
        # View lines 1-3 (0-indexed)
        viewed = file_manager.view("test.txt", start_line=1, end_line=3)
        assert viewed.is_truncated
        assert viewed.start_line == 1
        assert viewed.end_line == 3
        assert "Line 2" in viewed.content
        assert "Line 3" in viewed.content
        assert "Line 1" not in viewed.content
        
    def test_str_replace(self, file_manager, temp_dir):
        """Test string replacement."""
        content = "Hello World"
        file_manager.write("test.txt", content)
        
        # Replace "World" with "Universe"
        result = file_manager.write("test.txt", content.replace("World", "Universe"))
        
        viewed = file_manager.view("test.txt")
        assert viewed.content == "Hello Universe"
        
    def test_sandbox_violation(self, temp_dir):
        """Test that sandbox prevents access outside root."""
        fm = FileManager(root_dir=temp_dir, sandbox_enabled=True)
        
        # Try to access file outside sandbox
        with pytest.raises(ValueError):
            fm.view("/etc/passwd")
            
    def test_file_not_found(self, file_manager):
        """Test handling of non-existent file."""
        with pytest.raises(FileNotFoundError):
            file_manager.view("nonexistent.txt")
            
    def test_delete_file(self, file_manager, temp_dir):
        """Test file deletion."""
        file_manager.write("test.txt", "content")
        assert file_manager.exists("test.txt")
        
        deleted = file_manager.delete("test.txt")
        assert deleted
        assert not file_manager.exists("test.txt")
        
    def test_list_directory(self, file_manager, temp_dir):
        """Test directory listing."""
        file_manager.write("file1.txt", "content1")
        file_manager.write("file2.txt", "content2")
        
        files = file_manager.list_directory(temp_dir)
        assert len(files) == 2
        assert "file1.txt" in files
        assert "file2.txt" in files


class TestDiffEngine:
    """Tests for DiffEngine class."""
    
    def test_str_replace_single(self):
        """Test single string replacement."""
        engine = DiffEngine()
        content = "Hello World"
        
        result = engine.str_replace(content, "World", "Universe")
        
        assert result.success
        assert result.new_content == "Hello Universe"
        assert result.changes_applied == 1
        
    def test_str_replace_not_found(self):
        """Test replacement when string not found."""
        engine = DiffEngine()
        content = "Hello World"
        
        result = engine.str_replace(content, "NotFound", "Something")
        
        assert not result.success
        assert result.error_message is not None
        
    def test_str_replace_all_occurrences(self):
        """Test replacing all occurrences."""
        engine = DiffEngine()
        content = "cat cat cat"
        
        result = engine.str_replace(content, "cat", "dog", occurrence=-1)
        
        assert result.success
        assert result.new_content == "dog dog dog"
        assert result.changes_applied == 3
        
    def test_insert_line(self):
        """Test line insertion."""
        engine = DiffEngine()
        content = "Line 1\nLine 2"
        
        result = engine.insert(content, "Inserted Line", 1)
        
        assert result.success
        assert "Inserted Line" in result.new_content
        lines = result.new_content.split('\n')
        assert lines[1] == "Inserted Line"
        
    def test_delete_range(self):
        """Test range deletion."""
        engine = DiffEngine()
        content = "Line 1\nLine 2\nLine 3\nLine 4"
        
        result = engine.delete_range(content, 1, 3)
        
        assert result.success
        assert "Line 2" not in result.new_content
        assert "Line 3" not in result.new_content
        assert "Line 1" in result.new_content
        assert "Line 4" in result.new_content
        
    def test_apply_command(self):
        """Test applying edit commands."""
        engine = DiffEngine()
        content = "Original"
        
        command = EditCommand(
            edit_type=EditType.STR_REPLACE,
            file_path="test.txt",
            old_str="Original",
            new_str="Modified"
        )
        
        result = engine.apply_command(command, content)
        
        assert result.success
        assert result.new_content == "Modified"


class TestAccessControl:
    """Tests for AccessControl class."""
    
    def test_default_policies(self):
        """Test default access policies."""
        ac = AccessControl()
        
        # Register admin user
        ac.register_user("admin1", {Role.ADMIN})
        
        # Admin should have full access
        assert ac.can_read("admin1", "any_file.txt")
        assert ac.can_write("admin1", "any_file.txt")
        assert ac.can_delete("admin1", "any_file.txt")
        
    def test_developer_permissions(self):
        """Test developer role permissions."""
        ac = AccessControl()
        ac.register_user("dev1", {Role.DEVELOPER})
        
        # Developer can read and write .py files
        assert ac.can_read("dev1", "code.py")
        assert ac.can_write("dev1", "code.py")
        
    def test_viewer_permissions(self):
        """Test viewer role permissions."""
        ac = AccessControl()
        ac.register_user("viewer1", {Role.VIEWER})
        
        # Viewer can only read
        assert ac.can_read("viewer1", "file.txt")
        assert not ac.can_write("viewer1", "file.txt")
        
    def test_sensitive_file_policy(self):
        """Test sensitive file policies."""
        ac = AccessControl()
        ac.create_sensitive_policy("*.secret")
        
        ac.register_user("user1", {Role.DEVELOPER})
        
        # Regular developer shouldn't access sensitive files
        assert not ac.can_write("user1", "config.secret")
        
    def test_access_validation(self):
        """Test access validation for edits."""
        ac = AccessControl()
        ac.register_user("dev1", {Role.DEVELOPER})
        
        result = ac.validate_user_access_for_edit("dev1", "code.py", "write")
        
        assert result["allowed"]
        assert not result["requires_approval"]


class TestAuditLogger:
    """Tests for AuditLogger class."""
    
    @pytest.fixture
    def temp_log_file(self):
        """Create a temporary log file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        yield path
        # Cleanup
        if os.path.exists(path):
            os.unlink(path)
            
    def test_log_actions(self, temp_log_file):
        """Test logging various actions."""
        logger = AuditLogger(storage_path=temp_log_file)
        
        # Log some actions
        logger.log_view("user1", "file1.txt")
        logger.log_modify("user1", "file1.txt", changes_summary="Changed line 5")
        logger.log_create("user1", "file2.txt")
        
        # Query logs
        entries = logger.query(user_id="user1")
        assert len(entries) == 3
        
    def test_file_history(self, temp_log_file):
        """Test retrieving file history."""
        logger = AuditLogger(storage_path=temp_log_file)
        
        logger.log_view("user1", "test.txt")
        logger.log_modify("user1", "test.txt")
        logger.log_view("user2", "test.txt")
        
        history = logger.get_file_history("test.txt")
        assert len(history) == 3
        
    def test_integrity_verification(self, temp_log_file):
        """Test audit log integrity verification."""
        logger = AuditLogger(storage_path=temp_log_file)
        
        logger.log_view("user1", "file.txt")
        logger.log_modify("user1", "file.txt")
        
        # Integrity should be valid
        assert logger.verify_integrity()
        
    def test_export_json(self, temp_log_file):
        """Test JSON export."""
        logger = AuditLogger(storage_path=temp_log_file)
        logger.log_view("user1", "file.txt")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            export_path = f.name
            
        try:
            logger.export_json(export_path)
            assert os.path.exists(export_path)
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
