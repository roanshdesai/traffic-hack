"""HTTP routes for the early-warning product. Contract: ``schemas.py`` / ``docs/API.md``."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..traffic import RoadTrafficProvider
from .config import DISCLAIMERS, SIMULATED_DISCLAIMER, STATUS_DEFINITIONS
from .dataset import FMT, OVERVIEW_LIMIT, SiteSnapshot, WarningDataset, WarningDatasetError
from .model import Assessment
from .schemas import (
    AlertEpisode,
    AlertsResponse,
    Baseline,
    EarlyWarning,
    EvaluationResponse,
    Forecast,
    OverviewResponse,
    SimulatedEvent,
    Site,
    SiteListResponse,
    SiteStatus,
    TimelineResponse,
    WarningMeta,
    WarningProvenance,
    WindowAssessment,
)

PRODUCT = "Overcrowding early warning (prototype)"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def site_model(s) -> Site:
    return Site(
        site_id=s.site_id, name=s.name, kind=s.kind, lat=s.lat, lon=s.lon, source=s.source, coverage=s.coverage,
        window_minutes=s.window_minutes, unit=s.unit,
        alert_threshold=s.alert_threshold if s.coverage == "full_count" else None,
    )  # fmt: skip


def assessment_model(a: Assessment) -> WindowAssessment:
    b = a.baseline
    return WindowAssessment(
        window_start=a.window_start.strftime(FMT),
        window_end=a.window_end.strftime(FMT),
        observed=a.observed,
        baseline=None
        if b is None
        else Baseline(
            median=b.median,
            low=round(b.low, 1),
            high=round(b.high, 1),
            support_days=b.support_days,
            basis=b.basis,
            quality=b.quality,
        ),  # fmt: skip
        ratio=a.ratio,
        z=a.z,
        status=a.status,
        triggers=a.triggers,
        reasons=a.reasons,
    )


def snapshot_model(s: SiteSnapshot) -> SiteStatus:
    return SiteStatus(
        site=site_model(s.site),
        at=s.at.strftime(FMT),
        current=assessment_model(s.current),
        forecasts=[
            Forecast(
                horizon_min=p.horizon_min,
                window_start=p.window_start.strftime(FMT),
                predicted=p.predicted,
                low=p.low,
                high=p.high,
                usual=p.usual,
                status=p.status,
            )  # fmt: skip
            for p in s.forecasts
        ],
        early_warning=None
        if s.warning is None
        else EarlyWarning(
            expected_at=s.warning.expected_at.strftime(FMT),
            lead_min=s.warning.lead_min,
            predicted=s.warning.predicted,
            summary=s.warning.summary,
        ),  # fmt: skip
    )


def create_router(dataset_dir: str | Path, traffic: RoadTrafficProvider, planner_available) -> APIRouter:
    router = APIRouter()
    state: dict[str, Any] = {"ds": None, "error": None}

    def ds() -> WarningDataset:
        if state["ds"] is None and state["error"] is None:
            try:
                state["ds"] = WarningDataset(dataset_dir)
            except WarningDatasetError as exc:
                state["error"] = str(exc)
        if state["ds"] is None:
            raise _error(503, "no_dataset", state["error"] or "No dataset loaded.")
        return state["ds"]

    def provenance(d: WarningDataset) -> WarningProvenance:
        return WarningProvenance(**d.provenance)

    def disclaimers(d: WarningDataset) -> list[str]:
        return ([SIMULATED_DISCLAIMER] if d.provenance["simulated"] else []) + list(DISCLAIMERS)

    def parse_at(d: WarningDataset, value: str | None) -> datetime:
        if value is None:
            return d.default_at()
        try:
            moment = datetime.strptime(value[:16], FMT)
        except ValueError:
            raise _error(400, "bad_time", "at must be YYYY-MM-DDTHH:MM (local time).") from None
        if not d.in_replay(moment.date()):
            raise _error(400, "out_of_range", f"at must fall within the replay period {d.replay_start} to "
                         f"{d.replay_end}.")  # fmt: skip
        return d.clamp_to_service(moment)

    def parse_date(d: WarningDataset, value: str | None, required_in_range: bool = True) -> date:
        if value is None:
            return d.default_at().date()
        try:
            day = date.fromisoformat(value)
        except ValueError:
            raise _error(400, "bad_date", "date must be YYYY-MM-DD.") from None
        if required_in_range and not d.in_replay(day):
            raise _error(400, "out_of_range", f"date must fall within the replay period {d.replay_start} to "
                         f"{d.replay_end}.")  # fmt: skip
        return day

    @router.get("/api/health")
    def health() -> dict[str, Any]:
        try:
            ds()
        except HTTPException as exc:
            return {"status": "no_dataset", "dataset_dir": str(dataset_dir), "detail": exc.detail["message"]}
        return {"status": "ok", "dataset_dir": str(dataset_dir), "detail": None}

    @router.get("/api/meta", response_model=WarningMeta)
    def meta() -> WarningMeta:
        d = ds()
        return WarningMeta(
            product=PRODUCT,
            provenance=provenance(d),
            default_at=d.default_at().strftime(FMT),
            counts={"sites": len(d.obs.sites), "alert_episodes": len(d.episodes)},
            settings={
                "model": d.cfg.to_dict(),
                "source": d.quality_report["sources"][0].get("kind"),
                "window_minutes": d.obs.spec.window_minutes,
            },  # fmt: skip
            status_definitions=STATUS_DEFINITIONS,
            disclaimers=disclaimers(d),
            road_traffic=traffic.status(),
            planner_available=planner_available(),
        )

    @router.get("/api/overview", response_model=OverviewResponse)
    def overview(at: str | None = None) -> OverviewResponse:
        d = ds()
        moment = parse_at(d, at)
        snaps, counts = d.overview(moment)
        return OverviewResponse(
            at=moment.strftime(FMT),
            provenance=provenance(d),
            counts=counts,
            sites=[snapshot_model(s) for s in snaps[:OVERVIEW_LIMIT]],
            total_sites=len(snaps),
            disclaimers=disclaimers(d),
            road_traffic=traffic.status(),
        )

    @router.get("/api/sites", response_model=SiteListResponse)
    def sites(q: str = "", limit: int = Query(50, ge=1, le=500)) -> SiteListResponse:
        d = ds()
        found = d.search(q, limit)
        return SiteListResponse(query=q, sites=[site_model(s) for s in found], total=len(d.obs.sites))

    @router.get("/api/sites/{site_id}/timeline", response_model=TimelineResponse)
    def timeline(site_id: str, date_: str | None = Query(None, alias="date")) -> TimelineResponse:
        d = ds()
        if site_id not in d.obs.sites:
            raise _error(404, "unknown_site", f"Unknown site: {site_id!r}.")
        day = parse_date(d, date_)
        return TimelineResponse(
            site=site_model(d.obs.sites[site_id]),
            date=day.isoformat(),
            windows=[assessment_model(a) for a in d.timeline(site_id, day)],
            episodes=[AlertEpisode(**e) for e in d.episodes_on(day, site_id)],
            simulated_events=[SimulatedEvent(**e) for e in d.events_on(site_id, day)]
            if d.provenance["simulated"]
            else [],
            provenance=provenance(d),
        )

    @router.get("/api/alerts", response_model=AlertsResponse)
    def alerts(date_: str | None = Query(None, alias="date")) -> AlertsResponse:
        d = ds()
        day = parse_date(d, date_) if date_ is not None else None
        return AlertsResponse(
            date=day.isoformat() if day else None,
            episodes=[AlertEpisode(**e) for e in d.episodes_on(day)],
            provenance=provenance(d),
        )

    @router.get("/api/evaluation", response_model=EvaluationResponse)
    def evaluation() -> EvaluationResponse:
        d = ds()
        return EvaluationResponse(**{**d.evaluation, "provenance": provenance(d)})

    @router.get("/api/data-quality")
    def data_quality() -> dict[str, Any]:
        return ds().quality_report

    return router
