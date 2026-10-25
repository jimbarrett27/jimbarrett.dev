"""Model clients, against a stub OpenAI-compatible server."""

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gb_agent.models import build_chat_model, get_profile

REPLY = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "gemma-4-26b-a4b",
    "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": "",
        "reasoning_content": "The screen didn't change, so A did nothing here.",
        "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "run_script", "arguments": json.dumps({"name": "walk"})}}],
    }}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class Stub(BaseHTTPRequestHandler):
    """Answers every chat completion like llama-server does for a thinking model."""

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps(REPLY).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    httpd.shutdown()


def test_local_models_keep_the_reasoning_llama_server_sends(server):
    profile = replace(get_profile("gemma-4-26b-local"), base_url=server)

    reply = build_chat_model(profile).invoke("look at the screen")

    assert reply.additional_kwargs["reasoning_content"].startswith("The screen didn't change")
    assert reply.tool_calls[0]["name"] == "run_script"
    assert reply.tool_calls[0]["args"] == {"name": "walk"}
