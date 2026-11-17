# SIMULATED fixtures

**Everything in this folder is synthetic.** The stops, coordinates, routes,
timetables and ticket rows were invented by `backend/busplanner/synthetic.py`.
They do not describe real Delhi bus services, real ridership or real crowding,
and must not be presented as such.

* `gtfs/` is a tiny static GTFS feed (agency `SIMULATED Transit`).
* `tickets.csv` holds simulated ticket samples. Every row has `data_label=SIMULATED`
  and a `SIM-` ticket number.
* `ticket_mapping.json` maps the ticket columns onto the canonical ticket fields.
* `aliases.json` is the reviewed route/stop alias table.

The files contain deliberate defects (a backwards trip, an out-of-region stop,
duplicate route names, unknown and misspelt references, invalid rows) so the
validators and the matcher have something to flag.

Do not edit these files by hand. Regenerate them with:

```
make fixtures        # or: busplanner generate-fixtures
```

`backend/tests/test_fixtures.py` fails if the committed files drift from the generator.
