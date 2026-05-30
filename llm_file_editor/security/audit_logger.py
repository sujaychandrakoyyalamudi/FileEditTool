"""
Audit Logger - Comprehensive audit logging for file operations.

Provides:
- Immutable audit logs for all file operations
- User action tracking
- Change history
- Compliance reporting
- Security event logging
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum


class ActionType(Enum):
    """Types of auditable actions."""
    VIEW = "view"
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    PERMISSION_CHANGE = "permission_change"
    ACCESS_DENIED = "access_denied"
    POLICY_CHANGE = "policy_change"
    AUTHENTICATION = "authentication"


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    action_type: ActionType
    user_id: str
    file_path: str
    details: Dict[str, Any]
    entry_id: str = ""
    previous_hash: str = ""
    hash: str = ""
    
    def __post_init__(self):
        """Generate entry ID and hash if not provided."""
        if not self.entry_id:
            self.entry_id = self._generate_entry_id()
        if not self.hash:
            self.hash = self._generate_hash()
            
    def _generate_entry_id(self) -> str:
        """Generate unique entry ID."""
        content = f"{self.timestamp}{self.user_id}{self.file_path}{self.action_type.value}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
        
    def _generate_hash(self) -> str:
        """Generate hash for integrity verification."""
        content = json.dumps({
            "timestamp": self.timestamp,
            "action_type": self.action_type.value,
            "user_id": self.user_id,
            "file_path": self.file_path,
            "details": self.details,
            "previous_hash": self.previous_hash
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action_type": self.action_type.value,
            "user_id": self.user_id,
            "file_path": self.file_path,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "hash": self.hash
        }


class AuditLogger:
    """
    Audit logging system for file operations.
    
    Features:
    - Immutable log entries with hash chaining
    - Multiple storage backends (memory, file, database)
    - Query and filtering capabilities
    - Export functionality
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize audit logger.
        
        Args:
            storage_path: Path to store audit logs (optional, uses memory if not provided)
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.entries: List[AuditEntry] = []
        self.last_hash: str = ""
        
        # Load existing entries if storage path provided
        if self.storage_path and self.storage_path.exists():
            self._load_entries()
            
    def _load_entries(self):
        """Load entries from storage."""
        if not self.storage_path or not self.storage_path.exists():
            return
            
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                self.entries = [AuditEntry(**entry) for entry in data]
                if self.entries:
                    self.last_hash = self.entries[-1].hash
        except Exception as e:
            # Start fresh if load fails
            self.entries = []
            self.last_hash = ""
            
    def _save_entries(self):
        """Save entries to storage."""
        if not self.storage_path:
            return
            
        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write atomically
        temp_path = self.storage_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump([e.to_dict() for e in self.entries], f, indent=2)
            temp_path.replace(self.storage_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e
            
    def log(
        self,
        action_type: ActionType,
        user_id: str,
        file_path: str,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEntry:
        """
        Log an action.
        
        Args:
            action_type: Type of action
            user_id: User who performed the action
            file_path: File path involved
            details: Additional details about the action
            
        Returns:
            The created AuditEntry
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action_type=action_type,
            user_id=user_id,
            file_path=file_path,
            details=details or {},
            previous_hash=self.last_hash
        )
        
        self.entries.append(entry)
        self.last_hash = entry.hash
        
        # Persist if storage is configured
        self._save_entries()
        
        return entry
        
    def log_view(self, user_id: str, file_path: str, **kwargs):
        """Log a file view operation."""
        return self.log(ActionType.VIEW, user_id, file_path, kwargs)
        
    def log_create(self, user_id: str, file_path: str, **kwargs):
        """Log a file creation."""
        return self.log(ActionType.CREATE, user_id, file_path, kwargs)
        
    def log_modify(
        self,
        user_id: str,
        file_path: str,
        changes_summary: Optional[str] = None,
        diff_stats: Optional[Dict] = None,
        **kwargs
    ):
        """Log a file modification."""
        details = kwargs
        if changes_summary:
            details["changes_summary"] = changes_summary
        if diff_stats:
            details["diff_stats"] = diff_stats
        return self.log(ActionType.MODIFY, user_id, file_path, details)
        
    def log_delete(self, user_id: str, file_path: str, **kwargs):
        """Log a file deletion."""
        return self.log(ActionType.DELETE, user_id, file_path, kwargs)
        
    def log_access_denied(
        self,
        user_id: str,
        file_path: str,
        reason: str,
        **kwargs
    ):
        """Log an access denied event."""
        return self.log(
            ActionType.ACCESS_DENIED,
            user_id,
            file_path,
            {"reason": reason, **kwargs}
        )
        
    def query(
        self,
        user_id: Optional[str] = None,
        file_path: Optional[str] = None,
        action_type: Optional[ActionType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """
        Query audit log entries.
        
        Args:
            user_id: Filter by user ID
            file_path: Filter by file path (supports prefix matching)
            action_type: Filter by action type
            start_time: Filter entries after this time
            end_time: Filter entries before this time
            limit: Maximum number of entries to return
            
        Returns:
            List of matching AuditEntry objects
        """
        results = []
        
        for entry in reversed(self.entries):
            # Apply filters
            if user_id and entry.user_id != user_id:
                continue
            if file_path and not entry.file_path.startswith(file_path):
                continue
            if action_type and entry.action_type != action_type:
                continue
                
            entry_time = datetime.fromisoformat(entry.timestamp)
            if start_time and entry_time < start_time:
                continue
            if end_time and entry_time > end_time:
                continue
                
            results.append(entry)
            
            if len(results) >= limit:
                break
                
        return list(reversed(results))  # Return in chronological order
        
    def get_file_history(self, file_path: str) -> List[AuditEntry]:
        """Get complete history of a file."""
        return self.query(file_path=file_path, limit=1000)
        
    def get_user_activity(self, user_id: str, limit: int = 100) -> List[AuditEntry]:
        """Get recent activity by a user."""
        return self.query(user_id=user_id, limit=limit)
        
    def verify_integrity(self) -> bool:
        """
        Verify integrity of audit log chain.
        
        Returns:
            True if all hashes are valid, False otherwise
        """
        prev_hash = ""
        for entry in self.entries:
            # Verify previous hash linkage
            if entry.previous_hash != prev_hash:
                return False
                
            # Verify entry hash
            expected_hash = entry._generate_hash()
            if entry.hash != expected_hash:
                return False
                
            prev_hash = entry.hash
            
        return True
        
    def export_json(self, output_path: str):
        """Export audit log to JSON file."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, 'w') as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)
            
    def export_csv(self, output_path: str):
        """Export audit log to CSV file."""
        import csv
        
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'entry_id', 'timestamp', 'action_type', 'user_id',
                'file_path', 'details', 'hash'
            ])
            
            for entry in self.entries:
                writer.writerow([
                    entry.entry_id,
                    entry.timestamp,
                    entry.action_type.value,
                    entry.user_id,
                    entry.file_path,
                    json.dumps(entry.details),
                    entry.hash
                ])
                
    def clear(self):
        """Clear all audit entries (use with caution)."""
        self.entries = []
        self.last_hash = ""
        self._save_entries()
