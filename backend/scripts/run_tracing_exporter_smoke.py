"""Wire-level smoke for the real Langfuse SDK OTLP exporter."""

from __future__ import annotations

import gzip
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.observability import LangfuseTraceBackend, Observability  # noqa: E402

REPORT_PATH = ROOT / "data" / "reports" / "observability" / "langfuse_wire_smoke.json"


class _CaptureHandler(BaseHTTPRequestHandler):
    request_event = threading.Event()
    captured: dict[str, object] = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        if self.headers.get("content-encoding") == "gzip":
            body = gzip.decompress(body)
        type(self).captured = {
            "path": self.path,
            "content_type": self.headers.get("content-type"),
            "authorization_present": bool(self.headers.get("authorization")),
            "body": body,
        }
        self.send_response(200)
        self.send_header("content-type", "application/x-protobuf")
        self.end_headers()
        type(self).request_event.set()

    def log_message(self, _format: str, *args: object) -> None:
        return


def _decode_spans(body: bytes) -> list[dict[str, object]]:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    decoded: list[dict[str, object]] = []
    for resource_spans in request.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                attributes = {item.key: str(item.value) for item in span.attributes}
                decoded.append(
                    {
                        "name": span.name,
                        "trace_id": span.trace_id.hex(),
                        "status_code": int(span.status.code),
                        "attributes": attributes,
                    }
                )
    return decoded


def main() -> int:
    _CaptureHandler.request_event.clear()
    _CaptureHandler.captured = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_port}"

    observability = Observability(
        [
            LangfuseTraceBackend(
                public_key="pk-local-wire-smoke",
                secret_key="sk-local-wire-smoke",
                host=host,
            )
        ]
    )
    try:
        with observability.trace(
            "research.preview",
            inputs={"doc_id": "trace-smoke-doc", "question_length": 12},
            metadata={"service": "ResearchService", "smoke": True},
        ) as span:
            span.set_output(
                {
                    "grounded": True,
                    "hit_count": 3,
                    "warning_count": 0,
                    "revision_count": 0,
                }
            )
        observability.flush()
        received = _CaptureHandler.request_event.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    captured = _CaptureHandler.captured
    spans = _decode_spans(captured.get("body", b"")) if received else []
    matching = [item for item in spans if item["name"] == "research.preview"]
    trace_id = span.backend_trace_ids.get("langfuse")
    passed = bool(
        received
        and captured.get("path") == "/api/public/otel/v1/traces"
        and captured.get("content_type") == "application/x-protobuf"
        and captured.get("authorization_present")
        and matching
        and trace_id
        and matching[0]["trace_id"] == trace_id
        and len(trace_id) == 32
    )
    report = {
        "passed": passed,
        "exporter": "langfuse-sdk-otlp-http",
        "endpoint_path": captured.get("path"),
        "content_type": captured.get("content_type"),
        "authorization_present": captured.get("authorization_present", False),
        "span_count": len(spans),
        "span_name": matching[0]["name"] if matching else None,
        "trace_id": trace_id,
        "trace_id_matches_payload": bool(
            matching and trace_id and matching[0]["trace_id"] == trace_id
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
