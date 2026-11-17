# SIMULATED early-warning fixtures

**Everything in this folder is synthetic.** It was produced by
`backend/busplanner/earlywarning/synthetic.py`. The sites, people counts and
crowd events are invented. They do not describe real places, cameras, people
or crowds.

* `sites.csv`: five "Sim ..." sites. `alert_threshold` is a made-up operator
  setting, not a capacity.
* `simulated_camera_counts.csv`: three weeks (2 to 22 Nov 2026) of 15-minute
  people counts, as camera counting software might report them, with a
  detector `confidence`. Counts only: no images, no identities.
* `simulated_events.csv`: the crowd events injected into the counts. They are
  the ground truth used to score detection and early warning on test data.
  `onset` is when the injected surge first reaches 1.6x the normal level.
* `mapping.json`: column mapping for the counts file.

Planted defects: a duplicate window, a misaligned timestamp, a negative count,
a non-numeric count, a window outside service hours, an unknown site, an
unparseable timestamp, an implausible 99,999 reading, a 3-hour sensor outage
and low-confidence evening readings.

Do not edit by hand. Regenerate with `make fixtures`.
