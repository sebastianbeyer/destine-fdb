# destine-fdb

Lazy `xarray` access to DestinE Climate DT data sitting in a **local FDB** —
log into an HPC, open a run, analyse it in Python. No polytope, no data bridge,
no token, no download step.

```python
from destine_fdb import open_run

ds = open_run("/gpfs/projects/ehpc01/dte/fdb/healpix",
              activity="story-nudging", experiment="hist", member=11,
              frequency="monthly", resolution="high")

ds.avg_2t.sel(time="2017-07").mean("time").compute()
```

Opening is instant: the dataset knows its shape, variables and time axis, but
holds no data. Each `.compute()` / `.values` / `.plot()` turns into the FDB
reads it needs and no more.

## Quickstart

On the HPC, once:

```bash
# login nodes have no internet, so push the code rather than cloning it
rsync -a --exclude='.pixi' --exclude='.git' ./ mn5:destine-fdb/
ssh mn5 'cd destine-fdb && pixi install -e explore'
```

(If the login node cannot reach conda-forge, run a CONNECT proxy on your laptop,
open it with `ssh -R 18081:localhost:18081 mn5`, and set
`https_proxy=http://localhost:18081` before `pixi install`.)

Then, per session — launch on a compute node, connect from the laptop:

```bash
ssh mn5 'export FDB5_DIR=/path/to/climateDT/build_intel; \
         cd destine-fdb && sbatch tools/jupyter.slurm'

./tools/connect.sh --open        # finds the job, opens the tunnel, opens the URL
```

That is the whole loop. `scancel <jobid>` when you are done; Ctrl-C in
`connect.sh` only closes the tunnel. Details, and the VSCode variants, are in
[Notebooks](#notebooks-vscode-against-an-hpc) below.

For local use against a copied FDB, `pixi install` (or `pip install -e .`) and
skip all of the above.

## Why?

The data bridge only carries published runs. Anything still in flight — a
rerun, a new member, an experiment that has not been promoted — lives only in
the FDB on the machine that produced it. This package makes that FDB directly
readable as an xarray Dataset.


## Install

```bash
pixi install          # or: pip install -e .
```

Then, per session, point `pyfdb` at the FDB5 library from your model build:

```bash
export FDB5_DIR=/path/to/climateDT/build_intel
export LD_LIBRARY_PATH=$FDB5_DIR/lib:$LD_LIBRARY_PATH
```

The FDB *config* is handled in Python — pass `fdb=` to `open_run`.

## Pointing at an FDB

Hand over the **root directory**, not the config file:

```python
open_run("/gpfs/projects/ehpc01/dte/fdb/healpix", ...)
```

The root form also sets `FDB_HOME`, which the shared DestinE config needs: it
is a `type: select` config whose entries point their schema at
`~fdb/etc/fdb/schema`, and eckit expands that `~fdb` prefix from `$FDB_HOME`.
Without it every request fails to find a schema, with an error that never
mentions `FDB_HOME`. Passing a config file directly also works; then set
`fdb_home=` yourself if the config uses `~fdb` paths.

## Requirements

`pyfdb` must find the `libfdb5.so` that matches your FDB. The listing API
differs between pyfdb versions -- 5.21 takes `level=` and returns elements with
`.combined_key()`, older builds take `depth=`/`keys=` and return dicts -- and
this package handles both, because the version you get is pinned by the model
build on your machine, not by PyPI.

## Notebooks (VSCode against an HPC)

The `explore` environment adds jupyterlab, cartopy, healpy, easygems and xdggs
on top of the reader:

```bash
pixi install -e explore
```

There are two ways to get a notebook running against it, and one trap.

**The trap:** do not point VSCode at `.pixi/envs/explore/bin/python`. VSCode
discovers that interpreter and execs `ipykernel_launcher` itself, which skips
pixi activation entirely — so the kernel has no `FDB5_DIR` and no
`LD_LIBRARY_PATH`, `findlibs` cannot locate `libfdb5.so`, and every `open_run`
dies at import. Setting them inside the notebook does not rescue it either:
`LD_LIBRARY_PATH` is read by the dynamic loader when the process starts.

**Kernel via `pixi run`.** Register a kernelspec that does the activation
itself, from a shell where `FDB5_DIR` is already exported:

```bash
pixi run -e explore kernel
pixi run -e explore kernel --fdb5-dir /path/to/climateDT/build_intel
pixi run -e explore kernel --module intel     # if libfdb5's deps need the toolchain
```

This writes `~/.local/share/jupyter/kernels/destine-fdb/{launch.sh,kernel.json}`.
The launcher does the module loads, exports `FDB5_DIR` and prepends to
`LD_LIBRARY_PATH` (rather than replacing it — libfdb5 needs its eckit/metkit
siblings), then `exec`s `pixi run -e explore python -m ipykernel_launcher`.
Pick **"destine-fdb (pixi)"** as the kernel in VSCode. `--dry-run` prints both
files without writing them; `--no-fdb-env` gives a plain kernel for
zarr/netCDF-only work.

**Or run the server on a compute node.** Prefer this for anything heavy:
login nodes on MN5 kill processes over the CPU/memory limits, and a dask read
of an H512 run will trip that. A server started this way inherits the activated
environment by construction, so no kernelspec is involved.

`tools/jupyter.slurm` is a batch job that does it:

```bash
export FDB5_DIR=/path/to/climateDT/build_intel   # inherited by the job
sbatch tools/jupyter.slurm                       # submit from the repo root
tail -f jupyter-<jobid>.log
```

The log prints the node, a free port, and the exact command to paste:

```
 JupyterLab on gs01r2b23:49286   (job 1234567, 16 cores)

     ssh -N -L 49286:gs01r2b23:49286 mn5
```

Same port on both ends, so the `http://127.0.0.1:49286/lab?token=...` URL that
Jupyter prints just below works verbatim — in a browser, or pasted into VSCode
under *Select Kernel → Existing Jupyter Server* (it wants the whole URL,
token included). The login node can reach the compute node directly, so one
`-L` hop is enough; no nested tunnel.

The forward is a laptop-side thing, so it has to be (re)opened per session, and
both halves change with every job. `tools/connect.sh` does the lookup for you —
it runs **on the laptop**, asks `squeue` for your running job, reads node, port
and token out of its log, opens the tunnel and prints the URL:

```bash
./tools/connect.sh                     # tunnel + URL, Ctrl-C to close
./tools/connect.sh --open              # and open it in a browser
./tools/connect.sh --local-port 8899   # if the remote port is taken here
```

`MN5_HOST`, `REMOTE_DIR` and `JOB_NAME` override the ssh alias, the remote
checkout and the job name. If you already have a session open on the login
node, `~C` followed by `-L <port>:<node>:<port>` adds the forward to it instead
(needs `EnableEscapeCommandline yes`; OpenSSH disables that escape by default
since 8.9). In a VSCode Remote-SSH window, the Ports panel → *Forward a Port* →
`<node>:<port>` is the same thing again — VSCode's auto-detection will not find
it on its own, because it only watches the login node's own ports.

Edit the `--account` / `--qos` headers for your project (`sacctmgr show assoc
user=$USER` lists what you may use; `gp_debug` caps at 2 hours). Modules for
libfdb5's dependencies go in via
`sbatch --export=ALL,JUPYTER_MODULES="intel" tools/jupyter.slurm`.

MN5 `gpp` nodes are shared (`OverSubscribe=OK`), so the 16 cores in the header
cost 16 cores, not the 112-core node — no reason to grab the whole thing. What
`--cpus-per-task` really controls is memory: MN5 hands out 2000 MB per
allocated CPU, so 16 lands at ~32 GB. Raise it (or add `--mem`) before a large
H512 read, not because the notebook needs the threads.

For a quick look, `salloc` plus `pixi run -e explore lab` does the same thing
by hand.

**Getting VSCode onto an airgapped login node.** Remote-SSH normally downloads
`vscode-server` on the remote, which has no internet. Set
`"remote.SSH.localServerDownload": "always"` locally — your laptop fetches the
tarball and pipes it over the SSH connection.

## Exploring an FDB you don't know

Three levels, coarse to fine. The first two read database directory names only,
so they are near-instant.

```python
destine_fdb.runs(FDB)          # every run in the FDB
destine_fdb.overview(FDB, ...) # one run, across every levtype
destine_fdb.scan_run(FDB, ...) # one levtype: params and levels
```

`runs` is where to start on an unfamiliar FDB. On the shared DestinE one it
returns **828 runs over ~190,000 databases in under a second**, including
things you would never guess at:

```
   experiment     model realization stream   covers    first     last
    Tplus2.0K IFS-FESOM           1   clmn  3 years     2021     2026
    Tplus2.0K IFS-FESOM           1   clte 368 days 20210501 20260430
```

A raw database count is not a unit anyone thinks in, so `covers` spells it out.
What one database spans is set by the schema, which keys it on `date` for the
hourly and daily streams and on `year` for the monthly one — so **one database
is one day for `clte` and one year for `clmn`**, never a month. The integer is
still there as `databases` if you want to compute with it.

Some other things it turns up: `HighResMIP`, `ScenarioMIP`, `abrupt4xco2`
runs with 18,000 databases each, and a dozen `expver`s beyond `0001`. It also
makes the case duplicates visible — `Tplus2.0K` alongside `tplus2.0k`,
`HighResMIP` alongside `highresmip`.

`overview` answers "what is in this run", which `open_run` cannot: **`open_run`
opens one levtype at a time**, so with no `variables=` you get every variable of
one family — `sfc`, 34 of them — and never see the ocean or the pressure levels.

```
levtype freq  variables  timesteps         first          last  levels
    sfc    h         34        673 20260501/0000 20260529/0000       0
     pl    h          9        673 20260501/0000 20260529/0000      19
     hl    h          2        673 20260501/0000 20260529/0000       1
    sol    h          3        673 20260501/0000 20260529/0000       5
    o2d    D         12         28 20260501/0000 20260528/0000       0
    o3d    D          5         28 20260501/0000 20260528/0000      70
```

All three exist as commands too: `destine-fdb runs`, `destine-fdb overview`
(add `--names` for the variable lists), `destine-fdb scan`.

## Look before you open

```bash
destine-fdb scan /gpfs/projects/ehpc01/dte/fdb/healpix \
    --activity story-nudging --experiment hist --member 11 \
    --frequency monthly --resolution high
```

```
timesteps : 8761  (20170101/0000 .. 20180101/0000)
listed at : depth 3
params    : 36
   167      2t
   ...
```

This is the smoke test for a new FDB, and the fastest way to see how far a
running experiment has got.

If the run is not found, the error lists the activity/experiment/model/
realization combinations the FDB does hold — a wrong `model=` is as easy to
get wrong as a wrong `member=`. If the run exists but has nothing for the
requested levtype, the error says so and lists the resolution/levtype pairs
that are there.

## Ocean, and not having to know the levtype

Ocean works the same as atmosphere — `o2d` for the 2-D ocean and sea ice,
`o3d` for the 3-D fields, both daily:

```python
ds = open_run(FDB, frequency="daily", variables=["avg_tos"])       # -> o2d
ds = open_run(FDB, frequency="daily", variables=["avg_thetao"])    # -> o3d
```

Note there is no `levtype=` in either. **It is inferred from the variable
names**, because having to know that `avg_thetao` lives at `o3d` is exactly the
kind of thing a catalogue should answer for you. Only three names in the whole
Gen2 portfolio are ambiguous — `sd`/`avg_sd` (sfc and sol) and `u`/`v` (pl and
hl) — and those raise, naming the choices, rather than guessing. Naming
variables from two different levtypes at once also raises: one dataset holds one
levtype.

The ocean fields carry a land mask, so roughly 71% of cells are finite at the
surface and fewer with depth. On the storyline FDB, `avg_tos` runs from 271.13 K
— the freezing point of seawater — to 306 K, and `avg_thetao` at level 40 covers
65% of cells against 71% at level 1, which is the bathymetry.

Levels are detected from the FDB rather than assumed: the portfolio pads `o3d`
to 75 levels, and a scan of the IFS-FESOM storyline run reports the 70 it
actually has.

## Portfolios

The catalogue is generated from <https://variables.sbeyer.net> and carries the
three portfolio tiers as declared facts:

```python
open_run(FDB, frequency="monthly", tier="minimal")   # 35 variables
open_run(FDB, frequency="monthly", tier="reduced")   # 35
open_run(FDB, frequency="monthly")                   # full: 65
```

**Frequency is per variable, not per levtype.** `lsm` is archived daily while
everything else at `sfc` is hourly, so an hourly dataset excludes it rather than
carrying a variable with no hourly data behind it. Asking for one at a
frequency it is not archived at fails up front and says where it does live:

```
KeyError: 'avg_tos' exists but is not in this portfolio. It is a o2d field,
archived at daily/monthly, so check the frequency= and tier= you asked for.
```

On top of the declared tier, the scan still **intersects the catalogue with what
it found in the FDB**, so a run that is partway through archiving yields only
what is really there; the rest are listed in `ds.attrs["portfolio_missing"]`.
Pass `portfolio=` to supply your own catalogue.

Skip the scan with `scan=False` plus explicit `start=`/`end=` when you already
know the range and want the fastest possible open.

## Skipping the scan

A scan has two halves: enumerating the dates (slow, grows with the run) and one
index probe for params and levels (~0.1s). **Passing both `start=` and `end=`
skips the slow half only** — the probe still runs, so the variable list is still
narrowed to what is archived and the levels are still the real ones:

```python
ds = open_run(FDB, experiment="hist", frequency="hourly",
              start="2017-01-01", end="2017-12-31 23:00")
```

On the storyline FDB that is 0.21s against 0.81s for a full scan, and it still
reports the real **70** ocean levels where the portfolio's fallback pads to 75.

`scan=False` goes further and reads nothing at all, which is what costs you the
narrowing and the levels. Use it only when you want to assert that the index is
never touched.

A range also gets **trimmed to what the run actually holds**, because an
oversized one is not merely empty at the edges — it builds a dask chunk per
timestep. Asking for six years of 3-D ocean where 29 days exist is 870,000
chunks and 18 seconds of graph construction, almost all of it resolving to NaN.
Trimming says so on stderr and takes it back to 0.22s. `scan=False` keeps the
range exactly as given.

## How fast is the scan?

Measured on MN5 against the shared DestinE FDB (9720 databases, `standard`
resolution, `sfc`):

| run | databases in the run | timesteps | scan |
|---|---|---|---|
| story-nudging/hist r1, hourly | 123 | 2 953 | 7.2 s |
| story-nudging/hist r11, hourly | 366 | 8 761 | 10.6 s |
| story-nudging/cont r1, hourly | 333 | 9 481 | 20.1 s |
| story-nudging/hist r1, monthly | 29 | 24 | 0.8 s |

**Scan time tracks the size of the run you ask for, not the size of the FDB.**
The level-1 and level-2 listings are keyed on the database prefix, so FDB goes
straight to the matching databases and never walks the rest. A 2.7 TB private
FDB with 87 databases and a shared FDB with 9720 both scan a comparable run in
comparable time.

What *does* cost is databases-per-run, and for hourly data one database is one
day, so a decade of hourly output is thousands of them. Monthly is cheap
throughout because one database is a whole year. If a scan is too slow for an
interactive loop, pass explicit `start=`/`end=` and it is skipped entirely.

Higher resolution costs nothing extra: `high` and `standard` scan the same,
because the index is the same size either way — only the fields behind it are
bigger.

### Scan modes

`scan_mode` defaults to **`"auto"`**: try the filesystem, fall back to the index
if it cannot be read. The filesystem path is 8–70x faster and agreed with the
index on every run tested, but it needs the config's roots mounted on this
machine, which a remote or non-`toc` FDB will not have. A run that is genuinely
absent raises rather than falling through, so the fallback cannot mask a wrong
key.

Force either with `scan_mode="filesystem"` or `scan_mode="index"`. The index is
the authoritative one: it sees masked and duplicated entries that directory
names cannot show.

### What `scan_mode="filesystem"` does

An FDB database is a directory whose *name* is the level-1 MARS key tuple:

```
d1:climate-dt:story-nudging:hist:2:ifs-fesom:11:0001:clte:20170101
```

So one `os.listdir` answers what the index answers by opening one TOC per
database. Measured on MN5, against the index mode on the same runs:

| run | index | filesystem | |
|---|---|---|---|
| story-nudging/hist r11, hourly (8 761 steps) | 4.8 s | 0.62 s | **8×** |
| projections/ssp1-2.6, hourly (292 897 steps) | 303 s | 4.35 s | **70×** |
| story-nudging/hist, monthly | 3.0 s | 0.28 s | 11× |
| private FDB, hourly (673 steps) | 0.54 s | 0.06 s | 9× |

The time axis was **identical** in all four. Params, levels and the hours in a
day still come from one index probe either way — directory names cannot answer
those.

It is opt-in because it trades rigour for speed: a directory name carries
nothing below level 1, so it trusts that a directory means data, and it cannot
see masked or duplicated entries the way the index can.

The thing it must get right — and the reason not to hand-roll this with `ls` —
is that **a config has more than one root**. The shared DestinE config is
`type: select` and gives each space a scratch tree *and* a gateway tree.
Listing only the first reports 4292 dates where the truth is 12205. The mode
resolves the config's `select` rules (and `excludes`) against the request and
reads every root that matches.

## Plotting: the grid describes itself

Data comes back on the native HEALPix mesh, as a 1-D `cell` dimension. That
dimension carries the standard grid metadata:

```python
ds.cell.attrs
# {'grid_name': 'healpix', 'level': 9, 'indexing_scheme': 'nested',
#  'nside': 512, 'nest': True}
```

Those are the names [xdggs](https://github.com/xarray-contrib/xdggs) reads, and
a scalar `crs` variable carries the same thing in CF grid-mapping form, so both
of xdggs' conventions decode (verified against xdggs 0.6):

```python
import xdggs
ds = xdggs.decode(ds, name="cell")                    # xdggs convention
ds = xdggs.decode(ds, convention="cf", name="cell")   # CF grid mapping
ds.dggs.grid_info      # HealpixInfo(level=9, indexing_scheme='nested')
ds.dggs.cell_centers()
```

`name="cell"` is needed because xdggs defaults to a coordinate called
`cell_ids`, while this package keeps the dimension named `cell` — the name
easygems and the nextGEMS/DestinE HEALPix tooling use. `ds.rename(cell="cell_ids")`
makes the argument unnecessary if you prefer xdggs' default.

One sharp edge worth knowing if you write these attributes yourself: xdggs feeds
the whole attrs dict to `HealpixInfo(**attrs)`, which rejects **any** key it does
not recognise. A helpful extra like `standard_name` or `nside` on the coordinate
turns `decode` into a `TypeError`. So the coordinate carries exactly the grid
parameters, and the healpy-style aliases live on `ds.attrs`
(`healpix_nside`, `healpix_nest`) where nothing parses them.

For [easygems](https://easy.gems.dkrz.de/Processing/healpix/):

```python
import easygems.healpix as egh
ds = open_run(..., add_latlon=True)          # what egh.attach_coords does
ax.set_global()                              # set the extent BEFORE sampling
egh.healpix_show(ds["2t"].isel(time=0), ax=ax)
```

`healpix_show` resamples the HEALPix cells onto the *screen raster* of a cartopy
axes (nearest-neighbour by default) and `imshow`s that — no regrid to a lat/lon
grid, which is why it is fast and needs no interpolation weights. Because it
samples the axes' current extent, set the extent before calling it or you get a
blank map. Note its own `nest=True` default: it assumes nested unless told.

The `lat`/`lon` that `add_latlon=True` attaches agree with xdggs'
`cell_centers()` to 4e-06 degrees, which is float32 rounding.

**This package deliberately does not register an accessor of its own.** Accessor
namespaces are global to the xarray process and first-registration-wins, so a
data-access library claiming `.hp` would collide with whatever the user already
has. Emitting the metadata that the existing HEALPix libraries already read
composes instead of competing, and costs no dependency. A plain
`da.isel(time=0).plot()` gives you a line plot against cell index, because that
is honestly what a 1-D array is — the map needs one of the tools above, or a
regrid to lat/lon (which this package leaves to `earthkit-regrid`, since pulling
its interpolation matrices is the one thing that would need network access).

`ordering` defaults to `"nested"`, which is what DestinE archives — confirmed
against the GRIB `orderingConvention`. It is not merely assumed: the first field
to arrive is checked against it, so a mismatch is an error naming the fix rather
than a silently scrambled map.

## Small, copied and monthly-only FDBs

A single-experiment FDB copied off an HPC works, including on a laptop:

```python
ds = open_run("~/climateDT/fdb_example_for_analysis/a35z/fdb",
              scan_mode="filesystem",
              activity="baseline", experiment="hist", model="IFS-FESOM",
              frequency="monthly", levtype="sfc", resolution="standard",
              expver="a35z")          # any MARS key can be overridden
```

Three things that come up with these and not with the shared FDB:

* **A non-default `expver`.** Requests default to `expver="0001"`; anything else
  goes through as a keyword, like `expver="a35z"` above. The same works for any
  MARS key.
* **A relocated FDB.** Root paths in a config are absolute and name the machine
  that wrote it, so a copied FDB points at a `/gpfs` tree that is not there. When
  none of the configured roots exist, the directory you passed as `fdb=` is used
  instead, provided it holds database directories.
* **No `pyfdb`.** `scan_mode="filesystem"` derives the time axis from directory
  names alone, so it can describe an FDB on a machine that cannot open one. It
  says on stderr that the variable list is not narrowed, and reading data still
  needs `pyfdb` and `libfdb5`.

Monthly-only FDBs need nothing special: `clmn` keeps its months in the index
*filenames* (`month:resolution:type:levtype`), so filesystem mode reads them
without opening anything. Hourly data keeps its hours inside the index, so
there `scan_mode="filesystem"` still probes it once.

## How fast is reading?

Measured on MN5, H512 (12.6 MB per field), reading 96 hourly `2t` fields
(1.2 GB) out of a local FDB.

**Request size** — how many timesteps `time_chunk` puts in one FDB request:

| `time_chunk` | requests | throughput | per field |
|---|---|---|---|
| 1 | 96 | 104 MB/s | 122 ms |
| 4 | 24 | 150 MB/s | 84 ms |
| 8 | 12 | 156 MB/s | 81 ms |
| 24 (default) | 4 | 161 MB/s | 78 ms |
| 96 | 1 | 161 MB/s | 78 ms |

Batching is worth about 55%, and it is all won by `time_chunk=8` — beyond that
the curve is flat. Fixed cost per request is ~44 ms, which is real but nothing
like an HTTP round trip, so there is no reason to build huge requests. The
default of one calendar day is already at the plateau.

**Parallelism is the bigger win.** FDB reads release the GIL and are safe to
run concurrently, so dask threads work:

| workers | `time_chunk=8` | `time_chunk=24` |
|---|---|---|
| 1 | 156 MB/s | 162 MB/s |
| 2 | 275 MB/s | 303 MB/s |
| 4 | 378 MB/s | **458 MB/s** |
| 8 | 302 MB/s | — |

```python
import dask
with dask.config.set(scheduler="threads", num_workers=4):
    result = ds["2t"].sel(time="2017-07").mean("cell").compute()
```

Four workers is the sweet spot at ~2.8× — 27 ms per field. More than that got
*slower* in testing, so do not leave dask on its default of one thread per core
on a big login node.

## What the laziness is made of

One dask chunk is exactly one FDB request.

A MARS request is a cross product of its keys, so `date=[d1,d2] time=[00,12]`
asks for four fields. Chunks are therefore never allowed to span a calendar day
(hourly) or a calendar year (monthly), which makes that cross product precisely
the set of timesteps in the chunk — nothing is over-fetched, and the returned
field count doubles as a correctness check. Fields are then ordered by their
GRIB `dataDate`/`dataTime` rather than trusted in arrival order, which sidesteps
having to know whether a monthly mean is dated to the start or the end of its
period.

There is **no zarr dependency**. The ECMWF notebook this borrows from gets its
laziness by faking a zarr v2 store so xarray's zarr reader does the work, which
pins it to `zarr<3`. Doing it with `dask.delayed` instead is less code and
leaves your environment's zarr version alone.

## Arguments

| | |
|---|---|
| `fdb` | FDB root dir or config file. Omit to use the ambient `FDB5_CONFIG`/`FDB_HOME`. |
| `activity`, `experiment` | MARS keys. `"plus2K"` is accepted for `tplus2.0k`. |
| `member` | Ensemble member (`realization`). Default 1. |
| `frequency` | `monthly` → `clmn`; `hourly`/`daily` → `clte`. |
| `resolution` | `standard` / `high`. The FDB's key, not a target grid. |
| `levtype` | `sfc`, `pl`, `hl`, `sol`, `o2d`, `o3d`. Inferred from `variables` if omitted. |
| `variables`, `levels` | Narrow the selection. |
| `start`, `end` | Restrict the time axis; both given skips the scan. |
| `nside` | Override the inferred HEALPix Nside. |
| `add_latlon` | Attach per-cell `lat`/`lon` (needs healpy). |
| `time_chunk` | Timesteps per request. |
| `**overrides` | Extra MARS keys, e.g. `expver="0002"`. |

`Nside` is a property of the simulation and cannot be read back from a request,
so it is inferred from `(activity, resolution)` — story-nudging tops out at
H512, free and projection runs at H1024. If a field comes back the wrong size
you get an error naming `nside=` rather than a silent reshape.

## Tests

```bash
pixi run test
```

Every FDB-touching seam is injectable, so the suite runs anywhere — no
`libfdb5`, no HPC, no network.

## Status

Verified end to end on MN5 against two real FDBs — a 2.7 TB private one and the
9720-database shared DestinE FDB.

Values are **bitwise identical** to a raw `earthkit.data.from_source("fdb", ...)`
request after the deliberate float32 cast, checked on a single field, on hour 7
and hour 23 of a 24-field batched request, across a chunk boundary into the next
day, and on a pressure level. (Raw earthkit returns float64; this package stores
float32, which is a `1.5e-05` difference on a ~300 K field and half the memory.)

The scan follows the Climate DT schema:

```
clte:  [ ..., stream=clte, date ] [ resolution, type, levtype ] [ time, levelist?, param ]
clmn:  [ ..., stream=clmn, year ] [ month, resolution, type, levtype ] [ levelist?, param ]
```

Two things about that are worth knowing, because both produced real bugs:
`time` is a **level-3** key while `date` is level 1, and a level-1 listing
**ignores** request keys from deeper levels — so `resolution` and `levtype` do
not prune it, and a database can appear at level 1 while holding nothing for the
levtype you asked for. The time axis therefore comes from level 2.

## Credits

The variable catalogue is generated from <https://variables.sbeyer.net>. The
lazy-browse idea — synthesise the dataset up front, turn coordinates into data
requests only when values are read — comes from the `polytope_zarr.py` explorer
notebook in ECMWF's
[polytope-examples](https://github.com/destination-earth-digital-twins/polytope-examples).
