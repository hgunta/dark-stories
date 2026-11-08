"""Isolated in-process API tests: no dotenv, credentials, or network access."""

import importlib
import itertools
import random
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_app(monkeypatch):
    monkeypatch.setenv("USE_API", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not construct OpenAI clients or use the network")

    monkeypatch.setattr("openai.OpenAI.__init__", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "backend"))
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "ROOMS", {})
    monkeypatch.setattr(module, "CODE_MAP", {})
    monkeypatch.setattr(module, "client", None)
    monkeypatch.setattr(module, "request_limiter", module.RequestLimiter())
    ids = itertools.count(1)
    monkeypatch.setattr(module.uuid, "uuid4", lambda: SimpleNamespace(hex=f"{next(ids):08x}" + "0" * 24))
    monkeypatch.setattr(module.random, "choice", random.Random(0).choice)
    yield module
    module.ROOMS.clear()
    module.CODE_MAP.clear()


@pytest.fixture
def client(isolated_app):
    with TestClient(isolated_app.app) as api:
        yield api


@pytest.fixture
def create_room(client):
    def create(mystery_id="ms-001"):
        response = client.post("/api/create_room", json={"mystery_id": mystery_id})
        assert response.status_code == 200
        return response.json()
    return create


@pytest.fixture
def mystery():
    def load(mystery_id):
        path = Path(__file__).resolve().parents[1] / "backend" / "mysteries" / f"{mystery_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))
    return load


@pytest.fixture
def moderator(monkeypatch, isolated_app):
    """Exercise the real classifier and routes; replace only SDK completion I/O."""
    monkeypatch.setenv("USE_API", "true")
    create = Mock(name="chat.completions.create")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(isolated_app, "client", fake_client)

    def respond(label="Yes", nudge="", indices=None):
        args = {"kind": "question", "label": label, "short_explanation": nudge,
                "fact_indices": indices if indices is not None else []}
        call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(args)))
        create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
        return create

    respond()
    return respond
