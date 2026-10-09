"""Keep fixture output and network traffic away from the owner's running app."""
from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

# Configure before collection imports settings or decision-store modules.
_TEST_OUTPUT = Path(tempfile.mkdtemp(prefix="chakraops-pytest-"))
os.environ["OUT_DIR"] = str(_TEST_OUTPUT / "decisions")
os.environ["SNAPSHOT_OUTPUT_DIR"] = str(_TEST_OUTPUT / "pipeline")


@pytest.fixture(autouse=True)
def isolated_runtime_output_and_network(monkeypatch):
    from app.core.eval import evaluation_store_v2

    evaluation_store_v2.reset_output_dir()
    original_connect = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple):
            host, port = address[:2]
            if host not in ("localhost", "127.0.0.1", "::1") or port in (18800, 18873):
                raise OSError("Fixture network access to external services or the running app is disabled")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    yield
    evaluation_store_v2.reset_output_dir()
