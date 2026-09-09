"""shortName -> GRIB paramId for the DestinE Climate DT Gen2 portfolio.

FDB matches request keys literally against what was archived, and the archived
``param`` key is the numeric paramId -- unlike polytope, which runs the MARS
language over the request and accepts shortNames. So every request this package
builds has to translate the portfolio's shortName into a paramId first.

Covers every variable in the clmn, clte and storyline portfolios, plus the
``lsm``/``orog`` statics.
"""

PARAM_ID = {
    '10si'        : 207,
    '10u'         : 165,
    '10v'         : 166,
    '2d'          : 168,
    '2t'          : 167,
    'avg_10u'     : 235165,
    'avg_10v'     : 235166,
    'avg_10ws'    : 228005,
    'avg_2d'      : 235168,
    'avg_2t'      : 228004,
    'avg_clwc'    : 235246,
    'avg_hc300m'  : 263121,
    'avg_hc700m'  : 263122,
    'avg_hcbtm'   : 263123,
    'avg_ie'      : 235043,
    'avg_iews'    : 235041,
    'avg_inss'    : 235042,
    'avg_ishf'    : 235033,
    'avg_msl'     : 235151,
    'avg_pv'      : 235100,
    'avg_q'       : 235133,
    'avg_r'       : 235157,
    'avg_sd'      : 235078,
    'avg_sdlwrf'  : 235036,
    'avg_sdswrf'  : 235035,
    'avg_siconc'  : 263001,
    'avg_sithick' : 263000,
    'avg_siue'    : 263003,
    'avg_sivn'    : 263004,
    'avg_sivol'   : 263008,
    'avg_skt'     : 235079,
    'avg_slhtf'   : 235034,
    'avg_snlwrf'  : 235038,
    'avg_snlwrfcs': 235052,
    'avg_snswrf'  : 235037,
    'avg_snswrfcs': 235051,
    'avg_snvol'   : 263009,
    'avg_so'      : 263500,
    'avg_sos'     : 263100,
    'avg_sp'      : 235134,
    'avg_ssurfror': 235021,
    'avg_surfror' : 235020,
    'avg_t'       : 235130,
    'avg_tcc'     : 235288,
    'avg_tciw'    : 235088,
    'avg_tclw'    : 235087,
    'avg_tcw'     : 235136,
    'avg_tcwv'    : 235137,
    'avg_tdswrf'  : 235053,
    'avg_thetao'  : 263501,
    'avg_tnlwrf'  : 235040,
    'avg_tnlwrfcs': 235050,
    'avg_tnswrf'  : 235039,
    'avg_tnswrfcs': 235049,
    'avg_tos'     : 263101,
    'avg_tprate'  : 235055,
    'avg_tsrwe'   : 235031,
    'avg_u'       : 235131,
    'avg_uoe'     : 263506,
    'avg_v'       : 235132,
    'avg_von'     : 263505,
    'avg_vsw'     : 235077,
    'avg_w'       : 235135,
    'avg_wo'      : 263507,
    'avg_z'       : 235129,
    'avg_zos'     : 263124,
    'clwc'        : 246,
    'lsm'         : 172,
    'msl'         : 151,
    'orog'        : 228002,
    'pv'          : 60,
    'q'           : 133,
    'r'           : 157,
    'sd'          : 228141,
    'skt'         : 235,
    'sot'         : 260360,
    'sp'          : 134,
    't'           : 130,
    'tcc'         : 228164,
    'tciw'        : 79,
    'tclw'        : 78,
    'tcw'         : 136,
    'tcwv'        : 137,
    'u'           : 131,
    'v'           : 132,
    'vsw'         : 260199,
    'w'           : 135,
    'z'           : 129,
}

SHORT_NAME = {v: k for k, v in PARAM_ID.items()}


def to_param_id(name):
    """Resolve a shortName (or an already-numeric paramId) to an int paramId."""
    if isinstance(name, int):
        return name
    if isinstance(name, str) and name.isdigit():
        return int(name)
    try:
        return PARAM_ID[name]
    except KeyError:
        raise KeyError(
            f"Unknown variable {name!r}. Pass a numeric paramId instead, or add "
            f"it to destine_fdb.params.PARAM_ID."
        ) from None
