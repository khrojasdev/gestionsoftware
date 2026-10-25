"""Lectura y escritura XLSX/CSV sin modificar archivos de insumos.

El lector usa únicamente la especificación OOXML mínima (ZIP + XML), por lo
que el backend puede validar archivos aun cuando ``openpyxl`` no esté
instalado en el entorno de ejecución. Se aceptan también CSV UTF-8 por hoja.
"""

from __future__ import annotations

import csv
import zipfile
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .models import CANONICAL_COLUMNS, CANONICAL_SHEETS, SUPPLEMENTAL_SHEETS

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS}
EXCEL_EPOCH = date(1899, 12, 30)


def excel_serial_to_date(value: float) -> date:
    """Convierte el serial de Excel, incluido el ajuste del año bisiesto de 1900."""

    return EXCEL_EPOCH + timedelta(days=int(value))


def parse_cell_date(value: Any) -> date | None:
    """Normaliza fechas ISO, dd-mm-aaaa, datetime y serial Excel."""

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    try:
        return excel_serial_to_date(float(text))
    except (TypeError, ValueError, OverflowError):
        return None


def _column_number(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    number = 0
    for character in letters.upper():
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(item.itertext()) for item in root.findall("m:si", NS)]


def _workbook_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
    result: list[tuple[str, str]] = []
    sheets_node = workbook.find("m:sheets", NS)
    for sheet in sheets_node if sheets_node is not None else []:
        relation_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = targets[relation_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        result.append((sheet.attrib["name"], target))
    return result


def read_xlsx(path: Path) -> dict[str, list[list[Any]]]:
    """Lee un XLSX como ``hoja -> matriz`` conservando filas y columnas vacías."""

    with zipfile.ZipFile(path, "r") as archive:
        strings = _shared_strings(archive)
        sheets: dict[str, list[list[Any]]] = {}
        for name, target in _workbook_targets(archive):
            root = ET.fromstring(archive.read(target))
            parsed: dict[int, dict[int, Any]] = {}
            max_column = 0
            for row in root.findall(".//m:sheetData/m:row", NS):
                row_number = int(row.attrib["r"])
                parsed[row_number] = {}
                for cell in row.findall("m:c", NS):
                    reference = cell.attrib.get("r", "A1")
                    column_number = _column_number(reference)
                    value_node = cell.find("m:v", NS)
                    inline_node = cell.find("m:is", NS)
                    value: Any = ""
                    if inline_node is not None:
                        value = "".join(inline_node.itertext())
                    elif value_node is not None:
                        value = value_node.text or ""
                        if cell.attrib.get("t") == "s":
                            value = strings[int(value)]
                        elif cell.attrib.get("t") == "b":
                            value = value == "1"
                    parsed[row_number][column_number] = value
                    max_column = max(max_column, column_number)
            rows: list[list[Any]] = []
            for row_number in range(1, max(parsed, default=0) + 1):
                row = parsed.get(row_number, {})
                rows.append([row.get(column, "") for column in range(1, max_column + 1)])
            sheets[name] = rows
        return sheets


def read_csv_bundle(path: Path) -> dict[str, list[list[str]]]:
    """Lee un archivo CSV o un directorio con un CSV por hoja.

    Los nombres se comparan por ``stem`` y se acepta ``.csv`` en cualquier
    combinación de mayúsculas. Un CSV individual se considera la hoja Gantt.
    """

    files = [path] if path.is_file() else sorted(path.glob("*.csv"))
    if not files:
        raise ValueError(f"No se encontraron CSV en {path}")
    result: dict[str, list[list[str]]] = {}
    for file_path in files:
        name = file_path.stem
        if len(files) == 1 and name.lower() not in {sheet.lower() for sheet in CANONICAL_SHEETS}:
            name = "Gantt"
        canonical_name = next(
            (sheet for sheet in CANONICAL_SHEETS if sheet.lower() == name.lower()), name
        )
        with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
            result[canonical_name] = [row for row in csv.reader(stream)]
    return result


def rows_to_sheets(raw: dict[str, list[list[Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Transforma una matriz con encabezados a filas con nombres canónicos."""

    result: dict[str, list[dict[str, Any]]] = {}
    for sheet, rows in raw.items():
        if not rows:
            result[sheet] = []
            continue
        headers = [str(value).strip() for value in rows[0]]
        expected = CANONICAL_COLUMNS.get(sheet, tuple(headers))
        indexes = {header: index for index, header in enumerate(headers) if header}
        normalized: list[dict[str, Any]] = []
        for values in rows[1:]:
            row = {
                column: values[indexes[column]] if column in indexes and indexes[column] < len(values) else ""
                for column in expected
            }
            if any(str(value).strip() for value in row.values()):
                normalized.append(row)
        result[sheet] = normalized
    return result


def write_csv_bundle(sheets: dict[str, list[dict[str, Any]]], directory: Path) -> None:
    """Escribe una representación CSV separada por hoja."""

    directory.mkdir(parents=True, exist_ok=True)
    for sheet in CANONICAL_SHEETS:
        path = directory / f"{sheet}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CANONICAL_COLUMNS[sheet])
            writer.writeheader()
            writer.writerows(sheets.get(sheet, []))
    for sheet in SUPPLEMENTAL_SHEETS:
        rows = sheets.get(sheet, [])
        if not rows:
            continue
        headers = list(rows[0])
        with (directory / f"{sheet}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)


def _xml_value(value: Any) -> tuple[str, str | None]:
    if value is None:
        return "", None
    if isinstance(value, date | datetime):
        return value.isoformat(), None
    if isinstance(value, bool):
        return "1" if value else "0", "b"
    return str(value), "inlineStr"


def write_xlsx(sheets: dict[str, list[dict[str, Any]]], path: Path) -> None:
    """Escribe un XLSX pequeño y portable con las hojas canónicas."""

    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_names = list(CANONICAL_SHEETS) + [
        sheet for sheet in SUPPLEMENTAL_SHEETS if sheet in sheets
    ]
    shared_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    for index in range(1, len(sheet_names) + 1):
        shared_parts.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    shared_parts.append("</Types>")
    workbook = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}"><sheets>',
    ]
    relationships = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Relationships xmlns="{PACKAGE_REL_NS}">',
    ]
    sheet_xml: dict[str, str] = {}
    for index, sheet in enumerate(sheet_names, 1):
        workbook.append(f'<sheet name="{sheet}" sheetId="{index}" r:id="rId{index}"/>')
        relationships.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        rows: list[str] = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', f'<worksheet xmlns="{MAIN_NS}"><sheetData>']
        rows_for_sheet = sheets.get(sheet, [])
        headers = list(CANONICAL_COLUMNS[sheet]) if sheet in CANONICAL_COLUMNS else list(rows_for_sheet[0])
        all_rows: list[Iterable[Any]] = [headers]
        all_rows.extend(
            [row.get(column, "") for column in headers] for row in rows_for_sheet
        )
        for row_number, values in enumerate(all_rows, 1):
            cells: list[str] = []
            for column_number, value in enumerate(values, 1):
                text, value_type = _xml_value(value)
                if text == "":
                    continue
                reference = _cell_reference(column_number, row_number)
                escaped = _escape_xml(text)
                if value_type == "inlineStr":
                    cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{escaped}</t></is></c>')
                else:
                    cells.append(f'<c r="{reference}" t="{value_type or "n"}"><v>{escaped}</v></c>')
            rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
        rows.append("</sheetData></worksheet>")
        sheet_xml[sheet] = "".join(rows)
    workbook.append("</sheets></workbook>")
    relationships.append("</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(shared_parts))
        archive.writestr("xl/workbook.xml", "".join(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(relationships))
        archive.writestr(
            "_rels/.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        for index, sheet in enumerate(sheet_names, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml[sheet])


def _cell_reference(column: int, row: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
