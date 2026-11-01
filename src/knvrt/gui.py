"""Desktop app (PySide6). Install with ``pip install 'knvrt[gui]'`` and run ``knvrt gui``.

All maths lives in :mod:`knvrt.units` and :mod:`knvrt.calculators`; this module
only wires widgets to it.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .calculators import CALCULATORS, CalcError, regime
from .units import UnitError, convert, format_number, list_units


class ConverterTab(QWidget):
    """Value + two unit boxes. The result updates as you type."""

    def __init__(self) -> None:
        super().__init__()
        self.value = QLineEdit("1")
        self.value.setPlaceholderText("Value")
        self.category = QComboBox()
        self.units = list_units()
        convertible = {k: v for k, v in self.units.items() if k != "dimensionless"}
        self.category.addItems(sorted(convertible))
        self.from_unit = QComboBox()
        self.to_unit = QComboBox()
        for box in (self.from_unit, self.to_unit):
            box.setEditable(True)
        self.swap = QPushButton("⇄")
        self.swap.setToolTip("Swap units")
        self.result = QLabel("")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result.setStyleSheet("font-size: 20px; padding: 8px;")
        self.error = QLabel("")
        self.error.setStyleSheet("color: #b00020;")

        form = QFormLayout()
        form.addRow("Quantity", self.category)
        form.addRow("Value", self.value)
        row = QHBoxLayout()
        row.addWidget(self.from_unit)
        row.addWidget(self.swap)
        row.addWidget(self.to_unit)
        form.addRow("From → To", row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.result)
        layout.addWidget(self.error)
        layout.addStretch(1)

        self.category.currentTextChanged.connect(self._fill_units)
        self.value.textChanged.connect(self.update_result)
        self.from_unit.currentTextChanged.connect(self.update_result)
        self.to_unit.currentTextChanged.connect(self.update_result)
        self.swap.clicked.connect(self._swap)
        self._fill_units(self.category.currentText())

    def _fill_units(self, category: str) -> None:
        names = [n.rstrip("*") for n in self.units.get(category, [])]
        for box in (self.from_unit, self.to_unit):
            box.blockSignals(True)
            box.clear()
            box.addItems(names)
            box.blockSignals(False)
        if len(names) > 1:
            self.to_unit.setCurrentIndex(1)
        self.update_result()

    def _swap(self) -> None:
        a, b = self.from_unit.currentText(), self.to_unit.currentText()
        self.from_unit.setCurrentText(b)
        self.to_unit.setCurrentText(a)

    def update_result(self) -> None:
        self.error.clear()
        text = self.value.text().strip()
        if not text:
            self.result.clear()
            return
        try:
            number = float(text)
            out = convert(number, self.from_unit.currentText(), self.to_unit.currentText())
        except ValueError as e:  # UnitError is a ValueError
            self.result.clear()
            self.error.setText(str(e) if isinstance(e, UnitError) else f"'{text}' is not a number")
            return
        self.result.setText(
            f"{format_number(number)} {self.from_unit.currentText()} = "
            f"{format_number(out)} {self.to_unit.currentText()}"
        )


class CalculatorTab(QWidget):
    """A form generated from the selected calculator's declared inputs."""

    def __init__(self) -> None:
        super().__init__()
        self.picker = QComboBox()
        for name, calc in CALCULATORS.items():
            self.picker.addItem(calc.title, name)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.form = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        self.button = QPushButton("Calculate")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Result", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #b00020;")
        self.error.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.picker)
        layout.addWidget(self.info)
        layout.addLayout(self.form)
        layout.addWidget(self.button)
        layout.addWidget(self.error)
        layout.addWidget(self.table)

        self.picker.currentIndexChanged.connect(self._rebuild)
        self.button.clicked.connect(self.calculate)
        self._rebuild()

    @property
    def current(self) -> str:
        return str(self.picker.currentData())

    def _rebuild(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields.clear()
        self.table.setRowCount(0)
        self.error.clear()
        calc = CALCULATORS[self.current]
        self.info.setText(f"{calc.summary}\n{calc.formula}")
        for p in calc.params:
            edit = QLineEdit()
            unit = f" ({p.default_unit})" if p.default_unit else ""
            edit.setPlaceholderText(f"{p.help}{unit}" + (" · optional" if p.optional else ""))
            edit.returnPressed.connect(self.calculate)
            self.fields[p.name] = edit
            label = QLabel(p.name)
            self.form.addRow(label, edit)
            label.show()  # rows added after the window is shown start hidden
            edit.show()

    def calculate(self) -> None:
        self.error.clear()
        inputs = {k: e.text().strip() for k, e in self.fields.items() if e.text().strip()}
        try:
            outputs = CALCULATORS[self.current].run(inputs)
        except (CalcError, UnitError) as e:
            self.table.setRowCount(0)
            self.error.setText(str(e))
            return
        self.table.setRowCount(len(outputs))
        for row, o in enumerate(outputs):
            unit = f" {o.unit}" if o.unit else ""
            extra = f" ({regime(o.value)})" if o.name == "reynolds number" else ""
            self.table.setItem(row, 0, QTableWidgetItem(o.name))
            self.table.setItem(row, 1, QTableWidgetItem(f"{format_number(o.value)}{unit}{extra}"))
        self.table.resizeColumnToContents(0)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"knvrt {__version__}")
        self.converter = ConverterTab()
        self.calculators = CalculatorTab()
        tabs = QTabWidget()
        tabs.addTab(self.converter, "Convert")
        tabs.addTab(self.calculators, "Calculate")
        self.setCentralWidget(tabs)
        self.resize(560, 520)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return int(app.exec())
