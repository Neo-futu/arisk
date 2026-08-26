import json
from pathlib import Path

import pytest

import handler

EVENTS = json.loads((Path(__file__).parent / "data" / "events.json").read_text())


def _body(resp):
    return json.loads(resp["body"])


def test_health_returns_ok():
    resp = handler.handler(EVENTS["function_url_health"])
    assert resp["statusCode"] == 200
    body = _body(resp)
    assert body["status"] == "ok"
    assert body["app"] == "demo-app"
    assert body["env"] == "dev"
    assert "time" in body


def test_rest_api_health_route():
    resp = handler.handler(EVENTS["rest_api_health"])
    assert _body(resp)["status"] == "ok"


def test_root_returns_hello():
    resp = handler.handler(EVENTS["function_url_root"])
    assert resp["statusCode"] == 200
    body = _body(resp)
    assert body["message"] == "hello from demo-app"
    assert body["path"] == "/"


def test_direct_invoke_defaults_to_root():
    resp = handler.handler(EVENTS["direct_invoke_empty"])
    body = _body(resp)
    assert body["message"] == "hello from demo-app"
    assert body["path"] == "/"


@pytest.mark.parametrize("bad_event", [None, "not-a-dict", 123])
def test_non_dict_event_is_safe(bad_event):
    resp = handler.handler(bad_event)
    assert resp["statusCode"] == 200


def test_response_is_json_serializable():
    resp = handler.handler(EVENTS["function_url_root"])
    assert resp["headers"]["content-type"] == "application/json"
    # body 必须是合法 JSON 字符串
    json.loads(resp["body"])
