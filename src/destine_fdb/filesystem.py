"""Scanning by reading the FDB's directory names instead of its index.

An FDB database is a directory whose *name* is the level-1 MARS key tuple::

    d1:climate-dt:story-nudging:hist:2:ifs-fesom:11:0001:clte:20170101

so one ``os.listdir`` of a root answers what the index answers by opening one
TOC per database. On MN5 that is 0.01s for every run in the FDB, against 23s
for a single run through the index, and 139s cold.

Two things make this less trivial than it looks, and both bite:

* **A config has more than one root.** The shared DestinE config is
  ``type: select`` and gives each space two roots -- a scratch tree and a
  gateway tree. Listing one of them silently under-reports: 4292 dates instead
  of 12205 for projections/ssp1-2.6. :func:`data_roots` resolves the select
  rules against the request and returns all of them.
* **A directory is not a guarantee.** Its name carries nothing below level 1, so
  it cannot say whether the levtype you want is inside, and it cannot see
  masked or duplicated entries the way the index can. The index filenames
  within a database do carry ``resolution:type:levtype``, which is how
  :func:`levtype_present` checks a database without opening anything.

So this mode trades a little rigour for a lot of speed. It is opt-in.
"""

import os
import re
from pathlib import Path

# Level-1 key order for the Climate DT schema rules, which is what the database
# directory name is built from:
#   [ class, dataset, activity, experiment, generation, model, realization,
#     expver, stream, date|year ]
L1_ORDER = ("class", "dataset", "activity", "experiment", "generation",
            "model", "realization", "expver", "stream")


def looks_like_a_root(path):
    """Does this directory hold FDB database directories?"""
    try:
        return any(entry.count(":") >= 5 for entry in os.listdir(path))
    except OSError:
        return False


def data_roots(config, request, fallback=None):
    """Every root a ``request`` could live under, per an FDB5 config dict.

    Handles ``type: select`` (match the request against each rule's ``select``
    regexes, honouring ``excludes``) and plain ``type: local``.

    Root paths in a config are absolute and refer to the machine that wrote it,
    so an FDB copied off an HPC points at a ``/gpfs`` tree that is not there any
    more. When none of the configured roots exist, ``fallback`` -- the directory
    the config was found in -- is used instead, provided it actually holds
    database directories.
    """
    roots = []

    def collect(node):
        for space in node.get("spaces") or []:
            for root in space.get("roots") or []:
                path = root.get("path")
                if path and path not in roots:
                    roots.append(path)

    if config.get("type") == "select":
        for rule in config.get("fdbs") or []:
            if not _matches(rule.get("select"), request):
                continue
            if any(_matches(x, request) for x in rule.get("excludes") or []):
                continue
            collect(rule)
    else:
        collect(config)

    present = [Path(r) for r in roots if os.path.isdir(r)]
    if present:
        return present
    if fallback is not None and looks_like_a_root(fallback):
        return [Path(fallback)]
    return [Path(r) for r in roots]


def all_roots(config):
    """Every root in a config, ignoring which rule would serve a request.

    :func:`data_roots` narrows to the rules matching one request, which is
    right when fetching. Enumerating what an FDB *contains* has no request to
    narrow by, so take the union.
    """
    roots = []

    def collect(node):
        for space in node.get("spaces") or []:
            for root in space.get("roots") or []:
                path = root.get("path")
                if path and path not in roots:
                    roots.append(path)

    collect(config)
    for rule in config.get("fdbs") or []:
        collect(rule)
    return [Path(r) for r in roots if os.path.isdir(r)]


def list_runs(roots):
    """``{(class, dataset, activity, ..., stream): {top values}}`` for every database."""
    found = {}
    for root in roots:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            parts = name.split(":")
            if len(parts) != len(L1_ORDER) + 1:
                continue
            found.setdefault(tuple(parts[:-1]), set()).add(parts[-1])
    return found


def _matches(selector, request):
    """``class=d1,dataset=^climate-dt$,expver=(0001|o[0-9a-z]{3})`` against a request.

    A key the request does not set cannot disqualify it -- the rule is about
    where data may live, and an unspecified key means "any".
    """
    if not selector:
        return False
    for clause in str(selector).split(","):
        if "=" not in clause:
            continue
        key, _, pattern = clause.partition("=")
        value = request.get(key.strip())
        if value is None:
            continue
        if not re.fullmatch(pattern.strip(), str(value), re.IGNORECASE):
            return False
    return True


def databases(roots, request, top_key):
    """``{top_value: [database directory, ...]}`` for the run in ``request``.

    Matching is case-insensitive because FDB folds case on keys like model and
    experiment, and the shared FDB has databases on disk under both
    ``IFS-FESOM`` and ``ifs-fesom`` for the same run.
    """
    wanted = {k: str(v).lower() for k, v in request.items() if k in L1_ORDER}
    found = {}
    for root in roots:
        try:
            names = os.listdir(root)
        except OSError:
            continue                    # a root that is not mounted here
        for name in names:
            parts = name.split(":")
            if len(parts) != len(L1_ORDER) + 1:
                continue
            keys = dict(zip(L1_ORDER, parts))
            if any(keys[k].lower() != v for k, v in wanted.items()):
                continue
            found.setdefault(parts[-1], []).append(root / name)
    return found


def levtype_present(database, resolution, levtype, type_="fc"):
    """Does this database hold an index for resolution/levtype?

    Index files are named ``<index keys>.<timestamp>.<host>.<id>.index``, and
    for the Climate DT rules those keys are ``resolution:type:levtype`` (clte)
    or ``month:resolution:type:levtype`` (clmn). Reading the names costs one
    listdir and no TOC parsing.
    """
    try:
        names = os.listdir(database)
    except OSError:
        return False
    for name in names:
        if not name.endswith(".index"):
            continue
        keys = name.split(".")[0].split(":")
        if resolution in keys and levtype in keys and type_ in keys:
            return True
    return False


def index_keys(database):
    """All ``resolution:type:levtype`` (or ``month:...``) tuples in a database."""
    out = set()
    try:
        names = os.listdir(database)
    except OSError:
        return out
    for name in names:
        if name.endswith(".index"):
            out.add(tuple(name.split(".")[0].split(":")))
    return out
