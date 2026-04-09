from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from library.microservices.structure._PythonChunkerMS import PythonChunkerMS
from library.microservices.structure._TextChunkerMS import TextChunkerMS

from lib.reference_utils import PROSE_EXTENSIONS, char_range_from_lines, summarize_text


@dataclass
class ProviderManifest:
    provider_id: str
    schema_version: str
    provider_kind: str
    strategy: str
    priority: int
    entrypoint: str
    supported_extensions: list[str]
    supported_media_types: list[str]
    healthcheck: str
    timeout_sec: int
    enabled: bool
    version: str


@dataclass
class ProviderRequest:
    request_id: str
    strategy_hint: str
    logical_path: str
    media_type: str
    extension: str
    content_hash: str
    text_path: str | None
    blob_path: str | None
    max_chars: int
    overlap_chars: int
    metadata: dict[str, Any]


@dataclass
class ProviderSection:
    section_id: str
    parent_section_id: str | None
    ordinal: int
    depth: int
    section_kind: str
    anchor_path: str
    title: str
    summary: str
    exact_text: str
    char_start: int
    char_end: int
    source_span: dict[str, Any]
    metadata: dict[str, Any]


@dataclass
class ProviderResult:
    provider_id: str
    provider_kind: str
    provider_version: str
    strategy_used: str
    status: str
    warnings: list[str]
    sections: list[ProviderSection]


class BaseProvider:
    def __init__(self, manifest: ProviderManifest):
        self.manifest = manifest

    def health(self) -> dict[str, Any]:
        return {"status": "online", "provider_id": self.manifest.provider_id}

    def parse(self, request: ProviderRequest, text: str) -> ProviderResult:
        raise NotImplementedError


class PythonAstProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            ProviderManifest(
                provider_id="python_ast_provider",
                schema_version="1.0",
                provider_kind="python_provider",
                strategy="tree_splitter",
                priority=100,
                entrypoint="vendor/library/microservices/structure/_PythonChunkerMS.py:PythonChunkerMS.chunk",
                supported_extensions=[".py"],
                supported_media_types=["text/x-python", "text/plain"],
                healthcheck="PythonChunkerMS.get_health",
                timeout_sec=15,
                enabled=True,
                version="1.2.0",
            )
        )
        self._service = PythonChunkerMS()

    def health(self) -> dict[str, Any]:
        return self._service.get_health()

    def parse(self, request: ProviderRequest, text: str) -> ProviderResult:
        chunks = self._service.chunk(content=text)
        sections: list[ProviderSection] = []
        for index, chunk in enumerate(chunks, start=1):
            start_line = int(chunk.get("start_line", 1))
            end_line = int(chunk.get("end_line", start_line))
            char_start, char_end = char_range_from_lines(text, start_line, end_line)
            exact_text = chunk.get("content", text[char_start:char_end])
            title = str(chunk.get("name", f"chunk-{index}"))
            summary = summarize_text(chunk.get("docstring", "") or exact_text)
            sections.append(
                ProviderSection(
                    section_id=f"{request.request_id}:section:{index}",
                    parent_section_id=None,
                    ordinal=index,
                    depth=1,
                    section_kind=str(chunk.get("type", "python_block")),
                    anchor_path=f"python/{title}",
                    title=title,
                    summary=summary,
                    exact_text=exact_text,
                    char_start=char_start,
                    char_end=char_end,
                    source_span={"start_line": start_line, "end_line": end_line},
                    metadata={
                        "docstring": chunk.get("docstring", ""),
                        "logical_path": request.logical_path,
                    },
                )
            )
        return ProviderResult(
            provider_id=self.manifest.provider_id,
            provider_kind=self.manifest.provider_kind,
            provider_version=self.manifest.version,
            strategy_used=self.manifest.strategy,
            status="ok",
            warnings=[],
            sections=sections,
        )


class ProseMicroserviceProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            ProviderManifest(
                provider_id="prose_paragraph_provider",
                schema_version="1.0",
                provider_kind="microservice_provider",
                strategy="peg_document",
                priority=50,
                entrypoint="vendor/library/microservices/structure/_TextChunkerMS.py:TextChunkerMS.chunk_by_paragraphs",
                supported_extensions=sorted(PROSE_EXTENSIONS),
                supported_media_types=["text/plain", "text/markdown", "text/x-rst"],
                healthcheck="TextChunkerMS.get_health",
                timeout_sec=15,
                enabled=True,
                version="1.0.0",
            )
        )
        self._service = TextChunkerMS()

    def health(self) -> dict[str, Any]:
        return self._service.get_health()

    def parse(self, request: ProviderRequest, text: str) -> ProviderResult:
        overlap = 1 if request.overlap_chars > 0 else 0
        raw_chunks = self._service.chunk_by_paragraphs(
            text=text,
            target_chars=max(200, request.max_chars),
            overlap_paragraphs=overlap,
        )
        sections: list[ProviderSection] = []
        search_start = 0
        for index, chunk in enumerate(raw_chunks, start=1):
            lookup_start = max(0, search_start - min(len(chunk), request.overlap_chars))
            char_start = text.find(chunk, lookup_start)
            if char_start < 0:
                char_start = text.find(chunk)
            if char_start < 0:
                char_start = search_start
            char_end = min(len(text), char_start + len(chunk))
            search_start = char_end
            heading = chunk.splitlines()[0].strip() if chunk.strip() else f"chunk-{index}"
            if heading.startswith("#"):
                heading = heading.lstrip("#").strip() or f"section-{index}"
            sections.append(
                ProviderSection(
                    section_id=f"{request.request_id}:section:{index}",
                    parent_section_id=None,
                    ordinal=index,
                    depth=1,
                    section_kind="prose_chunk",
                    anchor_path=f"prose/{index}",
                    title=heading[:120] or f"section-{index}",
                    summary=summarize_text(chunk),
                    exact_text=chunk,
                    char_start=char_start,
                    char_end=char_end,
                    source_span={"kind": "paragraph_window", "index": index},
                    metadata={"logical_path": request.logical_path},
                )
            )
        return ProviderResult(
            provider_id=self.manifest.provider_id,
            provider_kind=self.manifest.provider_kind,
            provider_version=self.manifest.version,
            strategy_used=self.manifest.strategy,
            status="ok",
            warnings=[],
            sections=sections,
        )


class FallbackChunkProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            ProviderManifest(
                provider_id="readable_text_fallback_provider",
                schema_version="1.0",
                provider_kind="microservice_provider",
                strategy="fallback_chunker",
                priority=10,
                entrypoint="vendor/library/microservices/structure/_TextChunkerMS.py:TextChunkerMS.chunk_by_lines",
                supported_extensions=[],
                supported_media_types=["text/plain"],
                healthcheck="TextChunkerMS.get_health",
                timeout_sec=15,
                enabled=True,
                version="1.0.0",
            )
        )
        self._service = TextChunkerMS()

    def health(self) -> dict[str, Any]:
        return self._service.get_health()

    def parse(self, request: ProviderRequest, text: str) -> ProviderResult:
        max_lines = max(20, request.max_chars // 90)
        raw_chunks = self._service.chunk_by_lines(
            text=text,
            max_lines=max_lines,
            max_chars=max(200, request.max_chars),
        )
        sections: list[ProviderSection] = []
        for index, chunk in enumerate(raw_chunks, start=1):
            start_line = int(chunk.get("start_line", 1))
            end_line = int(chunk.get("end_line", start_line))
            char_start, char_end = char_range_from_lines(text, start_line, end_line)
            exact_text = str(chunk.get("text", text[char_start:char_end]))
            sections.append(
                ProviderSection(
                    section_id=f"{request.request_id}:section:{index}",
                    parent_section_id=None,
                    ordinal=index,
                    depth=1,
                    section_kind="line_chunk",
                    anchor_path=f"lines/{start_line}-{end_line}",
                    title=f"Lines {start_line}-{end_line}",
                    summary=summarize_text(exact_text),
                    exact_text=exact_text,
                    char_start=char_start,
                    char_end=char_end,
                    source_span={"start_line": start_line, "end_line": end_line},
                    metadata={"logical_path": request.logical_path},
                )
            )
        return ProviderResult(
            provider_id=self.manifest.provider_id,
            provider_kind=self.manifest.provider_kind,
            provider_version=self.manifest.version,
            strategy_used=self.manifest.strategy,
            status="ok",
            warnings=[],
            sections=sections,
        )


class ProviderRegistry:
    def __init__(self, providers: list[BaseProvider] | None = None) -> None:
        self.providers = providers or [
            PythonAstProvider(),
            ProseMicroserviceProvider(),
            FallbackChunkProvider(),
        ]
        self._provider_map = {provider.manifest.provider_id: provider for provider in self.providers}

    def manifests(self) -> list[dict[str, Any]]:
        return [asdict(provider.manifest) for provider in self.providers]

    def validate(self) -> None:
        for provider in self.providers:
            if not provider.manifest.enabled:
                continue
            health = provider.health()
            if str(health.get("status", "")).lower() not in {"online", "ok"}:
                raise RuntimeError(
                    f"Provider {provider.manifest.provider_id} is unavailable: {health}"
                )

    def _supports(self, provider: BaseProvider, extension: str, media_type: str) -> bool:
        manifest = provider.manifest
        if extension and extension.lower() in {item.lower() for item in manifest.supported_extensions}:
            return True
        if media_type and media_type.lower() in {item.lower() for item in manifest.supported_media_types}:
            return True
        return False

    def select(self, request: ProviderRequest, readable_text: bool) -> BaseProvider | None:
        enabled = [provider for provider in self.providers if provider.manifest.enabled]
        candidates = sorted(enabled, key=lambda item: item.manifest.priority, reverse=True)

        for provider in candidates:
            if provider.manifest.strategy == "tree_splitter" and self._supports(
                provider, request.extension, request.media_type
            ):
                return provider

        if request.extension.lower() in PROSE_EXTENSIONS or request.media_type in {
            "text/plain",
            "text/markdown",
            "text/x-rst",
        }:
            for provider in candidates:
                if provider.manifest.strategy == "peg_document":
                    return provider

        if readable_text:
            for provider in candidates:
                if provider.manifest.strategy == "fallback_chunker":
                    return provider

        return None

    def get(self, provider_id: str) -> BaseProvider | None:
        return self._provider_map.get(provider_id)
