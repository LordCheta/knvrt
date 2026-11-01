"""Unit registry, unit-expression parser and conversions.

A *unit expression* looks like ``km/h``, ``N*m``, ``kg*m^2/s^2`` or ``psi``.
Every unit has a scale factor to SI and a dimension, so conversions between
compatible units work for any combination (``mph`` to ``m/s``, ``kWh`` to ``MJ``)
and incompatible conversions are rejected with a helpful message.

Temperatures (°C, °F, K, °R) are affine, so °C, °F and °R are only supported as a single
unit, e.g. ``convert(100, "degC", "F")`` (a lone ``C`` is the coulomb, but ``convert``
reads it as Celsius when the other side is a temperature). Kelvin may also appear in
compound units such as ``W/m/K``; use it for temperature differences.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import dimensions as d
from .dimensions import Dimension


class UnitError(ValueError):
    """Raised for unknown units, bad expressions or incompatible conversions."""


@dataclass(frozen=True, slots=True)
class Unit:
    name: str
    dim: Dimension
    factor: float  # multiply a value in this unit by `factor` to get SI
    prefixable: bool = False
    category: str = ""


# ---- registry --------------------------------------------------------------

_ATOMS: dict[str, Unit] = {}
_ALIASES: dict[str, str] = {}


def _add(
    name: str,
    dim: Dimension,
    factor: float,
    *,
    prefixable: bool = False,
    aliases: tuple[str, ...] = (),
) -> None:
    category = d.describe(dim)
    _ATOMS[name] = Unit(name, dim, factor, prefixable, category)
    for alias in aliases:
        _ALIASES[alias] = name


_G = 9.80665  # standard gravity, m/s^2
_IN = 0.0254
_FT = 0.3048
_LB = 0.45359237

# length
_add("m", d.LENGTH, 1.0, prefixable=True, aliases=("meter", "meters", "metre", "metres"))
_add("in", d.LENGTH, _IN, aliases=("inch", "inches"))
_add("ft", d.LENGTH, _FT, aliases=("foot", "feet"))
_add("yd", d.LENGTH, 0.9144, aliases=("yard", "yards"))
_add("mi", d.LENGTH, 1609.344, aliases=("mile", "miles"))
_add("nmi", d.LENGTH, 1852.0, aliases=("nauticalmile",))
# mass
_add("g", d.MASS, 1e-3, prefixable=True, aliases=("gram", "grams"))
_add("lb", d.MASS, _LB, aliases=("lbs", "pound", "pounds", "lbm"))
_add("oz", d.MASS, _LB / 16, aliases=("ounce", "ounces"))
_add("t", d.MASS, 1000.0, aliases=("tonne", "tonnes"))
_add("slug", d.MASS, 14.593903)
# time
_add("s", d.TIME, 1.0, prefixable=True, aliases=("sec", "second", "seconds"))
_add("min", d.TIME, 60.0, aliases=("minute", "minutes"))
_add("h", d.TIME, 3600.0, aliases=("hr", "hour", "hours"))
_add("day", d.TIME, 86400.0, aliases=("days",))
# area / volume
_add("L", d.VOLUME, 1e-3, prefixable=True, aliases=("l", "liter", "liters", "litre", "litres"))
_add("gal", d.VOLUME, 3.785411784e-3, aliases=("gallon", "gallons"))
_add("qt", d.VOLUME, 3.785411784e-3 / 4, aliases=("quart", "quarts"))
_add("ha", d.AREA, 1e4, aliases=("hectare", "hectares"))
_add("acre", d.AREA, 4046.8564224, aliases=("acres",))
# speed
_add("kn", d.SPEED, 1852.0 / 3600.0, aliases=("knot", "knots", "kt"))
_add("mph", d.SPEED, 1609.344 / 3600.0)
_add("kph", d.SPEED, 1000.0 / 3600.0)
# force
_add("N", d.FORCE, 1.0, prefixable=True, aliases=("newton", "newtons"))
_add("lbf", d.FORCE, _LB * _G)
_add("kgf", d.FORCE, _G)
# pressure
_add("Pa", d.PRESSURE, 1.0, prefixable=True, aliases=("pascal", "pascals"))
_add("bar", d.PRESSURE, 1e5, aliases=("bars",))
_add("atm", d.PRESSURE, 101325.0)
_add("psi", d.PRESSURE, _LB * _G / (_IN**2))
_add("mmHg", d.PRESSURE, 133.322387415, aliases=("torr",))
_add("inHg", d.PRESSURE, 3386.389)
# energy / power
_add("J", d.ENERGY, 1.0, prefixable=True, aliases=("joule", "joules"))
_add("Wh", d.ENERGY, 3600.0, prefixable=True)
_add("cal", d.ENERGY, 4.184, prefixable=True, aliases=("calorie", "calories"))
_add("BTU", d.ENERGY, 1055.05585262, aliases=("btu",))
_add("ftlbf", d.ENERGY, _FT * _LB * _G)
_add("eV", d.ENERGY, 1.602176634e-19, prefixable=True)
_add("W", d.POWER, 1.0, prefixable=True, aliases=("watt", "watts"))
_add("hp", d.POWER, 745.69987158227, aliases=("horsepower",))
# electrical
_add("A", d.CURRENT, 1.0, prefixable=True, aliases=("amp", "amps", "ampere", "amperes"))
_add("V", d.VOLTAGE, 1.0, prefixable=True, aliases=("volt", "volts"))
_add("ohm", d.RESISTANCE, 1.0, prefixable=True, aliases=("Ω", "ohms"))
_add("C", d.CHARGE, 1.0, prefixable=True, aliases=("coulomb", "coulombs"))
# frequency / angle
_add("Hz", d.FREQUENCY, 1.0, prefixable=True, aliases=("hertz",))
_add("rpm", d.FREQUENCY, 1.0 / 60.0)
_add("rad", d.DIMENSIONLESS, 1.0, aliases=("radian", "radians"))
_add("deg", d.DIMENSIONLESS, math.pi / 180.0, aliases=("degree", "degrees", "°"))
_add("rev", d.DIMENSIONLESS, 2 * math.pi, aliases=("revolution", "revolutions"))
_add("%", d.DIMENSIONLESS, 0.01, aliases=("percent",))

_add("K", d.TEMPERATURE, 1.0, aliases=("kelvin",))

# affine temperature scales: (name, scale to kelvin, offset in kelvin at 0 of the scale)
_TEMPS: dict[str, tuple[float, float]] = {
    "K": (1.0, 0.0),
    "C": (1.0, 273.15),
    "F": (5.0 / 9.0, 255.3722222222222),  # (F + 459.67) * 5/9
    "R": (5.0 / 9.0, 0.0),
}
_TEMP_ALIASES = {
    "degC": "C", "°C": "C", "celsius": "C", "degF": "F", "°F": "F",
    "fahrenheit": "F", "degR": "R", "°R": "R", "rankine": "R",
}  # fmt: skip

_PREFIXES: dict[str, float] = {
    "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "c": 1e-2, "m": 1e-3,
    "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12,
}  # fmt: skip
# 'da' (deca) is omitted on purpose: it collides with 'day' and is rarely used.


def _lookup_atom(name: str) -> Unit:
    """Resolve a single unit symbol, with optional SI prefix."""
    name = _ALIASES.get(name, name)
    if name in _ATOMS:
        return _ATOMS[name]
    if len(name) > 1:
        prefix, rest = name[0], name[1:]
        rest = _ALIASES.get(rest, rest)
        if prefix in _PREFIXES and rest in _ATOMS and _ATOMS[rest].prefixable:
            base = _ATOMS[rest]
            return Unit(name, base.dim, base.factor * _PREFIXES[prefix], False, base.category)
    raise UnitError(f"Unknown unit '{name}'. Run `knvrt units` to see what is supported.")


_TOKEN = re.compile(r"\s*(?:([*/·])|(\^?-?\d+)|([^\s*/·^\d][^\s*/·^]*))")


@dataclass(frozen=True, slots=True)
class Compound:
    """A parsed unit expression."""

    expression: str
    dim: Dimension
    factor: float
    temperature_scale: str | None = None  # set for a lone °C/°F/K/°R


def parse_unit(expression: str) -> Compound:
    """Parse ``km/h``, ``N*m``, ``kg*m^2/s^2`` ... into a dimension and SI factor."""
    text = expression.strip()
    if not text:
        raise UnitError("Empty unit")
    # A lone "C" is the coulomb. Celsius is "degC", "°C" or "celsius" (convert()
    # also treats "C" as Celsius when the other side is a temperature).
    single = _TEMP_ALIASES.get(text, text if text in ("K", "F", "R", "kelvin") else None)
    if single == "kelvin":
        single = "K"
    if single in _TEMPS:
        return Compound(text, d.TEMPERATURE, _TEMPS[single][0], single)

    dim = d.DIMENSIONLESS
    factor = 1.0
    sign = 1  # +1 numerator, -1 denominator
    expecting_unit = True
    last: tuple[Dimension, float] | None = None
    pos = 0
    text = text.replace("**", "^")
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise UnitError(f"Cannot parse unit expression '{expression}'")
        pos = m.end()
        op, num, name = m.groups()
        if op:
            if expecting_unit:
                raise UnitError(f"Unexpected '{op}' in '{expression}'")
            sign = -1 if op == "/" else 1
            expecting_unit = True
        elif num is not None:
            if last is None or expecting_unit:
                raise UnitError(f"Unexpected exponent in '{expression}'")
            exp = int(num.lstrip("^"))
            ldim, lfac = last
            # undo the single power applied earlier and apply the full one
            dim = dim * (ldim ** (sign * (exp - 1)))
            factor *= lfac ** (sign * (exp - 1))
            last = None
        else:
            if not expecting_unit:  # implicit multiplication "N m"
                sign = 1
            unit = _lookup_atom(name)
            dim = dim * (unit.dim**sign)
            factor *= unit.factor**sign
            last = (unit.dim, unit.factor)
            expecting_unit = False
    if expecting_unit:
        raise UnitError(f"Incomplete unit expression '{expression}'")
    return Compound(expression.strip(), dim, factor)


# ---- conversion ------------------------------------------------------------


def _to_kelvin(value: float, scale: str) -> float:
    k, off = _TEMPS[scale]
    return value * k + off


def _from_kelvin(value: float, scale: str) -> float:
    k, off = _TEMPS[scale]
    return (value - off) / k


def _is_temperature_scale(unit: str) -> bool:
    t = unit.strip()
    return t in _TEMP_ALIASES or t in ("K", "F", "R", "kelvin")


def _celsius_hint(a: str, b: str) -> tuple[str, str]:
    """`convert(100, "C", "F")` means Celsius, not coulombs."""
    if a.strip() == "C" and _is_temperature_scale(b):
        return "degC", b
    if b.strip() == "C" and _is_temperature_scale(a):
        return a, "degC"
    return a, b


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` from one unit expression to another.

    >>> round(convert(5, "km", "mi"), 4)
    3.1069
    >>> convert(100, "degC", "F")
    212.0
    """
    if not math.isfinite(value):
        raise UnitError("Value must be a finite number")
    from_unit, to_unit = _celsius_hint(from_unit, to_unit)
    src, dst = parse_unit(from_unit), parse_unit(to_unit)
    if src.dim != dst.dim:
        raise UnitError(
            f"Cannot convert {d.describe(src.dim)} ({from_unit}) to {d.describe(dst.dim)} ({to_unit})"
        )
    if src.temperature_scale or dst.temperature_scale:
        s = _TEMP_ALIASES.get(src.temperature_scale or "", src.temperature_scale)
        t = _TEMP_ALIASES.get(dst.temperature_scale or "", dst.temperature_scale)
        if not (s and t):
            raise UnitError("Temperature scales can't be mixed with compound units; use K")
        result = _from_kelvin(_to_kelvin(value, s), t)
        return round(result, 10) + 0.0
    return value * src.factor / dst.factor


@dataclass(frozen=True, slots=True)
class Quantity:
    """A value in SI base units with its dimension."""

    si: float
    dim: Dimension

    @classmethod
    def of(cls, value: float, unit: str) -> Quantity:
        u = parse_unit(unit)
        if u.temperature_scale:
            return cls(_to_kelvin(value, _TEMP_ALIASES.get(u.temperature_scale, u.temperature_scale)), u.dim)
        return cls(value * u.factor, u.dim)

    def to(self, unit: str) -> float:
        u = parse_unit(unit)
        if u.dim != self.dim:
            raise UnitError(f"Cannot express {d.describe(self.dim)} in {unit} ({d.describe(u.dim)})")
        if u.temperature_scale:
            return _from_kelvin(self.si, _TEMP_ALIASES.get(u.temperature_scale, u.temperature_scale))
        return self.si / u.factor


_QUANTITY = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$")


def split_number_unit(text: str) -> tuple[float, str]:
    """Split ``"3.5e-3 m"`` into ``(0.0035, "m")``. The unit may be empty."""
    m = _QUANTITY.match(text)
    if not m:
        raise UnitError(f"Cannot read a number from '{text}'")
    number = float(m.group(1))
    if not math.isfinite(number):
        raise UnitError("Value must be a finite number")
    return number, m.group(2).strip()


def parse_quantity(text: str) -> Quantity:
    """Parse ``"12 V"``, ``"3.5e-3 m"``, ``"100 degC"``; a bare number is dimensionless."""
    number, unit = split_number_unit(text)
    if not unit:
        return Quantity(number, d.DIMENSIONLESS)
    return Quantity.of(number, unit)


def list_units() -> dict[str, list[str]]:
    """Units grouped by category (for `knvrt units`)."""
    groups: dict[str, list[str]] = {}
    for u in _ATOMS.values():
        groups.setdefault(u.category, []).append(u.name + ("*" if u.prefixable else ""))
    groups.setdefault("temperature", []).extend(["degC", "F", "R"])
    return {k: sorted(v) for k, v in sorted(groups.items())}


def format_number(x: float, digits: int = 6) -> str:
    """Compact human formatting.

    >>> format_number(3.1068559)
    '3.10686'
    >>> format_number(12000)
    '12000'
    >>> format_number(1.5e-9)
    '1.5e-9'
    """
    if x == 0:
        return "0"
    if abs(x) >= 1e9 or abs(x) < 1e-4:
        mantissa, _, exp = f"{x:.{digits - 1}e}".partition("e")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        sign = "-" if exp.startswith("-") else "+"
        exponent = exp.lstrip("+-").lstrip("0") or "0"
        return f"{mantissa}e{sign}{exponent}" if sign == "-" else f"{mantissa}e+{exponent}"
    return f"{x:.{digits}g}"
