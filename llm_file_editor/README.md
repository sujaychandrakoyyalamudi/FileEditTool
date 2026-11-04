# llm_file_editor

A Python library that gives LLM agents LangChain tools for viewing and editing files inside one root directory, plus standalone helpers for role-based permission checks and a hash-chained audit log.

This is the detailed reference. For a short overview, see the [repository README](../README.md).

## How it works

An agent calls one of six tools with structured arguments such as `file_path`, `old_str`, and `new_str`. An editing tool then:

1. reads the whole file through `FileManager`, which resolves the path and rejects it if it is outside `root_dir` or has a disallowed extension;
2. applies the edit in memory with `DiffEngine`, which also produces a unified diff;
3. writes the result with `FileManager.write` (a temporary file, then a rename);
4. returns a short text result to the model. `str_replace` includes up to 20 lines of the diff.

The model does not write diff patches. It issues structured edit commands, and the diff is computed from the before and after content.

```
LLM agent --> FileEditTools tools --> FileManager (path checks, read, write) --> files under root_dir
                     |
                     +--> DiffEngine (in-memory edit, unified diff)

AccessControl, AuditLogger: standalone helpers that your own code calls
```

`AccessControl` and `AuditLogger` are not called by the tools or by the agent helpers. Permission checks and audit entries happen only where your code calls these classes.

## Requirements

- Python 3.11 or newer (tested on 3.11, 3.12, 3.13, and 3.14).
- The packages in `requirements.txt`: `langchain`, `langchain-openai`, and `pydantic`, plus the development tools `pytest`, `pytest-cov`, `black`, `flake8`, and `mypy`.

## Installation

The package is not published on PyPI, and the repository has no `pyproject.toml` or `setup.py`, so it cannot be installed with pip. Clone it and install the dependencies:

```bash
git clone https://github.com/sujaychandrakoyyalamudi/FileEditTool.git
cd FileEditTool
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r llm_file_editor/requirements.txt
```

Run your scripts from the repository root, or add the root to `PYTHONPATH`, so `import llm_file_editor` works.

## Features

### File operations

- **View** a file or a line range. `start_line` is inclusive and `end_line` is exclusive, both 0-indexed. Returns a `FileContent` with `path`, `content`, `line_count`, `size_bytes`, a SHA-256 `hash`, `is_truncated`, and the `start_line` and `end_line` used.
- **Replace** an exact string, including whitespace. `occurrence=0` (the default) replaces the first match, `occurrence=N` replaces the Nth match (0-based), and `occurrence=-1` replaces all matches. The string does not have to be unique.
- **Insert** text before a 0-indexed line. Out-of-range line numbers are clamped to the start or end of the file.
- **Delete** the line range `[start_line, end_line)`.
- **Create** a file and any missing parent directories. The `create_file` tool refuses to overwrite an existing file.
- **List** the files in a directory, optionally recursively. Returns sorted file paths relative to `root_dir`; directories are not included.

### Safety controls in `FileManager`

- **Path sandboxing** (`sandbox_enabled=True` by default). Each path is resolved with `Path.resolve()`, which follows `..` and symlinks, and is rejected with `ValueError` if the result is outside `root_dir`. `root_dir` defaults to the current working directory.
- **Extension allow-list** (`allowed_extensions`, optional, case-insensitive).
- **Maximum file size for reads** (`max_file_size`, default 1 MiB).
- **Write by replace.** Content goes to `<name>.tmp` first and is then renamed over the target.

### Security helpers (standalone)

- **`AccessControl`**: roles `ADMIN`, `DEVELOPER`, `VIEWER`, and `RESTRICTED`; permissions `READ`, `WRITE`, `DELETE`, and `EXECUTE`; path policies (`AccessPolicy`) with simple glob patterns, optional `denied_roles`, and `is_sensitive` and `requires_approval` flags. Users who are not registered are denied.
- **`AuditLogger`**: records view, create, modify, delete, and access-denied events. Each `AuditEntry` stores a SHA-256 hash of its fields and the previous entry's hash, and `verify_integrity()` recomputes the chain. Supports filtering with `query()` and export with `export_json()` and `export_csv()`. Storage is in memory, or a JSON file when `storage_path` is set.

### LangChain integration

- **Tools**: `FileEditTools(...).get_tools()` returns six `langchain_core` `BaseTool` instances that share one `FileManager` and one `DiffEngine`.
- **System prompt**: `LangChainIntegration.DEFAULT_SYSTEM_PROMPT` describes the tools and careful editing practice. You can pass it, or your own prompt, to an agent.
- **Audit summary and export**: `LangChainIntegration.get_audit_summary()` and `export_audit_log(output_path, format="json")` (`"json"` or `"csv"`).
- `LangChainIntegration` also contains agent helpers (`create_agent_executor`, `create_simple_agent_chain`) and a callback handler (`FileEditingCallback`). They do not work with current LangChain releases; see [Known issues](#known-issues).

## Usage

### Tools

```python
from llm_file_editor import FileEditTools

tools = FileEditTools(root_dir="./workspace")  # every path must stay inside ./workspace
create = tools.get_tool_by_name("create_file")
replace = tools.get_tool_by_name("str_replace")
view = tools.get_tool_by_name("view_file")

print(create.invoke({"file_path": "hello.py", "content": "print('hello')\n"}))
print(replace.invoke({"file_path": "hello.py", "old_str": "'hello'", "new_str": "'Hello, World!'"}))
print(view.invoke({"file_path": "hello.py", "start_line": 0, "end_line": 10}))
```

### Direct API

```python
from llm_file_editor import FileManager, DiffEngine

fm = FileManager(root_dir="./workspace", allowed_extensions=[".py"], max_file_size=1024 * 1024)
engine = DiffEngine()  # this example edits hello.py from the previous one

# Ranged views are for reading. Edit the full content: writing back a ranged
# view would drop every line outside the range.
head = fm.view("hello.py", start_line=0, end_line=20)
print(f"Lines {head.start_line}-{head.end_line}:\n{head.content}")

result = engine.str_replace(fm.view("hello.py").content, "Hello", "Hi", occurrence=-1)
if result.success:
    fm.write("hello.py", result.new_content)
    print(f"Replaced {result.changes_applied} occurrence(s)")
    print("".join(result.diff_lines))
else:
    print(result.error_message)
```

### With a LangChain agent

The tools are standard LangChain tools, so any tool-calling agent can use them. With LangChain 1.x and `langchain-openai` (both installed by `requirements.txt`), set `OPENAI_API_KEY` and run:

```python
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from llm_file_editor import FileEditTools, LangChainIntegration

agent = create_agent(
    ChatOpenAI(model="gpt-4o"),
    tools=FileEditTools(root_dir="./workspace").get_tools(),
    system_prompt=LangChainIntegration.DEFAULT_SYSTEM_PROMPT,
)
result = agent.invoke({"messages": [{"role": "user", "content": "View hello.py and fix any syntax errors."}]})
print(result["messages"][-1].content)
```

The tools are synchronous only (`_arun` raises `NotImplementedError`), so use `invoke` or `stream`, not `ainvoke`.

### Access control

```python
from llm_file_editor.security.access_control import AccessControl, AccessPolicy, Role

ac = AccessControl()
ac.register_user("alice", {Role.ADMIN})
ac.register_user("bob", {Role.DEVELOPER})
ac.create_sensitive_policy("*.secret", allowed_roles={Role.ADMIN})

print(ac.can_write("bob", "src/main.py"))  # True
print(ac.can_read("bob", "README.md"))     # False: the default developer policy covers only *.py
check = ac.validate_user_access_for_edit("alice", "prod.secret", "write")
print(check["allowed"], check["is_sensitive"], check["requires_approval"])  # True True True

# Policies only grant access. To keep viewers out of *.secret files, add a deny rule:
ac.add_policy(AccessPolicy("*.secret", allowed_roles=set(), allowed_permissions=set(),
                           denied_roles={Role.VIEWER}))
```

`validate_user_access_for_edit` accepts `view`, `read`, `write`, `edit`, `create`, or `delete` and returns a dict with `allowed`, `reason`, `is_sensitive`, and `requires_approval`. Nothing acts on `requires_approval`; it is up to your code.

### Audit logging

```python
from llm_file_editor import AuditLogger

log = AuditLogger()  # in memory; pass storage_path="audit.json" to write a JSON file
log.log_view("alice", "src/main.py")
log.log_modify("alice", "src/main.py", changes_summary="Renamed foo to bar")

for entry in log.query(user_id="alice", limit=10):
    print(entry.timestamp, entry.action_type.value, entry.file_path)

print(log.verify_integrity())  # True while no stored entry has been altered
log.export_csv("audit.csv")
```

With `storage_path`, the whole log is rewritten to the JSON file after every entry. Reopening an existing log file is currently broken; see [Known issues](#known-issues).

## Tool reference

| Tool | Arguments | Notes |
| --- | --- | --- |
| `view_file` | `file_path`, `start_line` (optional), `end_line` (optional) | 0-indexed; `start_line` inclusive, `end_line` exclusive |
| `str_replace` | `file_path`, `old_str`, `new_str`, `occurrence` (default `0`) | `0` first match, `N` Nth match, `-1` all matches; returns up to 20 diff lines |
| `insert_line` | `file_path`, `insert_line`, `text` | inserts before the 0-indexed line; adds a newline when inserting before an existing line |
| `delete_range` | `file_path`, `start_line`, `end_line` | deletes `[start_line, end_line)` |
| `create_file` | `file_path`, `content` (default `""`) | fails if the file exists; creates parent directories |
| `list_directory` | `dir_path`, `recursive` (default `false`) | files only, as paths relative to `root_dir` |

The tools catch exceptions and return an error message string instead of raising.

## Python API summary

- `FileManager(root_dir=None, allowed_extensions=None, max_file_size=1048576, sandbox_enabled=True)`: `view(file_path, start_line=None, end_line=None)`, `write(file_path, content, create_parents=True)`, `exists(file_path)`, `delete(file_path)`, `list_directory(dir_path, recursive=False)`, `get_relative_path(file_path)`.
- `DiffEngine()`: `str_replace(content, old_str, new_str, occurrence=0)`, `insert(content, text, line_number)`, `delete_range(content, start_line, end_line)`, `create(content="")`, `generate_patch(old_content, new_content, old_path="a/file", new_path="b/file")`, and `apply_command(command, content)` for an `EditCommand`. Edits return a `DiffResult` with `success`, `original_content`, `new_content`, `changes_applied`, `error_message`, and `diff_lines`.
- `FileEditTools(root_dir=None, allowed_extensions=None, max_file_size=1048576, sandbox_enabled=True)`: `get_tools()`, `get_tool_by_name(name)`.
- `AccessControl()`: `register_user(user_id, roles, groups=None)` with a set of `Role` values, `add_policy(policy)`, `remove_policy(path_pattern)`, `check_permission(user_id, file_path, permission)`, `can_read`, `can_write`, `can_delete`, `create_sensitive_policy(path_pattern, allowed_roles=None)`, `is_sensitive(file_path)`, `requires_approval(file_path)`, `validate_user_access_for_edit(user_id, file_path, edit_type)`.
- `AuditLogger(storage_path=None)`: `log(action_type, user_id, file_path, details=None)`, `log_view`, `log_create`, `log_modify(user_id, file_path, changes_summary=None, diff_stats=None)`, `log_delete`, `log_access_denied(user_id, file_path, reason)`, `query(user_id=None, file_path=None, action_type=None, start_time=None, end_time=None, limit=100)` (`file_path` matches by prefix), `get_file_history(file_path)`, `get_user_activity(user_id, limit=100)`, `verify_integrity()`, `export_json(output_path)`, `export_csv(output_path)`, `clear()`.
- `LangChainIntegration(root_dir=None, allowed_extensions=None, max_file_size=1048576, sandbox_enabled=True, audit_enabled=True, audit_storage_path=None)`: `get_tools()`, `register_user(user_id, roles=None, groups=None)` with role names as strings (unknown names are ignored; the default role is `viewer`), `get_audit_summary(file_path=None)`, `export_audit_log(output_path, format="json")`, and the agent helpers described under [Known issues](#known-issues).
- `llm_file_editor.utils.helpers.format_diff_for_display(diff_lines, max_lines=50)`: colors diff lines with ANSI codes for terminal output.

## Limits

- Sandboxing is a path check in Python, not OS-level isolation.
- The tools do not check permissions or write audit entries. `LangChainIntegration.register_user` stores roles that nothing reads during tool calls.
- The default policies give `ADMIN` every permission on `*`, `DEVELOPER` read and write on `*.py` only, `VIEWER` read on `*`, and `RESTRICTED` nothing.
- Policies only grant access, except for `denied_roles`. A sensitive-file policy does not stop a `VIEWER` from reading the file through the default `*` read policy, and `requires_approval` is only a flag.
- Glob patterns are turned into regular expressions by replacing `*` with `.*` and `?` with `.`, without escaping. A `.` in a pattern matches any character, and `*` also matches `/`.
- The audit log is not immutable. Its hash chain only catches edits made without recomputing the hashes: the hashes are unkeyed, the JSON file is rewritten on every entry, and `clear()` empties it, so anyone with write access can rebuild a valid chain. Deleting the newest entries is not detected. The CSV export leaves out `previous_hash`.
- `str_replace` replaces the first match by default, even if the string appears more than once.
- `max_file_size` is checked on reads. `write` writes first and then reads the file back, so an oversized write lands on disk and then raises `ValueError`.

## Known issues

- **`create_agent_executor` and `create_file_editing_agent` do not work.** They call `langgraph.prebuilt.create_react_agent(llm, tools, state_modifier=...)`. Current LangGraph raises `TypeError` for `state_modifier` (it was replaced by `prompt`). `langgraph` is not in `requirements.txt`; LangChain 1.x installs it as a dependency. These helpers return a LangGraph graph that takes `{"messages": [...]}`, not an `AgentExecutor` that takes `{"input": ...}`.
- **`create_simple_agent_chain` does not work with LangChain 1.x.** It imports `langchain.chains` and `langchain.agents.initialize_agent`, which LangChain 1.x removed.
- **`create_file_editing_agent` is not exported** from the package root. It is in `llm_file_editor.integrations.langchain_integration`.
- **`FileEditingCallback` records nothing.** `create_agent_executor` builds it but never attaches it. The handler also reads the file path with `json.loads(input_str)`, but LangChain passes dict tool inputs as `str(dict)`, which is not valid JSON. It logs `delete_range` as a file `DELETE` and ignores `list_directory`.
- **`list_directory` fails when `allowed_extensions` is set**, because the directory path is checked against the extension list too.
- **Reopening an existing audit log file breaks the logger.** `_load_entries` keeps `action_type` as a plain string, so the next `log_*`, `export_*`, or `verify_integrity()` call raises `AttributeError`.
- **Appending at the end of a file without a trailing newline** with `insert` joins the new text to the last line instead of starting a new line.
- **`changes_applied` can overcount** with `occurrence=-1` when matches overlap. Replacing `aa` in `aaa` reports 2 changes but makes 1.

## Roadmap (not implemented yet)

- Enforce `AccessControl` permissions and write audit entries inside the tools.
- An approval workflow for sensitive files.
- Append-only or signed audit storage.
- Conversation memory for multi-turn editing sessions.
- Applying unified-diff patches written by the model.
- Version-control integration, such as committing each edit.

## Testing

From the repository root, with Python 3.11 or newer and the dependencies installed:

```bash
pytest llm_file_editor/tests/test_core.py -v
```

The tests cover `FileManager` (view, line ranges, write, delete, listing, sandbox violations), `DiffEngine` (replace, insert, delete, `apply_command`), `AccessControl` (default roles, sensitive policy, edit validation), and `AuditLogger` with a new log file (logging, history, integrity, JSON export). One more test checks that the type annotations of `create_file_editing_agent` resolve; an undefined name there breaks `import llm_file_editor` on Python 3.13 and older. They do not cover the LangChain tools, `LangChainIntegration`, reopening a log file, or `list_directory` with an extension allow-list.

## License

MIT. See [LICENSE](../LICENSE).
