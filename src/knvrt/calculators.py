"""Common engineering calculators.

Every calculator declares typed inputs (with the dimension each one must have)
and returns named results with a suggested display unit. Inputs are accepted
with any compatible unit (``"12 V"``, ``"2 in"``, ``"30 psi"``) and calculated
in SI, so you never have to convert by hand.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from . import dimensions as d
from .dimensions import Dimension
from .units import Quantity, UnitError, parse_quantity


class CalcError(ValueError):
    """Raised when inputs are missing, invalid or physically impossible."""


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    dim: Dimension
    help: str
    default_unit: str  # shown in help and used when a bare number is given
    optional: bool = False


@dataclass(frozen=True, slots=True)
class Output:
    name: str
    quantity: Quantity
    unit: str  # preferred display unit

    @property
    def value(self) -> float:
        return self.quantity.si if not self.unit else self.quantity.to(self.unit)


@dataclass(frozen=True)
class Calculator:
    name: str
    title: str
    summary: str
    formula: str
    params: tuple[Param, ...]
    solve: Callable[[dict[str, float]], list[tuple[str, float, Dimension, str]]]
    example: str = ""
    notes: str = field(default="")

    def run(self, inputs: Mapping[str, str | float | Quantity]) -> list[Output]:
        known = {p.name: p for p in self.params}
        unknown = set(inputs) - set(known)
        if unknown:
            raise CalcError(
                f"Unknown input(s) for {self.name}: {', '.join(sorted(unknown))}. "
                f"Expected: {', '.join(known)}"
            )
        si: dict[str, float] = {}
        for name, raw in inputs.items():
            p = known[name]
            q = _to_quantity(raw, p)
            if q.dim != p.dim:
                raise CalcError(
                    f"'{name}' must be a {d.describe(p.dim)} (e.g. {p.default_unit}), got {d.describe(q.dim)}"
                )
            if not math.isfinite(q.si):
                raise CalcError(f"'{name}' must be a finite number")
            si[name] = q.si
        missing = [p.name for p in self.params if not p.optional and p.name not in si]
        if missing:
            raise CalcError(f"Missing input(s) for {self.name}: {', '.join(missing)}")
        try:
            rows = self.solve(si)
        except ZeroDivisionError as e:
            raise CalcError("Division by zero: check that no input is 0") from e
        return [Output(n, Quantity(v, dim), unit) for n, v, dim, unit in rows]


def _to_quantity(raw: str | float | Quantity, p: Param) -> Quantity:
    if isinstance(raw, Quantity):
        return raw
    if isinstance(raw, int | float):
        return _bare(float(raw), p)
    try:
        q = parse_quantity(raw)
    except UnitError as e:
        raise CalcError(f"'{p.name}': {e}") from e
    if q.dim.is_dimensionless and p.dim != d.DIMENSIONLESS:
        return _bare(q.si, p)  # bare number: assume the default unit
    return q


def _bare(value: float, p: Param) -> Quantity:
    return Quantity(value, d.DIMENSIONLESS) if not p.default_unit else Quantity.of(value, p.default_unit)


def _positive(**values: float) -> None:
    for name, v in values.items():
        if v <= 0:
            raise CalcError(f"'{name}' must be greater than 0")


# ---- calculators -------------------------------------------------------------


def _ohms_law(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    given = {k: i[k] for k in ("v", "i", "r", "p") if k in i}
    if len(given) != 2:
        raise CalcError("Give exactly two of v, i, r, p (volts, amps, ohms, watts)")
    v, a, r, p = (given.get(k) for k in ("v", "i", "r", "p"))
    if v is not None and a is not None:
        r, p = v / a, v * a
    elif v is not None and r is not None:
        a, p = v / r, v * v / r
    elif v is not None and p is not None:
        a, r = p / v, v * v / p
    elif a is not None and r is not None:
        v, p = a * r, a * a * r
    elif a is not None and p is not None:
        v, r = p / a, p / (a * a)
    else:  # r and p
        assert r is not None and p is not None
        if r < 0 or p < 0:
            raise CalcError("r and p must not be negative")
        a = math.sqrt(p / r)
        v = math.sqrt(p * r)
    assert v is not None and a is not None and r is not None and p is not None
    return [
        ("voltage", v, d.VOLTAGE, "V"),
        ("current", a, d.CURRENT, "A"),
        ("resistance", r, d.RESISTANCE, "ohm"),
        ("power", p, d.POWER, "W"),
    ]


def _series_resistance(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(**i)
    return [("total resistance", sum(i.values()), d.RESISTANCE, "ohm")]


def _parallel_resistance(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(**i)
    return [("total resistance", 1.0 / sum(1.0 / v for v in i.values()), d.RESISTANCE, "ohm")]


def _voltage_divider(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(r1=i["r1"], r2=i["r2"])
    vout = i["vin"] * i["r2"] / (i["r1"] + i["r2"])
    return [
        ("output voltage", vout, d.VOLTAGE, "V"),
        ("current", i["vin"] / (i["r1"] + i["r2"]), d.CURRENT, "mA"),
    ]


def _stress(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(area=i["area"])
    sigma = i["force"] / i["area"]
    rows = [("stress", sigma, d.PRESSURE, "MPa")]
    if "yield_strength" in i:
        _positive(yield_strength=i["yield_strength"])
        rows.append(
            ("safety factor", i["yield_strength"] / abs(sigma) if sigma else math.inf, d.DIMENSIONLESS, "")
        )
    return rows


def _beam(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(length=i["length"], e=i["e"], inertia=i["inertia"])
    length, ei = i["length"], i["e"] * i["inertia"]
    has_p, has_w = "load" in i, "udl" in i
    if has_p == has_w:
        raise CalcError("Give exactly one of load (point load) or udl (uniform load per length)")
    if has_p:
        p = i["load"]
        defl = p * length**3 / (48 * ei)
        moment = p * length / 4
        reaction = p / 2
    else:
        w = i["udl"]
        defl = 5 * w * length**4 / (384 * ei)
        moment = w * length**2 / 8
        reaction = w * length / 2
    return [
        ("max deflection", defl, d.LENGTH, "mm"),
        ("max bending moment", moment, d.ENERGY, "N*m"),
        ("support reaction", reaction, d.FORCE, "N"),
    ]


def _cantilever(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(length=i["length"], e=i["e"], inertia=i["inertia"])
    length, ei = i["length"], i["e"] * i["inertia"]
    has_p, has_w = "load" in i, "udl" in i
    if has_p == has_w:
        raise CalcError("Give exactly one of load (tip load) or udl (uniform load per length)")
    if has_p:
        p = i["load"]
        defl, moment = p * length**3 / (3 * ei), p * length
    else:
        w = i["udl"]
        defl, moment = w * length**4 / (8 * ei), w * length**2 / 2
    return [("max deflection", defl, d.LENGTH, "mm"), ("max bending moment", moment, d.ENERGY, "N*m")]


def _rect_section(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(**i)
    b, h = i["width"], i["height"]
    inertia = b * h**3 / 12
    return [
        ("area", b * h, d.AREA, "mm^2"),
        ("second moment of area", inertia, d.MOMENT_OF_INERTIA_AREA, "mm^4"),
        ("section modulus", inertia / (h / 2), d.VOLUME, "mm^3"),
    ]


def _circ_section(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(diameter=i["diameter"])
    dia = i["diameter"]
    inner = i.get("inner_diameter", 0.0)
    if inner < 0 or inner >= dia:
        raise CalcError("'inner_diameter' must be at least 0 and smaller than 'diameter'")
    inertia = math.pi * (dia**4 - inner**4) / 64
    return [
        ("area", math.pi * (dia**2 - inner**2) / 4, d.AREA, "mm^2"),
        ("second moment of area", inertia, d.MOMENT_OF_INERTIA_AREA, "mm^4"),
        ("section modulus", inertia / (dia / 2), d.VOLUME, "mm^3"),
    ]


def _pipe_flow(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(flow=i["flow"], diameter=i["diameter"], density=i["density"], viscosity=i["viscosity"])
    area = math.pi * i["diameter"] ** 2 / 4
    v = i["flow"] / area
    re = i["density"] * v * i["diameter"] / i["viscosity"]
    return [
        ("velocity", v, d.SPEED, "m/s"),
        ("reynolds number", re, d.DIMENSIONLESS, ""),
    ]


def regime(reynolds: float) -> str:
    """Pipe-flow regime from the Reynolds number."""
    if reynolds < 2300:
        return "laminar"
    if reynolds < 4000:
        return "transitional"
    return "turbulent"


def _conduction(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(k=i["k"], area=i["area"], thickness=i["thickness"])
    q = i["k"] * i["area"] * i["delta_t"] / i["thickness"]
    return [("heat flow", q, d.POWER, "W")]


def _shaft_power(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    omega = i["speed"] * 2 * math.pi  # speed is a frequency in 1/s (rpm accepted)
    return [("power", i["torque"] * omega, d.POWER, "kW")]


def _gear_ratio(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(**i)
    ratio = i["driven_teeth"] / i["driver_teeth"]
    return [("gear ratio", ratio, d.DIMENSIONLESS, "")]


def _projectile(i: dict[str, float]) -> list[tuple[str, float, Dimension, str]]:
    _positive(speed=i["speed"])
    theta = i["angle"]
    if not 0 < theta < math.pi / 2:
        raise CalcError("'angle' must be between 0 and 90 degrees")
    g = 9.80665
    h0 = i.get("height", 0.0)
    if h0 < 0:
        raise CalcError("'height' must not be negative")
    vx, vy = i["speed"] * math.cos(theta), i["speed"] * math.sin(theta)
    t = (vy + math.sqrt(vy * vy + 2 * g * h0)) / g
    return [
        ("range", vx * t, d.LENGTH, "m"),
        ("flight time", t, d.TIME, "s"),
        ("max height", h0 + vy * vy / (2 * g), d.LENGTH, "m"),
    ]


def _p(name: str, dim: Dimension, help_: str, unit: str, optional: bool = False) -> Param:
    return Param(name, dim, help_, unit, optional)


CALCULATORS: dict[str, Calculator] = {}


def _register(c: Calculator) -> None:
    CALCULATORS[c.name] = c


_register(Calculator(
    "ohms-law", "Ohm's law", "Solve voltage, current, resistance and power from any two.",
    "V = I·R,  P = V·I",
    (_p("v", d.VOLTAGE, "voltage", "V", True), _p("i", d.CURRENT, "current", "A", True),
     _p("r", d.RESISTANCE, "resistance", "ohm", True), _p("p", d.POWER, "power", "W", True)),
    _ohms_law, "ohms-law v='12 V' r='470 ohm'",
))  # fmt: skip
_register(Calculator(
    "resistors-series", "Resistors in series", "Total resistance of resistors in series.",
    "R = R1 + R2 + …",
    tuple(_p(f"r{n}", d.RESISTANCE, f"resistor {n}", "ohm", n > 2) for n in range(1, 7)),
    _series_resistance, "resistors-series r1='1 kohm' r2='2.2 kohm'",
))  # fmt: skip
_register(Calculator(
    "resistors-parallel", "Resistors in parallel", "Total resistance of resistors in parallel.",
    "1/R = 1/R1 + 1/R2 + …",
    tuple(_p(f"r{n}", d.RESISTANCE, f"resistor {n}", "ohm", n > 2) for n in range(1, 7)),
    _parallel_resistance, "resistors-parallel r1='100 ohm' r2='100 ohm'",
))  # fmt: skip
_register(Calculator(
    "voltage-divider", "Voltage divider", "Output voltage and current of a two-resistor divider.",
    "Vout = Vin·R2 / (R1 + R2)",
    (_p("vin", d.VOLTAGE, "input voltage", "V"), _p("r1", d.RESISTANCE, "top resistor", "ohm"),
     _p("r2", d.RESISTANCE, "bottom resistor", "ohm")),
    _voltage_divider, "voltage-divider vin='5 V' r1='10 kohm' r2='10 kohm'",
))  # fmt: skip
_register(Calculator(
    "axial-stress", "Axial stress", "Normal stress in a bar, with optional safety factor against yield.",
    "σ = F / A,  n = σy / |σ|",
    (_p("force", d.FORCE, "axial force", "N"), _p("area", d.AREA, "cross-section area", "mm^2"),
     _p("yield_strength", d.PRESSURE, "yield strength", "MPa", True)),
    _stress, "axial-stress force='10 kN' area='200 mm^2' yield_strength='250 MPa'",
))  # fmt: skip
_register(Calculator(
    "beam-simply-supported", "Simply supported beam",
    "Max deflection, bending moment and reaction for a centre point load or a uniform load.",
    "δ = PL³/48EI (point),  δ = 5wL⁴/384EI (uniform)",
    (_p("length", d.LENGTH, "span", "m"), _p("e", d.PRESSURE, "Young's modulus", "GPa"),
     _p("inertia", d.MOMENT_OF_INERTIA_AREA, "second moment of area", "mm^4"),
     _p("load", d.FORCE, "centre point load", "N", True),
     _p("udl", d.FORCE / d.LENGTH, "uniform load per length", "N/m", True)),
    _beam, "beam-simply-supported length='3 m' e='200 GPa' inertia='8.0e6 mm^4' load='5 kN'",
))  # fmt: skip
_register(Calculator(
    "beam-cantilever", "Cantilever beam", "Max deflection and bending moment for a tip load or uniform load.",
    "δ = PL³/3EI (tip),  δ = wL⁴/8EI (uniform)",
    (_p("length", d.LENGTH, "length", "m"), _p("e", d.PRESSURE, "Young's modulus", "GPa"),
     _p("inertia", d.MOMENT_OF_INERTIA_AREA, "second moment of area", "mm^4"),
     _p("load", d.FORCE, "tip load", "N", True),
     _p("udl", d.FORCE / d.LENGTH, "uniform load per length", "N/m", True)),
    _cantilever, "beam-cantilever length='1.5 m' e='70 GPa' inertia='4e5 mm^4' load='200 N'",
))  # fmt: skip
_register(Calculator(
    "section-rectangle", "Rectangular section", "Area, second moment of area and section modulus.",
    "I = bh³/12,  S = I/(h/2)",
    (_p("width", d.LENGTH, "width b", "mm"), _p("height", d.LENGTH, "height h (bending direction)", "mm")),
    _rect_section, "section-rectangle width='40 mm' height='60 mm'",
))  # fmt: skip
_register(Calculator(
    "section-circle", "Circular / tubular section", "Area, second moment of area and section modulus.",
    "I = π(D⁴ − d⁴)/64",
    (_p("diameter", d.LENGTH, "outer diameter", "mm"),
     _p("inner_diameter", d.LENGTH, "inner diameter (tube)", "mm", True)),
    _circ_section, "section-circle diameter='50 mm' inner_diameter='42 mm'",
))  # fmt: skip
_register(Calculator(
    "pipe-flow", "Pipe flow", "Mean velocity and Reynolds number in a full circular pipe.",
    "v = Q/A,  Re = ρvD/μ",
    (_p("flow", d.FLOW_RATE, "volumetric flow", "L/s"), _p("diameter", d.LENGTH, "inner diameter", "mm"),
     _p("density", d.DENSITY, "fluid density", "kg/m^3"), _p("viscosity", d.VISCOSITY, "dynamic viscosity", "Pa*s")),
    _pipe_flow, "pipe-flow flow='2 L/s' diameter='50 mm' density='998 kg/m^3' viscosity='0.001 Pa*s'",
))  # fmt: skip
_register(Calculator(
    "conduction", "Conductive heat transfer", "Steady heat flow through a flat wall.",
    "Q = k·A·ΔT / L",
    (_p("k", d.THERMAL_CONDUCTIVITY, "thermal conductivity", "W/m/K"), _p("area", d.AREA, "area", "m^2"),
     _p("delta_t", d.TEMPERATURE, "temperature difference", "K"), _p("thickness", d.LENGTH, "wall thickness", "mm")),
    _conduction, "conduction k='0.04 W/m/K' area='10 m^2' delta_t='20 K' thickness='100 mm'",
))  # fmt: skip
_register(Calculator(
    "shaft-power", "Shaft power", "Power from torque and rotational speed.",
    "P = T·ω",
    (_p("torque", d.TORQUE, "torque", "N*m"), _p("speed", d.FREQUENCY, "speed", "rpm")),
    _shaft_power, "shaft-power torque='50 N*m' speed='3000 rpm'",
))  # fmt: skip
_register(Calculator(
    "gear-ratio", "Gear ratio", "Ratio from driver and driven tooth counts.",
    "i = N_driven / N_driver",
    (_p("driver_teeth", d.DIMENSIONLESS, "driver teeth", ""), _p("driven_teeth", d.DIMENSIONLESS, "driven teeth", "")),
    _gear_ratio, "gear-ratio driver_teeth=18 driven_teeth=54",
))  # fmt: skip
_register(Calculator(
    "projectile", "Projectile motion", "Range, flight time and apex for a launch at an angle (no drag).",
    "R = vₓ·t,  t = (v_y + √(v_y² + 2gh₀)) / g",
    (_p("speed", d.SPEED, "launch speed", "m/s"), _p("angle", d.DIMENSIONLESS, "launch angle", "deg"),
     _p("height", d.LENGTH, "launch height", "m", True)),
    _projectile, "projectile speed='20 m/s' angle='45 deg'",
))  # fmt: skip


def get(name: str) -> Calculator:
    try:
        return CALCULATORS[name]
    except KeyError:
        close = [n for n in CALCULATORS if name in n or n in name]
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        raise CalcError(f"Unknown calculator '{name}'.{hint} Run `knvrt calc` to list them.") from None
