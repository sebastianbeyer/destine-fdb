"""Filesystem scan mode: config-root resolution and directory parsing."""

import pytest
import yaml

from destine_fdb import fdb as fdbmod
from destine_fdb import filesystem as fs

# The shape that matters: type:select, two roots per space, and an excludes
# rule -- this is the shared DestinE config on MN5, trimmed.
SHARED_CONFIG = yaml.safe_load("""
type: select
fdbs:
- select: class=d1,dataset=^climate-dt$,generation=2,expver=(0001|o[0-9a-z]{3})
  type: local
  spaces:
  - roots:
    - path: /scratch/dte/fdb/healpix
    - path: /scratch/dte/fdb/gateway/prod
- select: class=d1,dataset=^climate-dt$
  excludes: ['class=d1,dataset=^climate-dt$,generation=2,expver=(0001|o[0-9a-z]{3})']
  type: local
  spaces:
  - roots:
    - path: /other/fdb/healpix
""")

REQUEST = {"class": "d1", "dataset": "climate-dt", "activity": "story-nudging",
           "experiment": "hist", "generation": "2", "model": "ifs-fesom",
           "realization": "11", "expver": "0001", "stream": "clte"}


def name(request, top, **over):
    keys = {**request, **over}
    return ":".join([keys[k] for k in fs.L1_ORDER] + [top])


# ── roots ───────────────────────────────────────────────────────────────

def test_all_roots_of_a_matching_rule_are_returned():
    """Listing only the first root under-reports; that is the whole trap."""
    roots = fs.data_roots(SHARED_CONFIG, REQUEST)
    assert [str(r) for r in roots] == ["/scratch/dte/fdb/healpix",
                                       "/scratch/dte/fdb/gateway/prod"]


def test_excludes_route_an_older_generation_elsewhere():
    roots = fs.data_roots(SHARED_CONFIG, {**REQUEST, "generation": "1"})
    assert [str(r) for r in roots] == ["/other/fdb/healpix"]


def test_plain_local_config_needs_no_select_rules():
    config = yaml.safe_load("type: local\nspaces:\n- roots:\n  - path: /a\n")
    assert [str(r) for r in fs.data_roots(config, REQUEST)] == ["/a"]


def test_a_key_the_request_omits_cannot_disqualify_it():
    assert fs._matches("class=d1,expver=0001", {"class": "d1"})
    assert not fs._matches("class=d1,expver=0001", {"class": "d1", "expver": "0009"})


# ── directory parsing ───────────────────────────────────────────────────

def test_databases_are_gathered_across_every_root(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for root, tops in ((a, ["20170101", "20170102"]), (b, ["20170103"])):
        root.mkdir()
        for top in tops:
            (root / name(REQUEST, top)).mkdir()

    found = fs.databases([a, b], REQUEST, "date")
    assert sorted(found) == ["20170101", "20170102", "20170103"]


def test_matching_folds_case_like_fdb_does(tmp_path):
    """The shared FDB has both IFS-FESOM and ifs-fesom directories for one run."""
    tmp_path.joinpath(name(REQUEST, "20170101", model="IFS-FESOM")).mkdir()
    tmp_path.joinpath(name(REQUEST, "20170102", model="ifs-fesom")).mkdir()

    found = fs.databases([tmp_path], REQUEST, "date")
    assert sorted(found) == ["20170101", "20170102"]


def test_other_runs_in_the_same_root_are_ignored(tmp_path):
    tmp_path.joinpath(name(REQUEST, "20170101")).mkdir()
    tmp_path.joinpath(name(REQUEST, "20170102", realization="1")).mkdir()
    tmp_path.joinpath("not-an-fdb-database").mkdir()

    assert sorted(fs.databases([tmp_path], REQUEST, "date")) == ["20170101"]


def test_a_missing_root_is_skipped_not_fatal(tmp_path):
    tmp_path.joinpath(name(REQUEST, "20170101")).mkdir()
    found = fs.databases([tmp_path, tmp_path / "nope"], REQUEST, "date")
    assert sorted(found) == ["20170101"]


# ── index filenames ─────────────────────────────────────────────────────

def test_levtype_is_read_from_index_filenames(tmp_path):
    db = tmp_path / name(REQUEST, "20170101")
    db.mkdir()
    (db / "high:fc:sfc.20260604.164453.host.123.index").touch()
    (db / "standard:fc:pl.20260604.164453.host.124.index").touch()
    (db / "high:fc:sfc.20260604.164453.host.125.data").touch()

    assert fs.levtype_present(db, "high", "sfc")
    assert fs.levtype_present(db, "standard", "pl")
    assert not fs.levtype_present(db, "standard", "sfc")
    assert fs.index_keys(db) == {("high", "fc", "sfc"), ("standard", "fc", "pl")}


# ── end to end through scan() ───────────────────────────────────────────

def test_scan_filesystem_builds_a_monthly_axis(tmp_path, monkeypatch):
    root = tmp_path / "healpix"
    root.mkdir()
    request = {**REQUEST, "stream": "clmn", "resolution": "standard",
               "levtype": "sfc", "type": "fc"}
    for year, months in (("2017", ["1", "2"]), ("2018", ["1"])):
        db = root / name(request, year)
        db.mkdir()
        for month in months:
            (db / f"{month}:standard:fc:sfc.2026.1.h.1.index").touch()

    monkeypatch.setenv("FDB5_CONFIG",
                       yaml.safe_dump({"type": "local",
                                       "spaces": [{"roots": [{"path": str(root)}]}]}))
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True: ({228004}, set(), set()))

    found = fdbmod.scan(request, "clmn", mode="filesystem")
    assert found["times"] == [("2017", "1"), ("2017", "2"), ("2018", "1")]
    assert found["params"] == {228004}
    assert found["raw_depth"] == "filesystem"


def test_scan_filesystem_says_when_nothing_matches(tmp_path, monkeypatch):
    root = tmp_path / "healpix"
    root.mkdir()
    monkeypatch.setenv("FDB5_CONFIG",
                       yaml.safe_dump({"type": "local",
                                       "spaces": [{"roots": [{"path": str(root)}]}]}))
    with pytest.raises(LookupError, match="No database directories"):
        fdbmod.scan({**REQUEST, "resolution": "standard", "levtype": "sfc"},
                    "clte", mode="filesystem")


def test_an_unknown_scan_mode_is_rejected():
    with pytest.raises(ValueError, match="scan_mode"):
        fdbmod.scan(REQUEST, "clte", mode="magic")


# ── discovery: runs() and overview() ────────────────────────────────────

def test_all_roots_ignores_which_rule_serves_a_request(tmp_path):
    """Enumerating an FDB has no request to narrow the rules by."""
    a, b, c = (tmp_path / n for n in "abc")
    for d in (a, b, c):
        d.mkdir()
    config = {"type": "select", "fdbs": [
        {"select": "class=d1,expver=0001", "spaces": [{"roots": [{"path": str(a)},
                                                                {"path": str(b)}]}]},
        {"select": "class=d1", "spaces": [{"roots": [{"path": str(c)}]}]},
    ]}
    assert [str(r) for r in fs.all_roots(config)] == [str(a), str(b), str(c)]


def test_all_roots_skips_paths_not_on_this_machine(tmp_path):
    config = {"type": "local",
              "spaces": [{"roots": [{"path": str(tmp_path)},
                                    {"path": "/gpfs/nope"}]}]}
    assert [str(r) for r in fs.all_roots(config)] == [str(tmp_path)]


def test_list_runs_groups_databases_by_run(tmp_path):
    for top in ("20170101", "20170102"):
        (tmp_path / name(REQUEST, top)).mkdir()
    (tmp_path / name(REQUEST, "20170101", realization="2")).mkdir()
    (tmp_path / "junk").mkdir()

    found = fs.list_runs([tmp_path])
    assert len(found) == 2
    counts = sorted(len(tops) for tops in found.values())
    assert counts == [1, 2]


def test_runs_reports_a_row_per_run(tmp_path, monkeypatch):
    import destine_fdb
    root = tmp_path / "healpix"
    root.mkdir()
    for top in ("20170101", "20170102", "20170103"):
        (root / name(REQUEST, top)).mkdir()
    (root / name(REQUEST, "2017", stream="clmn")).mkdir()

    monkeypatch.setenv("FDB5_CONFIG",
                       yaml.safe_dump({"type": "local",
                                       "spaces": [{"roots": [{"path": str(root)}]}]}))
    frame = destine_fdb.runs()
    assert len(frame) == 2
    clte = frame[frame["stream"] == "clte"].iloc[0]
    assert clte["databases"] == 3
    assert clte["first"] == "20170101" and clte["last"] == "20170103"
    assert clte["activity"] == "story-nudging"
    # "3 databases" means nothing to a reader; one clte database is one day.
    assert clte["covers"] == "3 days"
    clmn = frame[frame["stream"] == "clmn"].iloc[0]
    assert clmn["covers"] == "1 year"      # and one clmn database is one year


def test_overview_covers_every_levtype_that_has_data(monkeypatch):
    import destine_fdb
    from destine_fdb import fdb as fdbmod

    monkeypatch.setenv("FDB5_CONFIG", "type: local")

    def fake_scan(request, stream, mode="index"):
        if request["levtype"] in ("hl", "sol", "o3d"):
            raise LookupError("nothing archived here")
        return {"times": [("2017", "1"), ("2017", "2")],
                "params": set(), "levels": [], "raw_depth": "filesystem",
                "experiment": None}

    monkeypatch.setattr(fdbmod, "scan", fake_scan)
    frame = destine_fdb.overview(frequency="monthly")
    assert list(frame["levtype"]) == ["sfc", "pl", "o2d"]
    assert set(frame["timesteps"]) == {2}
    assert frame[frame.levtype == "sfc"].iloc[0]["variables"] == 34


def test_overview_says_when_a_run_has_nothing_anywhere(monkeypatch):
    import destine_fdb
    from destine_fdb import fdb as fdbmod

    monkeypatch.setenv("FDB5_CONFIG", "type: local")
    monkeypatch.setattr(fdbmod, "scan", lambda *a, **k: (_ for _ in ()).throw(
        LookupError("nope")))
    with pytest.raises(LookupError, match="in any levtype"):
        destine_fdb.overview(frequency="monthly")


# ── scan_mode="auto" ────────────────────────────────────────────────────

def test_auto_prefers_the_filesystem(monkeypatch):
    calls = []
    monkeypatch.setattr(fdbmod, "scan_filesystem",
                        lambda req, stream, env=None: calls.append("fs") or {"ok": 1})
    monkeypatch.setattr(fdbmod, "_list",
                        lambda *a, **k: calls.append("index") or iter(()))
    assert fdbmod.scan(REQUEST, "clte", mode="auto") == {"ok": 1}
    assert calls == ["fs"]


def test_auto_falls_back_to_the_index_when_roots_are_unreadable(monkeypatch, capsys):
    """A remote or non-toc FDB has no directories here, but the index still works."""
    def no_roots(req, stream, env=None):
        raise RuntimeError("Filesystem scanning needs the FDB config")

    monkeypatch.setattr(fdbmod, "scan_filesystem", no_roots)
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["20170101"], None))
    monkeypatch.setattr(fdbmod, "_list", lambda req, depth, expand=True: iter(
        [{"date": "20170101"}] if depth == 2 else []))
    monkeypatch.setattr(fdbmod, "_probe", lambda req: ({167}, set(), {"0000"}))

    found = fdbmod.scan(REQUEST, "clte", mode="auto")
    assert found["times"] == [("20170101", "0000")]
    assert "falling back to the index" in capsys.readouterr().err


def test_auto_does_not_mask_a_run_that_is_genuinely_absent(monkeypatch):
    """A LookupError means "not there", not "try another way"."""
    def absent(req, stream, env=None):
        raise LookupError("No database directories match")

    monkeypatch.setattr(fdbmod, "scan_filesystem", absent)
    monkeypatch.setattr(fdbmod, "_list",
                        lambda *a, **k: pytest.fail("index must not be consulted"))
    with pytest.raises(LookupError, match="No database directories"):
        fdbmod.scan(REQUEST, "clte", mode="auto")


def test_an_unknown_mode_is_still_rejected():
    with pytest.raises(ValueError, match="scan_mode"):
        fdbmod.scan(REQUEST, "clte", mode="magic")


def test_probe_range_picks_a_date_that_actually_exists(tmp_path, monkeypatch):
    """Probing an unarchived date is slow, not just useless -- 16s on MN5."""
    root = tmp_path / "healpix"
    root.mkdir()
    for top in ("20260501", "20260502", "20260503"):
        (root / name(REQUEST, top)).mkdir()
    monkeypatch.setenv("FDB5_CONFIG",
                       yaml.safe_dump({"type": "local",
                                       "spaces": [{"roots": [{"path": str(root)}]}]}))
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["x"], None))
    seen = []
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True:
                            seen.append(list(cands)) or ({167}, set(), set()))

    # A range starting years before anything was archived.
    fdbmod.probe_run(REQUEST, "clte", "2020-01-01", "2026-05-10")
    assert seen[0][0] == "20260503"          # newest archived date in range
    assert "2020-01-01" not in str(seen[0])
    assert all(c in ("20260501", "20260502", "20260503") for c in seen[0])


def test_probe_range_falls_back_to_guessing_without_a_readable_root(monkeypatch):
    monkeypatch.setenv("FDB5_CONFIG", "type: local\nspaces: []\n")
    monkeypatch.setattr(fdbmod, "_resolve_experiment",
                        lambda req, key: (req, ["x"], None))
    seen = []
    monkeypatch.setattr(fdbmod, "_probe_params",
                        lambda req, key, cands, required=True:
                            seen.append(list(cands)) or (set(), set(), set()))
    fdbmod.probe_run(REQUEST, "clte", "2026-05-01", "2026-05-03")
    assert seen[0] == ["20260503", "20260502", "20260501"]


def test_overview_refuses_a_pinned_levtype(monkeypatch):
    """It would silently apply to every levtype's request and report nonsense."""
    import destine_fdb

    monkeypatch.setenv("FDB5_CONFIG", "type: local")
    with pytest.raises(TypeError, match="every levtype"):
        destine_fdb.overview(frequency="hourly", levtype="sfc")


def test_overview_is_not_narrowed_by_frequency(monkeypatch):
    """The ocean is daily where the atmosphere is hourly; both belong here."""
    import destine_fdb
    from destine_fdb import fdb as fdbmod

    monkeypatch.setenv("FDB5_CONFIG", "type: local")
    monkeypatch.setattr(fdbmod, "scan", lambda request, stream, mode="auto": {
        "times": [("20260501", "0000")], "params": set(), "levels": [],
        "raw_depth": "filesystem", "experiment": None})

    frame = destine_fdb.overview(frequency="hourly")
    assert {"sfc", "pl", "o2d", "o3d"} <= set(frame["levtype"])
    ocean = frame[frame.levtype == "o2d"].iloc[0]
    assert "daily" in ocean["freq"]
    assert "hourly" in frame[frame.levtype == "sfc"].iloc[0]["freq"]
