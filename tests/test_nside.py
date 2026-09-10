"""The GRIB-header route to Nside, exercised without an FDB.

Nside cannot be asked for: `resolution` is a MARS key whose meaning depends on
the model resolution behind the run. What the data always carries is the point
count in GRIB2 section 3, which for HEALPix is 12*Nside^2.
"""

import struct

import pytest

from destine_fdb import fdb as fdbmod


def grib2_head(points, edition=2, section3_len=72):
    """A GRIB2 message head: section 0, a filler section 1, then section 3."""
    section0 = b"GRIB" + b"\0\0" + bytes([0]) + bytes([edition]) + b"\0" * 8
    section1 = struct.pack(">IB", 21, 1) + b"\0" * 16
    section3 = (struct.pack(">IB", section3_len, 3)
                + b"\0"                                   # source of grid def
                + struct.pack(">I", points)               # octets 7-10
                + b"\0" * (section3_len - 10))
    return section0 + section1 + section3


@pytest.mark.parametrize("nside", [32, 128, 512, 1024])
def test_point_count_comes_back_from_the_header(nside):
    assert fdbmod._grib_data_points(grib2_head(12 * nside * nside)) == 12 * nside * nside


def test_a_grib1_message_is_declined_rather_than_misread():
    # GRIB1 keeps the grid description somewhere else entirely; guessing at the
    # same offsets would return a plausible-looking wrong number.
    assert fdbmod._grib_data_points(grib2_head(196608, edition=1)) is None


def test_something_that_is_not_grib_is_declined():
    assert fdbmod._grib_data_points(b"\x00" * 200) is None


def test_a_head_that_stops_before_section_3_is_declined():
    assert fdbmod._grib_data_points(grib2_head(196608)[:30]) is None


def test_mars_alternatives_become_lists():
    # list() matches values literally, so "0000/0100" as one string finds
    # nothing -- while the request builders speak MARS.
    assert fdbmod._alternatives({"time": "0000/0100", "param": "167"}) == {
        "time": ["0000", "0100"], "param": "167"}


def test_measure_nside_reads_only_the_head(monkeypatch):
    reads = []

    class Handle:
        def open(self):
            pass

        def read(self, n):
            reads.append(n)
            return grib2_head(12 * 512 * 512)

        def close(self):
            pass

    class Element:
        data_handle = Handle()

    monkeypatch.setattr(fdbmod, "_elements", lambda request, depth: iter([Element()]))
    assert fdbmod.measure_nside({"param": "167"}) == 512
    assert reads == [512]           # a few hundred bytes, never the field


def test_a_point_count_that_is_not_healpix_is_declined(monkeypatch):
    class Handle:
        def open(self):
            pass

        def read(self, n):
            return grib2_head(1_038_240)          # an octahedral reduced gaussian grid

        def close(self):
            pass

    class Element:
        data_handle = Handle()

    monkeypatch.setattr(fdbmod, "_elements", lambda request, depth: iter([Element()]))
    assert fdbmod.measure_nside({}) is None


def test_one_unlistable_run_does_not_sink_the_whole_table(monkeypatch):
    """The shared DestinE FDB holds a `class=sbeyercopy_d1` run metkit rejects.

    That used to raise out of runs(check_nside=True), losing 800-odd good rows
    to one bad one.
    """
    import destine_fdb

    def explode(request, level, key):
        raise RuntimeError("UserError: TypeEnum[name=class]: cannot expand "
                           "'sbeyercopy_d1'")

    monkeypatch.setattr(fdbmod, "_values", explode)
    assert destine_fdb._measure_run_nside(
        {"class": "sbeyercopy_d1", "stream": "clmn", "first": "2026"}) is None


def test_a_resolution_that_cannot_be_measured_is_skipped_not_fatal(monkeypatch):
    import destine_fdb

    monkeypatch.setattr(fdbmod, "_values",
                        lambda request, level, key: {"standard", "high"})

    def measure(request, **kw):
        if request["resolution"] == "high":
            raise RuntimeError("boom")
        return 128

    monkeypatch.setattr(fdbmod, "measure_nside", measure)
    assert destine_fdb._measure_run_nside(
        {"stream": "clte", "first": "20260501"}) == 128
