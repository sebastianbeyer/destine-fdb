"""Assemble a lazy xarray Dataset whose dask chunks are FDB requests.

The idea is borrowed from ECMWF's ``polytope_zarr.py`` in `polytope-examples`:
synthesise the dataset's shape and metadata up front, and only turn coordinates
into a data request when someone actually reads values. That implementation does it by faking a zarr v2 store, which pins
it to ``zarr<3``. Here the same laziness comes from ``dask.delayed``, so the
package works on any zarr version and one dask chunk maps to exactly one FDB
request.

The blocking rule is what keeps requests exact. A MARS request is a cross
product of its keys, so ``date=[d1,d2] time=[00,12]`` asks for four fields. A
block is therefore never allowed to span a calendar day (hourly) or a calendar
year (monthly), which makes the cross product precisely the set of timesteps in
the block -- no over-fetching, and the returned field count is a real check.
"""

import numpy as np
import pandas as pd


def blocks(times, stream, freq, max_size):
    """Split a DatetimeIndex into contiguous blocks, one FDB request each."""
    times = pd.DatetimeIndex(times)
    if stream == "clmn":
        group = times.year                      # one request per calendar year
    elif freq == "h":
        group = times.normalize()               # one request per calendar day
    else:
        # Daily data: `time` is a single value, so a block may span many dates
        # and the cross product is still exact.
        group = np.arange(len(times)) // max_size

    out, start = [], 0
    for i in range(1, len(times) + 1):
        if i == len(times) or group[i] != group[start] or i - start >= max_size:
            out.append(np.arange(start, i))
            start = i
    return out


def request_for(base_request, param, stamps, stream, level=None):
    """Build the MARS request covering exactly ``stamps``."""
    request = dict(base_request)
    request["param"] = str(int(param))
    if level is not None:
        request["levelist"] = str(int(level))

    stamps = pd.DatetimeIndex(stamps)
    if stream == "clmn":
        years = sorted({t.year for t in stamps})
        if len(years) != 1:
            raise ValueError(f"a monthly block must sit inside one year, got {years}")
        request["year"] = str(years[0])
        request["month"] = "/".join(str(m) for m in sorted({t.month for t in stamps}))
    else:
        request["date"] = "/".join(sorted({t.strftime("%Y%m%d") for t in stamps}))
        request["time"] = "/".join(sorted({t.strftime("%H%M") for t in stamps}))
    return request


_ORDERING_CHECKED = set()


def _check_grid(field, n_cells, indexing_scheme, label):
    """Confirm a returned field really is the grid the dataset advertises.

    Nside and ordering are properties of the simulation that a request cannot
    ask for, so they are assumed at open time and can only be confirmed once
    data arrives. Checking here costs one metadata read per block and turns a
    silently wrong map into an error.
    """
    values = np.asarray(field.to_numpy()).ravel()
    if values.size != n_cells:
        raise ValueError(
            f"{label}: field has {values.size} values but the grid was assumed "
            f"to have {n_cells} cells. The run's Nside differs from the one "
            f"inferred from (activity, resolution) -- pass nside= explicitly."
        )
    key = (n_cells, indexing_scheme)
    if key not in _ORDERING_CHECKED:
        _ORDERING_CHECKED.add(key)
        try:
            actual = str(field.metadata("orderingConvention"))
        except Exception:  # noqa: BLE001 - not every backend exposes it
            return values
        if actual and actual != indexing_scheme:
            raise ValueError(
                f"{label}: the data is HEALPix '{actual}'-ordered but the "
                f"dataset was built as '{indexing_scheme}'. Pass "
                f"ordering={actual!r} to open_run(); plotting or lat/lon "
                f"lookups would otherwise scramble the map."
            )
    return values


def fetch_block(fetcher, request, n_times, n_cells, label,
                indexing_scheme="nested"):
    """Fetch one block and return it as a (n_times, n_cells) float32 array.

    Fields are ordered by their GRIB date/time rather than trusted in arrival
    order, and matched to the block positionally afterwards. Sorting sidesteps
    the question of which date convention a monthly mean carries (start of
    period, end of period): all that matters is that it increases with time.
    """
    blank = np.full((n_times, n_cells), np.nan, dtype=np.float32)
    try:
        fields = list(_as_fieldlist(fetcher(request)))
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        print(f"  ! {label}: FDB request failed: {exc}")
        return blank

    if len(fields) != n_times:
        print(f"  ! {label}: expected {n_times} fields, got {len(fields)} "
              f"-- block left as NaN. Request: {request}")
        return blank

    def sort_key(field):
        try:
            return (int(field.metadata("dataDate")), int(field.metadata("dataTime")))
        except Exception:                        # noqa: BLE001
            return (0, 0)

    out = np.empty((n_times, n_cells), dtype=np.float32)
    for i, field in enumerate(sorted(fields, key=sort_key)):
        out[i] = _check_grid(field, n_cells, indexing_scheme, label).astype(np.float32)
    return out


def _as_fieldlist(data):
    # earthkit-data >= 1.0 wraps the response in an object that is not itself
    # iterable; older versions return the FieldList directly.
    try:
        return data.to_fieldlist()
    except AttributeError:
        return data


def build_dataset(base_request, times, variables, stream, freq, nside,
                  levels=None, fetcher=None, time_chunk=None, coords_fn=None,
                  indexing_scheme="nested"):
    """Return the lazy Dataset for one run.

    ``variables`` maps name -> {"param", "dims", "long_name", "units"} where
    dims is ("time", "cell") or ("time", "level", "cell").
    """
    import dask
    import dask.array as da
    import xarray as xr

    fetcher = fetcher or _fdb_fetch
    times = pd.DatetimeIndex(times)
    n_cells = 12 * nside * nside
    default_chunk = {"clmn": 12}.get(stream, 24 if freq == "h" else 30)
    max_size = time_chunk or default_chunk
    index_blocks = blocks(times, stream, freq, max_size)

    def time_axis(param, level, label):
        """dask array of shape (n_times, n_cells) for one param/level."""
        pieces = []
        for idx in index_blocks:
            stamps = times[idx]
            request = request_for(base_request, param, stamps, stream, level=level)
            delayed = dask.delayed(fetch_block, pure=True)(
                fetcher, request, len(idx), n_cells,
                f"{label} {stamps[0]:%Y-%m-%d %H:%M}", indexing_scheme)
            pieces.append(da.from_delayed(delayed, shape=(len(idx), n_cells),
                                          dtype=np.float32))
        return da.concatenate(pieces, axis=0)

    data_vars = {}
    for name, spec in variables.items():
        attrs = {k: v for k, v in spec.items()
                 if k in ("long_name", "units")}
        attrs["paramId"] = int(spec["param"])
        attrs["grid_mapping"] = "healpix"
        if "level" in spec["dims"]:
            array = da.stack(
                [time_axis(spec["param"], lev, f"{name}@{lev}") for lev in levels],
                axis=1)
            data_vars[name] = (("time", "level", "cell"), array, attrs)
        else:
            data_vars[name] = (("time", "cell"), time_axis(spec["param"], None, name),
                               attrs)

    from .portfolio import crs_attrs, grid_attrs

    cell = xr.DataArray(np.arange(n_cells, dtype="int32"), dims="cell",
                        attrs=grid_attrs(nside, indexing_scheme))
    # Scalar grid-mapping variable, as CF expects alongside the index coord.
    crs = xr.DataArray(np.int8(0), attrs=crs_attrs(nside, indexing_scheme))
    coords = {"time": times, "cell": cell, "crs": crs}
    if levels is not None:
        coords["level"] = np.asarray(levels)
    if coords_fn is not None:
        coords.update(coords_fn(nside))

    return xr.Dataset(data_vars, coords=coords)


def _fdb_fetch(request):
    """Read a block by listing it and reading each field's own data handle.

    Deliberately not earthkit's ``"fdb"`` source, which goes through pyfdb's
    ``retrieve()``. Against the shared DestinE FDB on MN5 that returns an empty
    stream, while ``fdb read`` on the command line and this path both return the
    field -- same libfdb, same config, same data. Listing is also the cheaper
    route: it hands back bytes, where the earthkit source stages every request
    through a temp file on scratch first.

    Reading through ``data_handle`` rather than the element's path and offset
    keeps remote and gateway roots working, since libfdb resolves the location.
    """
    import earthkit.data

    from . import fdb as _fdb

    chunks = []
    for element in _fdb._elements(request, depth=3):
        handle = _fdb._member(element, "data_handle")
        if callable(getattr(handle, "open", None)):
            handle.open()
        try:
            chunks.append(handle.readall())
        finally:
            if callable(getattr(handle, "close", None)):
                handle.close()

    if not chunks:
        # Let the caller report it the same way as any other empty response.
        return earthkit.data.from_source("empty")
    return earthkit.data.from_source("memory", b"".join(chunks))


def _earthkit_fdb_fetch(request):
    """The earthkit ``"fdb"`` source, kept as an escape hatch for ``fetcher=``.

    stream=False is mandatory here: earthkit-data's default streaming path reads
    the pyfdb DataHandle without opening it first, which is broken against
    pyfdb 5.x.
    """
    import earthkit.data

    return earthkit.data.from_source("fdb", request, stream=False)
