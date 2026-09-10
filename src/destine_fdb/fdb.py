"""Locating a local FDB, and scanning it for what is actually archived.

Two jobs:

``configure()``
    Turn a user-supplied ``fdb=`` (a directory, a config file, or nothing) into
    the environment that ``pyfdb`` and ``earthkit-data`` both read. Notably it
    sets ``FDB_HOME`` when handed a directory: the shared DestinE configs are
    ``type: select`` and point their schema at ``~fdb/etc/fdb/schema``, which
    eckit expands from ``$FDB_HOME``. Miss that and every request fails to find
    a schema, with an error that does not mention FDB_HOME.

``scan()``
    Ask the FDB which dates, params and levels a run actually contains. This is
    the whole reason to prefer a local FDB over the data bridge: the runs that
    live here are often partial or unpublished, so a hardcoded time range from a
    portfolio table is a guess, while the FDB index is ground truth. It also
    means a reduced/minimal portfolio needs no table of its own -- it is just
    the full catalogue intersected with what the scan found.
"""

import os
import sys
import time
from pathlib import Path

import pandas as pd

def _chronological(times):
    """Sort (year, month) pairs numerically.

    MARS months are unpadded strings, so a plain sort puts month 10 before
    month 2. The Dataset's time axis is rebuilt from timestamps and is correct
    either way, but the scan's own report is read by humans and by
    ``_probe_params``, which wants a real newest-first candidate.
    """
    return sorted(times, key=lambda pair: (int(pair[0]), int(pair[1])))


# Directory the active config was found in, used to locate a relocated FDB.
_CONFIG_DIR = None

# MARS keys that carry the time coordinate, per stream.
_TIME_KEYS = {"clmn": ("year", "month"), "clte": ("date", "time")}


def configure(fdb=None, fdb_home=None, env=None):
    """Point pyfdb/earthkit at an FDB. Returns the config dict it applied.

    Parameters
    ----------
    fdb : str or Path, optional
        Either an FDB root directory (one holding ``etc/fdb/config.yaml``), or
        a path to an FDB5 config YAML directly. If omitted, the ambient
        ``FDB5_CONFIG`` / ``FDB5_CONFIG_FILE`` / ``FDB_HOME`` are left alone.
    fdb_home : str or Path, optional
        Override for ``FDB_HOME``. Only needed when ``fdb`` points straight at a
        config file whose schema path uses eckit's ``~fdb`` syntax.
    env : dict, optional
        Mapping to mutate instead of ``os.environ`` (for testing).
    """
    env = os.environ if env is None else env
    applied = {}

    if fdb is not None:
        path = Path(fdb).expanduser()
        if path.is_dir():
            config_file = path / "etc" / "fdb" / "config.yaml"
            if not config_file.is_file():
                raise FileNotFoundError(
                    f"{path} looks like an FDB root but has no etc/fdb/config.yaml. "
                    f"Pass the config file directly if it lives elsewhere."
                )
            applied["FDB_HOME"] = str(path)
        elif path.is_file():
            config_file = path
        else:
            raise FileNotFoundError(f"No such FDB root or config file: {path}")
        applied["FDB5_CONFIG"] = config_file.read_text()
        applied["_config_file"] = str(config_file)
        global _CONFIG_DIR
        _CONFIG_DIR = config_file.parent.parent.parent

    if fdb_home is not None:
        applied["FDB_HOME"] = str(Path(fdb_home).expanduser())

    for key, value in applied.items():
        if not key.startswith("_"):
            env[key] = value

    if "FDB5_CONFIG" not in env and "FDB5_CONFIG_FILE" not in env and "FDB_HOME" not in env:
        raise RuntimeError(
            "No FDB configured. Pass fdb=<root or config.yaml>, or set one of "
            "FDB5_CONFIG / FDB5_CONFIG_FILE / FDB_HOME in the environment."
        )
    # earthkit-data's fdb source reads FDB5_CONFIG, not FDB5_CONFIG_FILE.
    if "FDB5_CONFIG" not in env and "FDB5_CONFIG_FILE" in env:
        env["FDB5_CONFIG"] = Path(env["FDB5_CONFIG_FILE"]).expanduser().read_text()

    return applied


def _handle():
    import pyfdb
    return pyfdb.FDB()


def _elements(request, depth):
    """Yield raw pyfdb list elements, or nothing on the legacy dict API.

    Only the 5.21-style objects carry ``data_handle``/``length``, which is what
    reading and Nside measurement need. Callers that only want keys use
    ``_list`` instead, which works on both APIs.
    """
    fdb = _handle()
    import inspect

    try:
        params = inspect.signature(fdb.list).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return

    if "level" not in params:
        return
    yield from fdb.list(_alternatives(request or {}), level=depth)


def _alternatives(request):
    """Split MARS ``a/b/c`` alternatives into lists.

    ``list()`` matches values literally, so a joined string finds nothing;
    request builders elsewhere use the MARS spelling.
    """
    return {k: (v.split("/") if isinstance(v, str) and "/" in v else v)
            for k, v in request.items()}


def _member(obj, name):
    """pyfdb 5.21 exposes these as methods; other builds as plain attributes."""
    value = getattr(obj, name)
    return value() if callable(value) else value


def _grib_data_points(head):
    """Number of data points from a GRIB2 header, without decoding the field.

    Section 3 octets 7-10 hold the point count, and section 3 sits a few
    hundred bytes into the message -- so this needs the head of the message,
    not the field. For HEALPix that count is 12*Nside^2, which is the only
    honest way to know the grid: `resolution` is a MARS key whose meaning
    (`high` -> H512 or H1024) depends on the model resolution behind the run.
    """
    import struct

    if head[:4] != b"GRIB":
        return None
    if head[7] != 2:                             # GRIB1 puts the grid elsewhere
        return None
    pos = 16                                     # section 0 is fixed-length
    while pos + 10 <= len(head):
        seclen, secnum = struct.unpack(">IB", head[pos:pos + 5])
        if secnum == 3:
            return struct.unpack(">I", head[pos + 6:pos + 10])[0]
        if seclen <= 0:
            return None
        pos += seclen
    return None


def measure_nside(request, head_bytes=512):
    """Exact HEALPix Nside for a run, read from one GRIB header.

    Costs one lazy listing plus a few hundred bytes -- no field is retrieved.
    Returns None when the FDB holds nothing for the request, or when pyfdb is
    too old to hand out a data handle.
    """
    for element in _elements(request, depth=3):
        try:
            handle = _member(element, "data_handle")
            if callable(getattr(handle, "open", None)):
                handle.open()
            try:
                head = handle.read(head_bytes)
            finally:
                if callable(getattr(handle, "close", None)):
                    handle.close()
        except Exception:                        # noqa: BLE001 - best effort
            return None
        points = _grib_data_points(head)
        if not points or points % 12:
            return None
        nside = int(round((points // 12) ** 0.5))
        return nside if 12 * nside * nside == points else None
    return None


def _list(request, depth, expand=True):
    """Yield the MARS key dict of every FDB entry matching ``request``.

    pyfdb's listing API changed shape: 5.21 takes ``level=`` and returns objects
    with ``.combined_key()``, while the older interface takes
    ``keys=``/``depth=``/``expand=`` and returns plain dicts. Both are in the
    wild on HPC systems -- often an older one than PyPI's latest, because it has
    to match the ``libfdb5.so`` from a model build -- so support both rather
    than pinning a version the site may not have.
    """
    fdb = _handle()
    import inspect

    try:
        params = inspect.signature(fdb.list).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        params = {}

    if "level" in params:
        for element in fdb.list(request or {}, level=depth):
            yield element.combined_key()
        return

    kwargs = {"keys": True, "duplicates": False, "depth": depth}
    if "expand" in params:
        kwargs["expand"] = expand
    for entry in fdb.list(request, **kwargs):
        keys = entry.get("keys")
        if keys:
            yield keys


def _values(request, level, key):
    """Distinct values of one MARS key across a listing."""
    return {k[key] for k in _list(request, depth=level) if key in k}


def _probe(request, level=3):
    """One level-3 listing: params, levels and (for clte) the hours in a day."""
    params, levels, times = set(), set(), set()
    for keys in _list(request, depth=level):
        if "param" in keys:
            try:
                params.add(int(keys["param"]))
            except ValueError:
                pass
        if keys.get("levelist"):
            try:
                levels.add(int(float(keys["levelist"])))
            except ValueError:
                pass
        if "time" in keys:
            times.add(keys["time"])
    return params, levels, times


def experiments(base_request, max_entries=20000, timeout=10.0):
    """Every (activity, experiment, model, realization) present, for error messages.

    Time-boxed as well as capped. This only ever runs to explain a failure, and
    an unfiltered level-1 walk of a shared FDB is minutes of GPFS metadata IO --
    9720 databases on MN5. A truncated hint arrives; an exhaustive one looks
    like a hang, right when the user is already confused about why nothing was
    found.
    """
    relaxed = {k: v for k, v in base_request.items()
               if k in ("class", "dataset", "stream")}
    deadline = time.monotonic() + timeout
    found = set()
    for n, keys in enumerate(_list(relaxed, depth=1)):
        found.add((keys.get("activity"), keys.get("experiment"),
                   keys.get("model"), keys.get("realization")))
        if n + 1 >= max_entries or time.monotonic() > deadline:
            break
    return sorted(x for x in found if any(x))


def _resolve_experiment(base_request, top_key):
    """Find the run, retrying on a case-insensitive experiment match.

    Returns ``(base_request, tops, resolved_spelling)``. Most FDB schemas fold
    the experiment key, but the shared DestinE FDB has databases on disk under
    both ``Tplus2.0K`` and ``tplus2.0k``, so do not rely on it.
    """
    tops = sorted(_values(base_request, 1, top_key))
    if tops:
        return base_request, tops, None

    wanted = str(base_request.get("experiment", "")).lower()
    if not wanted:
        return base_request, tops, None

    for activity, experiment, _model, _realization in experiments(base_request):
        if (experiment or "").lower() != wanted or experiment == base_request.get("experiment"):
            continue
        candidate = {**base_request, "experiment": experiment}
        found = sorted(_values(candidate, 1, top_key))
        if found:
            return candidate, found, experiment
    return base_request, tops, None


def _not_found(base_request, top_key, stream):
    known = experiments(base_request)
    hint = ""
    if known:
        listed = ", ".join("/".join(str(p) for p in x) for x in known[:12])
        more = " (truncated)" if len(known) > 12 else ""
        hint = (f" This FDB holds activity/experiment/model/realization: "
                f"{listed}{more}.")
    return LookupError(
        f"No {top_key}s found for activity={base_request.get('activity')!r} "
        f"experiment={base_request.get('experiment')!r} "
        f"model={base_request.get('model')!r} "
        f"realization={base_request.get('realization')!r} "
        f"stream={stream!r}.{hint}"
    )


def _no_data_at(base_request, tops, top_key, timeout=10.0):
    """The run exists, but not for the asked-for resolution/levtype.

    Time-boxed like :func:`experiments`: dropping resolution and levtype widens
    the level-2 listing to every index in the run, which on a long hourly run is
    one per day times every levtype archived.
    """
    relaxed = {key: value for key, value in base_request.items()
               if key not in ("resolution", "levtype")}
    deadline = time.monotonic() + timeout
    combos = set()
    for keys in _list(relaxed, depth=2):
        combos.add((keys.get("resolution"), keys.get("levtype")))
        if time.monotonic() > deadline:
            break
    combos = sorted(combos - {(None, None)})
    listed = ", ".join(f"{r}/{lt}" for r, lt in combos[:20]) or "(none)"
    return LookupError(
        f"The run exists ({len(tops)} {top_key}s) but holds nothing at "
        f"resolution={base_request.get('resolution')!r} "
        f"levtype={base_request.get('levtype')!r}. "
        f"Available resolution/levtype: {listed}."
    )


def _probe_params(base_request, top_key, candidates, required=True):
    """Level-3 probe, retrying across candidate dates/years until one has data.

    With ``required=False`` a probe that cannot run at all -- no ``pyfdb``, no
    ``libfdb5`` -- degrades to "no params known" rather than failing. That is
    what lets ``scan_mode="filesystem"`` describe an FDB on a machine that
    cannot open one, at the cost of not narrowing the variable list.
    """
    for value in candidates:
        try:
            params, levels, times = _probe({**base_request, top_key: value})
        except Exception as exc:  # noqa: BLE001
            if required:
                raise
            print(f"[destine_fdb] no index probe ({type(exc).__name__}: "
                  f"{str(exc)[:80]}); variables will not be narrowed to what is "
                  f"archived.", file=sys.stderr)
            return set(), set(), set()
        if params:
            return params, levels, times
    return set(), set(), set()


def probe_run(base_request, stream, start, end):
    """Params and levels for a run, without discovering its time axis.

    When the caller supplies both ends of the time range there is nothing left
    for the index to say about *when* -- but it is still the only thing that
    knows *what*. Enumerating dates is the expensive half of a scan; a level-3
    probe of a single date is ~0.03s, and it is what returns the archived
    params and the real level list.

    Skipping it is why an explicit range used to hand back the padded fallback
    levels: 75 ocean levels where the storyline runs have 70.

    Returns the same shape as :func:`scan`, with an empty ``times``.
    """
    top_key = "year" if stream == "clmn" else "date"
    start, end = pd.Timestamp(start), pd.Timestamp(end)

    def key(ts):
        return str(ts.year) if stream == "clmn" else ts.strftime("%Y%m%d")

    # Probing a date that is not archived is not merely useless, it is slow:
    # FDB widens the search and a single miss cost 16s on MN5. So ask the
    # filesystem which dates actually exist -- that is a directory listing, and
    # it turns the guess into a fact.
    candidates, archived = None, None
    try:
        from . import filesystem as fs

        roots = fs.data_roots(_config_dict(), base_request, fallback=_CONFIG_DIR)
        archived = sorted(fs.databases(roots, base_request, top_key))
        inside = [t for t in archived if key(start) <= t <= key(end)]
        # Newest first: a run still being written is complete at its start and
        # ragged at its end, so the newest archived date in range is the one
        # most likely to carry every param.
        candidates = list(reversed(inside or archived))[:3]
    except Exception:  # noqa: BLE001 - fall back to guessing from the range
        candidates, archived = None, None

    if not candidates:
        middle = start + (end - start) / 2
        candidates = list(dict.fromkeys([key(end), key(middle), key(start)]))

    base_request, _, resolved = _resolve_experiment(base_request, top_key)
    params, levels, _ = _probe_params(base_request, top_key, candidates,
                                      required=False)
    if not params:
        print(f"[destine_fdb] index probe found nothing at {', '.join(candidates)}; "
              f"variables will not be narrowed and levels fall back to the "
              f"portfolio's.", file=sys.stderr)
    return {"times": [], "params": params, "levels": sorted(levels),
            "raw_depth": "probe", "experiment": resolved, "archived": archived}


SLOW_SCAN_SECONDS = 20.0


def _warn_if_slow(elapsed, stream):
    """Tell the user how to skip a scan that turned out to be expensive.

    Scan cost tracks databases-per-run, and for hourly data one database is one
    day, so a long free-running experiment can take minutes of GPFS metadata IO.
    Nothing is wrong when that happens -- but the user should know the escape
    hatch exists before they run it a second time.
    """
    if elapsed < SLOW_SCAN_SECONDS:
        return
    print(
        f"[destine_fdb] the {stream} index scan took {elapsed:.0f}s. Long hourly "
        f"runs have one database per day, so this grows with the run. Passing "
        f"both start= and end= to open_run() skips it entirely.",
        file=sys.stderr,
    )


def _config_dict(env=None):
    """The active FDB5 config, parsed. Needed to find the data roots."""
    import yaml
    env = os.environ if env is None else env
    text = env.get("FDB5_CONFIG")
    if not text and env.get("FDB5_CONFIG_FILE"):
        text = Path(env["FDB5_CONFIG_FILE"]).expanduser().read_text()
    if not text:
        raise RuntimeError(
            "Filesystem scanning needs the FDB config to locate the data roots, "
            "but neither FDB5_CONFIG nor FDB5_CONFIG_FILE is set. Pass "
            "fdb=<root or config.yaml> to open_run()."
        )
    return yaml.safe_load(text) or {}


def scan_filesystem(base_request, stream, env=None):
    """:func:`scan` by reading database directory names. See :mod:`.filesystem`.

    The time axis comes from the directories; params, levels and (for hourly
    data) the hours in a day still come from one level-3 index probe, which is
    cheap because it is scoped to a single date and is the part directory names
    cannot answer.
    """
    from . import filesystem as fs

    top_key = "year" if stream == "clmn" else "date"
    roots = fs.data_roots(_config_dict(env), base_request, fallback=_CONFIG_DIR)
    if not roots:
        raise LookupError(
            "No FDB data roots matched this request. Either the config has no "
            "rule for it, or it is not a type:select/type:local config -- use "
            "the default scan_mode='index' instead."
        )

    found = fs.databases(roots, base_request, top_key)
    if not found:
        raise LookupError(
            f"No database directories under {', '.join(str(r) for r in roots)} "
            f"match activity={base_request.get('activity')!r} "
            f"experiment={base_request.get('experiment')!r} "
            f"model={base_request.get('model')!r} "
            f"realization={base_request.get('realization')!r} stream={stream!r}."
        )

    tops = sorted(found)
    resolution = base_request.get("resolution")
    levtype = base_request.get("levtype")

    if stream == "clmn":
        # Months live one level down, but the index *filenames* carry them, so
        # a listdir per year is enough -- and there are only ever a few years.
        times = set()
        for year in tops:
            for database in found[year]:
                for keys in fs.index_keys(database):
                    if resolution in keys and levtype in keys and keys:
                        times.add((year, keys[0]))
        times = _chronological(times)
        if not times:
            raise LookupError(
                f"Found {len(tops)} year directories but none carry an index for "
                f"resolution={resolution!r} levtype={levtype!r}."
            )
        years = [year for year, _ in times]
        params, levels, _ = _probe_params(
            base_request, "year", dict.fromkeys([years[-1], years[0]]),
            required=False)
        return {"times": times, "params": params, "levels": sorted(levels),
                "raw_depth": "filesystem", "experiment": None}

    # clte: directory names give the dates; the hours need one index probe.
    dates = [d for d in tops
             if any(fs.levtype_present(db, resolution, levtype)
                    for db in found[d][:1])] or tops
    params, levels, hours_first = _probe({**base_request, "date": dates[0]})
    if len(dates) == 1:
        hours_last = hours_first
    else:
        more_params, more_levels, hours_last = _probe(
            {**base_request, "date": dates[-1]})
        params |= more_params
        levels |= more_levels
    if not hours_first:
        raise LookupError(
            f"Directory {dates[0]} exists but its index has no 'time' key for "
            f"resolution={resolution!r} levtype={levtype!r}. Hourly data keeps "
            f"its hours inside the index, so this mode still needs to read it."
        )

    times = [(date, hour) for date in dates[:-1] for hour in sorted(hours_first)]
    times += [(dates[-1], hour) for hour in sorted(hours_last or hours_first)]
    return {"times": sorted(times), "params": params, "levels": sorted(levels),
            "raw_depth": "filesystem", "experiment": None}


def scan(base_request, stream, mode="auto"):
    """Report what a run holds: time keys, params, levels.

    Follows the Climate DT schema rather than listing everything, because a
    level-3 listing of a whole run enumerates every field -- 32s for one levtype
    of one month of hourly data on MN5, and it only grows::

        clte:  [ ..., stream=clte, date ] [ resolution, type, levtype ] [ time, levelist?, param ]
        clmn:  [ ..., stream=clmn, year ] [ month, resolution, type, levtype ] [ levelist?, param ]

    Level 1 is one entry per day or year and is effectively free, but its keys
    are *not* filtered by resolution or levtype -- those are level-2 keys, so a
    database can appear at level 1 while holding nothing for the levtype asked
    for. The time axis therefore comes from level 2, which is both filtered and
    still cheap. Only hours, params and levels need level 3, and that is probed
    for a single date -- plus the last date, so a run that stopped part-way
    through a day still gets an exact time axis.

    Returns ``{"times": [(date, time), ...], "params": {...}, "levels": [...],
    "experiment": ...}`` with ``times`` as ``(year, month)`` pairs for clmn.
    ``experiment`` is set only when the run was found under a different spelling
    than the one asked for.
    """
    if mode == "auto":
        # Filesystem first because it is 8-70x faster and agreed with the index
        # on every run tested, but fall back rather than fail: it needs the
        # config's roots to be mounted here, and a remote or non-toc FDB has
        # none to read.
        try:
            return scan_filesystem(base_request, stream)
        except LookupError:
            raise                       # the run genuinely is not there
        except Exception as exc:        # noqa: BLE001 - any structural problem
            print(f"[destine_fdb] filesystem scan unavailable ({type(exc).__name__}: "
                  f"{str(exc)[:70]}); falling back to the index.", file=sys.stderr)
    elif mode == "filesystem":
        return scan_filesystem(base_request, stream)
    elif mode != "index":
        raise ValueError(
            f"scan_mode must be 'auto', 'filesystem' or 'index', got {mode!r}")

    top_key = "year" if stream == "clmn" else "date"
    started = time.monotonic()
    base_request, tops, resolved = _resolve_experiment(base_request, top_key)
    if not tops:
        raise _not_found(base_request, top_key, stream)

    if stream == "clmn":
        # year is level 1, month is level 2 -- one filtered listing gives the
        # exact (year, month) pairs for this resolution and levtype.
        times = _chronological({(keys["year"], keys["month"])
                                for keys in _list(base_request, depth=2)
                                if "year" in keys and "month" in keys})
        if not times:
            raise _no_data_at(base_request, tops, top_key)
        years = [year for year, _ in times]
        params, levels, _ = _probe_params(
            base_request, "year", dict.fromkeys([years[-1], years[0]]))
        _warn_if_slow(time.monotonic() - started, stream)
        return {"times": times, "params": params, "levels": sorted(levels),
                "raw_depth": 2, "experiment": resolved}

    # clte: date is level 1 but unfiltered, so take the dates from level 2.
    dates = sorted({keys["date"] for keys in _list(base_request, depth=2)
                    if "date" in keys})
    if not dates:
        raise _no_data_at(base_request, tops, top_key)

    params, levels, hours_first = _probe({**base_request, "date": dates[0]})
    if len(dates) == 1:
        hours_last = hours_first
    else:
        more_params, more_levels, hours_last = _probe(
            {**base_request, "date": dates[-1]})
        params |= more_params
        levels |= more_levels
    if not params:
        params, levels, _ = _probe_params(
            base_request, "date", dates[len(dates) // 2:len(dates) // 2 + 1])

    if not hours_first:
        raise LookupError(
            f"Found dates for this run but no 'time' key beneath {dates[0]}. "
            f"Check resolution={base_request.get('resolution')!r} and "
            f"levtype={base_request.get('levtype')!r}."
        )

    times = [(date, hour) for date in dates[:-1] for hour in sorted(hours_first)]
    times += [(dates[-1], hour) for hour in sorted(hours_last or hours_first)]
    _warn_if_slow(time.monotonic() - started, stream)
    return {"times": sorted(times), "params": params, "levels": sorted(levels),
            "raw_depth": 3, "experiment": resolved}
