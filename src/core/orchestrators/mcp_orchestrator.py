from __future__ import annotations

from typing import Any

from ..components.capability_component import CapabilityComponent
from ..components.extension_tool_component import ExtensionToolComponent
from ..managers.execution_manager import ExecutionManager
from ..managers.inference_manager import InferenceManager
from ..managers.memory_manager import MemoryManager
from ..managers.workspace_manager import WorkspaceManager
from ..models.protocol import JsonRpcError, error_response, success_response
from ..models.tooling import ToolRoute
from ..runtime.graph_engine import GraphEngine
from ..runtime.messages import Message
from ..runtime.nodes import GraphNode
from ..runtime.tool_registry import ToolRegistry
from ...config import AppConfig


class McpOrchestrator(GraphNode):
    """CORE-side orchestrator for JSON-RPC/MCP request routing."""

    def __init__(
        self,
        config: AppConfig,
        tool_registry: ToolRegistry,
        capability_component: CapabilityComponent,
        extension_tool_component: ExtensionToolComponent,
        workspace_manager: WorkspaceManager,
        execution_manager: ExecutionManager,
        inference_manager: InferenceManager,
        memory_manager: MemoryManager,
    ) -> None:
        super().__init__(node_id="core.mcp_orchestrator", node_type="orchestrator")
        self._config = config
        self._tool_registry = tool_registry
        self._capability_component = capability_component
        self._extension_tool_component = extension_tool_component
        self._workspace_manager = workspace_manager
        self._execution_manager = execution_manager
        self._inference_manager = inference_manager
        self._memory_manager = memory_manager
        self._graph_engine: GraphEngine | None = None
        self._dynamic_tool_names: set[str] = set()
        self._register_tool_routes()

    def bootstrap(self, graph_engine: GraphEngine) -> None:
        self._graph_engine = graph_engine
        graph_engine.register_node(self)
        graph_engine.register_node(self._workspace_manager)
        graph_engine.register_node(self._execution_manager)
        graph_engine.register_node(self._inference_manager)
        graph_engine.register_node(self._memory_manager)

        graph_engine.allow_route("app", self.node_id)
        graph_engine.allow_route(self.node_id, self._workspace_manager.node_id)
        graph_engine.allow_route(self.node_id, self._execution_manager.node_id)
        graph_engine.allow_route(self.node_id, self._inference_manager.node_id)
        graph_engine.allow_route(self.node_id, self._memory_manager.node_id)

    def receive(self, message: Message) -> dict[str, Any]:
        request = message.payload["request"]
        request_id = request.get("id")
        method = request["method"]
        params = request.get("params", {})
        self.local_state["last_method"] = method

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2026-04-07",
                    "serverInfo": {
                        "name": self._config.server_name,
                        "version": self._config.server_version,
                    },
                    "capabilities": {"tools": {}},
                }
                return {"rpc_response": success_response(request_id, result)}

            if method == "ping":
                return {"rpc_response": success_response(request_id, {"status": "ok"})}

            if method == "tools/list":
                return {
                    "rpc_response": success_response(
                        request_id,
                        {"tools": self._tool_registry.list_tools()},
                    )
                }

            if method == "tools/call":
                tool_name = str(params["name"])
                arguments = dict(params.get("arguments", {}))
                route = self._tool_registry.get(tool_name)
                return {
                    "rpc_response": success_response(
                        request_id,
                        self._call_tool(route, arguments),
                    )
                }

            return {
                "rpc_response": error_response(
                    request_id,
                    JsonRpcError(code=-32601, message=f"Method '{method}' not found."),
                )
            }
        except KeyError as error:
            return {
                "rpc_response": error_response(
                    request_id,
                    JsonRpcError(
                        code=-32602,
                        message="Missing required request field.",
                        data={"missing_field": str(error)},
                    ),
                )
            }
        except Exception as error:  # noqa: BLE001
            return {
                "rpc_response": error_response(
                    request_id,
                    JsonRpcError(code=-32000, message=str(error)),
                )
            }

    def _call_tool(self, route: ToolRoute, arguments: dict[str, Any]) -> dict[str, Any]:
        if route.manager == "orchestrator":
            if route.action == "capabilities.describe":
                structured_content = self._capability_component.describe_capabilities()
            elif route.action == "worker.refresh_extension_tools":
                structured_content = self.refresh_extension_tools()
            else:
                raise ValueError(f"Unsupported orchestrator tool action '{route.action}'.")
            return {
                "content": [{"type": "text", "text": "Orchestrator action completed."}],
                "structuredContent": structured_content,
                "isError": False,
            }

        if self._graph_engine is None:
            raise RuntimeError("McpOrchestrator has not been bootstrapped.")

        manager_node_id = {
            "workspace": self._workspace_manager.node_id,
            "execution": self._execution_manager.node_id,
            "inference": self._inference_manager.node_id,
            "memory": self._memory_manager.node_id,
        }[route.manager]

        response = self._graph_engine.dispatch(
            Message(
                sender=self.node_id,
                target=manager_node_id,
                action=route.action,
                payload={"arguments": arguments, "route_name": route.name},
            )
        )
        return {
            "content": [{"type": "text", "text": str(response["text"])}],
            "structuredContent": response["structured_content"],
            "isError": bool(response["is_error"]),
        }

    def _register_tool_routes(self) -> None:
        routes = [
            ToolRoute(
                name="capabilities.describe",
                description="Describe the worker's built-in capabilities and workspace guardrails.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                manager="orchestrator",
                action="capabilities.describe",
            ),
            ToolRoute(
                name="worker.refresh_extension_tools",
                description="Refresh validated extension-tool blueprints and hot-load newly implemented extension tools.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                manager="orchestrator",
                action="worker.refresh_extension_tools",
            ),
            ToolRoute(
                name="archive.inspect_zip",
                description="Inspect a bounded .zip archive and report entries plus unsafe path findings.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "archive_path": {"type": "string"},
                        "max_entries": {"type": "integer", "minimum": 1},
                    },
                    "required": ["archive_path"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="archive.inspect_zip",
            ),
            ToolRoute(
                name="archive.extract_zip",
                description="Safely extract a bounded .zip archive into a target workspace folder with zip-slip protection.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "archive_path": {"type": "string"},
                        "target_dir": {"type": "string"},
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                    },
                    "required": ["archive_path", "target_dir"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="archive.extract_zip",
            ),
            ToolRoute(
                name="intake.zip_to_sandbox",
                description="Inspect, extract, and ingest a bounded .zip bundle into sandbox HEAD in one call.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "archive_path": {"type": "string"},
                        "target_dir": {"type": "string"},
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                        "reset_sandbox": {"type": "boolean"},
                        "max_files": {"type": "integer", "minimum": 1},
                        "inspect_max_entries": {"type": "integer", "minimum": 1},
                    },
                    "required": ["archive_path", "target_dir"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="intake.zip_to_sandbox",
            ),
            ToolRoute(
                name="parts.catalog_build",
                description="Build or rebuild a local SQLite parts catalog from bounded workspace source trees.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "reset": {"type": "boolean"},
                        "max_files": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="workspace",
                action="parts.catalog_build",
            ),
            ToolRoute(
                name="parts.catalog_search",
                description="Search the local parts catalog by query text, kind, layer, and path prefix.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "kinds": {"type": "array", "items": {"type": "string"}},
                        "layers": {"type": "array", "items": {"type": "string"}},
                        "path_prefixes": {"type": "array", "items": {"type": "string"}},
                        "intent_target": {
                            "type": "string",
                            "enum": ["auto", "structural", "verbatim", "semantic", "relational"],
                        },
                        "prefer_code": {"type": "boolean"},
                        "prefer_docs": {"type": "boolean"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="parts.catalog_search",
            ),
            ToolRoute(
                name="parts.catalog_get",
                description="Read one or more parts from the local catalog with metadata, content, and symbols.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "part_ids": {"type": "array", "items": {"type": "string"}},
                        "max_chars_per_part": {"type": "integer", "minimum": 1},
                    },
                    "required": ["part_ids"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="parts.catalog_get",
            ),
            ToolRoute(
                name="parts.export_selection",
                description="Export selected catalog parts into a bounded workspace folder while preserving relative paths.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "part_ids": {"type": "array", "items": {"type": "string"}},
                        "target_dir": {"type": "string"},
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                    },
                    "required": ["part_ids", "target_dir"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="parts.export_selection",
            ),
            ToolRoute(
                name="fs.list_tree",
                description="List files and directories under a bounded workspace path.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_depth": {"type": "integer", "minimum": 0},
                    },
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.list_tree",
            ),
            ToolRoute(
                name="fs.make_tree",
                description="Create one or more directories under the workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "directories": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["directories"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.make_tree",
            ),
            ToolRoute(
                name="fs.read_files",
                description="Read one or more UTF-8 files from the workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_chars_per_file": {"type": "integer", "minimum": 1},
                    },
                    "required": ["paths"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.read_files",
            ),
            ToolRoute(
                name="fs.write_files",
                description="Write one or more UTF-8 files using structured JSON payloads.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["path", "content"],
                                "additionalProperties": False,
                            },
                        },
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                    },
                    "required": ["files"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.write_files",
            ),
            ToolRoute(
                name="fs.patch_text",
                description="Apply structured text operations to existing UTF-8 files.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "operation": {
                                        "type": "string",
                                        "enum": ["replace_text", "append_text", "prepend_text"],
                                    },
                                    "old_text": {"type": "string"},
                                    "new_text": {"type": "string"},
                                    "text": {"type": "string"},
                                    "count": {"type": "integer", "minimum": 1},
                                },
                                "required": ["path", "operation"],
                            },
                        }
                    },
                    "required": ["changes"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.patch_text",
            ),
            ToolRoute(
                name="fs.search_text",
                description="Search UTF-8 text files under the workspace root with regex support.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_results": {"type": "integer", "minimum": 1},
                        "case_sensitive": {"type": "boolean"},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="fs.search_text",
            ),
            ToolRoute(
                name="project.scaffold_from_manifest",
                description="Create a directory tree and boilerplate files from a structured manifest.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "directories": {"type": "array", "items": {"type": "string"}},
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["path", "content"],
                                "additionalProperties": False,
                            },
                        },
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                    },
                    "required": ["directories", "files"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="project.scaffold_from_manifest",
            ),
            ToolRoute(
                name="worker.create_tool_scaffold",
                description="Scaffold a new tool stub for the worker's own codebase.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "description": {"type": "string"},
                        "manager": {"type": "string", "enum": ["workspace", "memory"]},
                        "action": {"type": "string"},
                    },
                    "required": ["tool_name", "description", "manager", "action"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="worker.create_tool_scaffold",
            ),
            ToolRoute(
                name="sidecar.export_bundle",
                description="Preview or install a lean UsefulHELPER sidecar bundle into a target app folder with guarded reinstall support.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_dir": {"type": "string"},
                        "include_tests": {"type": "boolean"},
                        "overwrite": {"type": "boolean"},
                        "dry_run": {"type": "boolean"},
                        "reinstall": {"type": "boolean"},
                    },
                    "required": ["target_dir"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sidecar.export_bundle",
            ),
            ToolRoute(
                name="ast.scan_python",
                description="Scan Python files with the AST module and return structural summaries.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_files": {"type": "integer", "minimum": 1},
                        "max_symbols_per_file": {"type": "integer", "minimum": 1},
                    },
                    "required": ["paths"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="ast.scan_python",
            ),
            ToolRoute(
                name="sandbox.init",
                description="Initialize or reset the SQLite-backed project sandbox workbench.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "reset": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.init",
            ),
            ToolRoute(
                name="sandbox.ingest_workspace",
                description="Ingest bounded workspace files into the sandbox HEAD and revision history.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_files": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.ingest_workspace",
            ),
            ToolRoute(
                name="sandbox.read_head",
                description="Read one or more files from the sandbox HEAD state instead of the live workspace tree.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_chars_per_file": {"type": "integer", "minimum": 1},
                    },
                    "required": ["paths"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.read_head",
            ),
            ToolRoute(
                name="sandbox.search_head",
                description="Search sandbox HEAD files with regex support and without rereading the workspace tree.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_results": {"type": "integer", "minimum": 1},
                        "case_sensitive": {"type": "boolean"},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.search_head",
            ),
            ToolRoute(
                name="sandbox.stage_diff",
                description="Apply structured text diffs to sandbox HEAD and record immutable revisions.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "operation": {
                                        "type": "string",
                                        "enum": ["set_text", "replace_text", "append_text", "prepend_text"],
                                    },
                                    "old_text": {"type": "string"},
                                    "new_text": {"type": "string"},
                                    "text": {"type": "string"},
                                    "count": {"type": "integer", "minimum": 1},
                                },
                                "required": ["path", "operation"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["changes"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.stage_diff",
            ),
            ToolRoute(
                name="sandbox.export_head",
                description="Materialize sandbox HEAD back to a bounded workspace folder for testing or vendoring.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_dir": {"type": "string"},
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "mode": {"type": "string", "enum": ["overwrite", "create_only"]},
                    },
                    "required": ["target_dir"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.export_head",
            ),
            ToolRoute(
                name="sandbox.history_for_file",
                description="Read sandbox HEAD metadata and recent immutable revisions for one file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.history_for_file",
            ),
            ToolRoute(
                name="sandbox.query_symbols",
                description="Query Python symbol records from the current sandbox HEAD state.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "kinds": {"type": "array", "items": {"type": "string"}},
                        "name_contains": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="workspace",
                action="sandbox.query_symbols",
            ),
            ToolRoute(
                name="python.run_unittest",
                description="Run allowlisted Python unittest discovery inside the bounded workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "start_dir": {"type": "string"},
                        "pattern": {"type": "string"},
                        "top_level_dir": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="python.run_unittest",
            ),
            ToolRoute(
                name="python.run_compileall",
                description="Run allowlisted Python compileall checks inside the bounded workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="python.run_compileall",
            ),
            ToolRoute(
                name="sysops.git_status",
                description="Run a read-only allowlisted git status summary inside the bounded workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="sysops.git_status",
            ),
            ToolRoute(
                name="sysops.git_diff_summary",
                description="Run a read-only allowlisted git diff --stat summary inside the bounded workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "cached": {"type": "boolean"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="sysops.git_diff_summary",
            ),
            ToolRoute(
                name="sysops.git_repo_summary",
                description="Run a read-only allowlisted git repo summary inside the bounded workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="sysops.git_repo_summary",
            ),
            ToolRoute(
                name="sysops.git_recent_commits",
                description="Read a bounded recent git commit list inside the workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1},
                        "ref": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="execution",
                action="sysops.git_recent_commits",
            ),
            ToolRoute(
                name="inference.describe_loops",
                description="Describe the registered inference loop cartridges and the active default loop slot.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                manager="inference",
                action="inference.describe_loops",
            ),
            ToolRoute(
                name="ollama.chat_json",
                description="Run the active or requested inference loop cartridge and return a parsed JSON object response.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "loop_name": {"type": "string"},
                        "model": {"type": "string"},
                        "system": {"type": "string"},
                        "user": {"type": "string"},
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["role", "content"],
                                "additionalProperties": False,
                            },
                        },
                        "json_schema": {"type": "object"},
                        "temperature": {"type": "number"},
                        "max_tokens": {"type": "integer", "minimum": 1},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="inference",
                action="ollama.chat_json",
            ),
            ToolRoute(
                name="ollama.chat_text",
                description="Run the active or requested inference loop cartridge and return a text response.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "loop_name": {"type": "string"},
                        "model": {"type": "string"},
                        "system": {"type": "string"},
                        "user": {"type": "string"},
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["role", "content"],
                                "additionalProperties": False,
                            },
                        },
                        "temperature": {"type": "number"},
                        "max_tokens": {"type": "integer", "minimum": 1},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="inference",
                action="ollama.chat_text",
            ),
            ToolRoute(
                name="ollama.list_models",
                description="List locally available Ollama models from the local Ollama service.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                manager="inference",
                action="ollama.list_models",
            ),
            ToolRoute(
                name="journal.append",
                description="Append a phase journal entry to the app journal surfaces.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "files_changed": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "array", "items": {"type": "string"}},
                        "testing": {"type": "array", "items": {"type": "string"}},
                        "backlog": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "summary"],
                    "additionalProperties": False,
                },
                manager="memory",
                action="journal.append",
            ),
            ToolRoute(
                name="tasklist.replace",
                description="Replace the current builder tasklist with a bounded ordered list.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                    },
                                },
                                "required": ["text", "status"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
                manager="memory",
                action="tasklist.replace",
            ),
            ToolRoute(
                name="tasklist.view",
                description="Read the current builder tasklist mirror and SQLite records.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                manager="memory",
                action="tasklist.view",
            ),
        ]

        for route in routes:
            self._tool_registry.register(route)

    def refresh_extension_tools(self) -> dict[str, object]:
        static_tool_names = set(self._tool_registry.tool_names()) - self._dynamic_tool_names
        routes, result = self._extension_tool_component.refresh_extensions(
            reserved_tool_names=static_tool_names
        )

        for tool_name in list(self._dynamic_tool_names):
            self._tool_registry.unregister(tool_name)

        self._dynamic_tool_names = set()
        for route in routes:
            self._tool_registry.register(route)
            self._dynamic_tool_names.add(route.name)

        return {
            **result,
            "active_extension_tool_names": sorted(self._dynamic_tool_names),
        }
