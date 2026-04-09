from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JsonRpcError:
    """Structured JSON-RPC error payload."""

    code: int
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            payload["data"] = self.data
        return payload


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def error_response(request_id: Any, error: JsonRpcError) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error.to_dict(),
    }


def extract_request_error(payload: Any) -> JsonRpcError | None:
    """Return a structured error when a request is not valid JSON-RPC."""

    if not isinstance(payload, dict):
        return JsonRpcError(code=-32600, message="Request must be a JSON object.")

    if payload.get("jsonrpc") != "2.0":
        return JsonRpcError(code=-32600, message="Only JSON-RPC 2.0 requests are supported.")

    if "method" not in payload or not isinstance(payload["method"], str):
        return JsonRpcError(code=-32600, message="Request method must be a string.")

    params = payload.get("params", {})
    if params is not None and not isinstance(params, dict):
        return JsonRpcError(code=-32602, message="Request params must be an object when provided.")

    return None
