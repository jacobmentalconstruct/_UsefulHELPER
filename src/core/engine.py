from __future__ import annotations

from .components.archive_component import ArchiveComponent
from .components.ast_component import AstComponent
from .components.builder_memory_component import BuilderMemoryComponent
from .components.capability_component import CapabilityComponent
from .components.execution_component import ExecutionComponent
from .components.extension_tool_component import ExtensionToolComponent
from .components.extensions.ollama_chat_json_component import OllamaChatJsonComponent
from .components.extensions.ollama_inference_loop_cartridge import (
    OllamaSingleTurnLoopCartridge,
)
from .components.filesystem_component import FilesystemComponent
from .components.intake_component import IntakeComponent
from .components.parts_catalog_component import PartsCatalogComponent
from .components.sandbox_component import SandboxComponent
from .components.scaffold_component import ScaffoldComponent
from .components.sidecar_component import SidecarComponent
from .managers.execution_manager import ExecutionManager
from .managers.inference_manager import InferenceManager
from .managers.memory_manager import MemoryManager
from .managers.workspace_manager import WorkspaceManager
from .orchestrators.mcp_orchestrator import McpOrchestrator
from .runtime.graph_engine import GraphEngine
from .runtime.mcp_server import McpServer
from .runtime.sqlite_logger import SQLiteEventLogger
from .runtime.tool_registry import ToolRegistry
from .services.archive_intake_service import ArchiveIntakeService
from .services.archive_service import ArchiveService
from .services.extension_tool_service import ExtensionToolService
from .services.inference_loop_service import InferenceLoopService
from .services.journal_store import JournalStore
from .services.ollama_service import OllamaService
from .services.parts_catalog_store import PartsCatalogStore
from .services.python_runtime_service import PythonRuntimeService
from .services.root_guard import RootGuard
from .services.sandbox_store import SandboxStore
from .services.sysops_service import SysopsService
from ..config import AppConfig


class ApplicationEngine:
    """Builds the core runtime graph and runs the server loop."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._event_logger = SQLiteEventLogger(config.runtime_db_path)
        self._graph_engine = GraphEngine(self._event_logger)
        self._root_guard = RootGuard(config.workspace_root)
        self._journal_store = JournalStore(
            db_path=config.journal_db_path,
            entries_dir=config.journal_entries_dir,
            backlog_path=config.journal_backlog_path,
            tasklist_path=config.journal_tasklist_path,
        )
        self._registry = ToolRegistry()

        archive_service = ArchiveService(self._root_guard)
        archive_component = ArchiveComponent(archive_service)
        filesystem_component = FilesystemComponent(self._root_guard)
        parts_catalog_store = PartsCatalogStore(self._config.parts_db_path, self._root_guard)
        parts_catalog_component = PartsCatalogComponent(parts_catalog_store)
        scaffold_component = ScaffoldComponent(filesystem_component)
        sidecar_component = SidecarComponent(self._config, self._root_guard)
        ast_component = AstComponent(self._root_guard)
        builder_memory_component = BuilderMemoryComponent(self._journal_store)
        capability_component = CapabilityComponent(self._config, self._registry)
        extension_tool_service = ExtensionToolService(self._config.project_root)
        extension_tool_component = ExtensionToolComponent(extension_tool_service)
        ollama_service = OllamaService()
        ollama_component = OllamaChatJsonComponent(ollama_service)
        inference_loop_service = InferenceLoopService()
        inference_loop_service.register_cartridge(
            OllamaSingleTurnLoopCartridge(ollama_service),
            is_default=True,
        )
        python_runtime_service = PythonRuntimeService(self._root_guard)
        sysops_service = SysopsService(self._root_guard)
        execution_component = ExecutionComponent(python_runtime_service, sysops_service)
        sandbox_store = SandboxStore(self._config.sandbox_db_path, self._root_guard)
        sandbox_component = SandboxComponent(sandbox_store)
        archive_intake_service = ArchiveIntakeService(
            archive_service,
            sandbox_store,
            self._root_guard,
        )
        intake_component = IntakeComponent(archive_intake_service)

        self._workspace_manager = WorkspaceManager(
            archive_component=archive_component,
            extension_tool_component=extension_tool_component,
            filesystem_component=filesystem_component,
            intake_component=intake_component,
            parts_catalog_component=parts_catalog_component,
            scaffold_component=scaffold_component,
            sidecar_component=sidecar_component,
            ast_component=ast_component,
            sandbox_component=sandbox_component,
        )
        self._inference_manager = InferenceManager(
            ollama_component=ollama_component,
            inference_loop_service=inference_loop_service,
        )
        self._execution_manager = ExecutionManager(
            execution_component=execution_component,
        )
        self._memory_manager = MemoryManager(
            builder_memory_component=builder_memory_component,
            extension_tool_component=extension_tool_component,
        )
        self._orchestrator = McpOrchestrator(
            config=self._config,
            tool_registry=self._registry,
            capability_component=capability_component,
            extension_tool_component=extension_tool_component,
            workspace_manager=self._workspace_manager,
            execution_manager=self._execution_manager,
            inference_manager=self._inference_manager,
            memory_manager=self._memory_manager,
        )
        self._server = McpServer(
            graph_engine=self._graph_engine,
            orchestrator=self._orchestrator,
        )
        self._started = False

    @property
    def event_logger(self) -> SQLiteEventLogger:
        return self._event_logger

    @property
    def journal_store(self) -> JournalStore:
        return self._journal_store

    def start(self) -> None:
        if self._started:
            return

        self._event_logger.ensure_schema()
        self._journal_store.ensure_schema()
        self._orchestrator.bootstrap(self._graph_engine)
        self._orchestrator.refresh_extension_tools()
        self._started = True

    def serve(self, stdin_stream, stdout_stream, transport_mode: str) -> int:
        if not self._started:
            raise RuntimeError("ApplicationEngine must be started before serving.")
        return self._server.serve(
            stdin_stream=stdin_stream,
            stdout_stream=stdout_stream,
            transport_mode=transport_mode,
        )
