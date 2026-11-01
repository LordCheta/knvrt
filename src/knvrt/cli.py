"""Command-line interface: ``knvrt convert``, ``knvrt units``, ``knvrt calc``, ``knvrt gui``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .calculators import CALCULATORS, CalcError, Calculator, get, regime
from .units import UnitError, convert, format_number, list_units, split_number_unit


def _cmd_convert(args: argparse.Namespace) -> int:
    words: list[str] = args.words
    # Accept "5 km mi", "5km mi" (no space) and "'5 km' mi".
    if len(words) == 2:
        number, from_unit = split_number_unit(words[0])
        to_unit = words[1]
    elif len(words) == 3:
        number, from_unit = split_number_unit(words[0])
        if from_unit:
            raise UnitError("Usage: knvrt convert <value> <from-unit> <to-unit>   e.g. knvrt convert 5 km mi")
        from_unit, to_unit = words[1], words[2]
    else:
        raise UnitError("Usage: knvrt convert <value> <from-unit> <to-unit>   e.g. knvrt convert 5 km mi")
    value = number
    if not from_unit:
        raise UnitError("Missing source unit")
    result = convert(value, from_unit, to_unit)
    if args.json:
        print(json.dumps({"value": value, "from": from_unit, "to": to_unit, "result": result}))
    else:
        shown, converted = format_number(value, args.digits), format_number(result, args.digits)
        print(f"{shown} {from_unit} = {converted} {to_unit}")
    return 0


def _cmd_units(args: argparse.Namespace) -> int:
    groups = list_units()
    if args.json:
        print(json.dumps(groups, indent=2, ensure_ascii=False))
        return 0
    print("Units (* = accepts SI prefixes such as k, M, m, µ):\n")
    for category, names in groups.items():
        print(f"  {category:<15} {' '.join(names)}")
    print("\nCombine with * / ^, e.g. km/h, N*m, kg*m^2/s^2.")
    return 0


def _print_calc_list() -> None:
    width = max(len(n) for n in CALCULATORS)
    for name, c in CALCULATORS.items():
        print(f"  {name:<{width}}  {c.summary}")
    print("\nDetails: knvrt calc <name> --help    Run: knvrt calc <name> key='value unit' ...")


def _describe(c: Calculator) -> str:
    lines = [f"{c.title}: {c.summary}", f"Formula: {c.formula}", "", "Inputs:"]
    for p in c.params:
        opt = " (optional)" if p.optional else ""
        unit = f" [default unit: {p.default_unit}]" if p.default_unit else ""
        lines.append(f"  {p.name:<16} {p.help}{unit}{opt}")
    if c.example:
        lines += ["", f"Example: knvrt calc {c.example}"]
    return "\n".join(lines)


def _cmd_calc(args: argparse.Namespace) -> int:
    if not args.name:
        _print_calc_list()
        return 0
    calc = get(args.name)
    if args.help_calc:
        print(_describe(calc))
        return 0
    inputs: dict[str, str] = {}
    for item in args.inputs:
        if "=" not in item:
            raise CalcError(f"Expected key=value, got '{item}'. Example: {calc.example}")
        key, _, value = item.partition("=")
        inputs[key.strip().replace("-", "_")] = value.strip()
    outputs = calc.run(inputs)
    if args.json:
        print(
            json.dumps(
                {o.name: {"value": o.value, "unit": o.unit, "si": o.quantity.si} for o in outputs},
                indent=2,
            )
        )
        return 0
    width = max(len(o.name) for o in outputs)
    for o in outputs:
        extra = ""
        if o.name == "reynolds number":
            extra = f"  ({regime(o.value)})"
        unit = f" {o.unit}" if o.unit else ""
        print(f"{o.name:<{width}} = {format_number(o.value, args.digits)}{unit}{extra}")
    return 0


def _cmd_gui(_: argparse.Namespace) -> int:
    try:
        from .gui import run
    except ImportError:
        print(
            "The GUI needs PySide6. Install it with:  pip install 'knvrt[gui]'",
            file=sys.stderr,
        )
        return 2
    return run()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="knvrt",
        description="Unit conversions and everyday engineering calculators.",
        epilog="Examples:  knvrt convert 5 km mi   |   knvrt calc ohms-law v='12 V' r='470 ohm'",
    )
    p.add_argument("--version", action="version", version=f"knvrt {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.add_argument("--digits", type=int, default=6, help="significant digits (default 6)")

    c = sub.add_parser("convert", help="convert a value between units", description="Convert between units.")
    c.add_argument("words", nargs="+", metavar="VALUE UNIT TO_UNIT", help="e.g. 5 km mi  or  '5 km' mi")
    common(c)
    c.set_defaults(func=_cmd_convert)

    u = sub.add_parser("units", help="list supported units")
    u.add_argument("--json", action="store_true")
    u.set_defaults(func=_cmd_units)

    k = sub.add_parser("calc", help="engineering calculators", add_help=False)
    k.add_argument("name", nargs="?", help="calculator name (omit to list them)")
    k.add_argument("inputs", nargs="*", metavar="key=value")
    k.add_argument("-h", "--help", dest="help_calc", action="store_true")
    common(k)
    k.set_defaults(func=_cmd_calc)

    g = sub.add_parser("gui", help="open the desktop app (needs PySide6)")
    g.set_defaults(func=_cmd_gui)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "calc" and args.name is None and args.help_calc:
        _print_calc_list()
        return 0
    if getattr(args, "digits", 6) < 1 or getattr(args, "digits", 6) > 15:
        parser.error("--digits must be between 1 and 15")
    try:
        return int(args.func(args))
    except (UnitError, CalcError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
