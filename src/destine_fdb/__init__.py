"""Lazy xarray access to DestinE Climate DT data in a local FDB.

    from destine_fdb import open_run

    ds = open_run("/gpfs/projects/ehpc01/dte/fdb/healpix",
                  activity="story-nudging", experiment="hist",
                  member=11, frequency="monthly", resolution="high")

Nothing is read until you touch values. Metadata comes back immediately, the
time axis and variable list come from listing the FDB, and each ``.values`` or
``.plot()`` turns into the FDB reads it needs and no more.

Data stays on its native HEALPix mesh (a ``cell`` dimension), so this needs no
network at all -- which matters on an airgapped login node, where the
regridding path has to download interpolation matrices first.
"""

import sys

import numpy as np
import pandas as pd

from . import fdb as _fdb
from . import portfolio as _portfolio
from .params import to_param_id
from .portfolio import (  # noqa: F401  (re-exported)
    PANDAS_FREQ,
    STREAM_OF,
    TIERS,
    VARIABLES,
    catalogue,
)
from .lazy import build_dataset

__all__ = ["open_run", "scan_run", "overview", "runs", "catalogue",
           "VARIABLES", "TIERS"]

_STREAM = STREAM_OF

# The FDB/MARS experiment key for the +2K storyline is spelled several ways in
# the wild; accept the friendly names people actually type.
_EXPERIMENT_ALIASES = {
    "plus2k": "tplus2.0k", "+2k": "tplus2.0k", "tplus2.0k": "tplus2.0k",
}


def _base_request(activity, experiment, member, model, resolution, levtype,
                  stream, overrides):
    request = {
        "class": "d1",
        "dataset": "climate-dt",
        "type": "fc",
        "expver": "0001",
        "generation": "2",
        "activity": activity,
        "experiment": _EXPERIMENT_ALIASES.get(str(experiment).lower(), experiment),
        "model": model,
        "realization": str(member),
        "resolution": resolution,
        "stream": stream,
        "levtype": levtype,
    }
    request.update(overrides)
    return request


def _resolve_levtype(levtype, variables, catalogue):
    """Pick the levtype: explicit, else inferred from the variable names."""
    if levtype is not None:
        return levtype
    if variables:
        return _portfolio.infer_levtype(variables, catalogue)
    return "sfc"


def _default_portfolio(activity, stream, frequency=None, tier="full"):
    """The catalogue for a run, narrowed to its stream, tier and frequency.

    Narrowing by frequency matters: a levtype can mix them. ``lsm`` is the only
    daily field at ``sfc``, so an hourly dataset that included it would carry a
    variable with no hourly data behind it.
    """
    return _portfolio.catalogue(stream, tier, frequency=frequency)


def _times_from_scan(scanned, stream, freq):
    """Turn the scanned MARS time keys into a DatetimeIndex."""
    stamps = []
    for keys in scanned["times"]:
        if stream == "clmn":
            year, month = keys
            stamps.append(pd.Timestamp(int(year), int(month), 1))
        else:
            date, time = keys
            hhmm = int(time)
            stamps.append(pd.Timestamp(f"{date}") + pd.Timedelta(hours=hhmm // 100,
                                                                 minutes=hhmm % 100))
    index = pd.DatetimeIndex(sorted(set(stamps)))
    if stream == "clte" and freq == "D":
        index = pd.DatetimeIndex(sorted({t.normalize() for t in index}))
    return index


def scan_run(fdb=None, *, activity="story-nudging", experiment="hist",
             member=1, frequency="monthly", resolution="standard",
             levtype=None, model="ifs-fesom", fdb_home=None,
             scan_mode="auto", variables=None, tier="full", **overrides):
    """Report what a run actually contains, without opening it.

    Returns the raw ``{"times", "params", "levels"}`` dict from the FDB index.
    Useful on its own to find out whether a run is on the full, reduced or
    minimal portfolio, and how far it has got.
    """
    _fdb.configure(fdb, fdb_home=fdb_home)
    stream = _STREAM[frequency]
    levtype = _resolve_levtype(
        levtype, variables, _default_portfolio(activity, stream, frequency, tier))
    request = _base_request(activity, experiment, member, model, resolution,
                            levtype, stream, overrides)
    return _fdb.scan(request, stream, mode=scan_mode)


# What one FDB database spans, per stream. This is a property of the Climate DT
# schema: clte databases are keyed on `date`, clmn ones on `year`.
DB_SPANS = {"clte": "day", "clmn": "year"}


def _measure_run_nside(row):
    """Nside for one row of ``runs()``, per resolution present.

    A run can hold more than one resolution and they do not share a grid, so
    report each one ("standard:128 high:512") rather than picking a winner.
    """
    request = {k: v for k, v in row.items()
               if k in ("class", "dataset", "activity", "experiment", "model",
                        "realization", "generation", "expver", "stream")}
    request["year" if row.get("stream") == "clmn" else "date"] = row["first"]

    found = {}
    for resolution in sorted(_fdb._values(request, 2, "resolution")):
        nside = _fdb.measure_nside({**request, "resolution": resolution})
        if nside:
            found[resolution] = nside
    if not found:
        return None
    if len(found) == 1:
        return next(iter(found.values()))
    return " ".join(f"{res}:{nside}" for res, nside in sorted(found.items()))


def runs(fdb=None, *, fdb_home=None, check_nside=False):
    """Every run an FDB contains, as a DataFrame. The first question to ask.

    Reads database directory names, so it costs one listing per root rather
    than one index open per database -- on MN5 that is 0.01s for a 9720-database
    FDB.

    The ``databases`` count is the number of FDB databases, which is not a unit
    anyone thinks in. What it spans depends on the stream, because that is what
    the schema keys the database on: **one database is one day** for the hourly
    and daily streams (``clte``, keyed on ``date``) and **one year** for the
    monthly stream (``clmn``, keyed on ``year``). The ``covers`` column says
    that in words, and ``first``/``last`` give the actual range.

    ``check_nside=True`` adds an ``nside`` column, measured from one GRIB header
    per run and resolution. It is off by default because it is the only part of
    this function that talks to the FDB rather than the filesystem: a few
    hundred milliseconds per run, which on a shared FDB with hundreds of runs
    is minutes rather than the usual hundredth of a second.
    """
    import pandas as pd

    from . import filesystem as fs

    _fdb.configure(fdb, fdb_home=fdb_home)
    roots = fs.all_roots(_fdb._config_dict())
    if not roots:
        raise LookupError("No FDB data roots in this config exist on this machine.")

    rows = []
    for key, tops in fs.list_runs(roots).items():
        row = dict(zip(fs.L1_ORDER, key))
        row["databases"] = len(tops)
        unit = DB_SPANS.get(row.get("stream"), "database")
        row["covers"] = f"{len(tops)} {unit}{'s' if len(tops) != 1 else ''}"
        row["first"], row["last"] = min(tops), max(tops)
        rows.append(row)
    if not rows:
        raise LookupError(f"No FDB databases under {', '.join(map(str, roots))}.")

    if check_nside:
        for row in rows:
            row["nside"] = _measure_run_nside(row)

    frame = pd.DataFrame(rows)
    order = ["activity", "experiment", "model", "realization", "stream",
             "generation", "expver", "class", "dataset", "covers", "databases",
             "first", "last", "nside"]
    frame = frame[[c for c in order if c in frame]]
    return frame.sort_values(["activity", "experiment", "model", "realization",
                              "stream"]).reset_index(drop=True)


def overview(fdb=None, *, activity="story-nudging", experiment="hist",
             member=1, frequency="monthly", resolution="standard",
             model="ifs-fesom", portfolio=None, fdb_home=None,
             scan_mode="auto", tier="full", **overrides):
    """What one run holds, across *every* levtype, as a DataFrame.

    ``open_run`` opens one levtype at a time, so on an unfamiliar run this
    answers the question that comes first: which families of fields are there,
    how far do they go, and how many levels do they have.
    """
    import pandas as pd

    if "levtype" in overrides:
        raise TypeError(
            "overview() reports every levtype, so pinning one makes no sense -- "
            "it would silently apply to all of them. Use scan_run(levtype=...) "
            "for a single levtype."
        )

    _fdb.configure(fdb, fdb_home=fdb_home)
    stream = _STREAM[frequency]
    # Deliberately *not* narrowed by frequency: the point is to show everything
    # the run holds, and the ocean levtypes are daily where the atmosphere is
    # hourly. Each row reports its own frequencies instead.
    catalogue = portfolio or _default_portfolio(activity, stream, None, tier)

    rows = []
    for levtype, spec in catalogue.items():
        request = _base_request(activity, experiment, member, model, resolution,
                                levtype, stream, overrides)
        try:
            found = _fdb.scan(request, stream, mode=scan_mode)
        except LookupError:
            continue                      # nothing archived for this levtype
        times = found["times"]
        archived = {name for name in spec["variables"]
                    if not found["params"] or to_param_id(name) in found["params"]}
        in_stream = {f for f, st in STREAM_OF.items() if st == stream}
        freqs = sorted({f for name in archived
                        for f in _portfolio.frequencies(name, tier, levtype)
                        if f in in_stream})
        rows.append({
            "levtype": levtype,
            "freq": "/".join(freqs),
            "variables": len(archived),
            "timesteps": len(times),
            "first": "/".join(times[0]),
            "last": "/".join(times[-1]),
            "levels": len(found["levels"]),
            "names": " ".join(sorted(archived)),
        })
    if not rows:
        raise LookupError(
            f"Nothing archived for activity={activity!r} experiment={experiment!r} "
            f"member={member} at resolution={resolution!r}, in any levtype."
        )
    return pd.DataFrame(rows)


def open_run(fdb=None, *, activity="story-nudging", experiment="hist",
             member=1, frequency="monthly", resolution="standard",
             levtype=None, model="ifs-fesom", portfolio=None, tier="full",
             variables=None, start=None, end=None, levels=None, nside=None,
             fdb_home=None, time_chunk=None, add_latlon=False,
             ordering="nested", scan=True,
             scan_mode="auto", fetcher=None, **overrides):
    """Open one Climate DT run from a local FDB as a lazy xarray Dataset.

    Parameters
    ----------
    fdb : str or Path
        FDB root directory (one containing ``etc/fdb/config.yaml``) or a config
        file. Handing over the root is preferred: it also sets ``FDB_HOME``,
        which the shared DestinE config needs to resolve its schema. Omit to use
        whatever ``FDB5_CONFIG``/``FDB_HOME`` the environment already has.
    activity, experiment : str
        MARS keys, e.g. ``"story-nudging"`` and ``"hist"``. ``"plus2K"`` is
        accepted as an alias for the ``tplus2.0k`` experiment key.
    member : int
        Ensemble member (the ``realization`` key). Default 1.
    frequency : {"monthly", "hourly", "daily", "6-hourly"}
        Picks the stream: monthly -> clmn, otherwise clte.
    resolution : {"standard", "high"}
        The FDB's own resolution key, not a target grid -- data comes back on
        its native HEALPix mesh either way.
    levtype : {"sfc", "pl", "hl", "sol", "o2d", "o3d"}, optional
        Which family of fields to open. Left out, it is inferred from
        ``variables`` -- ``avg_thetao`` implies ``o3d``, ``avg_tos`` implies
        ``o2d`` -- and falls back to ``"sfc"`` when no variables are named.
        Only ``sd``/``avg_sd`` (sfc, sol) and ``u``/``v`` (pl, hl) are
        ambiguous; those raise rather than guess.
    portfolio : dict, optional
        Variable catalogue keyed by levtype. Defaults to the Gen2 portfolio for
        this activity. Whatever is passed gets intersected with what the scan
        found in the FDB, so a run on a reduced or minimal portfolio yields only
        the variables it really has.
    variables : list of str, optional
        Restrict to these variables instead of the whole levtype.
    start, end : str or Timestamp, optional
        Time range. **Passing both skips the expensive half of the scan** --
        enumerating dates -- which is what makes opening a long hourly run slow.
        The cheap half still runs: one index probe, so the variable list is
        still narrowed to what is archived and the levels are still the real
        ones. Pass ``scan=False`` as well to skip even that.
        Passing only one end filters a scanned axis instead.
    levels : list of int, optional
        Vertical levels for pl/hl/sol/o3d. Defaults to the scanned levels, then
        the portfolio's.
    nside : int, optional
        HEALPix Nside. Inferred from (activity, resolution) when omitted.
    time_chunk : int, optional
        Timesteps per dask chunk, i.e. per FDB request. Defaults to one calendar
        year for monthly, one calendar day for hourly, 30 days for daily.
    add_latlon : bool
        Attach per-cell ``lat``/``lon`` coordinates, which is what easygems'
        ``attach_coords`` does and what its ``healpix_show`` plots from. Needs
        healpy.
    ordering : {"nested", "ring"}
        HEALPix indexing scheme. DestinE archives ``nested`` -- confirmed
        against the GRIB ``orderingConvention`` -- and a mismatch is caught
        when the first field arrives rather than silently scrambling the map.
    scan : bool
        Set False to assert that the index must never be read at all; requires
        start= and end=. Note this also gives up the variable narrowing and the
        real level list, which a full range on its own does not.
    scan_mode : {"auto", "filesystem", "index"}
        How to find out what the run holds. ``"filesystem"`` reads the database
        directory names -- on MN5 that is 8-70x faster, and it agreed with the
        index on every run tested. ``"index"`` asks FDB, which is
        authoritative: it sees masked and duplicated entries, and it works when
        the config's roots are not mounted locally. ``"auto"`` (the default)
        tries the filesystem and falls back to the index if it cannot be read.
        Both then probe the index once for params and levels.
    fetcher : callable, optional
        ``fetcher(request) -> earthkit FieldList``, replacing the earthkit FDB
        source. Lets the dataset be built against a stub in tests, or against a
        different backend entirely.
    **overrides
        Extra MARS keys merged into every request (e.g. ``expver="0002"``).
    """
    _fdb.configure(fdb, fdb_home=fdb_home)

    stream = _STREAM[frequency]
    catalogue = portfolio or _default_portfolio(activity, stream, frequency, tier)
    levtype = _resolve_levtype(levtype, variables, catalogue)
    if levtype not in catalogue:
        raise KeyError(f"levtype {levtype!r} not in portfolio. "
                       f"Have: {', '.join(sorted(catalogue))}")
    spec = catalogue[levtype]

    request = _base_request(activity, experiment, member, model, resolution,
                            levtype, stream, overrides)

    have_range = start is not None and end is not None
    if not scan and not have_range:
        raise ValueError(
            "scan=False needs an explicit start= and end=: with no scan there is "
            "nothing to derive the time axis from. Note that passing both start= "
            "and end= already skips the scan, so scan=False is only needed to "
            "assert that it must never run."
        )
    if not scan:
        scanned = None
    elif have_range:
        # The range settles the time axis, but only the index knows which
        # variables and levels are archived -- and that is one cheap probe,
        # not the expensive date enumeration.
        scanned = _fdb.probe_run(request, stream, start, end)
    else:
        scanned = _fdb.scan(request, stream, mode=scan_mode)
    if scanned and scanned.get("experiment"):
        # The scan found the run under a different spelling; every data request
        # has to use that one too, or it will come back empty.
        request["experiment"] = scanned["experiment"]

    # ── time axis ───────────────────────────────────────────────────────
    if start is not None and end is not None:
        times = pd.date_range(start, end, freq=PANDAS_FREQ[frequency])
    else:
        times = _times_from_scan(scanned, stream, PANDAS_FREQ[frequency])
        if start is not None:
            times = times[times >= pd.Timestamp(start)]
        if end is not None:
            times = times[times <= pd.Timestamp(end)]
    # A range wider than the run is not merely empty at the edges -- it builds
    # a dask chunk for every timestep in it. Asking for six years of 3-D ocean
    # when 29 days exist is 870,000 chunks and 18s of graph construction, all
    # but a few thousand of which would resolve to NaN. Trim to what the FDB
    # actually has, and say so.
    if scanned and scanned.get("archived"):
        top = (lambda t: str(t.year)) if stream == "clmn" else (
            lambda t: t.strftime("%Y%m%d"))
        have = set(scanned["archived"])
        kept = times[[top(t) in have for t in times]]
        if len(kept) != len(times):
            print(f"[destine_fdb] the range covers {len(times)} steps but the run "
                  f"holds {len(kept)}; trimming to what is archived "
                  f"({'none' if not len(kept) else f'{kept[0]} .. {kept[-1]}'}). "
                  f"Pass scan=False to keep the full range.", file=sys.stderr)
        times = kept

    if len(times) == 0:
        raise LookupError("No timesteps found for this run in the given range.")

    # ── variables: catalogue intersected with what is archived ──────────
    wanted = list(variables) if variables else list(spec["variables"])
    selected = {}
    dropped = []
    for name in wanted:
        var_spec = spec["variables"].get(name)
        if var_spec is None:
            # The monthly stream prefixes time-means with avg_; the hourly one
            # does not. Asking for the wrong spelling is the usual mistake.
            for alt in (f"avg_{name}", name[4:] if name.startswith("avg_") else None):
                if alt and alt in spec["variables"]:
                    raise KeyError(
                        f"{name!r} is not in the {stream} {levtype} portfolio, "
                        f"but {alt!r} is -- the {stream} stream spells it that way."
                    )
            raise KeyError(f"{name!r} is not in the {stream} {levtype} portfolio.")
        param = to_param_id(name)
        if scanned is not None and scanned["params"] and param not in scanned["params"]:
            dropped.append(name)
            continue
        dims = ("time", "level", "cell") if _portfolio.is_3d(var_spec) else ("time", "cell")
        selected[name] = {**var_spec, "dims": dims, "param": param}

    if not selected:
        raise LookupError(
            f"None of the {levtype} portfolio's variables are archived in this "
            f"run. The FDB holds paramIds "
            f"{sorted(scanned['params']) if scanned else '(not scanned)'}."
        )

    # ── coordinates ─────────────────────────────────────────────────────
    # Measured, not inferred: `resolution` is a MARS key whose meaning depends
    # on the model resolution behind the run (`high` is H512 for one run and
    # H1024 for another), so the only reliable answer is the one in the data.
    # Costs one lazy listing and a few hundred bytes -- no field is read.
    if not nside:
        nside = _fdb.measure_nside(request)
    if not nside:
        raise LookupError(
            "Could not read the run's HEALPix Nside from the FDB. Nothing "
            "matched the request, or this pyfdb is too old to hand out a data "
            "handle. Pass nside= explicitly if you know it."
        )
    coords = {"time": times, "cell": range(_portfolio.npix(nside))}

    needs_level = any("level" in v["dims"] for v in selected.values())
    if needs_level:
        chosen = (levels
                  or (scanned["levels"] if scanned and scanned["levels"] else None)
                  or spec["levels"])
        if not chosen:
            raise LookupError(f"levtype {levtype!r} needs levels but none were found.")
        coords["level"] = list(chosen)

    dataset = build_dataset(
        request,
        times=times,
        variables=selected,
        stream=stream,
        freq=PANDAS_FREQ[frequency],
        nside=nside,
        levels=coords.get("level"),
        time_chunk=time_chunk,
        fetcher=fetcher,
        indexing_scheme=ordering,
        coords_fn=(lambda n: _latlon_coords(n, ordering)) if add_latlon else None,
    )
    dataset.attrs.update({
        "activity": activity,
        "experiment": request["experiment"],
        "realization": str(member),
        "resolution": resolution,
        "levtype": levtype,
        "stream": stream,
        "nside": nside,
        "grid": f"H{nside}",
        "indexing_scheme": ordering,
        "healpix_nside": nside,
        "healpix_nest": ordering == "nested",
        "source": "local FDB via destine_fdb",
    })
    if dropped:
        dataset.attrs["portfolio_missing"] = " ".join(sorted(dropped))
    return dataset


def _latlon_coords(nside, ordering="nested"):
    """Per-cell latitude/longitude, for plotting or nearest-point selection.

    Same coordinates easygems' ``attach_coords`` adds, so ``healpix_show`` and
    friends work on the result.
    """
    try:
        import healpy as hp
    except ImportError:
        raise ImportError(
            "add_latlon=True needs healpy (pip install 'destine-fdb[healpix]')"
        ) from None
    lon, lat = hp.pix2ang(nside, np.arange(12 * nside * nside),
                          nest=(ordering == "nested"), lonlat=True)
    return {"lat": ("cell", lat.astype("float32")),
            "lon": ("cell", (((lon + 180) % 360) - 180).astype("float32"))}
