from __future__ import annotations

import json
from typing import Any

from ..models.inference import (
    InferenceLoopCartridge,
    InferenceLoopRequest,
    InferenceResponseFormat,
)


class InferenceLoopService:
    """Owns loop-cartridge registration, slot selection, and normalized requests."""

    def __init__(self) -> None:
        self._cartridges: dict[str, InferenceLoopCartridge] = {}
        self._default_loop_name: str | None = None

    def register_cartridge(
        self,
        cartridge: InferenceLoopCartridge,
        *,
        is_default: bool = False,
    ) -> None:
        self._cartridges[cartridge.loop_name] = cartridge
        if is_default or self._default_loop_name is None:
            self._default_loop_name = cartridge.loop_name

    @property
    def default_loop_name(self) -> str:
        if self._default_loop_name is None:
            raise RuntimeError("No inference loop cartridges have been registered.")
        return self._default_loop_name

    def describe_loops(self) -> dict[str, Any]:
        active_default = self.default_loop_name
        loops = []
        for cartridge in self._cartridges.values():
            loops.append(
                {
                    "loop_name": cartridge.loop_name,
                    "provider": cartridge.provider,
                    "description": cartridge.description,
                    "supported_formats": list(cartridge.supported_formats),
                    "is_default": cartridge.loop_name == active_default,
                }
            )
        return {
            "default_loop_name": active_default,
            "loop_count": len(loops),
            "loops": sorted(loops, key=lambda item: str(item["loop_name"])),
        }

    def run_from_arguments(
        self,
        arguments: dict[str, object],
        *,
        response_format: InferenceResponseFormat,
        default_model: str,
    ) -> dict[str, Any]:
        request = self.build_request(
            arguments,
            response_format=response_format,
            default_model=default_model,
        )
        cartridge = self.get_cartridge(request.loop_name)
        if request.response_format not in cartridge.supported_formats:
            raise ValueError(
                f"Loop cartridge '{request.loop_name}' does not support "
                f"'{request.response_format}' responses."
            )
        return cartridge.run(request).to_payload()

    def build_request(
        self,
        arguments: dict[str, object],
        *,
        response_format: InferenceResponseFormat,
        default_model: str,
    ) -> InferenceLoopRequest:
        loop_name = str(arguments.get("loop_name", self.default_loop_name)).strip()
        model = str(arguments.get("model", default_model)).strip()
        if not model:
            raise ValueError("A model name is required.")

        temperature = float(arguments.get("temperature", 0.2))
        max_tokens = int(arguments.get("max_tokens", 600))
        timeout_seconds = int(arguments.get("timeout_seconds", 90))
        messages = self._build_messages(arguments)
        metadata = {
            "message_count": len(messages),
            "requested_loop_name": loop_name,
        }

        return InferenceLoopRequest(
            loop_name=loop_name,
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            metadata=metadata,
        )

    def get_cartridge(self, loop_name: str) -> InferenceLoopCartridge:
        try:
            return self._cartridges[loop_name]
        except KeyError as error:
            known = ", ".join(sorted(self._cartridges))
            raise ValueError(
                f"Unknown inference loop '{loop_name}'. Known loops: {known or 'none'}."
            ) from error

    def _build_messages(self, arguments: dict[str, object]) -> list[dict[str, str]]:
        json_schema = arguments.get("json_schema")
        system = str(arguments.get("system", "")).strip()
        user = str(arguments.get("user", "")).strip()
        raw_messages = arguments.get("messages")

        messages: list[dict[str, str]] = []
        if isinstance(raw_messages, list):
            for item in raw_messages:
                if not isinstance(item, dict):
                    raise ValueError("Each message entry must be an object with role and content.")
                role = str(item.get("role", "")).strip()
                content = str(item.get("content", "")).strip()
                if not role or not content:
                    raise ValueError("Each message entry must include role and content.")
                messages.append({"role": role, "content": content})

        if not messages:
            if not user:
                raise ValueError("Either 'messages' or 'user' must be provided.")
            if system:
                messages.append({"role": "system", "content": system})
            if json_schema is not None:
                schema_text = json.dumps(json_schema, indent=2, sort_keys=True)
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Return only a single JSON object that matches this schema as closely as possible:\n"
                            f"{schema_text}"
                        ),
                    }
                )
            messages.append({"role": "user", "content": user})

        return messages
