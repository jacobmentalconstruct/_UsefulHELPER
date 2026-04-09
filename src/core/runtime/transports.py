from __future__ import annotations

import json
from io import BufferedReader, BufferedWriter
from typing import Any


class BaseTransport:
    """Binary transport wrapper for framed JSON messages."""

    name = "base"

    def __init__(self, input_stream: BufferedReader, output_stream: BufferedWriter) -> None:
        self._input_stream = input_stream
        self._output_stream = output_stream

    def read_message(self) -> dict[str, Any] | None:
        raise NotImplementedError

    def write_message(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class NdjsonTransport(BaseTransport):
    name = "ndjson"

    def read_message(self) -> dict[str, Any] | None:
        while True:
            line = self._input_stream.readline()
            if not line:
                return None
            stripped = line.strip()
            if not stripped:
                continue
            return json.loads(stripped.decode("utf-8"))

    def write_message(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self._output_stream.write(encoded + b"\n")
        self._output_stream.flush()


class ContentLengthTransport(BaseTransport):
    name = "content-length"

    def read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}

        while True:
            line = self._input_stream.readline()
            if not line:
                return None if not headers else None
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8").strip()
            if ":" not in decoded:
                raise ValueError(f"Invalid header line '{decoded}'.")
            name, value = decoded.split(":", 1)
            headers[name.strip().lower()] = value.strip()

        if "content-length" not in headers:
            raise ValueError("Missing Content-Length header.")

        content_length = int(headers["content-length"])
        body = self._input_stream.read(content_length)
        if len(body) != content_length:
            raise ValueError("Incomplete content-length frame.")
        return json.loads(body.decode("utf-8"))

    def write_message(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("utf-8")
        self._output_stream.write(header)
        self._output_stream.write(encoded)
        self._output_stream.flush()


def detect_transport(input_stream: BufferedReader) -> str:
    """Detect framing from the first buffered bytes."""

    preview = input_stream.peek(64).lstrip()
    if preview.startswith(b"Content-Length:"):
        return "content-length"
    return "ndjson"


def build_transport(
    transport_mode: str,
    input_stream: BufferedReader,
    output_stream: BufferedWriter,
) -> BaseTransport:
    effective_mode = transport_mode
    if transport_mode == "auto":
        effective_mode = detect_transport(input_stream)

    if effective_mode == "ndjson":
        return NdjsonTransport(input_stream, output_stream)

    if effective_mode == "content-length":
        return ContentLengthTransport(input_stream, output_stream)

    raise ValueError(f"Unsupported transport mode '{transport_mode}'.")
