from __future__ import annotations

from ..components.archive_component import ArchiveComponent
from ..components.ast_component import AstComponent
from ..components.extension_tool_component import ExtensionToolComponent
from ..components.filesystem_component import FilesystemComponent
from ..components.intake_component import IntakeComponent
from ..components.parts_catalog_component import PartsCatalogComponent
from ..components.sandbox_component import SandboxComponent
from ..components.scaffold_component import ScaffoldComponent
from ..components.sidecar_component import SidecarComponent
from ..runtime.messages import Message
from ..runtime.nodes import GraphNode


class WorkspaceManager(GraphNode):
    """Coordinates bounded workspace-facing tool domains."""

    def __init__(
        self,
        archive_component: ArchiveComponent,
        extension_tool_component: ExtensionToolComponent,
        filesystem_component: FilesystemComponent,
        intake_component: IntakeComponent,
        parts_catalog_component: PartsCatalogComponent,
        scaffold_component: ScaffoldComponent,
        sidecar_component: SidecarComponent,
        ast_component: AstComponent,
        sandbox_component: SandboxComponent,
    ) -> None:
        super().__init__(node_id="core.workspace_manager", node_type="manager")
        self._archive_component = archive_component
        self._extension_tool_component = extension_tool_component
        self._filesystem_component = filesystem_component
        self._intake_component = intake_component
        self._parts_catalog_component = parts_catalog_component
        self._scaffold_component = scaffold_component
        self._sidecar_component = sidecar_component
        self._ast_component = ast_component
        self._sandbox_component = sandbox_component

    def receive(self, message: Message) -> dict[str, object]:
        arguments = message.payload.get("arguments", {})
        self.local_state["last_action"] = message.action

        if message.action == "archive.inspect_zip":
            result = self._archive_component.inspect_zip(
                archive_path=str(arguments["archive_path"]),
                max_entries=int(arguments.get("max_entries", 500)),
            )
        elif message.action == "archive.extract_zip":
            result = self._archive_component.extract_zip(
                archive_path=str(arguments["archive_path"]),
                target_dir=str(arguments["target_dir"]),
                mode=str(arguments.get("mode", "create_only")),
            )
        elif message.action == "extension.run":
            result = self._extension_tool_component.invoke_tool(
                tool_name=str(message.payload["route_name"]),
                arguments=dict(arguments),
            )
        elif message.action == "intake.zip_to_sandbox":
            result = self._intake_component.ingest_zip_to_sandbox(
                archive_path=str(arguments["archive_path"]),
                target_dir=str(arguments["target_dir"]),
                mode=str(arguments.get("mode", "overwrite")),
                reset_sandbox=bool(arguments.get("reset_sandbox", False)),
                max_files=int(arguments.get("max_files", 1000)),
                inspect_max_entries=int(arguments.get("inspect_max_entries", 500)),
            )
        elif message.action == "parts.catalog_build":
            result = self._parts_catalog_component.build_catalog(
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                reset=bool(arguments.get("reset", True)),
                max_files=int(arguments.get("max_files", 2000)),
            )
        elif message.action == "parts.catalog_search":
            result = self._parts_catalog_component.search_parts(
                query=str(arguments["query"]),
                kinds=(
                    None
                    if arguments.get("kinds") is None
                    else list(arguments.get("kinds", []))
                ),
                layers=(
                    None
                    if arguments.get("layers") is None
                    else list(arguments.get("layers", []))
                ),
                path_prefixes=(
                    None
                    if arguments.get("path_prefixes") is None
                    else list(arguments.get("path_prefixes", []))
                ),
                intent_target=str(arguments.get("intent_target", "auto")),
                prefer_code=bool(arguments.get("prefer_code", False)),
                prefer_docs=bool(arguments.get("prefer_docs", False)),
                limit=int(arguments.get("limit", 50)),
            )
        elif message.action == "parts.catalog_get":
            result = self._parts_catalog_component.get_parts(
                part_ids=list(arguments.get("part_ids", [])),
                max_chars_per_part=int(arguments.get("max_chars_per_part", 20000)),
            )
        elif message.action == "parts.export_selection":
            result = self._parts_catalog_component.export_selection(
                part_ids=list(arguments.get("part_ids", [])),
                target_dir=str(arguments["target_dir"]),
                mode=str(arguments.get("mode", "overwrite")),
            )
        elif message.action == "fs.list_tree":
            result = self._filesystem_component.list_tree(
                path=str(arguments.get("path", ".")),
                max_depth=int(arguments.get("max_depth", 4)),
            )
        elif message.action == "fs.make_tree":
            result = self._filesystem_component.make_tree(
                directories=list(arguments.get("directories", []))
            )
        elif message.action == "fs.read_files":
            result = self._filesystem_component.read_files(
                paths=list(arguments.get("paths", [])),
                max_chars_per_file=int(arguments.get("max_chars_per_file", 20000)),
            )
        elif message.action == "fs.write_files":
            result = self._filesystem_component.write_files(
                files=list(arguments.get("files", [])),
                mode=str(arguments.get("mode", "overwrite")),
            )
        elif message.action == "fs.patch_text":
            result = self._filesystem_component.patch_text(
                changes=list(arguments.get("changes", []))
            )
        elif message.action == "fs.search_text":
            result = self._filesystem_component.search_text(
                pattern=str(arguments["pattern"]),
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                max_results=int(arguments.get("max_results", 100)),
                case_sensitive=bool(arguments.get("case_sensitive", False)),
            )
        elif message.action == "project.scaffold_from_manifest":
            result = self._scaffold_component.scaffold_from_manifest(
                directories=list(arguments.get("directories", [])),
                files=list(arguments.get("files", [])),
                mode=str(arguments.get("mode", "create_only")),
            )
        elif message.action == "worker.create_tool_scaffold":
            result = self._scaffold_component.create_tool_scaffold(
                tool_name=str(arguments["tool_name"]),
                description=str(arguments["description"]),
                manager=str(arguments["manager"]),
                action=str(arguments["action"]),
            )
        elif message.action == "sidecar.export_bundle":
            result = self._sidecar_component.export_bundle(
                target_dir=str(arguments["target_dir"]),
                include_tests=bool(arguments.get("include_tests", False)),
                overwrite=bool(arguments.get("overwrite", False)),
                dry_run=bool(arguments.get("dry_run", False)),
                reinstall=bool(arguments.get("reinstall", False)),
            )
        elif message.action == "ast.scan_python":
            result = self._ast_component.scan_python(
                paths=list(arguments.get("paths", [])),
                max_files=int(arguments.get("max_files", 100)),
                max_symbols_per_file=int(arguments.get("max_symbols_per_file", 100)),
            )
        elif message.action == "sandbox.init":
            result = self._sandbox_component.initialize(
                reset=bool(arguments.get("reset", False))
            )
        elif message.action == "sandbox.ingest_workspace":
            result = self._sandbox_component.ingest_workspace(
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                max_files=int(arguments.get("max_files", 1000)),
            )
        elif message.action == "sandbox.read_head":
            result = self._sandbox_component.read_head(
                paths=list(arguments.get("paths", [])),
                max_chars_per_file=int(arguments.get("max_chars_per_file", 20000)),
            )
        elif message.action == "sandbox.search_head":
            result = self._sandbox_component.search_head(
                pattern=str(arguments["pattern"]),
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                max_results=int(arguments.get("max_results", 100)),
                case_sensitive=bool(arguments.get("case_sensitive", False)),
            )
        elif message.action == "sandbox.stage_diff":
            result = self._sandbox_component.stage_diff(
                changes=list(arguments.get("changes", []))
            )
        elif message.action == "sandbox.export_head":
            result = self._sandbox_component.export_head(
                target_dir=str(arguments["target_dir"]),
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                mode=str(arguments.get("mode", "overwrite")),
            )
        elif message.action == "sandbox.history_for_file":
            result = self._sandbox_component.history_for_file(
                path=str(arguments["path"]),
                limit=int(arguments.get("limit", 20)),
            )
        elif message.action == "sandbox.query_symbols":
            result = self._sandbox_component.query_symbols(
                paths=(
                    None
                    if arguments.get("paths") is None
                    else list(arguments.get("paths", []))
                ),
                kinds=(
                    None
                    if arguments.get("kinds") is None
                    else list(arguments.get("kinds", []))
                ),
                name_contains=(
                    None
                    if arguments.get("name_contains") is None
                    else str(arguments.get("name_contains"))
                ),
                limit=int(arguments.get("limit", 200)),
            )
        else:
            raise ValueError(f"Unsupported workspace action '{message.action}'.")

        return {
            "text": f"Workspace action '{message.action}' completed.",
            "structured_content": result,
            "is_error": False,
        }
