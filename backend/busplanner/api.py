"""HTTP API. Contract: ``schemas.py`` / ``docs/API.md``."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from .config import (
    DAY_TYPES,
    DISCLAIMERS,
    PERIODS,
    REPO_ROOT,
    SIMULATED_DISCLAIMER,
    dataset_dir_from_env,
    day_type_for_weekday,
    period_for_minute,
)
from .crowding import FALLBACKS
from .dataset import DatasetError, LoadedDataset, load_dataset
from .network import PlaceGroup
from .pipeline import IST
from .schemas import (
    HealthResponse,
    JourneyRequestEcho,
    JourneyResponse,
    MetaResponse,
    PeriodInfo,
    Place,
    StopSearchResponse,
)
from .traffic import default_provider


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _place(group: PlaceGroup) -> Place:
    return Place(
        place_id=group.place_id,
        name=group.name,
        stop_ids=group.stop_ids,
        lat=round(group.lat, 6),
        lon=round(group.lon, 6),
        routes=group.routes,
    )


def _clock(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def create_app(dataset_dir: str | Path | None = None, serve_frontend: bool = True) -> FastAPI:
    app = FastAPI(
        title="Delhi bus crowding-aware journey planner (prototype)",
        version="0.1.0",
        description=(
            "Scheduled bus journeys ranked as Fastest, Balanced and Less crowded. Times are scheduled GTFS "
            "times, not live. Crowding is a relative estimate from ticket samples, not occupancy."
        ),
    )
    directory = Path(dataset_dir) if dataset_dir else dataset_dir_from_env()
    state: dict[str, Any] = {"dataset": None, "error": None}
    traffic = default_provider()

    def dataset() -> LoadedDataset:
        if state["dataset"] is None and state["error"] is None:
            try:
                state["dataset"] = load_dataset(directory)
            except DatasetError as exc:
                state["error"] = str(exc)
        if state["dataset"] is None:
            raise _error(503, "no_dataset", state["error"] or "No dataset loaded.")
        return state["dataset"]

    def disclaimers(ds: LoadedDataset) -> list[str]:
        return ([SIMULATED_DISCLAIMER] if ds.provenance.simulated else []) + list(DISCLAIMERS)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            dataset()
        except HTTPException as exc:
            return HealthResponse(status="no_dataset", dataset_dir=str(directory), detail=exc.detail["message"])
        return HealthResponse(status="ok", dataset_dir=str(directory))

    @app.get("/api/meta", response_model=MetaResponse)
    def meta() -> MetaResponse:
        ds = dataset()
        feed, net = ds.network.feed, ds.network
        lo, hi = feed.date_range()
        return MetaResponse(
            provenance=ds.provenance,
            counts={
                "stops": len(net.stop_patterns),
                "places": len(net.places),
                "routes": len(net.patterns_by_route),
                "trips": len(feed.trips),
                "patterns": len(net.patterns),
            },
            service_date_range={"start": lo.isoformat() if lo else None, "end": hi.isoformat() if hi else None},
            suggested_query=_suggested_query(ds),
            periods=[PeriodInfo(id=p, label=label, start=_clock(s), end=_clock(e)) for p, label, s, e in PERIODS],
            day_types=list(DAY_TYPES),
            settings=ds.settings.to_dict(),
            fallbacks=list(FALLBACKS),
            disclaimers=disclaimers(ds),
            road_traffic=traffic.status(),
        )

    @app.get("/api/stops", response_model=StopSearchResponse)
    def stops(q: str = "", limit: int = Query(10, ge=1, le=50)) -> StopSearchResponse:
        ds = dataset()
        return StopSearchResponse(query=q, places=[_place(p) for p in ds.network.search_places(q, limit)])

    @app.get("/api/journeys", response_model=JourneyResponse)
    def journeys(
        origin_ref: str = Query(..., alias="from", description="place_id or stop_id"),
        dest_ref: str = Query(..., alias="to", description="place_id or stop_id"),
        date_: str | None = Query(None, alias="date", description="YYYY-MM-DD; default today (Asia/Kolkata)"),
        time_: str | None = Query(None, alias="time", description="HH:MM; default now (Asia/Kolkata)"),
    ) -> JourneyResponse:
        ds = dataset()
        now = datetime.now(IST)
        try:
            day = date.fromisoformat(date_) if date_ else now.date()
        except ValueError:
            raise _error(400, "bad_date", "date must be YYYY-MM-DD.") from None
        try:
            clock = datetime.strptime(time_, "%H:%M") if time_ else now
        except ValueError:
            raise _error(400, "bad_time", "time must be HH:MM (24-hour).") from None
        minute = clock.hour * 60 + clock.minute

        origin = ds.network.resolve_place(origin_ref)
        destination = ds.network.resolve_place(dest_ref)
        if origin is None:
            raise _error(404, "unknown_place", f"Unknown origin: {origin_ref!r}. Use a place_id from /api/stops.")
        if destination is None:
            raise _error(404, "unknown_place", f"Unknown destination: {dest_ref!r}. Use a place_id from /api/stops.")
        if set(origin.stop_ids) & set(destination.stop_ids):
            raise _error(400, "same_place", "Origin and destination are the same place.")

        result = ds.planner.plan(origin, destination, day, minute * 60)
        found = result.candidates_considered
        if found:
            message = f"3 options from {found} scheduled journey{'s' if found != 1 else ''}."
            insufficient = [o for o in result.options if o.status == "insufficient_evidence"]
            if insufficient:
                message += " Ticket evidence is insufficient to rank on crowding."
        else:
            message = result.options[0].reason.summary
        return JourneyResponse(
            request=JourneyRequestEcho(
                origin=_place(origin),
                destination=_place(destination),
                date=day.isoformat(),
                time=_clock(minute),
                day_type=day_type_for_weekday(day.weekday()),
                period=period_for_minute(minute),
            ),
            status="ok" if found else "no_journey",
            message=message,
            options=result.options,
            candidates_considered=found,
            provenance=ds.provenance,
            disclaimers=disclaimers(ds),
            road_traffic=traffic.status(),
        )

    @app.get("/api/data-quality")
    def data_quality() -> dict[str, Any]:
        return dataset().quality_report

    dist = REPO_ROOT / "frontend" / "dist"
    if serve_frontend and dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def _suggested_query(ds: LoadedDataset) -> dict[str, str] | None:
    """A weekday morning inside the feed's service range, so the UI can pre-fill a useful search.

    For simulated data the sampled ticket dates are used so the demo shows evidence.
    """
    feed = ds.network.feed
    lo, hi = feed.date_range()
    if lo is None or hi is None:
        return None
    today = datetime.now(IST).date()
    anchor = min(max(today, lo), hi)
    offsets = [timedelta(days=n) for n in range(8)]
    candidates = [anchor + o for o in offsets] + [anchor - o for o in offsets]
    sampled = (ds.quality_report.get("tickets") or {}).get("last_service_date")
    if ds.provenance.simulated and sampled:
        anchor = min(max(date.fromisoformat(sampled), lo), hi)
        candidates = [anchor - o for o in offsets]
    for candidate in candidates:
        if lo <= candidate <= hi and candidate.weekday() < 5 and feed.active_services(candidate):
            return {"date": candidate.isoformat(), "time": "08:00"}
    return None


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn busplanner.api:app_factory --factory``."""
    return create_app()
