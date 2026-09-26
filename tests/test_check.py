import httpx
import pytest
from fastapi.testclient import TestClient

from app.guard import GuardError, parse_verdict, pick_blocked
from app.main import app


def make_client(reply: str | None = None, status: int = 200):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.content)
        if status != 200:
            return httpx.Response(status, json={"error": "x"})
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    tc = TestClient(app)
    tc.__enter__()
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return tc, seen


def post(reply, direction="input", message="สวัสดี", status=200):
    tc, seen = make_client(reply, status)
    try:
        r = tc.post("/check", json={"message": message, "direction": direction})
        return r, seen
    finally:
        tc.__exit__(None, None, None)


def test_safe_returns_original_message():
    r, seen = post("safe", message="มีสินค้าอะไรบ้าง")
    assert r.status_code == 200
    assert r.json() == {"msg": "มีสินค้าอะไรบ้าง", "result": "safe", "direction": "input", "categories": []}
    assert seen["body"]["messages"] == [{"role": "user", "content": "มีสินค้าอะไรบ้าง"}]
    assert seen["body"]["model"] == "meta-llama/llama-guard-4-12b"


def test_unsafe_blocked_category_returns_thai_message():
    r, _ = post("unsafe\nS10", message="x")
    j = r.json()
    assert j["result"] == "unsafe" and j["categories"] == ["S10"]
    assert "เกลียดชัง" in j["msg"]


def test_unsafe_only_unblocked_category_is_safe():
    r, _ = post("unsafe\nS13", message="เลือกตั้งพรรคไหนดี")
    assert r.json()["result"] == "safe"


def test_mixed_categories_uses_first_blocked():
    r, _ = post("unsafe\nS13,S7,S1")
    assert r.json()["categories"] == ["S7", "S1"]


def test_output_direction_sends_assistant_role():
    r, seen = post("safe", direction="output", message="ตอบ")
    assert seen["body"]["messages"][0]["role"] == "assistant"
    assert r.json()["direction"] == "output"


def test_upstream_error_fails_closed():
    r, _ = post(None, status=500)
    assert r.status_code == 502


def test_unparsable_verdict_fails_closed():
    r, _ = post("maybe?")
    assert r.status_code == 502


@pytest.mark.parametrize("body", [
    {"message": "", "direction": "input"},
    {"message": "hi", "direction": "sideways"},
    {"direction": "input"},
])
def test_validation_errors(body):
    with TestClient(app) as tc:
        assert tc.post("/check", json=body).status_code == 422


def test_cors_preflight():
    with TestClient(app) as tc:
        r = tc.options("/check", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        })
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_parse_helpers():
    assert parse_verdict("unsafe\nS1, S2") == (True, ["S1", "S2"])
    assert pick_blocked(["S8", "S2"]) == ["S2"]
    with pytest.raises(GuardError):
        parse_verdict("")


def _with_blocklist(tmp_path, content):
    from app import main
    f = tmp_path / "bl.txt"
    f.write_text(content, encoding="utf-8")
    main.blocklist.path = f
    main.blocklist._mtime = None
    return main


@pytest.mark.parametrize("direction", ["input", "output"])
def test_blocklist_blocks_without_calling_guard(tmp_path, direction):
    _with_blocklist(tmp_path, "# c\n\nคำต้องห้าม\nBadWord\n")
    tc, seen = make_client("safe")
    with tc:
        r = tc.post("/check", json={"message": "นี่คือ badword นะ", "direction": direction})
    j = r.json()
    assert j["result"] == "unsafe" and j["categories"] == ["BLOCKLIST"] and j["direction"] == direction
    assert "ขออภัย" in j["msg"]
    assert "body" not in seen  # ไม่ได้เรียก OpenRouter


def test_blocklist_no_match_and_comments_ignored(tmp_path):
    _with_blocklist(tmp_path, "# badword\nอื่นๆ\n")
    r, seen = post("safe", message="badword")
    assert r.json()["result"] == "safe" and "body" in seen


def test_blocklist_missing_file_is_empty(tmp_path):
    from app import main
    main.blocklist.path = tmp_path / "nope.txt"
    main.blocklist._mtime = None
    r, _ = post("safe", message="อะไรก็ได้")
    assert r.json()["result"] == "safe"


def test_blocklist_reloads_on_change(tmp_path):
    import os
    main = _with_blocklist(tmp_path, "")
    assert not main.blocklist.matches("xyz")
    main.blocklist.path.write_text("xyz", encoding="utf-8")
    os.utime(main.blocklist.path, (1, 99999999))  # กัน mtime ซ้ำ
    assert main.blocklist.matches("XYZ")
