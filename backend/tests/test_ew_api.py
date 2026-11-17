"""Early warning API contract. SIMULATED data only."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from busplanner.api import create_app

FORBIDDEN_KEYS = {"occupancy", "seats", "seats_available", "percent_full", "load_factor", "capacity_used"}
FORBIDDEN_PHRASES = ("real-time", "live feed", "verified crowd", "% full", "seats available")


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, path)


def test_meta(ew_client):
    meta = ew_client.get("/api/meta").json()
    assert meta["provenance"]["simulated"] is True and meta["provenance"]["origin"] == "synthetic"
    assert meta["disclaimers"][0].startswith("SIMULATED DATA")
    assert any("not a live feed" in d for d in meta["disclaimers"])
    assert meta["provenance"]["replay_period"] == {"start": "2026-11-16", "end": "2026-11-22"}
    assert meta["default_at"].startswith("2026-11-")
    assert set(meta["status_definitions"]) == {
        "normal", "elevated", "overcrowding_alert", "insufficient_evidence", "no_data"}  # fmt: skip
    assert meta["planner_available"] is False
    assert meta["road_traffic"]["status"] == "not_configured"


def test_overview_orders_most_urgent_first(ew_client):
    body = ew_client.get("/api/overview", params={"at": "2026-11-18T17:45"}).json()
    assert body["at"] == "2026-11-18T17:45" and body["total_sites"] == 5
    first = body["sites"][0]
    assert first["site"]["site_id"] == "SIM_SITE_04"
    assert first["current"]["status"] == "overcrowding_alert"
    assert sum(v for k, v in body["counts"].items() if k != "early_warning") == 5


def test_overview_shows_an_early_warning_during_a_build_up(ew_client, ew_build):
    lead = next(e for e in ew_build[1]["evaluation"]["metrics"]["per_event"] if e["kind"] == "event_crowd")
    episodes = ew_client.get("/api/alerts", params={"date": "2026-11-18"}).json()["episodes"]
    warned_at = next(e["first_warning_at"] for e in episodes if e["site_id"] == "SIM_SITE_04")
    assert warned_at is not None and lead["warning_lead_before_alert_min"] > 0
    body = ew_client.get("/api/overview", params={"at": warned_at}).json()
    stadium = next(s for s in body["sites"] if s["site"]["site_id"] == "SIM_SITE_04")
    assert stadium["early_warning"] is not None
    assert stadium["current"]["status"] == "elevated"
    assert "forecast, not an observation" in stadium["early_warning"]["summary"]
    assert body["counts"]["early_warning"] >= 1


def test_overview_time_handling(ew_client):
    snapped = ew_client.get("/api/overview", params={"at": "2026-11-18T17:52"}).json()
    assert snapped["at"] == "2026-11-18T17:45"
    assert ew_client.get("/api/overview", params={"at": "2026-11-01T08:00"}).json()["detail"]["code"] == "out_of_range"
    assert ew_client.get("/api/overview", params={"at": "yesterday"}).json()["detail"]["code"] == "bad_time"
    assert ew_client.get("/api/overview").status_code == 200


def test_timeline(ew_client):
    body = ew_client.get("/api/sites/SIM_SITE_05/timeline", params={"date": "2026-11-19"}).json()
    assert len(body["windows"]) == 64
    statuses = [w["status"] for w in body["windows"]]
    assert statuses.count("no_data") == 12  # the 3-hour simulated outage
    assert body["simulated_events"] == []
    stadium = ew_client.get("/api/sites/SIM_SITE_04/timeline", params={"date": "2026-11-18"}).json()
    assert len(stadium["simulated_events"]) == 1 and stadium["episodes"]
    assert ew_client.get("/api/sites/NOPE/timeline").status_code == 404


def test_sites_search_and_alerts(ew_client):
    assert [s["name"] for s in ew_client.get("/api/sites", params={"q": "stadium"}).json()["sites"]] == [
        "Sim Stadium Stop"]  # fmt: skip
    episodes = ew_client.get("/api/alerts").json()["episodes"]
    assert episodes and all(e["matched_event"] is True for e in episodes)


def test_evaluation_and_quality(ew_client):
    ev = ew_client.get("/api/evaluation").json()
    assert ev["ground_truth"] == "simulated_events" and "SIMULATED" in ev["caveat"]
    dq = ew_client.get("/api/data-quality").json()
    assert dq["sources"][0]["kind"] == "camera_count" and dq["sources"][0]["summary"]["errors"] == 8
    assert any("camera" in b.lower() for b in dq["blocked"])


def test_no_occupancy_or_live_claims(ew_client):
    for path in ("/api/overview?at=2026-11-18T17:45", "/api/sites/SIM_SITE_04/timeline?date=2026-11-18",
                 "/api/meta", "/api/alerts"):  # fmt: skip
        body = ew_client.get(path).json()
        for p, key, _value in walk(body):
            assert key not in FORBIDDEN_KEYS, f"{path}{p}/{key}"
        body = {k: v for k, v in body.items() if k not in ("disclaimers", "road_traffic")}
        text = json.dumps(body).lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text, (path, phrase)


def test_road_traffic_never_inside_a_status(ew_client):
    body = ew_client.get("/api/overview", params={"at": "2026-11-18T17:45"}).json()
    for p, key, _value in walk(body["sites"]):
        assert "traffic" not in key.lower(), p
    assert body["road_traffic"]["status"] == "not_configured"


def test_missing_dataset_is_503(tmp_path):
    client = TestClient(create_app(tmp_path / "a", serve_frontend=False, warning_dataset_dir=tmp_path / "b"))
    assert client.get("/api/health").json()["status"] == "no_dataset"
    response = client.get("/api/overview")
    assert response.status_code == 503 and "make data" in response.json()["detail"]["message"]


def test_planner_is_still_reachable_as_secondary(client):
    assert client.get("/api/planner/health").json()["status"] == "ok"
