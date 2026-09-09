"""The DestinE Climate DT Generation 2 data portfolio.

Generated from the catalogue at https://variables.sbeyer.net, which carries two
things the ECMWF example catalogue this package used to vendor did not:

* **Portfolio tiers.** Runs are archived on a full, reduced or minimal
  portfolio, and which variables that leaves is a declared fact here rather
  than something to infer from what a scan happens to find.
* **Per-variable frequency.** The frequency is not a property of the levtype:
  ``lsm`` is archived daily while everything else at ``sfc`` is hourly, so a
  levtype-wide frequency would put a static field on an hourly axis and fill it
  with NaN.

Units are the one field the catalogue does not carry. They are per-parameter
facts of the GRIB definition and are tabulated here rather than looked up, so
that describing a dataset needs no eccodes call.
"""

# name -> one entry per levtype it is archived at. A few names appear
# twice: u/v at both pl and hl, sd at both sfc and sol.
VARIABLES = {
    '10si': [
        {"name": '10 metre wind speed',
         "param": 207, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    '10u': [
        {"name": '10 metre U wind component',
         "param": 165, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    '10v': [
        {"name": '10 metre V wind component',
         "param": 166, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    '2d': [
        {"name": '2 metre dewpoint temperature',
         "param": 168, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    '2t': [
        {"name": '2 metre temperature',
         "param": 167, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    'avg_10u': [
        {"name": 'Time-mean 10 metre U wind component',
         "param": 235165, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_10v': [
        {"name": 'Time-mean 10 metre V wind component',
         "param": 235166, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_10ws': [
        {"name": 'Time-mean 10 metre wind speed',
         "param": 228005, "levtype": 'sfc',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_2d': [
        {"name": 'Time-mean 2 metre dewpoint temperature',
         "param": 235168, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_2t': [
        {"name": 'Time-mean 2 metre temperature',
         "param": 228004, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_clwc': [
        {"name": 'Time-mean specific cloud liquid water content',
         "param": 235246, "levtype": 'pl',
         "units": 'kg kg**-1',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_hc300m': [
        {"name": 'Time-mean vertically-integrated heat content in the upper 300 m',
         "param": 263121, "levtype": 'o2d',
         "units": 'J m**-2',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_hc700m': [
        {"name": 'Time-mean vertically-integrated heat content in the upper 700 m',
         "param": 263122, "levtype": 'o2d',
         "units": 'J m**-2',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_hcbtm': [
        {"name": 'Time-mean total column heat content',
         "param": 263123, "levtype": 'o2d',
         "units": 'J m**-2',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_ie': [
        {"name": 'Time-mean moisture flux',
         "param": 235043, "levtype": 'sfc',
         "units": 'kg m**-2 s**-1',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('hourly', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_iews': [
        {"name": 'Time-mean eastward turbulent surface stress',
         "param": 235041, "levtype": 'sfc',
         "units": 'N m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_inss': [
        {"name": 'Time-mean northward turbulent surface stress',
         "param": 235042, "levtype": 'sfc',
         "units": 'N m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_ishf': [
        {"name": 'Time-mean surface sensible heat flux',
         "param": 235033, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_msl': [
        {"name": 'Time-mean mean sea level pressure',
         "param": 235151, "levtype": 'sfc',
         "units": 'Pa',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_pv': [
        {"name": 'Time-mean potential vorticity',
         "param": 235100, "levtype": 'pl',
         "units": 'K m**2 kg**-1 s**-1',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_q': [
        {"name": 'Time-mean specific humidity',
         "param": 235133, "levtype": 'pl',
         "units": 'kg kg**-1',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_r': [
        {"name": 'Time-mean relative humidity',
         "param": 235157, "levtype": 'pl',
         "units": '%',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_sd': [
        {"name": 'Time-mean snow depth water equivalent',
         "param": 235078, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
        {"name": 'Time-mean snow depth water equivalent',
         "param": 235078, "levtype": 'sol',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_sdlwrf': [
        {"name": 'Time-mean surface downward long-wave radiation flux',
         "param": 235036, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_sdswrf': [
        {"name": 'Time-mean surface downward short-wave radiation flux',
         "param": 235035, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('hourly', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_siconc': [
        {"name": 'Time-mean sea ice area fraction',
         "param": 263001, "levtype": 'o2d',
         "units": 'Fraction',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_sithick': [
        {"name": 'Time-mean sea ice thickness',
         "param": 263000, "levtype": 'o2d',
         "units": 'm',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_siue': [
        {"name": 'Time-mean eastward sea ice velocity',
         "param": 263003, "levtype": 'o2d',
         "units": 'm s**-1',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily',)}},
    ],
    'avg_sivn': [
        {"name": 'Time-mean northward sea ice velocity',
         "param": 263004, "levtype": 'o2d',
         "units": 'm s**-1',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily',)}},
    ],
    'avg_sivol': [
        {"name": 'Time-mean sea ice volume per unit area',
         "param": 263008, "levtype": 'o2d',
         "units": 'm**3 m**-2',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_skt': [
        {"name": 'Time-mean skin temperature',
         "param": 235079, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_slhtf': [
        {"name": 'Time-mean surface latent heat flux',
         "param": 235034, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_snlwrf': [
        {"name": 'Time-mean surface net long-wave radiation flux',
         "param": 235038, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_snlwrfcs': [
        {"name": 'Time-mean surface net long-wave radiation flux, clear sky',
         "param": 235052, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_snswrf': [
        {"name": 'Time-mean surface net short-wave radiation flux',
         "param": 235037, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_snswrfcs': [
        {"name": 'Time-mean surface net short-wave radiation flux, clear sky',
         "param": 235051, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_snvol': [
        {"name": 'Time-mean snow volume over sea ice per unit area',
         "param": 263009, "levtype": 'o2d',
         "units": 'm**3 m**-2',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_so': [
        {"name": 'Time-mean sea water practical salinity',
         "param": 263500, "levtype": 'o3d',
         "units": 'g kg**-1',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_sos': [
        {"name": 'Time-mean sea surface practical salinity',
         "param": 263100, "levtype": 'o2d',
         "units": 'g kg**-1',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_sot': [
        {"name": 'Time-mean soil temperature',
         "param": 235094, "levtype": 'sol',
         "units": 'K',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_sp': [
        {"name": 'Time-mean surface pressure',
         "param": 235134, "levtype": 'sfc',
         "units": 'Pa',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_ssurfror': [
        {"name": 'Time-mean sub-surface runoff rate',
         "param": 235021, "levtype": 'sfc',
         "units": 'kg m**-2 s**-1',
         "freq": {"full": ('hourly', 'monthly')}},
    ],
    'avg_surfror': [
        {"name": 'Time-mean surface runoff rate',
         "param": 235020, "levtype": 'sfc',
         "units": 'kg m**-2 s**-1',
         "freq": {"full": ('hourly', 'monthly')}},
    ],
    'avg_t': [
        {"name": 'Time-mean temperature',
         "param": 235130, "levtype": 'pl',
         "units": 'K',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tcc': [
        {"name": 'Time-mean total cloud cover',
         "param": 235288, "levtype": 'sfc',
         "units": '%',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tciw': [
        {"name": 'Time-mean total column cloud ice water',
         "param": 235088, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_tclw': [
        {"name": 'Time-mean total column liquid water',
         "param": 235087, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_tcw': [
        {"name": 'Time-mean total column water',
         "param": 235136, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_tcwv': [
        {"name": 'Time-mean total column vertically-integrated water vapour',
         "param": 235137, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_tdswrf': [
        {"name": 'Time mean top downward short-wave radiation flux',
         "param": 235053, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_thetao': [
        {"name": 'Time-mean sea water potential temperature',
         "param": 263501, "levtype": 'o3d',
         "units": 'K',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tnlwrf': [
        {"name": 'Time-mean top net long-wave radiation flux',
         "param": 235040, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('hourly', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_tnlwrfcs': [
        {"name": 'Time-mean top net long-wave radiation flux, clear sky',
         "param": 235050, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tnswrf': [
        {"name": 'Time-mean top net short-wave radiation flux',
         "param": 235039, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tnswrfcs': [
        {"name": 'Time-mean top net short-wave radiation flux, clear sky',
         "param": 235049, "levtype": 'sfc',
         "units": 'W m**-2',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_tos': [
        {"name": 'Time-mean sea surface temperature',
         "param": 263101, "levtype": 'o2d',
         "units": 'K',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_tprate': [
        {"name": 'Time-mean total precipitation rate',
         "param": 235055, "levtype": 'sfc',
         "units": 'kg m**-2 s**-1',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('hourly', 'monthly'), "minimal": ('monthly',)}},
    ],
    'avg_tsrwe': [
        {"name": 'Time-mean total snowfall rate water equivalent',
         "param": 235031, "levtype": 'sfc',
         "units": 'kg m**-2 s**-1',
         "freq": {"full": ('hourly', 'monthly'), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_u': [
        {"name": 'Time-mean U component of wind',
         "param": 235131, "levtype": 'hl',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',)}},
        {"name": 'Time-mean U component of wind',
         "param": 235131, "levtype": 'pl',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_uoe': [
        {"name": 'Time-mean eastward sea water velocity',
         "param": 263506, "levtype": 'o3d',
         "units": 'm s**-1',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_v': [
        {"name": 'Time-mean V component of wind',
         "param": 235132, "levtype": 'hl',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',)}},
        {"name": 'Time-mean V component of wind',
         "param": 235132, "levtype": 'pl',
         "units": 'm s**-1',
         "freq": {"full": ('monthly',), "reduced": ('monthly',), "minimal": ('monthly',)}},
    ],
    'avg_von': [
        {"name": 'Time-mean northward sea water velocity',
         "param": 263505, "levtype": 'o3d',
         "units": 'm s**-1',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_vsw': [
        {"name": 'Time-mean volumetric soil moisture',
         "param": 235077, "levtype": 'sol',
         "units": 'm**3 m**-3',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_w': [
        {"name": 'Time-mean vertical velocity',
         "param": 235135, "levtype": 'pl',
         "units": 'Pa s**-1',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_wo': [
        {"name": 'Time-mean upward sea water velocity',
         "param": 263507, "levtype": 'o3d',
         "units": 'm s**-1',
         "freq": {"full": ('daily', 'monthly')}},
    ],
    'avg_z': [
        {"name": 'Time-mean geopotential',
         "param": 235129, "levtype": 'pl',
         "units": 'm**2 s**-2',
         "freq": {"full": ('monthly',)}},
    ],
    'avg_zos': [
        {"name": 'Time-mean sea surface height',
         "param": 263124, "levtype": 'o2d',
         "units": 'm',
         "freq": {"full": ('daily', 'monthly'), "reduced": ('daily',)}},
    ],
    'clwc': [
        {"name": 'Specific cloud liquid water content',
         "param": 246, "levtype": 'pl',
         "units": 'kg kg**-1',
         "freq": {"full": ('hourly',)}},
    ],
    'lsm': [
        {"name": 'Land-sea mask',
         "param": 172, "levtype": 'sfc',
         "units": '(0 - 1)',
         "freq": {"full": ('daily',), "reduced": ('daily',)}},
    ],
    'msl': [
        {"name": 'Mean sea level pressure',
         "param": 151, "levtype": 'sfc',
         "units": 'Pa',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    'orog': [
        {"name": 'Orography',
         "param": 228002, "levtype": 'sfc',
         "units": 'm',
         "freq": {"full": ('daily',), "reduced": ('daily',)}},
    ],
    'pv': [
        {"name": 'Potential vorticity',
         "param": 60, "levtype": 'pl',
         "units": 'K m**2 kg**-1 s**-1',
         "freq": {"full": ('hourly',)}},
    ],
    'q': [
        {"name": 'Specific humidity',
         "param": 133, "levtype": 'pl',
         "units": 'kg kg**-1',
         "freq": {"full": ('hourly',)}},
    ],
    'r': [
        {"name": 'Relative humidity',
         "param": 157, "levtype": 'pl',
         "units": '%',
         "freq": {"full": ('hourly',)}},
    ],
    'sd': [
        {"name": 'Snow depth water equivalent',
         "param": 228141, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
        {"name": 'Snow depth water equivalent',
         "param": 228141, "levtype": 'sol',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
    ],
    'skt': [
        {"name": 'Skin temperature',
         "param": 235, "levtype": 'sfc',
         "units": 'K',
         "freq": {"full": ('hourly',)}},
    ],
    'sot': [
        {"name": 'Soil temperature',
         "param": 260360, "levtype": 'sol',
         "units": 'K',
         "freq": {"full": ('hourly',)}},
    ],
    'sp': [
        {"name": 'Surface pressure',
         "param": 134, "levtype": 'sfc',
         "units": 'Pa',
         "freq": {"full": ('hourly',)}},
    ],
    't': [
        {"name": 'Temperature',
         "param": 130, "levtype": 'pl',
         "units": 'K',
         "freq": {"full": ('hourly',)}},
    ],
    'tcc': [
        {"name": 'Total Cloud Cover',
         "param": 228164, "levtype": 'sfc',
         "units": '%',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
    ],
    'tciw': [
        {"name": 'Total column cloud ice water',
         "param": 79, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
    ],
    'tclw': [
        {"name": 'Total column cloud liquid water',
         "param": 78, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
    ],
    'tcw': [
        {"name": 'Total column water',
         "param": 136, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
    ],
    'tcwv': [
        {"name": 'Total column vertically-integrated water vapour',
         "param": 137, "levtype": 'sfc',
         "units": 'kg m**-2',
         "freq": {"full": ('hourly',)}},
    ],
    'u': [
        {"name": 'U component of wind',
         "param": 131, "levtype": 'hl',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
        {"name": 'U component of wind',
         "param": 131, "levtype": 'pl',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('6-hourly',)}},
    ],
    'v': [
        {"name": 'V component of wind',
         "param": 132, "levtype": 'hl',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('hourly',)}},
        {"name": 'V component of wind',
         "param": 132, "levtype": 'pl',
         "units": 'm s**-1',
         "freq": {"full": ('hourly',), "reduced": ('6-hourly',)}},
    ],
    'vsw': [
        {"name": 'Volumetric soil moisture',
         "param": 260199, "levtype": 'sol',
         "units": 'm**3 m**-3',
         "freq": {"full": ('hourly',)}},
    ],
    'w': [
        {"name": 'Vertical velocity',
         "param": 135, "levtype": 'pl',
         "units": 'Pa s**-1',
         "freq": {"full": ('hourly',)}},
    ],
    'z': [
        {"name": 'Geopotential',
         "param": 129, "levtype": 'pl',
         "units": 'm**2 s**-2',
         "freq": {"full": ('hourly',), "reduced": ('6-hourly',)}},
    ],
}
TIERS = ("full", "reduced", "minimal")

# Which stream a frequency is archived in, per the Climate DT schema.
STREAM_OF = {"monthly": "clmn", "daily": "clte",
             "hourly": "clte", "6-hourly": "clte"}

# ...and the pandas offset that builds its time axis.
PANDAS_FREQ = {"monthly": "MS", "daily": "D", "hourly": "h", "6-hourly": "6h"}

# Fallback level lists, used only when the FDB is not scanned. A scan is more
# accurate: the storyline runs carry 70 ocean levels, not the 75 this pads to.
LEVELS = {
    "pl": [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70,
           50, 30, 20, 10, 5, 1],
    "hl": [100],
    "sol": [1, 2, 3, 4, 5],
    "o3d": list(range(1, 76)),
}


def frequencies(name, tier="full", levtype=None):
    """Frequencies a variable is archived at, on a given portfolio tier."""
    out = set()
    for spec in VARIABLES.get(name, ()):
        if levtype is None or spec["levtype"] == levtype:
            out |= set(spec["freq"].get(tier, ()))
    return sorted(out)


def catalogue(stream="clte", tier="full", frequency=None):
    """``{levtype: {"levels": [...], "variables": {name: spec}}}``.

    Narrowed to one stream and tier, and optionally to a single frequency --
    which matters because a levtype can mix them.
    """
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    wanted = {frequency} if frequency else {
        f for f, s in STREAM_OF.items() if s == stream}

    out = {}
    for name, specs in VARIABLES.items():
        for spec in specs:
            if not wanted & set(spec["freq"].get(tier, ())):
                continue
            levtype = spec["levtype"]
            entry = out.setdefault(levtype, {"levtype": levtype,
                                             "levels": LEVELS.get(levtype),
                                             "variables": {}})
            entry["variables"][name] = {
                "long_name": spec["name"], "units": spec["units"],
                "param": spec["param"],
                "dims": ("time", "level", "cell") if levtype in LEVELS
                else ("time", "cell")}
    return out


def levtypes_for(name, catalogue):
    """Which levtypes of ``catalogue`` contain a variable, in portfolio order."""
    return [lt for lt, spec in catalogue.items() if name in spec["variables"]]


def infer_levtype(variables, catalogue):
    """Work out which levtype a set of variables lives on.

    Most names are unique across levtypes -- the ocean ones especially, since
    the 2-D and 3-D fields are different quantities with different names
    (``avg_tos`` is sea surface temperature, ``avg_thetao`` is 3-D potential
    temperature). The handful that are ambiguous raise rather than guess.
    """
    resolved = {}
    for name in variables:
        found = levtypes_for(name, catalogue)
        if not found:
            # The monthly stream prefixes time-means with avg_ and the hourly
            # one does not, so the usual cause is the other stream's spelling.
            for alt in (f"avg_{name}", name[4:] if name.startswith("avg_") else None):
                if alt and levtypes_for(alt, catalogue):
                    raise KeyError(
                        f"{name!r} is not in this portfolio, but {alt!r} is -- "
                        f"this stream spells it that way."
                    )
            known = VARIABLES.get(name)
            if known:
                where = "/".join(sorted({s["levtype"] for s in known}))
                when = sorted({f for s in known for fs in s["freq"].values()
                               for f in fs})
                raise KeyError(
                    f"{name!r} exists but is not in this portfolio. It is a "
                    f"{where} field, archived at {'/'.join(when)}, so check the "
                    f"frequency= and tier= you asked for."
                )
            raise KeyError(
                f"{name!r} is not in the portfolio. Pass levtype= explicitly if "
                f"you are naming a variable the catalogue does not carry."
            )
        if len(found) > 1:
            raise ValueError(
                f"{name!r} exists at more than one levtype ({', '.join(found)}), "
                f"so it cannot be inferred -- pass levtype= to say which."
            )
        resolved[name] = found[0]

    distinct = set(resolved.values())
    if len(distinct) > 1:
        listing = ", ".join(f"{n}={lt}" for n, lt in sorted(resolved.items()))
        raise ValueError(
            f"These variables span several levtypes ({listing}), and one "
            f"dataset holds one levtype. Open them separately."
        )
    return distinct.pop()


def is_3d(spec):
    """True if a portfolio variable spec has a vertical dimension."""
    return "level" in spec["dims"]


# HEALPix Nside per (activity, resolution). A property of the simulation that a
# request cannot ask for: story-nudging tops out at H512, free runs at H1024.
NSIDE = {
    "story-nudging": {"standard": 128, "high": 512},
    None: {"standard": 128, "high": 1024},
}


def nside_for(activity, resolution):
    """HEALPix Nside for an (activity, resolution) pair."""
    table = NSIDE.get(activity, NSIDE[None])
    try:
        return table[resolution]
    except KeyError:
        raise KeyError(
            f"No Nside known for activity={activity!r} resolution={resolution!r}. "
            f"Pass nside= explicitly."
        ) from None


def npix(nside):
    """Number of HEALPix cells for a given Nside."""
    return 12 * nside * nside


def level(nside):
    """HEALPix hierarchical level (order), i.e. log2(Nside)."""
    value = int(nside).bit_length() - 1
    if 1 << value != int(nside):
        raise ValueError(f"Nside must be a power of two, got {nside}")
    return value


def grid_attrs(nside, indexing_scheme="nested"):
    """Attributes for the cell coordinate describing the HEALPix mesh.

    These are xdggs's native convention, so ``xdggs.decode(ds, name="cell")``
    builds a DGGS index from them. The set has to be *exactly* the grid
    parameters: xdggs feeds the whole attrs dict to ``HealpixInfo(**attrs)``,
    which rejects any key it does not know.
    """
    return {"grid_name": "healpix", "level": level(nside),
            "indexing_scheme": indexing_scheme}


def crs_attrs(nside, indexing_scheme="nested"):
    """Attributes for the CF grid-mapping variable that accompanies the mesh."""
    return {"grid_mapping_name": "healpix", "refinement_level": level(nside),
            "indexing_scheme": indexing_scheme}
