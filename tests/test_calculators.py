"""Every expected value below was worked out by hand from the textbook formula."""

import math
import shlex

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from knvrt.calculators import CALCULATORS, CalcError, get, regime


def run(name, **inputs):
    """Run a calculator and return {output name: SI value}."""
    return {o.name: o.quantity.si for o in get(name).run(inputs)}


def test_every_calculator_runs_its_own_example():
    assert len(CALCULATORS) == 14
    for name, calc in CALCULATORS.items():
        args = dict(a.split("=", 1) for a in shlex.split(calc.example.split(" ", 1)[1]))
        outputs = calc.run(args)
        assert outputs, name
        assert all(math.isfinite(o.value) for o in outputs), name


def test_ohms_law_from_v_and_r():
    r = run("ohms-law", v="12 V", r="470 ohm")
    assert r["current"] == pytest.approx(12 / 470)
    assert r["power"] == pytest.approx(144 / 470)


@pytest.mark.parametrize("given", [("v", "i"), ("v", "r"), ("v", "p"), ("i", "r"), ("i", "p"), ("r", "p")])
def test_ohms_law_every_pair_agrees(given):
    truth = {"v": 12.0, "i": 0.5, "r": 24.0, "p": 6.0}
    r = run("ohms-law", **{k: truth[k] for k in given})
    assert r["voltage"] == pytest.approx(12)
    assert r["current"] == pytest.approx(0.5)
    assert r["resistance"] == pytest.approx(24)
    assert r["power"] == pytest.approx(6)


def test_ohms_law_needs_exactly_two():
    with pytest.raises(CalcError, match="exactly two"):
        run("ohms-law", v=12)
    with pytest.raises(CalcError, match="exactly two"):
        run("ohms-law", v=12, i=1, r=12)


def test_resistors():
    assert run("resistors-series", r1="1 kohm", r2="2.2 kohm")["total resistance"] == pytest.approx(3200)
    par = run("resistors-parallel", r1=100, r2=100, r3=100)
    assert par["total resistance"] == pytest.approx(100 / 3)


def test_voltage_divider():
    r = run("voltage-divider", vin="5 V", r1="10 kohm", r2="10 kohm")
    assert r["output voltage"] == pytest.approx(2.5)
    assert r["current"] == pytest.approx(5 / 20_000)


def test_axial_stress_and_safety_factor():
    r = run("axial-stress", force="10 kN", area="200 mm^2", yield_strength="250 MPa")
    assert r["stress"] == pytest.approx(50e6)
    assert r["safety factor"] == pytest.approx(5)
    assert "safety factor" not in run("axial-stress", force="10 kN", area="200 mm^2")


def test_simply_supported_point_load():
    r = run("beam-simply-supported", length="3 m", e="200 GPa", inertia="8e6 mm^4", load="5 kN")
    assert r["max deflection"] == pytest.approx(5000 * 27 / (48 * 200e9 * 8e-6))  # PL^3 / 48EI
    assert r["max bending moment"] == pytest.approx(3750)  # PL/4
    assert r["support reaction"] == pytest.approx(2500)  # P/2


def test_simply_supported_udl():
    r = run("beam-simply-supported", length="2 m", e="200 GPa", inertia="8e6 mm^4", udl="1 kN/m")
    assert r["max deflection"] == pytest.approx(5 * 1000 * 16 / (384 * 200e9 * 8e-6))
    assert r["max bending moment"] == pytest.approx(500)  # wL^2/8
    assert r["support reaction"] == pytest.approx(1000)  # wL/2


def test_cantilever():
    tip = run("beam-cantilever", length="1.5 m", e="70 GPa", inertia="4e5 mm^4", load="200 N")
    assert tip["max deflection"] == pytest.approx(200 * 1.5**3 / (3 * 70e9 * 4e-7))
    assert tip["max bending moment"] == pytest.approx(300)
    udl = run("beam-cantilever", length="1.5 m", e="70 GPa", inertia="4e5 mm^4", udl="100 N/m")
    assert udl["max deflection"] == pytest.approx(100 * 1.5**4 / (8 * 70e9 * 4e-7))
    assert udl["max bending moment"] == pytest.approx(112.5)


@pytest.mark.parametrize("name", ["beam-simply-supported", "beam-cantilever"])
def test_beam_needs_exactly_one_load(name):
    base = {"length": "1 m", "e": "200 GPa", "inertia": "1e6 mm^4"}
    with pytest.raises(CalcError, match="exactly one"):
        get(name).run(base)
    with pytest.raises(CalcError, match="exactly one"):
        get(name).run({**base, "load": "1 kN", "udl": "1 kN/m"})


def test_sections():
    rect = run("section-rectangle", width="40 mm", height="60 mm")
    assert rect["area"] == pytest.approx(2.4e-3)
    assert rect["second moment of area"] == pytest.approx(40 * 60**3 / 12 * 1e-12)
    assert rect["section modulus"] == pytest.approx(40 * 60**2 / 6 * 1e-9)
    solid = run("section-circle", diameter="50 mm")
    assert solid["area"] == pytest.approx(math.pi / 4 * 0.05**2)
    tube = run("section-circle", diameter="50 mm", inner_diameter="42 mm")
    assert tube["second moment of area"] == pytest.approx(math.pi / 64 * (50**4 - 42**4) * 1e-12)
    with pytest.raises(CalcError, match="inner_diameter"):
        run("section-circle", diameter="50 mm", inner_diameter="60 mm")


def test_pipe_flow_and_regime():
    r = run("pipe-flow", flow="2 L/s", diameter="50 mm", density="998 kg/m^3", viscosity="0.001 Pa*s")
    area = math.pi / 4 * 0.05**2
    assert r["velocity"] == pytest.approx(2e-3 / area)
    assert r["reynolds number"] == pytest.approx(998 * (2e-3 / area) * 0.05 / 0.001)
    assert (regime(1000), regime(3000), regime(50_000)) == ("laminar", "transitional", "turbulent")


def test_conduction_shaft_gear():
    assert run("conduction", k="0.04 W/m/K", area="10 m^2", delta_t="20 K", thickness="100 mm")[
        "heat flow"
    ] == pytest.approx(80)
    assert run("shaft-power", torque="50 N*m", speed="3000 rpm")["power"] == pytest.approx(
        50 * 3000 * 2 * math.pi / 60
    )
    assert run("gear-ratio", driver_teeth=18, driven_teeth=54)["gear ratio"] == pytest.approx(3)


def test_projectile():
    v, a = 20.0, 45.0
    g = 9.80665
    r = run("projectile", speed=v, angle=a)
    assert r["range"] == pytest.approx(v**2 * math.sin(2 * math.radians(a)) / g)
    assert r["flight time"] == pytest.approx(2 * v * math.sin(math.radians(a)) / g)
    assert r["max height"] == pytest.approx((v * math.sin(math.radians(a))) ** 2 / (2 * g))
    # launching from a height makes the flight longer
    assert run("projectile", speed=v, angle=a, height=10)["flight time"] > r["flight time"]
    with pytest.raises(CalcError, match="between 0 and 90"):
        run("projectile", speed=v, angle=120)


def test_accepts_any_compatible_unit():
    assert run("axial-stress", force="2248.09 lbf", area="0.31 in^2")["stress"] == pytest.approx(
        50e6, rel=1e-3
    )  # 2248.09 lbf is 10 kN and 0.31 in^2 is 200 mm^2


def test_input_errors_are_clear():
    with pytest.raises(CalcError, match="Missing input"):
        run("resistors-series", r1=100)
    with pytest.raises(CalcError, match="'force'"):
        run("axial-stress", force="10 m", area="1 mm^2")  # wrong dimension names the field
    with pytest.raises(CalcError, match="finite"):
        run("gear-ratio", driver_teeth=math.nan, driven_teeth=10)
    with pytest.raises(CalcError, match=r"Unknown calculator 'ohm'.*ohms-law"):
        get("ohm")
    with pytest.raises(CalcError, match="greater than 0"):
        run("section-rectangle", width=0, height=10)


@given(st.floats(1, 1e6), st.floats(1, 1e6))
def test_parallel_is_less_than_smallest(a, b):
    total = run("resistors-parallel", r1=a, r2=b)["total resistance"]
    assert total < min(a, b)
    assert run("resistors-series", r1=a, r2=b)["total resistance"] == pytest.approx(a + b)


@given(st.floats(1, 1e4), st.floats(1, 1e4), st.floats(0.1, 100))
def test_divider_output_never_exceeds_input(r1, r2, vin):
    assert 0 < run("voltage-divider", vin=vin, r1=r1, r2=r2)["output voltage"] < vin


@given(st.floats(1, 100), st.floats(1, 80))
def test_projectile_45_is_longest_range(speed, angle):
    assume(abs(angle - 45) > 1e-3)
    best = run("projectile", speed=speed, angle=45)["range"]
    assert run("projectile", speed=speed, angle=angle)["range"] <= best * (1 + 1e-12)
