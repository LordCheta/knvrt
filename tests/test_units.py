import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knvrt.units import (
    Quantity,
    UnitError,
    convert,
    format_number,
    list_units,
    parse_quantity,
    parse_unit,
    split_number_unit,
)


@pytest.mark.parametrize(
    ("value", "src", "dst", "expected"),
    [
        (1, "km", "m", 1000),
        (5, "km", "mi", 3.1068559611866697),
        (1, "in", "mm", 25.4),
        (1, "ft", "in", 12),
        (1, "mi", "ft", 5280),
        (1, "lb", "kg", 0.45359237),
        (16, "oz", "lb", 1),
        (1, "h", "s", 3600),
        (1, "gal", "L", 3.785411784),
        (1, "atm", "kPa", 101.325),
        (14.5037738, "psi", "bar", 1.0),
        (1, "bar", "Pa", 1e5),
        (60, "mph", "m/s", 26.8224),
        (100, "km/h", "mph", 62.13711922),
        (1, "kWh", "MJ", 3.6),
        (1, "hp", "kW", 0.74569987158),
        (1, "N*m", "J", 1),
        (1, "kg*m^2/s^2", "J", 1),
        (1, "m^2", "cm^2", 1e4),
        (1, "m^3", "L", 1000),
        (1, "ft^2", "in^2", 144),
        (3000, "rpm", "Hz", 50),
        (180, "deg", "rad", math.pi),
        (1, "rev", "deg", 360),
        (5, "kohm", "ohm", 5000),
        (2.2, "mV", "V", 0.0022),
        (1, "uA", "mA", 0.001),
        (1, "µm", "nm", 1000),
    ],
)
def test_known_conversions(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize(
    ("value", "src", "dst", "expected"),
    [
        (0, "degC", "K", 273.15),
        (100, "degC", "F", 212),
        (-40, "degC", "F", -40),
        (32, "F", "degC", 0),
        (0, "K", "degC", -273.15),
        (491.67, "R", "K", 273.15),
        (100, "C", "F", 212),  # a lone C next to a temperature scale means Celsius
        (300, "K", "°C", 26.85),
    ],
)
def test_temperatures(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, abs=1e-6)


def test_c_alone_is_the_coulomb():
    assert convert(1, "C", "mC") == pytest.approx(1000)
    assert parse_unit("C").dim == parse_unit("A*s").dim


def test_kelvin_inside_compound_units():
    assert parse_unit("W/m/K").factor == 1
    assert parse_unit("W/m/K").dim == parse_unit("W/m/K").dim
    assert convert(1, "W/m/K", "kW/m/K") == pytest.approx(1e-3)


@pytest.mark.parametrize(
    ("src", "dst", "message"),
    [
        ("m", "kg", "Cannot convert length"),
        ("N", "J", "force"),
        ("foo", "m", "Unknown unit 'foo'"),
        ("m", "bar_", "Unknown unit"),
        ("m//s", "m", "Unexpected"),
        ("m/", "m", "Incomplete"),
        ("", "m", "Empty unit"),
        ("m", " ", "Empty unit"),
        ("degC*m", "K", "Unknown unit"),
        ("*m", "m", "Unexpected"),
    ],
)
def test_errors(src, dst, message):
    with pytest.raises(UnitError, match=message):
        convert(1, src, dst)


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_rejects_non_finite(bad):
    with pytest.raises(UnitError, match="finite"):
        convert(bad, "m", "ft")


def test_prefix_only_applies_to_prefixable_units():
    assert convert(1, "km", "m") == 1000
    with pytest.raises(UnitError):
        convert(1, "kft", "m")  # feet are not SI
    with pytest.raises(UnitError):
        convert(1, "mpsi", "Pa")


def test_aliases_and_plurals():
    assert convert(2, "meters", "feet") == pytest.approx(6.561679790)
    assert convert(1, "minutes", "seconds") == 60


def test_exponent_forms():
    assert convert(1, "m^2", "m**2") == 1
    assert parse_unit("s^-1").dim == parse_unit("Hz").dim
    assert parse_unit("m/s^2").dim == parse_unit("m/s/s").dim


def test_quantity_round_trip():
    q = Quantity.of(5, "psi")
    assert q.to("kPa") == pytest.approx(34.4738, rel=1e-5)
    with pytest.raises(UnitError):
        q.to("m")
    assert Quantity.of(100, "degC").si == pytest.approx(373.15)


@pytest.mark.parametrize(
    ("text", "number", "unit"),
    [("12 V", 12, "V"), ("3.5e-3 m", 0.0035, "m"), ("-4kg", -4, "kg"), ("  7  ", 7, ""), (".5 m", 0.5, "m")],
)
def test_split_number_unit(text, number, unit):
    assert split_number_unit(text) == (number, unit)


@pytest.mark.parametrize("text", ["", "abc", "V 12", "--3 m"])
def test_unreadable_quantities(text):
    with pytest.raises(UnitError):
        parse_quantity(text)


def test_listing_covers_every_category():
    groups = list_units()
    assert {"length", "mass", "pressure", "temperature", "power"} <= set(groups)
    assert "kPa" not in groups["pressure"]  # prefixes are implied, not listed
    assert "Pa*" in groups["pressure"]


@pytest.mark.parametrize(
    ("x", "text"),
    [
        (0, "0"),
        (3.1068559, "3.10686"),
        (12000, "12000"),
        (1.5e-9, "1.5e-9"),
        (2.5e12, "2.5e+12"),
        (-0.00002, "-2e-5"),
    ],
)
def test_format_number(x, text):
    assert format_number(x) == text


# ---- properties -------------------------------------------------------------

LINEAR_UNITS = {
    "length": ["m", "km", "mm", "cm", "in", "ft", "yd", "mi", "nmi", "um"],
    "mass": ["kg", "g", "mg", "lb", "oz", "t", "slug"],
    "pressure": ["Pa", "kPa", "MPa", "bar", "atm", "psi", "mmHg", "inHg"],
    "energy": ["J", "kJ", "MJ", "Wh", "kWh", "cal", "kcal", "BTU", "ftlbf"],
    "power": ["W", "kW", "MW", "mW", "hp"],
    "volume": ["L", "mL", "gal", "qt", "m^3", "ft^3", "in^3"],
    "speed": ["m/s", "km/h", "mph", "kn", "ft/s"],
}
pairs = st.sampled_from(sorted(LINEAR_UNITS)).flatmap(
    lambda c: st.tuples(st.sampled_from(LINEAR_UNITS[c]), st.sampled_from(LINEAR_UNITS[c]))
)
values = st.floats(min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False)


@given(values, pairs)
def test_round_trip_is_stable(x, pair):
    a, b = pair
    assert convert(convert(x, a, b), b, a) == pytest.approx(x, rel=1e-9)


@given(values, pairs)
def test_conversion_is_linear(x, pair):
    a, b = pair
    assert convert(2 * x, a, b) == pytest.approx(2 * convert(x, a, b), rel=1e-9)


@given(values, st.sampled_from(["degC", "F", "K", "R"]), st.sampled_from(["degC", "F", "K", "R"]))
def test_temperature_round_trip(x, a, b):
    assert convert(convert(x, a, b), b, a) == pytest.approx(x, rel=1e-7, abs=1e-6)


@given(st.sampled_from(["m", "kg", "s", "Pa", "J", "W"]), st.sampled_from(["m", "kg", "s", "Pa", "J", "W"]))
def test_incompatible_units_always_raise(a, b):
    if parse_unit(a).dim == parse_unit(b).dim:
        assert convert(1, a, b) > 0
    else:
        with pytest.raises(UnitError):
            convert(1, a, b)
