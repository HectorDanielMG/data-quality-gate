"""Perfilado y validación de CSV, sin dependencias externas."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    code: str
    severity: str
    title: str
    message: str
    affected_rows: int = 0
    column: str | None = None
    example_lines: list[int] = dc_field(default_factory=list)


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    rows: int
    missing: int
    distinct: int
    completeness: float
    samples: list[str] = dc_field(default_factory=list)
    minimum: str | None = None
    maximum: str | None = None
    average: float | None = None


@dataclass
class Result:
    source: str
    contract: str
    generated_at: str
    row_count: int
    column_count: int
    score: float
    passed: bool
    columns: list[ColumnProfile]
    findings: list[Finding]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _number(value: str) -> Decimal | None:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _infer(value: str) -> str:
    text = value.strip()
    lowered = text.lower()
    if lowered in {"true", "false", "sí", "si", "no"}:
        return "booleano"
    if re.fullmatch(r"[+-]?\d+", text):
        return "entero"
    if _number(text) is not None:
        return "numérico"
    try:
        date.fromisoformat(text)
        return "fecha"
    except ValueError:
        return "texto"


def _profile(name: str, values: list[Any]) -> ColumnProfile:
    clean = [str(value).strip() for value in values if not _blank(value)]
    kinds = {_infer(value) for value in clean}
    inferred = "sin datos" if not kinds else ("numérico" if kinds <= {"entero", "numérico"} else next(iter(kinds)) if len(kinds) == 1 else "mixto")
    counts = Counter(clean)
    numbers = [_number(value) for value in clean]
    numeric = [value for value in numbers if value is not None]
    minimum = maximum = None
    average = None
    if clean and len(numeric) == len(clean):
        minimum, maximum = str(min(numeric).normalize()), str(max(numeric).normalize())
        average = round(float(sum(numeric) / len(numeric)), 4)
    missing = len(values) - len(clean)
    return ColumnProfile(name, inferred, len(values), missing, len(counts), round(100 * (len(clean) / len(values) if values else 1), 1), list(dict.fromkeys(clean))[:4], minimum, maximum, average)


def _type_ok(value: str, expected: str) -> bool:
    kind, text = expected.lower(), value.strip()
    if kind in {"string", "cadena", "texto"}:
        return True
    if kind in {"integer", "entero"}:
        return re.fullmatch(r"[+-]?\d+", text) is not None
    if kind in {"number", "numeric", "decimal", "numero", "numérico"}:
        return _number(text) is not None
    if kind in {"boolean", "booleano"}:
        return text.lower() in {"true", "false", "1", "0", "sí", "si", "no"}
    if kind in {"date", "fecha"}:
        try:
            date.fromisoformat(text)
            return True
        except ValueError:
            return False
    if kind in {"datetime", "fecha-hora"}:
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    raise ValueError(f"Tipo no compatible en el contrato: {expected}")


def _read_contract(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"El contrato JSON no es válido: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("columns"), dict) or not data["columns"]:
        raise ValueError("El contrato debe ser un objeto JSON con al menos una columna declarada.")
    for name, rules in data["columns"].items():
        if not isinstance(rules, dict):
            raise ValueError(f"Las reglas de '{name}' deben ser un objeto JSON.")
        if "regex" in rules:
            try:
                re.compile(str(rules["regex"]))
            except re.error as exc:
                raise ValueError(f"Expresión regular inválida en '{name}': {exc}") from exc
    return data


def analyze(csv_path: Path, contract_path: Path) -> Result:
    contract = _read_contract(contract_path)
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames
            if not headers:
                raise ValueError("El CSV está vacío o no tiene encabezados.")
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError("El archivo CSV debe usar codificación UTF-8.") from exc
    except csv.Error as exc:
        raise ValueError(f"No se pudo leer el CSV: {exc}") from exc

    findings: list[Finding] = []
    def add(code: str, severity: str, title: str, message: str, count: int = 0, column: str | None = None, lines: list[int] | None = None) -> None:
        findings.append(Finding(code, severity, title, message, count, column, (lines or [])[:5]))

    repeated_headers = [name for name, count in Counter(headers).items() if count > 1]
    if repeated_headers:
        add("DUPLICATE_HEADER", "error", "Encabezados repetidos", "Nombres duplicados: " + ", ".join(repeated_headers), len(repeated_headers))
    rules_by_column = contract["columns"]
    missing_columns = [name for name in rules_by_column if name not in headers]
    extra_columns = [name for name in headers if name not in rules_by_column]
    if missing_columns:
        add("MISSING_COLUMN", "error", "Faltan columnas", "Columnas requeridas por el contrato: " + ", ".join(missing_columns), max(1, len(rows)))
    if extra_columns:
        add("UNEXPECTED_COLUMN", "warning", "Columnas no declaradas", "Columnas fuera del contrato: " + ", ".join(extra_columns), len(extra_columns))
    malformed = [i + 2 for i, row in enumerate(rows) if None in row]
    if malformed:
        add("ROW_WIDTH", "error", "Filas con valores adicionales", f"{len(malformed)} fila(s) tienen más celdas que encabezados.", len(malformed), lines=malformed)

    profiles = [_profile(name, [row.get(name) for row in rows]) for name in headers]
    for name, rules in rules_by_column.items():
        if name not in headers:
            continue
        values = [row.get(name) for row in rows]
        filled = [(i + 2, str(value).strip()) for i, value in enumerate(values) if not _blank(value)]
        missing_lines = [i + 2 for i, value in enumerate(values) if _blank(value)]
        if rules.get("required") and missing_lines:
            add("REQUIRED", "error", "Campo obligatorio vacío", f"La columna '{name}' debe tener valor en todas las filas.", len(missing_lines), name, missing_lines)
        expected_type = rules.get("type")
        if expected_type:
            invalid = [line for line, value in filled if not _type_ok(value, str(expected_type))]
            if invalid:
                add("TYPE_MISMATCH", "error", "Tipo de dato incorrecto", f"La columna '{name}' debe ser de tipo {expected_type}.", len(invalid), name, invalid)
        if rules.get("unique"):
            seen: set[str] = set(); duplicates: list[int] = []
            for line, value in filled:
                if value in seen: duplicates.append(line)
                else: seen.add(value)
            if duplicates:
                add("NOT_UNIQUE", "error", "Valores duplicados", f"La columna '{name}' debe ser única.", len(duplicates), name, duplicates)
        if "allowed_values" in rules:
            allowed = {str(item) for item in rules["allowed_values"]}
            invalid = [line for line, value in filled if value not in allowed]
            if invalid:
                add("NOT_ALLOWED", "error", "Valor fuera del catálogo", f"Valores admitidos en '{name}': " + ", ".join(sorted(allowed)), len(invalid), name, invalid)
        if "regex" in rules:
            pattern = re.compile(str(rules["regex"]))
            invalid = [line for line, value in filled if pattern.fullmatch(value) is None]
            if invalid:
                add("PATTERN_MISMATCH", "error", "Formato no válido", f"La columna '{name}' no cumple el patrón requerido.", len(invalid), name, invalid)
        for bound_name, comparator, label in (("min", lambda x, y: x < y, "menor al mínimo"), ("max", lambda x, y: x > y, "mayor al máximo")):
            if bound_name in rules:
                bound = _number(str(rules[bound_name]))
                if bound is None: raise ValueError(f"El límite '{bound_name}' de '{name}' debe ser numérico.")
                invalid = [line for line, value in filled if (number := _number(value)) is not None and comparator(number, bound)]
                if invalid:
                    add("OUT_OF_RANGE", "error", "Valor fuera de rango", f"La columna '{name}' contiene valores {label} ({rules[bound_name]}).", len(invalid), name, invalid)

    minimum = int(contract.get("minimum_rows", 0))
    maximum = contract.get("maximum_rows")
    if len(rows) < minimum:
        add("ROW_COUNT_LOW", "error", "Lote incompleto", f"Se requieren al menos {minimum} filas; llegaron {len(rows)}.", minimum - len(rows))
    if maximum is not None and len(rows) > int(maximum):
        add("ROW_COUNT_HIGH", "error", "Lote excedido", f"Se permiten como máximo {maximum} filas; llegaron {len(rows)}.", len(rows) - int(maximum))
    if contract.get("primary_key") and contract["primary_key"] not in rules_by_column:
        raise ValueError("La llave primaria debe estar declarada en 'columns'.")

    seen_rows: set[tuple[Any, ...]] = set(); duplicate_lines: list[int] = []
    for i, row in enumerate(rows):
        signature = tuple(row.get(name) for name in headers)
        if signature in seen_rows: duplicate_lines.append(i + 2)
        else: seen_rows.add(signature)
    if duplicate_lines:
        add("DUPLICATE_ROW", "warning", "Filas idénticas", f"Se encontraron {len(duplicate_lines)} fila(s) repetidas.", len(duplicate_lines), lines=duplicate_lines)

    denominator = max(1, len(rows) * max(1, len(headers)))
    penalty = sum(item.affected_rows * (1 if item.severity == "error" else .25) for item in findings)
    score = round(max(0, 100 - 100 * penalty / denominator), 1)
    return Result(csv_path.name, str(contract.get("name", contract_path.stem)), datetime.now(timezone.utc).isoformat(timespec="seconds"), len(rows), len(headers), score, not any(item.severity == "error" for item in findings), profiles, findings)
