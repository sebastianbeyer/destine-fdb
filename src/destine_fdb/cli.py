"""Explore a local FDB from the command line.

    destine-fdb runs      <fdb>   every run the FDB contains -- start here
    destine-fdb overview  <fdb>   what one run holds, across every levtype
    destine-fdb scan      <fdb>   one levtype in detail: params and levels

Run this first on a new FDB. It prints the time range, the archived params and
the levels, which is both a smoke test for the connection and the fastest way
to see whether a run is on the full, reduced or minimal portfolio.

    destine-fdb scan /gpfs/projects/ehpc01/dte/fdb/healpix \\
        --activity story-nudging --experiment hist --member 11 \\
        --frequency monthly --resolution high
"""

import argparse
import sys

from . import overview, runs, scan_run
from .params import SHORT_NAME


def _parser():
    parser = argparse.ArgumentParser(prog="destine-fdb", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    runs = sub.add_parser("runs", help="every run in the FDB (start here)")
    runs.add_argument("fdb", nargs="?", default=None)
    runs.add_argument("--fdb-home", default=None)

    over = sub.add_parser("overview", help="what one run holds, every levtype")
    over.add_argument("fdb", nargs="?", default=None)
    over.add_argument("--activity", default="story-nudging")
    over.add_argument("--experiment", default="hist")
    over.add_argument("--member", type=int, default=1)
    over.add_argument("--model", default="ifs-fesom")
    over.add_argument("--frequency", default="monthly",
                      choices=["monthly", "hourly", "daily"])
    over.add_argument("--resolution", default="standard", choices=["standard", "high"])
    over.add_argument("--fdb-home", default=None)
    over.add_argument("--names", action="store_true", help="list variable names too")

    scan = sub.add_parser("scan", help="list what a run contains")
    scan.add_argument("fdb", nargs="?", default=None,
                      help="FDB root directory or config file. "
                           "Omit to use FDB5_CONFIG/FDB_HOME from the environment.")
    scan.add_argument("--activity", default="story-nudging")
    scan.add_argument("--experiment", default="hist")
    scan.add_argument("--member", type=int, default=1)
    scan.add_argument("--model", default="ifs-fesom")
    scan.add_argument("--frequency", default="monthly",
                      choices=["monthly", "hourly", "daily"])
    scan.add_argument("--resolution", default="standard", choices=["standard", "high"])
    scan.add_argument("--levtype", default="sfc",
                      choices=["sfc", "pl", "hl", "sol", "o2d", "o3d"])
    scan.add_argument("--fdb-home", default=None)
    scan.add_argument("--raw", action="store_true",
                      help="print every time key rather than just the range")
    return parser


def _show(frame, columns):
    import pandas as pd
    with pd.option_context("display.max_rows", 200, "display.width", 200,
                           "display.max_colwidth", 60):
        print(frame[columns].to_string(index=False))


def main(argv=None):
    args = _parser().parse_args(argv)

    if args.command == "runs":
        try:
            frame = runs(args.fdb, fdb_home=args.fdb_home)
        except Exception as exc:                 # noqa: BLE001 - a CLI
            print(f"listing runs failed: {exc}", file=sys.stderr)
            return 2
        _show(frame, [c for c in ("activity", "experiment", "model",
                                  "realization", "stream", "expver",
                                  "covers", "first", "last") if c in frame])
        print(f"\n{len(frame)} runs")
        return 0

    if args.command == "overview":
        try:
            frame = overview(args.fdb, activity=args.activity,
                             experiment=args.experiment, member=args.member,
                             model=args.model, frequency=args.frequency,
                             resolution=args.resolution, fdb_home=args.fdb_home)
        except Exception as exc:                 # noqa: BLE001 - a CLI
            print(f"overview failed: {exc}", file=sys.stderr)
            return 2
        _show(frame, ["levtype", "freq", "variables", "timesteps", "first",
                      "last", "levels"])
        if args.names:
            print()
            for _, row in frame.iterrows():
                print(f"{row['levtype']}: {row['names']}")
        return 0

    try:
        found = scan_run(args.fdb, activity=args.activity, experiment=args.experiment,
                         member=args.member, frequency=args.frequency,
                         resolution=args.resolution, levtype=args.levtype,
                         model=args.model, fdb_home=args.fdb_home)
    except Exception as exc:                     # noqa: BLE001 - a CLI, not a library
        print(f"scan failed: {exc}", file=sys.stderr)
        return 2

    times = found["times"]
    print(f"timesteps : {len(times)}  ({'/'.join(times[0])} .. {'/'.join(times[-1])})")
    print(f"listed at : depth {found['raw_depth']}")
    if args.raw:
        for keys in times:
            print("  ", "/".join(keys))

    params = sorted(found["params"])
    print(f"params    : {len(params)}")
    for param in params:
        print(f"   {param:<8} {SHORT_NAME.get(param, '?')}")
    if found["levels"]:
        print(f"levels    : {found['levels']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
