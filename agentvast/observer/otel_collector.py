"""Minimal OTLP/HTTP receiver that preserves every request before decoding."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from agentvast.observer.store import (
    append_raw_event,
    record_observer_error,
    update_manifest,
)


def _protobuf_type(path: str) -> Optional[Tuple[Any, Any]]:
    try:
        from google.protobuf.json_format import MessageToDict

        if path.endswith("/v1/logs"):
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
                ExportLogsServiceRequest,
            )

            return ExportLogsServiceRequest, MessageToDict
        if path.endswith("/v1/traces"):
            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
                ExportTraceServiceRequest,
            )

            return ExportTraceServiceRequest, MessageToDict
        if path.endswith("/v1/metrics"):
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
                ExportMetricsServiceRequest,
            )

            return ExportMetricsServiceRequest, MessageToDict
    except (ImportError, ModuleNotFoundError):
        return None
    return None


def decode_available() -> bool:
    return _protobuf_type("/v1/logs") is not None


def record_otel_request(
    session_id: str,
    path: str,
    headers: Dict[str, str],
    body: bytes,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    content_encoding = str(headers.get("Content-Encoding") or "").lower()
    decoded_body = body
    decompression_error: Optional[str] = None
    if content_encoding == "gzip":
        try:
            decoded_body = gzip.decompress(body)
        except OSError as error:
            decompression_error = str(error)

    content_type = str(headers.get("Content-Type") or "").lower()
    decoded: Any = None
    decode_error: Optional[str] = decompression_error
    decoded_format: Optional[str] = None
    if "json" in content_type:
        try:
            decoded = json.loads(decoded_body.decode("utf-8"))
            decoded_format = "json"
        except (UnicodeDecodeError, ValueError) as error:
            decode_error = str(error)
    elif decompression_error is None:
        decoder = _protobuf_type(path)
        if decoder is not None:
            message_type, to_dict = decoder
            try:
                message = message_type()
                message.ParseFromString(decoded_body)
                decoded = to_dict(
                    message,
                    preserving_proto_field_name=True,
                )
                decoded_format = "otlp-protobuf"
            except Exception as error:
                decode_error = str(error)
        else:
            decode_error = (
                "opentelemetry-proto is not installed; raw OTLP body was preserved"
            )

    raw_payload = {
        "request_path": path,
        "headers": headers,
        "body_base64": base64.b64encode(body).decode("ascii"),
        "body_size": len(body),
        "decoded": decoded,
        "decoded_format": decoded_format,
        "decode_error": decode_error,
    }
    return append_raw_event(
        session_id,
        "otel",
        raw_payload,
        root,
        metadata={
            "collector": "agentvast.observer.otel_collector",
            "request_path": path,
        },
    )


class ObserverOTLPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, session_id: str, root: Optional[str]):
        super().__init__(address, handler)
        self.observer_session_id = session_id
        self.observer_root = root


class OTLPRequestHandler(BaseHTTPRequestHandler):
    server: ObserverOTLPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            payload = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(max(0, length))
        headers = {str(key): str(value) for key, value in self.headers.items()}
        try:
            record_otel_request(
                self.server.observer_session_id,
                self.path,
                headers,
                body,
                self.server.observer_root,
            )
        except BaseException as error:
            # Telemetry must never affect Claude. A 200 response prevents retries
            # from amplifying an observer-side failure.
            record_observer_error(
                error,
                self.server.observer_root,
                {
                    "collector": "otel",
                    "request_path": self.path,
                    "body_size": len(body),
                },
            )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentvast-observer-otel")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--root")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4318)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    server = ObserverOTLPServer(
        (args.host, args.port),
        OTLPRequestHandler,
        args.session_id,
        args.root,
    )
    update_manifest(
        args.session_id,
        {
            "sources": {"otel": True},
            "collector": {
                "otel_decode_available": decode_available(),
                "otel_endpoint": "http://{0}:{1}".format(args.host, args.port),
            },
        },
        args.root,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
