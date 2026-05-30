"""
LangChain Integration - Seamless integration with LangChain agents and chains.

Provides:
- Pre-configured tool sets for LangChain agents
- Agent executor wrappers
- Prompt templates for file editing tasks
- Example agent configurations
- Memory management for file editing sessions
"""

from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_core.callbacks.base import BaseCallbackHandler

from ..tools.file_tools import FileEditTools, ViewFileTool, StrReplaceTool
from ..security.access_control import AccessControl, Role, UserContext
from ..security.audit_logger import AuditLogger, ActionType


class FileEditingCallback(BaseCallbackHandler):
    """Callback handler for tracking file editing operations."""
    
    def __init__(self, audit_logger: Optional[AuditLogger] = None, user_id: str = "anonymous"):
        self.audit_logger = audit_logger
        self.user_id = user_id
        self.current_file: Optional[str] = None
        
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs):
        """Called when a tool starts executing."""
        tool_name = serialized.get("name", "unknown")
        if tool_name in ["view_file", "str_replace", "insert_line", "delete_range", "create_file"]:
            # Extract file path from input
            try:
                import json
                input_data = json.loads(input_str)
                self.current_file = input_data.get("file_path", "unknown")
            except:
                pass
                
    def on_tool_end(self, output: str, **kwargs):
        """Called when a tool finishes executing."""
        if self.audit_logger and self.current_file:
            # Log the operation
            tool_name = kwargs.get("name", "unknown")
            if tool_name == "view_file":
                self.audit_logger.log_view(self.user_id, self.current_file)
            elif tool_name in ["str_replace", "insert_line"]:
                self.audit_logger.log_modify(
                    self.user_id,
                    self.current_file,
                    changes_summary=output[:200]  # First 200 chars
                )
            elif tool_name == "create_file":
                self.audit_logger.log_create(self.user_id, self.current_file)
            elif tool_name == "delete_range":
                self.audit_logger.log_delete(self.user_id, self.current_file)


class LangChainIntegration:
    """
    Integration layer for LangChain agents with file editing capabilities.
    
    Provides easy setup for:
    - Agent executors with file tools
    - Conversation memory for editing sessions
    - Security and audit logging
    - Custom prompt templates
    """
    
    DEFAULT_SYSTEM_PROMPT = """You are an AI assistant with the ability to edit files. 
You have access to the following tools:
- view_file: View the contents of a file (optionally with line ranges)
- str_replace: Replace exact strings in a file
- insert_line: Insert text at a specific line number
- delete_range: Delete a range of lines from a file
- create_file: Create a new file with content
- list_directory: List files in a directory

When editing files:
1. Always view the file first to understand its current state
2. Use precise string replacements - the old_str must match exactly
3. Make minimal, focused changes rather than rewriting entire files
4. Verify your changes by viewing the file again after editing
5. Explain what changes you made and why

Be careful not to modify unrelated code. Always preserve the original formatting and style."""

    def __init__(
        self,
        root_dir: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
        max_file_size: int = 1024 * 1024,
        sandbox_enabled: bool = True,
        audit_enabled: bool = True,
        audit_storage_path: Optional[str] = None
    ):
        """
        Initialize LangChain integration.
        
        Args:
            root_dir: Root directory for file operations
            allowed_extensions: Allowed file extensions
            max_file_size: Maximum file size in bytes
            sandbox_enabled: Enable path sandboxing
            audit_enabled: Enable audit logging
            audit_storage_path: Path to store audit logs
        """
        self.file_edit_tools = FileEditTools(
            root_dir=root_dir,
            allowed_extensions=allowed_extensions,
            max_file_size=max_file_size,
            sandbox_enabled=sandbox_enabled
        )
        
        self.audit_logger = AuditLogger(audit_storage_path) if audit_enabled else None
        self.access_control = AccessControl()
        
        self._agent_executor: Optional[AgentExecutor] = None
        self._memory: Optional[ConversationBufferMemory] = None
        
    def get_tools(self) -> List[BaseTool]:
        """Get all file editing tools."""
        return self.file_edit_tools.get_tools()
        
    def register_user(
        self,
        user_id: str,
        roles: Optional[List[str]] = None,
        groups: Optional[List[str]] = None
    ):
        """
        Register a user with access control.
        
        Args:
            user_id: User identifier
            roles: List of role names (admin, developer, viewer)
            groups: List of group names
        """
        role_set = set()
        if roles:
            for role_name in roles:
                try:
                    role_set.add(Role[role_name.upper()])
                except KeyError:
                    pass
                    
        if not role_set:
            role_set = {Role.VIEWER}  # Default role
            
        group_set = set(groups) if groups else set()
        
        self.access_control.register_user(user_id, role_set, group_set)
        
    def create_agent_executor(self, llm, system_prompt: Optional[str] = None,
                              verbose: bool = True, user_id: str = "anonymous"):
        """
        Create an agent executor with file editing tools using LangGraph.
        
        Args:
            llm: LangChain LLM instance (e.g., ChatOpenAI)
            system_prompt: Custom system prompt (optional)
            verbose: Enable verbose logging
            user_id: User ID for audit logging
            
        Returns:
            Compiled graph (agent executor)
        """
        from langgraph.prebuilt import create_react_agent
        
        tools = self.get_tools()
        
        # Setup callback for audit logging
        callbacks = []
        if self.audit_logger:
            callbacks.append(FileEditingCallback(self.audit_logger, user_id))
        
        # Create the ReAct agent with system prompt
        system_message = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        graph = create_react_agent(llm, tools, state_modifier=system_message)
        
        return graph
        
    def create_simple_agent_chain(self, llm, user_id: str = "anonymous"):
        """
        Create a simple chain for single-turn file operations.
        
        Args:
            llm: LangChain LLM instance
            user_id: User ID for audit logging
            
        Returns:
            Simple chain for file operations
        """
        from langchain.chains import LLMMathChain
        from langchain.agents import initialize_agent, AgentType
        
        tools = self.get_tools()
        
        # Setup callback for audit logging
        callbacks = []
        if self.audit_logger:
            callbacks.append(FileEditingCallback(self.audit_logger, user_id))
            
        agent = initialize_agent(
            tools,
            llm,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=True,
            callbacks=callbacks,
            handle_parsing_errors=True
        )
        
        return agent
        
    def get_audit_summary(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary of audit log entries.
        
        Args:
            file_path: Optional file path to filter by
            
        Returns:
            Dictionary with audit summary statistics
        """
        if not self.audit_logger:
            return {"error": "Audit logging not enabled"}
            
        entries = self.audit_logger.query(file_path=file_path, limit=1000)
        
        summary = {
            "total_entries": len(entries),
            "by_action_type": {},
            "by_user": {},
            "files_affected": set()
        }
        
        for entry in entries:
            # Count by action type
            action = entry.action_type.value
            summary["by_action_type"][action] = summary["by_action_type"].get(action, 0) + 1
            
            # Count by user
            user = entry.user_id
            summary["by_user"][user] = summary["by_user"].get(user, 0) + 1
            
            # Track files
            summary["files_affected"].add(entry.file_path)
            
        summary["files_affected"] = list(summary["files_affected"])
        
        return summary
        
    def export_audit_log(self, output_path: str, format: str = "json"):
        """
        Export audit log to file.
        
        Args:
            output_path: Path to export to
            format: Export format ("json" or "csv")
        """
        if not self.audit_logger:
            raise ValueError("Audit logging not enabled")
            
        if format.lower() == "json":
            self.audit_logger.export_json(output_path)
        elif format.lower() == "csv":
            self.audit_logger.export_csv(output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")


# Convenience function for quick setup

def create_file_editing_agent(
    llm,
    root_dir: Optional[str] = None,
    user_id: str = "default",
    verbose: bool = True
) -> AgentExecutor:
    """
    Quick setup function to create a file editing agent.
    
    Args:
        llm: LangChain LLM instance
        root_dir: Root directory for file operations
        user_id: User ID for audit logging
        verbose: Enable verbose output
        
    Returns:
        Configured AgentExecutor ready to use
        
    Example:
        ```python
        from langchain.chat_models import ChatOpenAI
        from llm_file_editor import create_file_editing_agent
        
        llm = ChatOpenAI(model="gpt-4")
        agent = create_file_editing_agent(llm, root_dir="/path/to/project")
        
        result = agent.invoke({"input": "Fix the bug in main.py"})
        ```
    """
    integration = LangChainIntegration(root_dir=root_dir)
    integration.register_user(user_id, ["developer"])
    return integration.create_agent_executor(llm, verbose=verbose, user_id=user_id)
