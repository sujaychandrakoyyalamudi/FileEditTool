# FileEditTool

`llm_file_editor` is a Python library that gives LLM agents LangChain tools for viewing and editing files inside one root directory.

## What it does

The package provides six LangChain tools that work inside one root directory: view a file (optionally a line range), replace an exact string, insert text at a line, delete a range of lines, create a file, and list files. `DiffEngine` applies each edit in memory and produces a unified diff, and `FileManager` checks the path and writes the result through a temporary file and a rename.

The model does not write patches. It calls the tools with structured arguments (`file_path`, `old_str`, `new_str`, line numbers), and the diff is computed from the before and after content.

The package also includes two standalone helpers: a role-based permission checker (`AccessControl`) and a hash-chained audit log (`AuditLogger`). The tools do not call them; your own code has to.

## Features

- View a file, optionally by line range (0-indexed, end exclusive): `FileManager.view`, `view_file` tool.
- Exact string replacement of the first match (default), the Nth match, or every match (`occurrence=-1`): `DiffEngine.str_replace`.
- Line insertion and line-range deletion: `DiffEngine.insert`, `DiffEngine.delete_range`.
- File creation that refuses to overwrite an existing file: `create_file` tool.
- File listing, optionally recursive. Returns file paths relative to the root; directories are not listed.
- Path sandboxing: paths are resolved (following `..` and symlinks) and rejected if they leave `root_dir`. Optional file-extension allow-list and a maximum file size for reads (default 1 MiB).
- A unified diff for every edit (`DiffResult.diff_lines`, `DiffEngine.generate_patch`).
- Permission checks with `ADMIN`, `DEVELOPER`, `VIEWER`, and `RESTRICTED` roles and glob-style path policies: `AccessControl`.
- Audit log with SHA-256 hash chaining, `verify_integrity()`, filtering, and JSON or CSV export: `AuditLogger`.
- `FileEditTools(...).get_tools()` returns standard LangChain `BaseTool` objects that any tool-calling agent can use.

## Install

The package is not on PyPI and has no `pyproject.toml` or `setup.py`. Clone the repository and install the dependencies:

```bash
git clone https://github.com/sujaychandrakoyyalamudi/FileEditTool.git
cd FileEditTool
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r llm_file_editor/requirements.txt
```

Use Python 3.14 or newer. On Python 3.13 and older, `import llm_file_editor` currently fails (see [Safety and limits](#safety-and-limits)). `requirements.txt` also installs the development tools (pytest, pytest-cov, black, flake8, mypy). Run your code from the repository root so `llm_file_editor` is importable.

## Quick start

```python
from llm_file_editor import FileEditTools

tools = FileEditTools(root_dir="./workspace")  # every path must stay inside ./workspace
create = tools.get_tool_by_name("create_file")
replace = tools.get_tool_by_name("str_replace")
view = tools.get_tool_by_name("view_file")

print(create.invoke({"file_path": "hello.py", "content": "print('hello')\n"}))
print(replace.invoke({"file_path": "hello.py", "old_str": "'hello'", "new_str": "'Hello, World!'"}))
print(view.invoke({"file_path": "hello.py"}))
print(view.invoke({"file_path": "../secrets.txt"}))  # "Error: Path '../secrets.txt' is outside sandbox root ..."
```

To use the tools in an agent, pass them to LangChain's `create_agent` (LangChain 1.x, installed by `requirements.txt`; set `OPENAI_API_KEY`):

```python
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from llm_file_editor import FileEditTools, LangChainIntegration

agent = create_agent(
    ChatOpenAI(model="gpt-4o"),
    tools=FileEditTools(root_dir="./workspace").get_tools(),
    system_prompt=LangChainIntegration.DEFAULT_SYSTEM_PROMPT,
)
result = agent.invoke({"messages": [{"role": "user", "content": "Add a docstring to hello.py"}]})
print(result["messages"][-1].content)
```

## Safety and limits

- Sandboxing is a path check in Python, not OS-level isolation.
- **Access control and audit logging are not applied to tool calls.** The tools never call `AccessControl` or `AuditLogger`, so `LangChainIntegration.register_user` does not limit what an agent can do.
- The default `DEVELOPER` policy covers only `*.py` files. Policies can only grant access unless a policy lists `denied_roles`, so a file marked sensitive is still readable by a `VIEWER` through the default `*` read policy. "Requires approval" is a flag; there is no approval workflow.
- The audit log is not immutable. Its hash chain only catches edits made without recomputing the hashes: the hashes are unkeyed, the JSON file is rewritten on every entry, and `clear()` empties it, so anyone with write access can rebuild a valid chain. Deleting the newest entries is not detected.
- `str_replace` replaces the first match by default, even when the string appears more than once.

Known issues in the current code:

- On Python 3.13 and older, importing the package raises `NameError: name 'AgentExecutor' is not defined`. The return annotation of `create_file_editing_agent` names a class that is never imported.
- The built-in agent helpers do not work with current LangChain. `create_agent_executor` and `create_file_editing_agent` call LangGraph's `create_react_agent` with `state_modifier`, which current LangGraph rejects with a `TypeError`. `create_simple_agent_chain` uses `initialize_agent` and `langchain.chains`, which LangChain 1.x removed. Use `create_agent` as shown above.
- `FileEditingCallback` is never attached by `create_agent_executor`, and it only records a call when the tool input is a JSON string, so agent runs are not audit-logged.
- `list_directory` fails whenever `allowed_extensions` is set, because the directory path itself fails the extension check.
- Reopening an existing audit log file breaks the logger: the next `log_*`, `export_*`, or `verify_integrity()` call raises `AttributeError`.

## Project layout

```
llm_file_editor/
├── __init__.py                    # exports FileManager, DiffEngine, FileEditTools,
│                                  # AccessControl, AuditLogger, LangChainIntegration
├── core/file_manager.py           # FileManager: path checks, view, write, delete, list
├── core/diff_engine.py            # DiffEngine: str_replace, insert, delete_range, diffs
├── tools/file_tools.py            # six LangChain tools and the FileEditTools factory
├── security/access_control.py     # AccessControl, Role, Permission, AccessPolicy
├── security/audit_logger.py       # AuditLogger, AuditEntry, ActionType
├── integrations/langchain_integration.py  # LangChainIntegration, FileEditingCallback
├── utils/helpers.py               # format_diff_for_display (ANSI-colored diff)
├── tests/test_core.py
├── requirements.txt
└── README.md                      # detailed reference
```

## Tests

From the repository root, with Python 3.14 or newer and the dependencies installed:

```bash
pytest llm_file_editor/tests/test_core.py -v
```

The tests cover `FileManager`, `DiffEngine`, `AccessControl`, and `AuditLogger`. They do not cover the LangChain tools or the integration module.

## Roadmap (not implemented yet)

- Enforce `AccessControl` permissions and write audit entries inside the tools.
- An approval workflow for sensitive files.
- Append-only or signed audit storage.
- Conversation memory for multi-turn editing sessions.
- Applying unified-diff patches written by the model.
- Version-control integration, such as committing each edit.

## License

MIT. See [LICENSE](LICENSE).

## Detailed documentation

Tool parameters, the Python API, and more on each known issue are in [llm_file_editor/README.md](llm_file_editor/README.md).
