from __future__ import annotations

from ..components.extensions.ollama_chat_json_component import OllamaChatJsonComponent
from ..runtime.messages import Message
from ..runtime.nodes import GraphNode
from ..services.inference_loop_service import InferenceLoopService


class InferenceManager(GraphNode):
    """Coordinates bounded local-model inference actions."""

    def __init__(
        self,
        ollama_component: OllamaChatJsonComponent,
        inference_loop_service: InferenceLoopService,
    ) -> None:
        super().__init__(node_id="core.inference_manager", node_type="manager")
        self._ollama_component = ollama_component
        self._inference_loop_service = inference_loop_service

    def receive(self, message: Message) -> dict[str, object]:
        arguments = message.payload.get("arguments", {})
        self.local_state["last_action"] = message.action

        if message.action == "ollama.chat_json":
            result = self._inference_loop_service.run_from_arguments(
                arguments,
                response_format="json",
                default_model="qwen3.5:4b",
            )
        elif message.action == "ollama.chat_text":
            result = self._inference_loop_service.run_from_arguments(
                arguments,
                response_format="text",
                default_model="qwen3.5:4b",
            )
        elif message.action == "ollama.list_models":
            result = self._ollama_component.ollama_list_models(arguments)
        elif message.action == "inference.describe_loops":
            result = self._inference_loop_service.describe_loops()
        else:
            raise ValueError(f"Unsupported inference action '{message.action}'.")

        return {
            "text": f"Inference action '{message.action}' completed.",
            "structured_content": result,
            "is_error": False,
        }
