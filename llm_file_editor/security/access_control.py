"""
Access Control - Role-based access control for file operations.

Provides:
- RBAC (Role-Based Access Control) for files and directories
- Permission checking for read/write/delete operations
- Integration with authentication systems
- Policy enforcement for sensitive files
"""

from typing import Dict, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
import re


class Permission(Enum):
    """File operation permissions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


class Role(Enum):
    """Predefined roles."""
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"
    RESTRICTED = "restricted"


@dataclass
class AccessPolicy:
    """Defines access policy for a path pattern."""
    path_pattern: str  # Can be glob pattern or exact path
    allowed_roles: Set[Role]
    allowed_permissions: Set[Permission]
    denied_roles: Set[Role] = field(default_factory=set)
    requires_approval: bool = False
    is_sensitive: bool = False
    
    def matches_path(self, path: str) -> bool:
        """Check if this policy applies to the given path."""
        # Convert glob pattern to regex
        pattern = self.path_pattern.replace('*', '.*').replace('?', '.')
        regex = f"^{pattern}$"
        return bool(re.match(regex, path))


@dataclass
class UserContext:
    """User context for access control."""
    user_id: str
    roles: Set[Role]
    groups: Set[str] = field(default_factory=set)
    metadata: Dict[str, str] = field(default_factory=dict)


class AccessControl:
    """
    Role-based access control system for file operations.
    
    Features:
    - Path-based policies with glob support
    - Role-based permissions
    - Explicit deny rules
    - Sensitive file marking
    - Approval workflow hooks
    """
    
    def __init__(self):
        """Initialize access control with default policies."""
        self.policies: List[AccessPolicy] = []
        self.user_contexts: Dict[str, UserContext] = {}
        
        # Add default policies
        self._setup_default_policies()
        
    def _setup_default_policies(self):
        """Set up default access policies."""
        # Admin can do everything
        self.add_policy(AccessPolicy(
            path_pattern="*",
            allowed_roles={Role.ADMIN},
            allowed_permissions={Permission.READ, Permission.WRITE, Permission.DELETE, Permission.EXECUTE}
        ))
        
        # Developers can read and write most files
        self.add_policy(AccessPolicy(
            path_pattern="*.py",
            allowed_roles={Role.DEVELOPER},
            allowed_permissions={Permission.READ, Permission.WRITE}
        ))
        
        # Viewers can only read
        self.add_policy(AccessPolicy(
            path_pattern="*",
            allowed_roles={Role.VIEWER},
            allowed_permissions={Permission.READ}
        ))
        
    def add_policy(self, policy: AccessPolicy):
        """Add an access policy."""
        self.policies.append(policy)
        
    def remove_policy(self, path_pattern: str) -> bool:
        """Remove a policy by path pattern."""
        for i, policy in enumerate(self.policies):
            if policy.path_pattern == path_pattern:
                self.policies.pop(i)
                return True
        return False
        
    def register_user(self, user_id: str, roles: Set[Role], groups: Optional[Set[str]] = None):
        """Register a user with roles and groups."""
        self.user_contexts[user_id] = UserContext(
            user_id=user_id,
            roles=roles,
            groups=groups or set()
        )
        
    def get_user_context(self, user_id: str) -> Optional[UserContext]:
        """Get user context by user ID."""
        return self.user_contexts.get(user_id)
        
    def check_permission(
        self,
        user_id: str,
        file_path: str,
        permission: Permission
    ) -> bool:
        """
        Check if a user has permission to perform an action on a file.
        
        Args:
            user_id: User identifier
            file_path: Path to the file
            permission: Permission to check
            
        Returns:
            True if permission is granted, False otherwise
        """
        user_context = self.user_contexts.get(user_id)
        if not user_context:
            # No user context, deny by default
            return False
            
        # Normalize path
        path_str = str(Path(file_path))
        
        # Find applicable policies (most specific first)
        applicable_policies = []
        for policy in self.policies:
            if policy.matches_path(path_str):
                applicable_policies.append(policy)
                
        # Sort by specificity (longer pattern = more specific)
        applicable_policies.sort(
            key=lambda p: len(p.path_pattern),
            reverse=True
        )
        
        # Check policies in order
        for policy in applicable_policies:
            # Check explicit denies first
            if user_context.roles & policy.denied_roles:
                return False
                
            # Check if user has required role and permission
            user_roles = user_context.roles
            if user_roles & policy.allowed_roles:
                if permission in policy.allowed_permissions:
                    return True
                    
        # No policy matched, deny by default
        return False
        
    def can_read(self, user_id: str, file_path: str) -> bool:
        """Check if user can read a file."""
        return self.check_permission(user_id, file_path, Permission.READ)
        
    def can_write(self, user_id: str, file_path: str) -> bool:
        """Check if user can write to a file."""
        return self.check_permission(user_id, file_path, Permission.WRITE)
        
    def can_delete(self, user_id: str, file_path: str) -> bool:
        """Check if user can delete a file."""
        return self.check_permission(user_id, file_path, Permission.DELETE)
        
    def requires_approval(self, file_path: str) -> bool:
        """Check if operations on a file require approval."""
        path_str = str(Path(file_path))
        for policy in self.policies:
            if policy.matches_path(path_str):
                if policy.requires_approval:
                    return True
        return False
        
    def is_sensitive(self, file_path: str) -> bool:
        """Check if a file is marked as sensitive."""
        path_str = str(Path(file_path))
        for policy in self.policies:
            if policy.matches_path(path_str):
                if policy.is_sensitive:
                    return True
        return False
        
    def get_sensitive_patterns(self) -> List[str]:
        """Get list of patterns that mark files as sensitive."""
        return [p.path_pattern for p in self.policies if p.is_sensitive]
        
    def create_sensitive_policy(
        self,
        path_pattern: str,
        allowed_roles: Optional[Set[Role]] = None
    ):
        """Create a policy for sensitive files."""
        self.add_policy(AccessPolicy(
            path_pattern=path_pattern,
            allowed_roles=allowed_roles or {Role.ADMIN},
            allowed_permissions={Permission.READ},
            is_sensitive=True,
            requires_approval=True
        ))
        
    def validate_user_access_for_edit(
        self,
        user_id: str,
        file_path: str,
        edit_type: str
    ) -> Dict[str, any]:
        """
        Validate user access for an edit operation.
        
        Args:
            user_id: User identifier
            file_path: Path to file
            edit_type: Type of edit (view, write, delete, create)
            
        Returns:
            Dict with validation result and details
        """
        result = {
            "allowed": False,
            "user_id": user_id,
            "file_path": file_path,
            "edit_type": edit_type,
            "reason": "",
            "requires_approval": False,
            "is_sensitive": False
        }
        
        # Map edit type to permission
        permission_map = {
            "view": Permission.READ,
            "read": Permission.READ,
            "write": Permission.WRITE,
            "edit": Permission.WRITE,
            "create": Permission.WRITE,
            "delete": Permission.DELETE
        }
        
        permission = permission_map.get(edit_type.lower())
        if not permission:
            result["reason"] = f"Unknown edit type: {edit_type}"
            return result
            
        # Check permission
        if not self.check_permission(user_id, file_path, permission):
            result["reason"] = f"User lacks {permission.value} permission"
            return result
            
        # Check special conditions
        result["is_sensitive"] = self.is_sensitive(file_path)
        result["requires_approval"] = self.requires_approval(file_path)
        
        # All checks passed
        result["allowed"] = True
        return result
