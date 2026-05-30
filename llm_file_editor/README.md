# LLM-Based File Editing Tool

A comprehensive file editing tool that leverages LLMs to generate precise diff patches which are then applied by a safe execution layer. Integrates seamlessly with LangChain for AI-powered file operations.

## Features

### Core Functionality
- **View files** - Read file contents with optional line ranges for context management
- **String replacement** - Replace exact strings with new text (supports multiple occurrences)
- **Line insertion** - Insert text at specific line numbers
- **Range deletion** - Delete ranges of lines from files
- **File creation** - Create new files with content
- **Directory listing** - List files in directories (recursive option available)

### Security & Privacy
- **Role-Based Access Control (RBAC)** - Admin, Developer, Viewer roles with customizable permissions
- **Path sandboxing** - Restrict file operations to designated directories
- **File extension filtering** - Whitelist allowed file types
- **Audit logging** - Immutable, hash-chained audit logs for compliance
- **Sensitive file policies** - Mark files as requiring approval for access

### LangChain Integration
- **Pre-configured tools** - Ready-to-use LangChain tools for all file operations
- **Agent executor** - Easy setup of AI agents with file editing capabilities
- **Conversation memory** - Maintain context across editing sessions
- **Callback handlers** - Automatic audit logging through LangChain callbacks
- **Custom prompts** - Configurable system prompts for specialized workflows

## Installation

```bash
pip install langchain langchain-openai pydantic
```

## Quick Start

### Basic Usage with LangChain Agent

```python
from langchain.chat_models import ChatOpenAI
from llm_file_editor import LangChainIntegration, create_file_editing_agent

# Initialize the integration
integration = LangChainIntegration(
    root_dir="/path/to/your/project",
    allowed_extensions=[".py", ".txt", ".md", ".js"],
    audit_enabled=True
)

# Register a user
integration.register_user("developer1", ["developer"])

# Create an agent
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = integration.create_agent_executor(llm, user_id="developer1")

# Use the agent
result = agent.invoke({
    "input": "View main.py and fix any syntax errors you find"
})
print(result["output"])
```

### Using Individual Tools

```python
from llm_file_editor.tools.file_tools import FileEditTools

# Initialize tools
tools_factory = FileEditTools(
    root_dir="./workspace",
    sandbox_enabled=True
)

# Get all tools
tools = tools_factory.get_tools()

# Use a specific tool
view_tool = tools_factory.get_tool_by_name("view_file")
result = view_tool._run(file_path="example.py")
print(result)

# Edit a file
replace_tool = tools_factory.get_tool_by_name("str_replace")
result = replace_tool._run(
    file_path="example.py",
    old_str="def old_function():",
    new_str="def new_function():"
)
print(result)
```

### Direct API Usage

```python
from llm_file_editor.core.file_manager import FileManager
from llm_file_editor.core.diff_engine import DiffEngine

# File Manager
fm = FileManager(root_dir="./workspace", max_file_size=1024*1024)

# View a file
content = fm.view("example.py", start_line=0, end_line=50)
print(f"Lines {content.start_line}-{content.end_line}:")
print(content.content)

# Diff Engine
engine = DiffEngine()

# Generate a replacement
result = engine.str_replace(
    content.content,
    old_str="print('hello')",
    new_str="print('Hello, World!')"
)

if result.success:
    # Apply the change
    fm.write("example.py", result.new_content)
    print(f"Applied {result.changes_applied} changes")
    print("Diff preview:")
    print('\n'.join(result.diff_lines[:10]))
```

### Audit Logging

```python
from llm_file_editor.security.audit_logger import AuditLogger, ActionType

# Initialize logger
logger = AuditLogger(storage_path="./audit_logs.json")

# Log operations
logger.log_view("user123", "config.py")
logger.log_modify("user123", "config.py", changes_summary="Updated API key")

# Query logs
entries = logger.query(user_id="user123", limit=10)
for entry in entries:
    print(f"{entry.timestamp}: {entry.action_type.value} on {entry.file_path}")

# Export for compliance
logger.export_csv("./compliance_report.csv")
```

### Access Control

```python
from llm_file_editor.security.access_control import AccessControl, Role, Permission

# Initialize access control
ac = AccessControl()

# Register users
ac.register_user("admin1", {Role.ADMIN})
ac.register_user("dev1", {Role.DEVELOPER})
ac.register_user("viewer1", {Role.VIEWER})

# Create sensitive file policy
ac.create_sensitive_policy("*.secret", allowed_roles={Role.ADMIN})

# Check permissions
if ac.can_write("dev1", "code.py"):
    print("Developer can write to Python files")
    
if not ac.can_write("dev1", "credentials.secret"):
    print("Developer cannot modify secret files")

# Validate before edit
validation = ac.validate_user_access_for_edit(
    "dev1",
    "src/main.py",
    "write"
)
if validation["allowed"]:
    print("Edit allowed")
    if validation["requires_approval"]:
        print("But requires approval")
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User / IDE     │────▶│  LangChain Agent │────▶│  File Tools     │
│                 │◀────│                  │◀────│  (LangChain)    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
         ┌────────────────────────────────────────────────┤
         │                                                │
         ▼                                                ▼
┌─────────────────┐                              ┌─────────────────┐
│  Audit Logger   │                              │  Access Control │
│  (Immutable)    │                              │  (RBAC)         │
└─────────────────┘                              └────────┬────────┘
                                                          │
         ┌────────────────────────────────────────────────┤
         │                                                │
         ▼                                                ▼
┌─────────────────┐                              ┌─────────────────┐
│  Diff Engine    │◀────────────────────────────▶│  File Manager   │
│  (Safe Patches) │                              │  (Sandboxed)    │
└─────────────────┘                              └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  File System    │
                                                 │  (Version Ctrl) │
                                                 └─────────────────┘
```

## Tool Specifications

### view_file
View file contents with optional line range.
- **Parameters:**
  - `file_path` (required): Path to the file
  - `start_line` (optional): Starting line number (0-indexed, inclusive)
  - `end_line` (optional): Ending line number (0-indexed, exclusive)

### str_replace
Replace exact string in a file.
- **Parameters:**
  - `file_path` (required): Path to the file
  - `old_str` (required): Exact string to replace
  - `new_str` (required): Replacement string
  - `occurrence` (optional): Which occurrence to replace (0=first, -1=all)

### insert_line
Insert text at a specific line.
- **Parameters:**
  - `file_path` (required): Path to the file
  - `insert_line` (required): Line number to insert at (0-indexed)
  - `text` (required): Text to insert

### delete_range
Delete a range of lines.
- **Parameters:**
  - `file_path` (required): Path to the file
  - `start_line` (required): Starting line (0-indexed, inclusive)
  - `end_line` (required): Ending line (0-indexed, exclusive)

### create_file
Create a new file.
- **Parameters:**
  - `file_path` (required): Path where to create the file
  - `content` (optional): Content to write (defaults to empty)

### list_directory
List directory contents.
- **Parameters:**
  - `dir_path` (required): Path to the directory
  - `recursive` (optional): Whether to list recursively (default: False)

## Best Practices

1. **Always view before editing** - Let the LLM view the file first to understand context
2. **Use precise replacements** - The `old_str` must match exactly including whitespace
3. **Make minimal changes** - Prefer small, focused edits over rewriting entire files
4. **Verify after editing** - View the file again to confirm changes are correct
5. **Enable audit logging** - Keep records of all changes for compliance and debugging
6. **Use sandboxing** - Always enable path sandboxing in production
7. **Set appropriate permissions** - Use RBAC to restrict access based on roles

## Testing

Run the test suite:

```bash
cd /workspace
pytest llm_file_editor/tests/ -v
```

## Example Workflow

Here's a complete example of using the tool with an LLM agent:

```python
from langchain.chat_models import ChatOpenAI
from llm_file_editor import LangChainIntegration

# Setup
integration = LangChainIntegration(
    root_dir="./my_project",
    allowed_extensions=[".py", ".md"],
    audit_enabled=True,
    audit_storage_path="./audit.json"
)

# Register user with developer role
integration.register_user("alice", ["developer"])

# Create agent
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = integration.create_agent_executor(
    llm,
    verbose=True,
    user_id="alice"
)

# Task: Fix a bug
response = agent.invoke({
    "input": """
    Look at utils/calculator.py. There's a bug in the divide function 
    where it doesn't handle division by zero. Please fix it.
    """
})

print(response["output"])

# Review audit log
summary = integration.get_audit_summary()
print(f"Total operations: {summary['total_entries']}")
print(f"Files affected: {summary['files_affected']}")
```

## License

MIT License

## Contributing

Contributions welcome! Please read our contributing guidelines before submitting PRs.
