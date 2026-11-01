"""Physical dimensions as exponent vectors over the SI base quantities."""

from __future__ import annotations

from dataclasses import dataclass

_NAMES = ("L", "M", "T", "I", "Θ")  # length, mass, time, current, temperature


@dataclass(frozen=True, slots=True)
class Dimension:
    """Exponents of (length, mass, time, current, temperature)."""

    length: int = 0
    mass: int = 0
    time: int = 0
    current: int = 0
    temperature: int = 0

    def _tuple(self) -> tuple[int, int, int, int, int]:
        return (self.length, self.mass, self.time, self.current, self.temperature)

    def __mul__(self, other: Dimension) -> Dimension:
        return Dimension(*(a + b for a, b in zip(self._tuple(), other._tuple(), strict=True)))

    def __truediv__(self, other: Dimension) -> Dimension:
        return Dimension(*(a - b for a, b in zip(self._tuple(), other._tuple(), strict=True)))

    def __pow__(self, n: int) -> Dimension:
        return Dimension(*(a * n for a in self._tuple()))

    @property
    def is_dimensionless(self) -> bool:
        return not any(self._tuple())

    def __str__(self) -> str:
        if self.is_dimensionless:
            return "dimensionless"
        parts = []
        for name, exp in zip(_NAMES, self._tuple(), strict=True):
            if exp == 1:
                parts.append(name)
            elif exp:
                parts.append(f"{name}^{exp}")
        return "·".join(parts)


DIMENSIONLESS = Dimension()
LENGTH = Dimension(length=1)
MASS = Dimension(mass=1)
TIME = Dimension(time=1)
CURRENT = Dimension(current=1)
TEMPERATURE = Dimension(temperature=1)

AREA = LENGTH**2
VOLUME = LENGTH**3
SPEED = LENGTH / TIME
ACCELERATION = LENGTH / TIME**2
FORCE = MASS * ACCELERATION
PRESSURE = FORCE / AREA
ENERGY = FORCE * LENGTH
POWER = ENERGY / TIME
FREQUENCY = DIMENSIONLESS / TIME
CHARGE = CURRENT * TIME
VOLTAGE = POWER / CURRENT
RESISTANCE = VOLTAGE / CURRENT
DENSITY = MASS / VOLUME
VISCOSITY = PRESSURE * TIME  # dynamic viscosity, Pa·s
FLOW_RATE = VOLUME / TIME
MOMENT_OF_INERTIA_AREA = LENGTH**4
THERMAL_CONDUCTIVITY = POWER / (LENGTH * TEMPERATURE)
TORQUE = ENERGY  # same dimension as energy (N·m)

NAMED: dict[str, Dimension] = {
    "length": LENGTH,
    "mass": MASS,
    "time": TIME,
    "temperature": TEMPERATURE,
    "current": CURRENT,
    "area": AREA,
    "volume": VOLUME,
    "speed": SPEED,
    "acceleration": ACCELERATION,
    "force": FORCE,
    "pressure": PRESSURE,
    "energy": ENERGY,
    "power": POWER,
    "frequency": FREQUENCY,
    "voltage": VOLTAGE,
    "resistance": RESISTANCE,
    "charge": CHARGE,
    "density": DENSITY,
    "flow rate": FLOW_RATE,
}


def describe(dim: Dimension) -> str:
    """Friendly name for a dimension when we have one, otherwise its exponents."""
    for name, d in NAMED.items():
        if d == dim:
            return name
    return str(dim)
