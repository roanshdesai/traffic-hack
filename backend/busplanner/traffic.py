"""Road traffic boundary.

Road traffic (vehicles on roads, e.g. from the Google Routes API) is a
different signal from passenger crowding (people on buses). It lives behind
this module and is returned in its own ``road_traffic`` response field. It must
never be blended into a crowding level, rank or evidence grade.

The prototype makes no external calls. A real provider would need an API key
supplied through the environment (never committed) and the owner's go-ahead.
"""

from __future__ import annotations

from typing import Protocol

from .schemas import RoadTraffic


class RoadTrafficProvider(Protocol):
    def status(self) -> RoadTraffic: ...


class NotConfiguredTraffic:
    def status(self) -> RoadTraffic:
        return RoadTraffic(
            status="not_configured",
            note=(
                "Road traffic is not connected in this prototype and no Google API is called. "
                "If added later it stays a separate signal and is never merged into passenger crowding."
            ),
        )


def default_provider() -> RoadTrafficProvider:
    return NotConfiguredTraffic()
