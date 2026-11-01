import os

import pytest

pytest.importorskip("PySide6", reason="install knvrt[gui] to run the GUI test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from knvrt.gui import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_converter_updates_live_and_reports_errors(app):
    w = MainWindow()
    c = w.converter
    c.category.setCurrentText("length")
    c.from_unit.setCurrentText("km")
    c.to_unit.setCurrentText("mi")
    c.value.setText("5")
    assert c.result.text() == "5 km = 3.10686 mi"
    c.swap.click()
    assert (c.from_unit.currentText(), c.to_unit.currentText()) == ("mi", "km")
    c.to_unit.setCurrentText("kg")
    assert "Cannot convert" in c.error.text()
    c.value.setText("abc")
    assert "not a number" in c.error.text()


def test_calculator_form_is_built_from_the_registry(app):
    w = MainWindow()
    t = w.calculators
    t.picker.setCurrentIndex(t.picker.findData("ohms-law"))
    assert set(t.fields) == {"v", "i", "r", "p"}
    t.fields["v"].setText("12 V")
    t.fields["r"].setText("470 ohm")
    t.calculate()
    rows = {t.table.item(r, 0).text(): t.table.item(r, 1).text() for r in range(t.table.rowCount())}
    assert rows["current"].startswith("0.0255319")
    t.fields["p"].setText("1 W")
    t.calculate()
    assert "exactly two" in t.error.text()
    assert t.table.rowCount() == 0


def test_calculator_fields_are_visible_after_switching(app):
    w = MainWindow()
    w.show()
    t = w.calculators
    w.centralWidget().setCurrentIndex(1)
    t.picker.setCurrentIndex(t.picker.findData("pipe-flow"))
    assert t.fields and all(f.isVisible() for f in t.fields.values())
    assert all(t.form.labelForField(f).isVisible() for f in t.fields.values())
