"""Cover scan() against a stubbed FDB index laid out like the real schema.

    clte:  [ ..., stream=clte, date ] [ resolution, type, levtype ] [ time, levelist?, param ]
    clmn:  [ ..., stream=clmn, year ] [ month, resolution, type, levtype ] [ levelist?, param ]
"""

import pytest

from destine_fdb import fdb as fdbmod

BASE = {"class": "d1", "dataset": "climate-dt", "activity": "story-nudging",
        "experiment": "hist", "realization": "1", "stream": "clte",
        "resolution": "high", "levtype": "sfc"}


L1_KEYS = {"class", "dataset", "activity", "experiment", "generation", "model",
           "realization", "expver", "stream", "date", "year"}
L2_KEYS = L1_KEYS | {"month", "resolution", "type", "levtype"}
L3_KEYS = L2_KEYS | {"time", "levelist", "param", "step"}
LEVEL_KEYS = {1: L1_KEYS, 2: L2_KEYS, 3: L3_KEYS}


class StubIndex:
    """A level-faithful stand-in for pyfdb's listing.

    The behaviour that matters -- and that a naive stub gets wrong -- is that a
    listing at level 1 **ignores** request keys belonging to deeper levels. That
    is why the shared FDB reports years 2017-2026 for a run whose monthly sfc
    data only starts in 2021: resolution and levtype are level-2 keys and do not
    prune the level-1 answer.
    """

    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def __call__(self, request, depth, expand=True):
        request = request or {}
        self.calls.append((depth, dict(request)))
        visible = LEVEL_KEYS[depth]

        seen = []
        for entry in self.entries:
            if any(entry.get(k) != v for k, v in request.items() if k in visible):
                continue
            keys = {k: v for k, v in entry.items() if k in visible}
            if keys not in seen:
                seen.append(keys)
        return iter(seen)


def clte_entries(dates, hours, params, levels=(None,)):
    out = []
    for date in dates:
        for hour in hours.get(date, hours["*"]):
            for param in params:
                for level in levels:
                    entry = {**BASE, "date": date, "time": hour,
                             "param": str(param), "type": "fc"}
                    if level is not None:
                        entry["levelist"] = str(level)
                    out.append(entry)
    return out


def clmn_entries(years, months, params):
    return [{**BASE, "stream": "clmn", "year": y, "month": m,
             "param": str(p), "type": "fc"}
            for y in years for m in months for p in params]


@pytest.fixture
def stub(monkeypatch):
    def install(entries):
        index = StubIndex(entries)
        monkeypatch.setattr(fdbmod, "_list", index)
        return index
    return install


# ── clte ────────────────────────────────────────────────────────────────

def test_clte_builds_dates_from_level1_and_hours_from_level3(stub):
    index = stub(clte_entries(["20260501", "20260502"],
                              {"*": [f"{h:02d}00" for h in range(24)]},
                              [167, 165]))
    found = fdbmod.scan(BASE, "clte")

    assert len(found["times"]) == 48
    assert found["times"][0] == ("20260501", "0000")
    assert found["params"] == {167, 165}
    # Never listed the whole run at level 3: only the two probed dates.
    level3 = [request for level, request in index.calls if level == 3]
    assert len(level3) == 2
    assert {r["date"] for r in level3} == {"20260501", "20260502"}


def test_clte_handles_a_run_that_stopped_mid_day(stub):
    stub(clte_entries(
        ["20260501", "20260502", "20260503"],
        {"*": [f"{h:02d}00" for h in range(24)],
         "20260503": ["0000", "0100", "0200"]},
        [167]))
    found = fdbmod.scan(BASE, "clte")

    assert len(found["times"]) == 24 + 24 + 3
    assert found["times"][-1] == ("20260503", "0200")


def test_clte_single_date_needs_only_one_probe(stub):
    index = stub(clte_entries(["20260501"], {"*": ["0000", "0100"]}, [167]))
    found = fdbmod.scan(BASE, "clte")
    assert len(found["times"]) == 2
    assert len([1 for level, _ in index.calls if level == 3]) == 1


def test_clte_collects_levels(stub):
    entries = clte_entries(["20260501"], {"*": ["0000"]}, [130],
                           levels=(850, 500, 250))
    for entry in entries:
        entry["levtype"] = "pl"
    stub(entries)
    found = fdbmod.scan({**BASE, "levtype": "pl"}, "clte")
    assert found["levels"] == [250, 500, 850]


# ── clmn ────────────────────────────────────────────────────────────────

def test_clmn_pairs_year_and_month_from_level2(stub):
    index = stub(clmn_entries(["2017", "2018"], [str(m) for m in range(1, 13)],
                              [228004]))
    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")

    assert len(found["times"]) == 24
    assert found["times"][0] == ("2017", "1")
    assert found["params"] == {228004}
    assert [level for level, _ in index.calls].count(3) == 1


def test_clmn_reports_a_partial_year(stub):
    entries = (clmn_entries(["2017"], [str(m) for m in range(1, 13)], [228004])
               + clmn_entries(["2018"], ["1", "2", "3"], [228004]))
    stub(entries)
    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")
    assert len(found["times"]) == 15
    assert found["times"][-1] == ("2018", "3")


# ── errors that name the fix ────────────────────────────────────────────

def test_unknown_run_lists_what_the_fdb_actually_has(stub):
    stub(clte_entries(["20260501"], {"*": ["0000"]}, [167]))
    with pytest.raises(LookupError) as excinfo:
        fdbmod.scan({**BASE, "experiment": "Tplus2.0K"}, "clte")
    message = str(excinfo.value)
    assert "story-nudging/hist" in message


def test_dates_without_a_time_key_is_reported(stub):
    entries = [{**BASE, "date": "20260501", "param": "167", "type": "fc"}]
    stub(entries)
    with pytest.raises(LookupError, match="no 'time' key"):
        fdbmod.scan(BASE, "clte")


def test_experiment_case_mismatch_is_resolved(stub):
    """The shared FDB carries both Tplus2.0K and tplus2.0k; FDB matches literally."""
    entries = clte_entries(["20260501"], {"*": ["0000", "0100"]}, [167])
    for entry in entries:
        entry["experiment"] = "Tplus2.0K"
    stub(entries)

    found = fdbmod.scan({**BASE, "experiment": "tplus2.0k"}, "clte")
    assert found["experiment"] == "Tplus2.0K"
    assert len(found["times"]) == 2


def test_exact_match_reports_no_rename(stub):
    stub(clte_entries(["20260501"], {"*": ["0000"]}, [167]))
    assert fdbmod.scan(BASE, "clte")["experiment"] is None


# ── regressions found against the real MN5 FDBs ─────────────────────────

def test_time_axis_ignores_years_with_no_data_for_this_levtype(stub):
    """Level 1 is not filtered by resolution/levtype -- level 2 is.

    The shared FDB has story-nudging/Tplus2.0K databases for 2017-2026 but
    monthly sfc data only from 2021, so a level-1 year list starts at 2017.
    """
    entries = clmn_entries(["2021", "2026"], ["5", "8"], [228004])
    empty_year = {k: v for k, v in BASE.items() if k in L1_KEYS}
    empty_year.update(stream="clmn", year="2017")             # level-1 only
    stub([empty_year] + entries)

    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")
    assert [y for y, _ in found["times"]] == ["2021", "2021", "2026", "2026"]
    assert found["params"] == {228004}


def test_probe_falls_back_when_the_newest_year_is_empty(stub):
    entries = clmn_entries(["2021"], ["5"], [228004])
    entries.append({**BASE, "stream": "clmn", "year": "2026", "month": "8",
                    "type": "fc"})            # level-2 only: no param beneath
    stub(entries)
    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")
    assert found["params"] == {228004}


def test_run_present_but_not_at_this_levtype_says_what_is_there(stub):
    entries = clte_entries(["20260501"], {"*": ["0000"]}, [167])
    for entry in entries:
        entry["levtype"] = "o3d"
        entry["resolution"] = "standard"
    stub(entries)

    with pytest.raises(LookupError) as excinfo:
        fdbmod.scan({**BASE, "levtype": "sfc", "resolution": "high"}, "clte")
    message = str(excinfo.value)
    assert "standard/o3d" in message
    assert "holds nothing at" in message


def test_clte_dates_come_from_the_filtered_level2(stub):
    entries = clte_entries(["20260501", "20260502"], {"*": ["0000"]}, [167])
    bare = {k: v for k, v in BASE.items() if k in L1_KEYS}
    entries.append({**bare, "date": "20260503"})   # level-1 only, no sfc data
    stub(entries)

    found = fdbmod.scan(BASE, "clte")
    assert [d for d, _ in found["times"]] == ["20260501", "20260502"]


def test_a_slow_scan_tells_the_user_how_to_skip_it(stub, monkeypatch, capsys):
    stub(clte_entries(["20260501"], {"*": ["0000"]}, [167]))
    calls = []

    def clock():
        calls.append(1)
        return 0.0 if len(calls) == 1 else 999.0

    monkeypatch.setattr(fdbmod.time, "monotonic", clock)
    fdbmod.scan(BASE, "clte")
    assert "start= and end=" in capsys.readouterr().err


def test_months_are_ordered_numerically_not_as_strings(stub):
    """MARS months are unpadded, so a plain sort puts '10' before '2'."""
    stub(clmn_entries(["1990"], [str(m) for m in range(1, 13)], [228004]))
    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")
    assert [m for _, m in found["times"]] == [str(m) for m in range(1, 13)]


def test_probe_candidates_use_the_newest_year(stub):
    stub(clmn_entries(["1999", "2000", "2001"], ["1"], [228004]))
    found = fdbmod.scan({**BASE, "stream": "clmn"}, "clmn")
    assert found["times"][0] == ("1999", "1")
    assert found["times"][-1] == ("2001", "1")
