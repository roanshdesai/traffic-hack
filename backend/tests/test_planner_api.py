"""Secondary feature: the journey planner, now served under /api/planner."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from busplanner.api import create_app

from .conftest import place

Q = {"from": place(1), "to": place(6), "date": "2026-11-13", "time": "08:00"}
FORBIDDEN_KEYS = {"occupancy", "seats", "seats_available", "percent_full", "load_factor", "live", "eta", "delay"}


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, path)


def test_health_and_meta(client):
    assert client.get("/api/planner/health").json()["status"] == "ok"
    meta = client.get("/api/planner/meta").json()
    assert meta["provenance"]["simulated"] is True
    assert meta["provenance"]["gtfs_source"] == meta["provenance"]["tickets_source"] == "synthetic"
    assert meta["disclaimers"][0].startswith("SIMULATED DATA")
    assert any("not live" in d for d in meta["disclaimers"])
    assert [f["basis"] for f in meta["fallbacks"]] == [
        "segment_period_daytype", "segment_period", "segment_all_day", "none",
    ]  # fmt: skip
    assert meta["counts"]["places"] == 16
    assert meta["suggested_query"] == {"date": "2026-11-13", "time": "08:00"}
    assert meta["settings"]["crowding"]["min_tickets"] == 10


def test_stop_search(client):
    body = client.get("/api/planner/stops", params={"q": "sim m"}).json()
    assert [p["name"] for p in body["places"]] == ["Sim Market", "Sim Mill Road"]
    assert body["places"][0]["stop_ids"] == ["SIM_S03A", "SIM_S03B"]
    assert body["places"][0]["routes"] == ["S1", "S3"]
    assert len(client.get("/api/planner/stops", params={"limit": 5}).json()["places"]) == 5
    assert client.get("/api/planner/stops", params={"q": "zzz"}).json()["places"] == []
    assert client.get("/api/planner/stops", params={"limit": 500}).status_code == 422


def test_journeys_contract(client):
    response = client.get("/api/planner/journeys", params=Q)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [o["kind"] for o in body["options"]] == ["fastest", "balanced", "less_crowded"]
    assert body["request"]["day_type"] == "weekday" and body["request"]["period"] == "am_peak"
    assert body["provenance"]["simulated"] is True
    assert body["disclaimers"][0].startswith("SIMULATED DATA")
    journey = body["options"][0]["journey"]
    assert journey["scheduled_departure"].endswith("+05:30")
    leg = journey["legs"][0]
    assert leg["type"] == "bus" and len(leg["segments"]) == len(leg["stops"]) - 1
    evidence = leg["segments"][0]["crowding"]["evidence"]
    assert set(evidence) == {
        "quality", "basis", "ticket_count", "rider_count", "service_days", "scheduled_trips", "min_tickets_required",
    }  # fmt: skip


def test_response_never_exposes_occupancy_or_live_fields(client):
    for params in (Q, {**Q, "from": place(12), "to": place(16)}, {**Q, "from": place(10)}):
        body = client.get("/api/planner/journeys", params=params).json()
        for path, key, value in walk(body):
            assert key not in FORBIDDEN_KEYS, f"{path}/{key}"
            if key == "relative_rank":
                assert value is None or 0.0 <= value <= 1.0
            if key in ("scheduled_departure", "scheduled_arrival"):
                assert value.endswith("+05:30")
        text = json.dumps(body["options"]).lower()
        for phrase in ("seats available", "% full", "percent full", "live arrival", "real-time"):
            assert phrase not in text


def test_road_traffic_is_separate_and_not_configured(client):
    body = client.get("/api/planner/journeys", params=Q).json()
    assert body["road_traffic"]["status"] == "not_configured"
    for path, key, _value in walk(body["options"]):
        assert "traffic" not in key.lower(), f"{path}/{key}"


def test_insufficient_evidence_over_http(client):
    body = client.get("/api/planner/journeys", params={**Q, "from": place(12), "to": place(16)}).json()
    assert body["status"] == "ok"
    assert [o["status"] for o in body["options"]] == ["ok", "insufficient_evidence", "insufficient_evidence"]
    assert body["options"][1]["journey"] is None
    assert "insufficient" in body["message"].lower()


def test_no_journey_is_200_not_an_error(client):
    body = client.get("/api/planner/journeys", params={**Q, "time": "23:30"}).json()
    assert body["status"] == "no_journey" and body["candidates_considered"] == 0
    assert [o["status"] for o in body["options"]] == ["no_journey"] * 3


def test_errors(client):
    cases = [
        ({**Q, "from": "nope"}, 404, "unknown_place"),
        ({**Q, "to": "nope"}, 404, "unknown_place"),
        ({**Q, "to": Q["from"]}, 400, "same_place"),
        ({**Q, "to": "SIM_S01B"}, 400, "same_place"),
        ({**Q, "date": "13-11-2026"}, 400, "bad_date"),
        ({**Q, "time": "8am"}, 400, "bad_time"),
    ]
    for params, status, code in cases:
        response = client.get("/api/planner/journeys", params=params)
        assert response.status_code == status, params
        assert response.json()["detail"]["code"] == code
    assert client.get("/api/planner/journeys", params={"from": place(1)}).status_code == 422


def test_date_and_time_default_to_now(client):
    body = client.get("/api/planner/journeys", params={"from": place(1), "to": place(6)}).json()
    assert body["status"] in ("ok", "no_journey")
    assert len(body["request"]["date"]) == 10 and len(body["request"]["time"]) == 5


def test_data_quality_report(client):
    report = client.get("/api/planner/data-quality").json()
    assert {"generated_at", "provenance", "gtfs", "tickets", "matching", "crowding", "blocked"} <= set(report)
    assert report["gtfs"]["usable"] is True and report["gtfs"]["summary"]["errors"] == 1
    assert report["tickets"]["rows_rejected"] == 15
    assert report["matching"]["by_status"]["ambiguous_route"] == 5
    assert report["crowding"]["usable"] is True
    assert len(report["blocked"]) == 3 and "Real Delhi static GTFS is not imported" in report["blocked"][0]


def test_missing_dataset_is_a_503_with_instructions(tmp_path):
    client = TestClient(create_app(tmp_path / "nothing-here", serve_frontend=False))
    assert client.get("/api/planner/health").json()["status"] == "no_dataset"
    response = client.get("/api/planner/journeys", params=Q)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "no_dataset"
    assert "make data" in response.json()["detail"]["message"]


def test_openapi_documents_the_contract(client):
    spec = client.get("/openapi.json").json()
    assert {
        "/api/planner/health",
        "/api/planner/meta",
        "/api/planner/stops",
        "/api/planner/journeys",
        "/api/planner/data-quality",
    } <= set(spec["paths"])
    assert "JourneyResponse" in spec["components"]["schemas"]
