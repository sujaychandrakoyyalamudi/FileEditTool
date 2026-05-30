"""
LLM-Based File Editing Tool with LangChain Integration

A comprehensive file editing tool that leverages LLMs to generate precise diff patches
which are then applied by a safe execution layer. Supports viewing, editing, versioning,
security controls, and integrates seamlessly with LangChain.
"""

__version__ = "0.1.0"
__author__ = "LLM File Editor Team"

from .core.file_manager import FileManager
from .core.diff_engine import DiffEngine
from .tools.file_tools import FileEditTools
from .security.access_control import AccessControl
from .security.audit_logger import AuditLogger
from .integrations.langchain_integration import LangChainIntegration

__all__ = [
    "FileManager",
    "DiffEngine",
    "FileEditTools",
    "AccessControl",
    "AuditLogger",
    "LangChainIntegration",
]
