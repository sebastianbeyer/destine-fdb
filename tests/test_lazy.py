"""Exercise the whole dataset-building path against a stub FDB.

Every FDB-touching seam is injectable, so these run anywhere -- no libfdb5,
no HPC, no network.
"""

import numpy as np
import pandas as pd
import pytest

import destine_fdb
from destine_fdb import fdb as fdbmod
from destine_fdb import lazy


class StubField:
    """The two things lazy.py asks of an earthkit field."""

    def __init__(self, date, time, values):
        self._meta = {"dataDate": date, "dataTime": time}
        self._values = values

    def metadata(self, key):
        return self._meta[key]

    def to_numpy(self):
        return self._values


class StubFDB:
    """Answers requests with fields whose values encode their timestamp."""

    def __init__(self, n_cells, shuffle=False, drop=0):
        self.n_cells = n_cells
        self.shuffle = shuffle
        self.drop = drop
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        stamps = _expand(request)
        fields = [
            StubField(int(t.strftime("%Y%m%d")), t.hour * 100,
                      np.full(self.n_cells, float(t.dayofyear + t.hour / 100.0)))
            for t in stamps
        ]
        if self.drop:
            fields = fields[: -self.drop]
        if self.shuffle:
            fields = fields[::-1]
        return fields


def _expand(request):
    """Cross product of a MARS request's time keys, as timestamps."""
    if "year" in request:
        year = int(request["year"])
        return [pd.Timestamp(year, int(m), 1) for m in request["month"].split("/")]
    out = []
    for date in request["date"].split("/"):
        for time in request["time"].split("/"):
            out.append(pd.Timestamp(date) + pd.Timedelta(hours=int(time) // 100))
    return sorted(out)


# ── blocking ────────────────────────────────────────────────────────────

def test_hourly_blocks_never_span_a_day():
    times = pd.date_range("2017-01-01", "2017-01-03 23:00", freq="h")
    out = lazy.blocks(times, "clte", "h", 24)
    assert len(out) == 3
    for idx in out:
        assert len({t.normalize() for t in times[idx]}) == 1


def test_monthly_blocks_never_span_a_year():
    times = pd.date_range("2017-01-01", "2018-12-01", freq="MS")
    out = lazy.blocks(times, "clmn", "MS", 12)
    assert [len(i) for i in out] == [12, 12]


def test_partial_day_is_its_own_block():
    times = pd.date_range("2017-01-01 18:00", "2017-01-02 05:00", freq="h")
    out = lazy.blocks(times, "clte", "h", 24)
    assert [len(i) for i in out] == [6, 6]


def test_daily_blocks_group_by_size():
    times = pd.date_range("2017-01-01", periods=70, freq="D")
    assert [len(i) for i in lazy.blocks(times, "clte", "D", 30)] == [30, 30, 10]


# ── request construction ────────────────────────────────────────────────

def test_monthly_request_uses_year_and_month():
    stamps = pd.date_range("2017-03-01", periods=3, freq="MS")
    request = lazy.request_for({"class": "d1"}, 228004, stamps, "clmn")
    assert request["year"] == "2017" and request["month"] == "3/4/5"
    assert request["param"] == "228004"


def test_hourly_request_is_an_exact_cross_product():
    stamps = pd.date_range("2017-03-01", periods=24, freq="h")
    request = lazy.request_for({}, 167, stamps, "clte")
    assert request["date"] == "20170301"
    assert len(request["time"].split("/")) == 24
    assert len(_expand(request)) == 24


def test_monthly_block_spanning_years_is_rejected():
    stamps = pd.DatetimeIndex(["2017-12-01", "2018-01-01"])
    with pytest.raises(ValueError, match="one year"):
        lazy.request_for({}, 1, stamps, "clmn")


def test_level_goes_into_the_request():
    stamps = pd.date_range("2017-03-01", periods=1, freq="MS")
    assert lazy.request_for({}, 130, stamps, "clmn", level=850)["levelist"] == "850"


# ── block fetching ──────────────────────────────────────────────────────

def test_fields_are_reordered_by_grib_date():
    stub = StubFDB(n_cells=4, shuffle=True)
    stamps = pd.date_range("2017-01-01", periods=24, freq="h")
    request = lazy.request_for({}, 167, stamps, "clte")
    block = lazy.fetch_block(stub, request, 24, 4, "2t")
    assert block[:, 0].tolist() == pytest.approx(sorted(block[:, 0].tolist()))
    assert block[0, 0] == pytest.approx(1.0)      # Jan 1, hour 0
    assert block[23, 0] == pytest.approx(1.23)    # Jan 1, hour 23


def test_short_response_yields_nan_not_misalignment():
    stub = StubFDB(n_cells=4, drop=2)
    stamps = pd.date_range("2017-01-01", periods=24, freq="h")
    request = lazy.request_for({}, 167, stamps, "clte")
    assert np.isnan(lazy.fetch_block(stub, request, 24, 4, "2t")).all()


def test_failed_request_yields_nan():
    def boom(request):
        raise RuntimeError("no schema")

    stamps = pd.date_range("2017-01-01", periods=1, freq="MS")
    request = lazy.request_for({}, 167, stamps, "clmn")
    assert np.isnan(lazy.fetch_block(boom, request, 1, 4, "avg_2t")).all()


def test_wrong_cell_count_is_a_loud_error():
    stub = StubFDB(n_cells=999)
    stamps = pd.date_range("2017-01-01", periods=1, freq="MS")
    request = lazy.request_for({}, 167, stamps, "clmn")
    with pytest.raises(ValueError, match="Nside"):
        lazy.fetch_block(stub, request, 1, 4, "avg_2t")


# ── end to end ──────────────────────────────────────────────────────────

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("FDB5_CONFIG", "type: local")


def test_open_run_is_lazy_until_values_are_touched(configured):
    stub = StubFDB(n_cells=12 * 128 * 128)
    ds = destine_fdb.open_run(
        activity="story-nudging", experiment="hist", member=11,
        frequency="monthly", resolution="standard", levtype="sfc",
        start="2017-01-01", end="2018-12-01", scan=False,
        variables=["avg_2t"], fetcher=stub)

    assert stub.requests == []                      # nothing fetched yet
    assert ds.avg_2t.dims == ("time", "cell")
    assert ds.sizes == {"time": 24, "cell": 196608}
    assert ds.attrs["grid"] == "H128"

    ds.avg_2t.isel(time=0).values                   # one year -> one request
    assert len(stub.requests) == 1
    assert stub.requests[0]["month"] == "1/2/3/4/5/6/7/8/9/10/11/12"
    assert stub.requests[0]["realization"] == "11"


def test_values_land_on_the_right_timesteps(configured):
    stub = StubFDB(n_cells=12 * 128 * 128, shuffle=True)
    ds = destine_fdb.open_run(
        frequency="hourly", levtype="sfc", start="2017-06-01",
        end="2017-06-02 23:00", scan=False, variables=["2t"], fetcher=stub)
    values = ds["2t"].isel(cell=0).values
    expected = [t.dayofyear + t.hour / 100.0 for t in pd.DatetimeIndex(ds.time.values)]
    assert values.tolist() == pytest.approx(expected)
    assert len(stub.requests) == 2                  # two calendar days


def test_pressure_levels_get_a_level_dim(configured):
    stub = StubFDB(n_cells=12 * 128 * 128)
    ds = destine_fdb.open_run(
        frequency="monthly", levtype="pl", start="2017-01-01", end="2017-03-01",
        scan=False, variables=["avg_t"], levels=[850, 500], fetcher=stub)
    assert ds["avg_t"].dims == ("time", "level", "cell")
    assert ds.level.values.tolist() == [850, 500]
    ds["avg_t"].isel(cell=0).values
    assert {r["levelist"] for r in stub.requests} == {"850", "500"}


def test_wrong_stream_spelling_names_the_right_one(configured):
    with pytest.raises(KeyError, match="avg_2t"):
        destine_fdb.open_run(frequency="monthly", start="2017-01-01",
                             end="2017-01-01", scan=False, variables=["2t"])


def test_plus2k_alias_maps_to_the_mars_key(configured):
    stub = StubFDB(n_cells=12 * 128 * 128)
    ds = destine_fdb.open_run(
        experiment="plus2K", frequency="monthly", start="2017-01-01",
        end="2017-01-01", scan=False, variables=["avg_2t"], fetcher=stub)
    assert ds.attrs["experiment"] == "tplus2.0k"


def test_high_resolution_storyline_is_h512(configured):
    stub = StubFDB(n_cells=12 * 512 * 512)
    ds = destine_fdb.open_run(
        frequency="monthly", resolution="high", start="2017-01-01",
        end="2017-01-01", scan=False, variables=["avg_2t"], fetcher=stub)
    assert ds.sizes["cell"] == 12 * 512 * 512
    assert ds.attrs["grid"] == "H512"


# ── portfolio narrowing from the scan ───────────────────────────────────

def test_scan_narrows_the_portfolio_to_what_is_archived(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "scan", lambda request, stream, mode="index": {
        "times": [("2017", str(m)) for m in range(1, 4)],
        "params": {228004, 228005},     # avg_2t, avg_10ws only: a reduced run
        "levels": [],
        "raw_depth": 2,
    })
    stub = StubFDB(n_cells=12 * 128 * 128)
    ds = destine_fdb.open_run(frequency="monthly", levtype="sfc", fetcher=stub)

    assert set(ds.data_vars) == {"avg_2t", "avg_10ws"}
    assert ds.sizes["time"] == 3
    assert "avg_msl" in ds.attrs["portfolio_missing"]


def test_scan_builds_the_hourly_time_axis(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "scan", lambda request, stream, mode="index": {
        "times": [("20170101", f"{h:02d}00") for h in range(4)],
        "params": {167}, "levels": [], "raw_depth": 2,
    })
    ds = destine_fdb.open_run(frequency="hourly", levtype="sfc",
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 4
    assert str(ds.time.values[-1]) == "2017-01-01T03:00:00.000000000"


def test_a_run_with_none_of_the_portfolio_says_so(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "scan", lambda request, stream, mode="index": {
        "times": [("2017", "1")], "params": {999999}, "levels": [], "raw_depth": 2,
    })
    with pytest.raises(LookupError, match="None of the"):
        destine_fdb.open_run(frequency="monthly", levtype="sfc")


# ── FDB configuration ───────────────────────────────────────────────────

def test_fdb_root_sets_fdb_home(tmp_path):
    config = tmp_path / "etc" / "fdb" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("type: select\nschema: ~fdb/etc/fdb/schema\n")
    env = {}
    fdbmod.configure(tmp_path, env=env)
    assert env["FDB_HOME"] == str(tmp_path)
    assert "~fdb" in env["FDB5_CONFIG"]


def test_config_file_alone_does_not_invent_an_fdb_home(tmp_path):
    config = tmp_path / "fdb-config.yaml"
    config.write_text("type: local\n")
    env = {}
    fdbmod.configure(config, env=env)
    assert "FDB_HOME" not in env
    assert env["FDB5_CONFIG"] == "type: local\n"


def test_root_without_a_config_is_reported_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="etc/fdb/config.yaml"):
        fdbmod.configure(tmp_path, env={})


def test_no_config_anywhere_is_an_error():
    with pytest.raises(RuntimeError, match="No FDB configured"):
        fdbmod.configure(env={})


def test_open_run_requests_use_the_resolved_experiment_spelling(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "scan", lambda request, stream, mode="index": {
        "times": [("2017", "1")], "params": {228004}, "levels": [],
        "raw_depth": 2, "experiment": "Tplus2.0K",
    })
    stub = StubFDB(n_cells=12 * 128 * 128)
    ds = destine_fdb.open_run(experiment="plus2K", frequency="monthly",
                              variables=["avg_2t"], fetcher=stub)
    ds.avg_2t.isel(time=0, cell=0).values
    assert stub.requests[0]["experiment"] == "Tplus2.0K"
    assert ds.attrs["experiment"] == "Tplus2.0K"


def test_scan_false_without_a_range_says_why(configured):
    with pytest.raises(ValueError, match="needs an explicit start"):
        destine_fdb.open_run(frequency="monthly", scan=False, variables=["avg_2t"])


def test_a_full_range_skips_the_date_enumeration_but_still_probes(
        configured, monkeypatch):
    """The range settles *when*; only the index knows *what*."""
    def boom(request, stream, mode="auto"):
        raise AssertionError("dates must not be enumerated when a range is given")

    probes = []
    monkeypatch.setattr(fdbmod, "scan", boom)
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True:
                            probes.append(list(cands)) or ({228004}, set(), set()))
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["x"], None))

    ds = destine_fdb.open_run(frequency="monthly", start="2017-01-01",
                              end="2017-03-01", variables=["avg_2t"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 3
    assert probes == [["2017", "2017"]] or probes == [["2017"]]


def test_scan_false_touches_the_index_not_at_all(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "scan", lambda *a, **k: pytest.fail("no scan"))
    monkeypatch.setattr(fdbmod, "probe_run", lambda *a, **k: pytest.fail("no probe"))
    ds = destine_fdb.open_run(frequency="monthly", start="2017-01-01",
                              end="2017-03-01", scan=False, variables=["avg_2t"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 3


def test_a_range_still_gets_the_real_levels(configured, monkeypatch):
    """This is what skipping the probe used to cost: 75 padded ocean levels."""
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["x"], None))
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True:
                            ({263501}, set(range(1, 71)), set()))

    ds = destine_fdb.open_run(frequency="daily", start="2017-01-01",
                              end="2017-01-02", variables=["avg_thetao"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["level"] == 70              # not the portfolio's padded 75

    bare = destine_fdb.open_run(frequency="daily", start="2017-01-01",
                                end="2017-01-02", variables=["avg_thetao"],
                                scan=False,
                                fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert bare.sizes["level"] == 75            # fallback, when nothing is read


def test_a_range_still_narrows_the_variable_list(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["x"], None))
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True:
                            ({228004}, set(), set()))
    ds = destine_fdb.open_run(frequency="monthly", start="2017-01-01",
                              end="2017-01-01",
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert set(ds.data_vars) == {"avg_2t"}
    assert "avg_msl" in ds.attrs["portfolio_missing"]


# ── HEALPix grid metadata ───────────────────────────────────────────────

def test_cell_coord_carries_xdggs_grid_metadata(configured):
    """Emitting the standard attrs is what lets ds.dggs.decode() work."""
    ds = destine_fdb.open_run(
        frequency="monthly", resolution="high", start="2017-01-01",
        end="2017-01-01", scan=False, variables=["avg_2t"],
        fetcher=StubFDB(n_cells=12 * 512 * 512))
    attrs = ds.cell.attrs
    assert attrs["grid_name"] == "healpix"
    assert attrs["level"] == 9              # Nside 512 -> level 9
    assert attrs["indexing_scheme"] == "nested"
    # xdggs feeds these straight to HealpixInfo(**attrs), which rejects any key
    # it does not know -- so a stray "nside" or "standard_name" here is a
    # TypeError at decode time, not a harmless extra.
    assert set(attrs) == {"grid_name", "level", "indexing_scheme"}
    assert ds.attrs["healpix_nside"] == 512
    assert ds.attrs["healpix_nest"] is True


def test_cf_grid_mapping_variable_accompanies_the_mesh(configured):
    ds = destine_fdb.open_run(
        frequency="monthly", start="2017-01-01", end="2017-01-01", scan=False,
        variables=["avg_2t"], fetcher=StubFDB(n_cells=12 * 128 * 128))
    crs = ds["crs"].attrs
    assert crs == {"grid_mapping_name": "healpix", "refinement_level": 7,
                   "indexing_scheme": "nested"}
    assert ds["avg_2t"].attrs["grid_mapping"] == "healpix"


def test_ring_ordering_is_reflected_in_the_metadata(configured):
    ds = destine_fdb.open_run(
        frequency="monthly", start="2017-01-01", end="2017-01-01", scan=False,
        variables=["avg_2t"], ordering="ring",
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.cell.attrs["indexing_scheme"] == "ring"
    assert ds["crs"].attrs["indexing_scheme"] == "ring"
    assert ds.attrs["healpix_nest"] is False


def test_data_that_contradicts_the_assumed_ordering_is_an_error(configured):
    from destine_fdb import lazy

    lazy._ORDERING_CHECKED.clear()

    class RingField(StubField):
        def metadata(self, key):
            if key == "orderingConvention":
                return "ring"
            return super().metadata(key)

    stub = StubFDB(n_cells=4)
    stamps = pd.date_range("2017-01-01", periods=1, freq="MS")
    request = lazy.request_for({}, 167, stamps, "clmn")
    fields = [RingField(19700101, 0, np.zeros(4))]
    with pytest.raises(ValueError, match="ordering='ring'"):
        lazy.fetch_block(lambda r: fields, request, 1, 4, "avg_2t", "nested")


def test_matching_ordering_passes_the_check(configured):
    from destine_fdb import lazy

    lazy._ORDERING_CHECKED.clear()

    class NestedField(StubField):
        def metadata(self, key):
            if key == "orderingConvention":
                return "nested"
            return super().metadata(key)

    stamps = pd.date_range("2017-01-01", periods=1, freq="MS")
    request = lazy.request_for({}, 167, stamps, "clmn")
    fields = [NestedField(19700101, 0, np.full(4, 7.0))]
    block = lazy.fetch_block(lambda r: fields, request, 1, 4, "avg_2t", "nested")
    assert block[0].tolist() == [7.0] * 4


# ── levtype inference ───────────────────────────────────────────────────

def test_levtype_is_inferred_from_the_variable_names(configured):
    """A user should not have to know that avg_thetao lives at o3d."""
    ds = destine_fdb.open_run(
        frequency="daily", start="2017-01-01", end="2017-01-02", scan=False,
        variables=["avg_thetao"], levels=[1, 2],
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.attrs["levtype"] == "o3d"
    assert ds["avg_thetao"].dims == ("time", "level", "cell")


def test_two_dimensional_ocean_infers_o2d(configured):
    ds = destine_fdb.open_run(
        frequency="daily", start="2017-01-01", end="2017-01-02", scan=False,
        variables=["avg_tos", "avg_siconc"],
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.attrs["levtype"] == "o2d"
    assert ds["avg_tos"].dims == ("time", "cell")


def test_explicit_levtype_still_wins(configured):
    ds = destine_fdb.open_run(
        frequency="hourly", levtype="sfc", start="2017-01-01",
        end="2017-01-01 01:00", scan=False, variables=["2t"],
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.attrs["levtype"] == "sfc"


def test_no_variables_named_falls_back_to_sfc(configured):
    ds = destine_fdb.open_run(
        frequency="monthly", start="2017-01-01", end="2017-01-01", scan=False,
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.attrs["levtype"] == "sfc"


def test_an_ambiguous_name_refuses_to_guess(configured):
    """u and v exist at both pl and hl; sd at both sfc and sol."""
    with pytest.raises(ValueError, match="more than one levtype"):
        destine_fdb.open_run(frequency="hourly", start="2017-01-01",
                             end="2017-01-01 01:00", scan=False,
                             variables=["u"])


def test_variables_spanning_levtypes_are_refused(configured):
    """2t is sfc and t is pl; both hourly, so only the levtype clash is left."""
    with pytest.raises(ValueError, match="span several levtypes"):
        destine_fdb.open_run(frequency="hourly", start="2017-01-01",
                             end="2017-01-01 01:00", scan=False,
                             variables=["2t", "t"])


def test_a_variable_not_archived_at_this_frequency_says_so(configured):
    """avg_tos is daily and monthly only -- there is no hourly sea surface temp."""
    with pytest.raises(KeyError, match="archived at"):
        destine_fdb.open_run(frequency="hourly", start="2017-01-01",
                             end="2017-01-01 01:00", scan=False,
                             variables=["avg_tos"])


def test_a_name_in_no_levtype_says_so(configured):
    with pytest.raises(KeyError, match="not in the portfolio"):
        destine_fdb.open_run(frequency="hourly", start="2017-01-01",
                             end="2017-01-01 01:00", scan=False,
                             variables=["nonsense"])


# ── portfolio tiers, from the catalogue rather than inferred ────────────

def test_tiers_narrow_the_catalogue():
    from destine_fdb import catalogue

    counts = {tier: sum(len(s["variables"]) for s in catalogue("clmn", tier).values())
              for tier in ("full", "reduced", "minimal")}
    assert counts["full"] > counts["reduced"] >= counts["minimal"]
    assert counts["minimal"] == 35


def test_a_minimal_run_offers_fewer_variables(configured):
    full = destine_fdb.open_run(
        frequency="monthly", start="2017-01-01", end="2017-01-01", scan=False,
        fetcher=StubFDB(n_cells=12 * 128 * 128))
    minimal = destine_fdb.open_run(
        frequency="monthly", start="2017-01-01", end="2017-01-01", scan=False,
        tier="minimal", fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert len(minimal.data_vars) < len(full.data_vars)


def test_frequency_is_per_variable_not_per_levtype(configured):
    """lsm is the only daily field at sfc; everything else there is hourly."""
    from destine_fdb import catalogue

    hourly = catalogue("clte", "full", frequency="hourly")["sfc"]["variables"]
    daily = catalogue("clte", "full", frequency="daily")["sfc"]["variables"]
    assert "2t" in hourly and "lsm" not in hourly
    assert "lsm" in daily and "2t" not in daily


def test_units_survived_the_catalogue_swap():
    from destine_fdb import catalogue

    sfc = catalogue("clte", "full", frequency="hourly")["sfc"]["variables"]
    assert sfc["2t"]["units"] == "K"
    assert sfc["2t"]["long_name"] == "2 metre temperature"
    assert sum(1 for v in sfc.values() if not v["units"]) == 0


def test_a_range_wider_than_the_run_is_trimmed(configured, monkeypatch, capsys):
    """Untrimmed, six years of 3-D ocean is 870k dask chunks of mostly NaN."""
    monkeypatch.setattr(fdbmod, "probe_run", lambda req, stream, start, end: {
        "times": [], "params": set(), "levels": [], "raw_depth": "probe",
        "experiment": None,
        "archived": ["20260501", "20260502", "20260503"]})

    ds = destine_fdb.open_run(frequency="daily", start="2020-01-01",
                              end="2026-05-10", variables=["avg_tos"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 3
    assert "trimming to what is archived" in capsys.readouterr().err


def test_scan_false_keeps_the_range_the_caller_asked_for(configured, monkeypatch):
    monkeypatch.setattr(fdbmod, "probe_run",
                        lambda *a, **k: pytest.fail("scan=False must not probe"))
    ds = destine_fdb.open_run(frequency="daily", start="2026-05-01",
                              end="2026-05-10", scan=False, variables=["avg_tos"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 10


def test_a_range_inside_the_run_is_left_alone(configured, monkeypatch, capsys):
    monkeypatch.setattr(fdbmod, "probe_run", lambda req, stream, start, end: {
        "times": [], "params": set(), "levels": [], "raw_depth": "probe",
        "experiment": None,
        "archived": [f"202605{d:02d}" for d in range(1, 30)]})
    ds = destine_fdb.open_run(frequency="daily", start="2026-05-02",
                              end="2026-05-05", variables=["avg_tos"],
                              fetcher=StubFDB(n_cells=12 * 128 * 128))
    assert ds.sizes["time"] == 4
    assert "trimming" not in capsys.readouterr().err
