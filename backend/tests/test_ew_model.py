"""Early warning: baselines, statuses, forecasts, warnings and the backtest. SIMULATED data only."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from busplanner.earlywarning.config import CAMERA_SOURCE, Calendar, WarningConfig
from busplanner.earlywarning.model import BaselineCell, Baselines, Detector
from busplanner.earlywarning.sources import ObservationSet, SiteInfo

CFG = WarningConfig()


def site(threshold=None, coverage="full_count") -> SiteInfo:
    return SiteInfo("S", "Sim S", "bus_stop", None, None, "camera_count", coverage, 15, "people counted", threshold)


def detector_with(base: BaselineCell | None, threshold=None, coverage="full_count") -> Detector:
    obs = ObservationSet(spec=CAMERA_SOURCE)
    obs.sites = {"S": site(threshold, coverage)}
    cells = {} if base is None else {("site_daytype_slot", "S", "weekday", 8): base}
    return Detector(obs, Baselines(cells), Calendar(), CFG)


BASE = BaselineCell(median=50, sigma=7.1, support_days=10, basis="site_daytype_slot", quality="high")


@pytest.mark.parametrize(
    ("count", "status", "triggers"),
    [(50, "normal", []), (62, "normal", []), (70, "elevated", []), (95, "overcrowding_alert", ["relative"])],
)
def test_classification_bands(count, status, triggers):
    got, trig, ratio, z, _ = detector_with(BASE).classify(site(), count, BASE)
    assert (got, trig) == (status, triggers)
    assert ratio == pytest.approx(count / 50)


def test_operator_threshold_triggers_alert_even_when_usual():
    det = detector_with(BASE, threshold=60)
    status, triggers, *_ = det.classify(det.obs.sites["S"], 62, BASE)
    assert (status, triggers) == ("overcrowding_alert", ["threshold"])


def test_thresholds_are_ignored_for_sample_sources():
    det = detector_with(BASE, threshold=10, coverage="sample")
    status, triggers, *_ = det.classify(det.obs.sites["S"], 55, BASE)
    assert (status, triggers) == ("normal", [])


def test_small_usual_levels_are_capped_at_elevated():
    small = BaselineCell(median=3, sigma=1.73, support_days=10, basis="site_daytype_slot", quality="high")
    status, triggers, _ratio, _z, capped = detector_with(small).classify(site(), 14, small)
    assert status == "elevated" and triggers == [] and capped


def test_without_history_status_is_insufficient_not_normal():
    status, *_ = detector_with(None).classify(site(), 500, None)
    assert status == "insufficient_evidence"
    status, triggers, *_ = detector_with(None, threshold=100).classify(site(100), 500, None)
    assert (status, triggers) == ("overcrowding_alert", ["threshold"])


def test_sigma_has_a_poisson_floor():
    obs = ObservationSet(spec=CAMERA_SOURCE)
    obs.sites = {"S": site()}
    days = [date(2026, 11, d) for d in (2, 3, 4, 5, 6)]  # identical counts every weekday
    for d in days:
        obs.days.add(d)
        for slot in range(obs.slots_per_day):
            obs.counts["S"][(d, slot)] = 100
    cell = Baselines.build(obs, days, Calendar(), CFG).lookup("S", "weekday", 8, 4)
    assert cell.median == 100 and cell.sigma == pytest.approx(10.0)  # sqrt(100), not 0
    assert cell.support_days == 5 and cell.quality == "medium"


def test_calendar_day_types():
    plain, split = Calendar(frozenset({date(2026, 10, 2)})), Calendar(frozenset({date(2026, 10, 2)}), True)
    assert plain.day_type(date(2026, 10, 2)) == "weekend_or_holiday"  # a Friday holiday
    assert plain.day_type(date(2026, 10, 3)) == "weekend_or_holiday"
    assert split.day_type(date(2026, 10, 3)) == "saturday"
    assert split.day_type(date(2026, 10, 4)) == "sunday_or_holiday"
    assert split.day_type(date(2026, 10, 2)) == "sunday_or_holiday"
    assert split.day_type(date(2026, 10, 5)) == "weekday"


def test_no_data_windows_are_reported_as_such(ew_dataset):
    a = ew_dataset.detector.assess("SIM_SITE_05", datetime(2026, 11, 19, 11, 0))
    assert a.status == "no_data" and a.observed is None
    assert ew_dataset.detector.forecast("SIM_SITE_05", datetime(2026, 11, 19, 11, 0))[0].status != "no_data"


def test_assessment_only_uses_its_own_window(ew_dataset):
    a = ew_dataset.detector.assess("SIM_SITE_04", datetime(2026, 11, 18, 17, 37))
    assert a.window_start == datetime(2026, 11, 18, 17, 30) and a.window_end == datetime(2026, 11, 18, 17, 45)
    assert a.reasons and "usually" in a.reasons[0]


def test_forecast_does_not_look_ahead(ew_dataset):
    """Changing the future must not change a forecast made now."""
    det = ew_dataset.detector
    at = datetime(2026, 11, 18, 16, 45)
    before = [(p.predicted, p.status) for p in det.forecast("SIM_SITE_04", at)]
    future_slot = (18 * 60 - 6 * 60) // 15
    key = (date(2026, 11, 18), future_slot)
    saved = det.obs.counts["SIM_SITE_04"][key]
    det.obs.counts["SIM_SITE_04"][key] = 0
    try:
        assert [(p.predicted, p.status) for p in det.forecast("SIM_SITE_04", at)] == before
    finally:
        det.obs.counts["SIM_SITE_04"][key] = saved


def test_forecast_horizons_are_capped_at_one_hour(ew_dataset):
    points = ew_dataset.detector.forecast("SIM_SITE_01", datetime(2026, 11, 18, 9, 0))
    assert [p.horizon_min for p in points] == [15, 30, 45, 60]
    assert all(p.low <= p.predicted <= p.high for p in points if p.predicted is not None)


def test_gradual_build_up_is_warned_before_the_alert(ew_build):
    per_event = {e["kind"]: e for e in ew_build[1]["evaluation"]["metrics"]["per_event"]}
    assert per_event["event_crowd"]["warned_before_alert"] is True
    assert per_event["market_day"]["warned_before_alert"] is True
    # A sudden spike has no build-up: it is detected when it happens, not forecast.
    assert per_event["sudden_spike"]["detected"] and not per_event["sudden_spike"]["warned_before_alert"]


def test_backtest_metrics_on_simulated_events(ew_build):
    evaluation = ew_build[1]["evaluation"]
    m = evaluation["metrics"]
    assert evaluation["ground_truth"] == "simulated_events"
    assert "SIMULATED" in evaluation["caveat"]
    assert m["events_in_replay"] == 4 and m["event_recall"] == 1.0
    assert m["false_alert_episodes"] == 0
    assert m["window_precision"] == 1.0
    assert m["early_warnings_issued"] >= m["events_warned_before_first_alert"] == 2
    # The baseline-period event (7 Nov) is not scored: the replay starts 16 Nov.
    assert all(e["onset"] >= "2026-11-16" for e in m["per_event"])


def test_baseline_period_event_does_not_poison_the_usual_level(ew_dataset):
    """The 7 Nov market spike is in the baseline; the median should ignore one odd Saturday."""
    cell = ew_dataset.detector.baseline_for("SIM_SITE_03", datetime(2026, 11, 21, 12, 30))
    assert cell is not None and cell.median < 80
