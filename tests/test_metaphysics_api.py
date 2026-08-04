"""Metaphysics API integration tests — TestClient against real route handlers, DB-free."""
import json
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.routes.metaphysics as meta_routes
import services.metaphysics.cache as cache_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated TestClient with DB-free monkeypatching."""
    # Isolate all file paths to tmp_path
    b = tmp_path / "birth_info.json"
    bc = tmp_path / "bazi_cache.json"
    zc = tmp_path / "ziwei_cache.json"

    monkeypatch.setattr(meta_routes, "BIRTH_INFO_PATH", str(b))
    monkeypatch.setattr(cache_mod, "BIRTH_INFO_PATH", str(b))
    monkeypatch.setattr(cache_mod, "BAZI_CACHE_PATH", str(bc))
    monkeypatch.setattr(cache_mod, "ZIWEI_CACHE_PATH", str(zc))

    # Stub DB — never connect
    monkeypatch.setattr("app.db.q", lambda *a, **k: [])
    monkeypatch.setattr("app.db.execute", lambda *a, **k: 1)

    # Force fallback reading path
    monkeypatch.setattr("app.utils.get_llm", lambda: None)

    # Reset cache state
    cache_mod.cache.invalidate()
    meta_routes._reading_cache.clear()

    # Build minimal app with only the metaphysics router
    app = FastAPI()
    app.include_router(meta_routes.router)
    return TestClient(app)


def _seed_birth(client, **kwargs):
    """Helper: POST valid birth info and return it."""
    info = {
        "solar_date": "2000-01-01",
        "clock_time": "08:00",
        "city": "北京",
        "gender": "女",
        **kwargs,
    }
    resp = client.post("/api/metaphysics/birth-info", json=info)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    return info


# ═══ full-chart tests (Bug 1 + Bug 2 verification) ═══


def test_full_chart_shape(client):
    """Bug 1: full-chart returns {chart: {bazi, ziwei}, etag} shape."""
    _seed_birth(client)
    resp = client.get("/api/metaphysics/full-chart")
    assert resp.status_code == 200
    body = resp.json()
    chart = body["chart"]
    # bazi structure
    assert chart["bazi"]["static"]["four_pillars"]["year"]["gan"] in "甲乙丙丁戊己庚辛壬癸"
    assert len(chart["bazi"]["static"]["four_pillars"]) == 4
    assert chart["bazi"]["static"]["day_master"] in "甲乙丙丁戊己庚辛壬癸"
    # ziwei structure
    assert len(chart["ziwei"]["static"]["palaces"]) == 12
    mg = chart["ziwei"]["static"]["ming_gong"]
    assert mg["gan"] in "甲乙丙丁戊己庚辛壬癸"
    assert mg["zhi"] in "子丑寅卯辰巳午未申酉戌亥"
    assert len(mg.get("stars", [])) >= 1
    # sihua
    assert len(chart["ziwei"]["static"].get("sihua", {})) >= 1


def test_full_chart_etag_header_and_304(client):
    """Bug 2: ETag header is set, If-None-Match returns 304."""
    _seed_birth(client)
    resp1 = client.get("/api/metaphysics/full-chart")
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag")
    assert etag, "ETag header should be present"
    assert etag == resp1.json()["etag"], "header ETag should match body etag"

    # Second request with matching ETag → 304
    resp2 = client.get("/api/metaphysics/full-chart", headers={"If-None-Match": etag})
    assert resp2.status_code == 304, f"Expected 304, got {resp2.status_code}"


def test_etag_changes_after_birth_update(client):
    """ETag changes when birth info is modified."""
    _seed_birth(client)
    etag1 = client.get("/api/metaphysics/full-chart").headers["ETag"]

    # Update birth with different date
    _seed_birth(client, solar_date="1990-06-15")
    etag2 = client.get("/api/metaphysics/full-chart").headers["ETag"]

    assert etag1 != etag2, "ETag should change after birth update"

    # Old ETag should no longer match
    resp = client.get("/api/metaphysics/full-chart", headers={"If-None-Match": etag1})
    assert resp.status_code == 200, f"Old ETag should not match, got {resp.status_code}"


def test_full_chart_missing_birth(client):
    """No birth info → error response with 200 status."""
    resp = client.get("/api/metaphysics/full-chart")
    assert resp.status_code == 200
    assert resp.json()["error"] is True


# ═══ hehun tests (Bug 3 verification) ═══


def test_hehun_combined_result(client):
    """Bug 3: hehun returns both bazi compatibility + ziwei hepan."""
    _seed_birth(client)
    resp = client.post("/api/metaphysics/hehun", json={
        "other_birth": {"solar_date": "1990-06-15", "clock_time": "14:30", "city": "上海", "gender": "女"}
    })
    assert resp.status_code == 200
    data = resp.json()
    # Bazi hehun keys (from compute_hehun)
    assert 0 <= data["compatibility_score"] <= 100
    assert isinstance(data["nayan_relation"], str) and len(data["nayan_relation"]) > 0
    assert isinstance(data["ganzhi_he"], list)
    assert isinstance(data["shishen_complement"], str)
    assert isinstance(data["wuxing_balance"], str)
    # Ziwei hepan keys (from compute_hepan)
    assert "hepan" in data
    assert "star_interactions" in data["hepan"]
    assert "couple_flying" in data["hepan"]
    assert "daxian_sync" in data["hepan"]
    # Self/other chart data
    assert "self" in data and "bazi" in data["self"] and "ziwei" in data["self"]
    assert "other" in data and "bazi" in data["other"] and "ziwei" in data["other"]


def test_hehun_no_own_birth(client):
    """Missing own birth info → 400."""
    resp = client.post("/api/metaphysics/hehun", json={
        "other_birth": {"solar_date": "1990-06-15", "clock_time": "14:30", "city": "上海", "gender": "女"}
    })
    assert resp.status_code == 400


def test_hehun_invalid_other_birth(client):
    """Invalid other birth date → 422."""
    _seed_birth(client)
    resp = client.post("/api/metaphysics/hehun", json={
        "other_birth": {"solar_date": "not-a-date", "clock_time": "14:30", "city": "上海", "gender": "女"}
    })
    assert resp.status_code == 422


# ═══ birth-info CRUD ═══


def test_birth_info_flow(client):
    """POST → GET round-trip preserves all fields."""
    # GET with no file
    resp = client.get("/api/metaphysics/birth-info")
    assert resp.json()["has_birth_info"] is False
    assert resp.json()["birth_info"] is None

    # POST
    info = {"solar_date": "2000-01-01", "clock_time": "08:00", "city": "北京", "gender": "女"}
    resp = client.post("/api/metaphysics/birth-info", json=info)
    assert resp.json()["ok"] is True

    # GET should return it
    resp = client.get("/api/metaphysics/birth-info")
    assert resp.json()["has_birth_info"] is True
    assert resp.json()["birth_info"]["solar_date"] == "2000-01-01"
    assert resp.json()["birth_info"]["clock_time"] == "08:00"

    # Update with different date
    info["solar_date"] = "1990-06-15"
    resp = client.post("/api/metaphysics/birth-info", json=info)
    assert resp.json()["ok"] is True
    resp = client.get("/api/metaphysics/birth-info")
    assert resp.json()["birth_info"]["solar_date"] == "1990-06-15"


# ═══ reading tests ═══


def test_reading_fallback(client):
    """POST /reading with no LLM → fallback reading."""
    _seed_birth(client)
    resp = client.post("/api/metaphysics/reading", json={"type": "bazi", "scope": "general"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_fallback"] is True
    assert "命盘" in data["reading_text"]
    assert "仅供文化研究与娱乐参考" in data["reading_text"]


def test_reading_get_after_post_cached(client, monkeypatch):
    """GET /reading returns cached result after a successful POST reading."""
    _seed_birth(client)

    # Use fake LLM so the reading path succeeds and caches
    class FakeLLM:
        class Chat:
            class Completions:
                def create(self, **kwargs):
                    msg = types.SimpleNamespace(content="AI 解读测试内容")
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("app.utils.get_llm", lambda: FakeLLM())

    post_resp = client.post("/api/metaphysics/reading", json={"type": "bazi", "scope": "general"})
    assert post_resp.status_code == 200
    assert post_resp.json()["is_cached"] is False

    get_resp = client.get("/api/metaphysics/reading", params={"type": "bazi", "scope": "general"})
    assert get_resp.status_code == 200
    assert get_resp.json()["cached"] is True
    assert get_resp.json()["reading_text"] == "AI 解读测试内容"


def test_reading_throttle_429(client):
    """Two back-to-back POSTs → second gets 429."""
    _seed_birth(client)
    resp1 = client.post("/api/metaphysics/reading", json={"type": "bazi", "scope": "general"})
    assert resp1.status_code == 200
    resp2 = client.post("/api/metaphysics/reading", json={"type": "bazi", "scope": "general"})
    assert resp2.status_code == 429, f"Expected 429 throttle, got {resp2.status_code}"


def test_reading_no_birth_400(client):
    """No birth info → 400."""
    resp = client.post("/api/metaphysics/reading", json={"type": "bazi", "scope": "general"})
    assert resp.status_code == 400


def test_reading_temp_birth_invalid_422(client):
    """Invalid temp_birth date → 422."""
    resp = client.post("/api/metaphysics/reading", json={
        "type": "bazi", "scope": "general",
        "temp_birth": {"solar_date": "bad-date", "clock_time": "12:00", "city": "北京", "gender": "女"}
    })
    assert resp.status_code == 422


def test_reading_temp_birth_valid(client):
    """Valid temp_birth bypasses saved birth requirement."""
    resp = client.post("/api/metaphysics/reading", json={
        "type": "bazi", "scope": "general",
        "temp_birth": {"solar_date": "2000-01-01", "clock_time": "08:00", "city": "北京", "gender": "女"}
    })
    assert resp.status_code == 200
    assert "reading_text" in resp.json()


def test_reading_kb_injection(client, monkeypatch):
    """KB entries actually appear in the LLM prompt."""
    _seed_birth(client)

    captured_prompt = []

    class FakeLLM:
        def __init__(self):
            self._captured = captured_prompt
        class Chat:
            class Completions:
                def create(self, **kwargs):
                    captured_prompt.append(kwargs.get("messages", [{}])[0].get("content", ""))
                    msg = types.SimpleNamespace(content="测试解读—KB注入验证")
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr("app.utils.get_llm", lambda: FakeLLM())

    resp = client.post("/api/metaphysics/reading", json={
        "type": "bazi", "scope": "general", "context": "财运事业"
    })
    assert resp.status_code == 200
    assert "测试解读" in resp.json()["reading_text"]
    assert len(captured_prompt) == 1
    prompt = captured_prompt[0]
    # KB Layer 2 should contain classical references
    assert "古籍参考" in prompt
    # At least one KB entry with a tag matching "财运" or "事业" should inject
    assert "(" in prompt or "《" in prompt, "KB classical_ref not found in prompt"


# ═══ bazi / ziwei standalone endpoints ═══


def test_bazi_endpoint(client):
    """GET /bazi returns four pillars + dynamic layer."""
    _seed_birth(client)
    resp = client.get("/api/metaphysics/bazi")
    assert resp.status_code == 200
    data = resp.json()
    assert "static" in data
    assert "four_pillars" in data["static"]
    assert data["static"]["day_master"] in "甲乙丙丁戊己庚辛壬癸"
    assert "current" in data
    assert "dayun" in data["current"]


def test_ziwei_endpoint(client):
    """GET /ziwei returns 12 palaces + dynamic layer."""
    _seed_birth(client)
    resp = client.get("/api/metaphysics/ziwei")
    assert resp.status_code == 200
    data = resp.json()
    assert "static" in data
    assert len(data["static"]["palaces"]) == 12
    assert "current" in data


def test_bazi_endpoint_no_birth(client):
    """GET /bazi without birth info → error dict with 200."""
    resp = client.get("/api/metaphysics/bazi")
    assert resp.status_code == 200
    assert resp.json().get("error") is True
