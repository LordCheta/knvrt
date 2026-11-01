import json
import subprocess
import sys

import pytest

from knvrt import __version__
from knvrt.cli import main


def test_convert_forms(capsys):
    for argv in (["convert", "5", "km", "mi"], ["convert", "5 km", "mi"], ["convert", "5km", "mi"]):
        assert main(argv) == 0
        assert capsys.readouterr().out.strip() == "5 km = 3.10686 mi"


def test_convert_negative_and_temperature(capsys):
    assert main(["convert", "-40", "degC", "F"]) == 0
    assert capsys.readouterr().out.strip() == "-40 degC = -40 F"


def test_convert_json_and_digits(capsys):
    assert main(["convert", "1", "mi", "km", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == pytest.approx(1.609344)
    assert main(["convert", "1", "mi", "km", "--digits", "3"]) == 0
    assert capsys.readouterr().out.strip() == "1 mi = 1.61 km"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["convert", "5", "kg", "m"], "Cannot convert mass"),
        (["convert", "5", "parsecs", "m"], "Unknown unit"),
        (["convert", "abc", "m", "ft"], "Cannot read a number"),
        (["convert", "5"], "Usage"),
        (["convert", "5 km"], "Usage"),
        (["calc", "nope"], "Unknown calculator"),
        (["calc", "ohms-law", "v12"], "key=value"),
        (["calc", "ohms-law", "v=12"], "exactly two"),
    ],
)
def test_user_errors_exit_2_without_traceback(argv, message, capsys):
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert message in err
    assert "Traceback" not in err


def test_units_listing(capsys):
    assert main(["units"]) == 0
    assert "pressure" in capsys.readouterr().out
    assert main(["units", "--json"]) == 0
    assert "length" in json.loads(capsys.readouterr().out)


def test_calc_list_help_and_run(capsys):
    assert main(["calc"]) == 0
    assert "ohms-law" in capsys.readouterr().out
    assert main(["calc", "pipe-flow", "--help"]) == 0
    out = capsys.readouterr().out
    assert "Formula:" in out
    assert "viscosity" in out
    assert main(["calc", "ohms-law", "v=12 V", "r=470 ohm"]) == 0
    assert "current    = 0.0255319 A" in capsys.readouterr().out


def test_calc_json_and_dashes_in_keys(capsys):
    argv = ["calc", "pipe-flow", "flow=2 L/s", "diameter=50 mm", "density=998", "viscosity=0.001", "--json"]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["velocity"]["unit"] == "m/s"
    assert out["reynolds number"]["value"] == pytest.approx(50828, abs=1)
    assert main(["calc", "section-circle", "diameter=50", "inner-diameter=42", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["area"]["value"] == pytest.approx(578.05, abs=0.01)


def test_regime_is_shown(capsys):
    assert main(["calc", "pipe-flow", "flow=2 L/s", "diameter=50 mm", "density=998", "viscosity=0.001"]) == 0
    assert "(turbulent)" in capsys.readouterr().out


def test_bad_digits_is_rejected():
    with pytest.raises(SystemExit) as e:
        main(["convert", "1", "m", "ft", "--digits", "0"])
    assert e.value.code == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_python_dash_m_entry_point():
    r = subprocess.run(
        [sys.executable, "-m", "knvrt", "convert", "1", "kWh", "MJ"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == "1 kWh = 3.6 MJ"
