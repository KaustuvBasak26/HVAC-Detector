from __future__ import annotations

from app.processing.dimension_parser import find_dimension_candidates, parse_dimension_text


def test_parse_rect_simple():
    p = parse_dimension_text("24x12")
    assert p is not None
    assert p.width_in == 24
    assert p.height_in == 12
    assert p.diameter_in is None


def test_parse_rect_embedded():
    p = parse_dimension_text("SUPPLY 18 x 6 RUN")
    assert p is not None
    assert p.width_in == 18
    assert p.height_in == 6


def test_parse_diameter():
    p = parse_dimension_text("Ø12")
    assert p is not None
    assert p.diameter_in == 12


def test_parse_empty():
    assert parse_dimension_text("") is None
    assert parse_dimension_text("   ") is None


def test_find_dimension_candidates_multi():
    found = find_dimension_candidates("Main 12x8 branch and Ø10 drop")
    kinds = {(x.width_in, x.height_in, x.diameter_in) for x in found}
    assert (12.0, 8.0, None) in kinds
    assert any(x.diameter_in == 10 for x in found)
