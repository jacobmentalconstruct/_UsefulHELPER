from __future__ import annotations

import json
from typing import BinaryIO

from ..models.protocol import JsonRpcError, error_response, extract_request_error
from ..orchestrators.mcp_orchestrator import McpOrchestrator
from .graph_engine import GraphEngine
from .messages import Message
from .transports import build_transport


class McpServer:
    """JSON-RPC server loop over NDJSON or Content-Length framing."""

    def __init__(self, graph_engine: GraphEngine, orchestrator: McpOrchestrator) -> None:
        self._graph_engine = graph_engine
        self._orchestrator = orchestrator

    def serve(
        self,
        stdin_stream: BinaryIO,
        stdout_stream: BinaryIO,
        transport_mode: str,
    ) -> int:
        transport = build_transport(
            transport_mode=transport_mode,
            input_stream=stdin_stream,
            output_stream=stdout_stream,
        )
        request_count = 0

        while True:
            try:
                payload = transport.read_message()
            except json.JSONDecodeError as error:
                transport.write_message(
                    error_response(None, JsonRpcError(code=-32700, message=str(error)))
                )
                continue
            except ValueError as error:
                transport.write_message(
                    error_response(None, JsonRpcError(code=-32700, message=str(error)))
                )
                continue

            if payload is None:
                return request_count

            request_count += 1
            request_error = extract_request_error(payload)
            if request_error is not None:
                request_id = payload.get("id") if isinstance(payload, dict) else None
                transport.write_message(error_response(request_id, request_error))
                continue

            response = self._graph_engine.dispatch(
                Message(
                    sender="app",
                    target=self._orchestrator.node_id,
                    action="rpc.request",
                    payload={"request": payload},
                )
            )
            transport.write_message(response["rpc_response"])
