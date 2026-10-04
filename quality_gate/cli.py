"""Comando qualitygate."""
import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .engine import analyze
from .report import write_html

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qualitygate", description="Perfila un CSV y valida su contrato de calidad.")
    parser.add_argument("--version", action="version", version=f"Data Quality Gate {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="valida y perfila un archivo CSV")
    check.add_argument("file", type=Path, help="archivo CSV")
    check.add_argument("--contract", required=True, type=Path, help="contrato JSON")
    check.add_argument("--html", type=Path, help="guarda un informe HTML")
    check.add_argument("--json", type=Path, help="guarda resultados legibles por máquina")
    check.add_argument("--fail-on-warning", action="store_true", help="también devuelve error ante advertencias")
    args = parser.parse_args(argv)
    if not args.file.is_file():
        print(f"Error: no existe el CSV: {args.file}", file=sys.stderr); return 2
    if not args.contract.is_file():
        print(f"Error: no existe el contrato: {args.contract}", file=sys.stderr); return 2
    outputs = [p.resolve() for p in (args.html, args.json) if p]
    if len(set(outputs)) != len(outputs) or any(p in {args.file.resolve(), args.contract.resolve()} for p in outputs):
        print("Error: cada archivo de salida debe usar una ruta distinta a las entradas.", file=sys.stderr); return 2
    try:
        result = analyze(args.file, args.contract)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.html: write_html(result, args.html)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 2
    errors = sum(f.severity == "error" for f in result.findings)
    warnings = sum(f.severity == "warning" for f in result.findings)
    print(f"Data Quality Gate · {result.source}")
    print(f"Estado: {'APROBADO' if result.passed else 'BLOQUEADO'} · Calidad: {result.score:.1f}/100")
    print(f"Filas: {result.row_count} · Columnas: {result.column_count} · Errores: {errors} · Advertencias: {warnings}")
    for finding in result.findings[:8]:
        column = f" [{finding.column}]" if finding.column else ""
        print(f"  {finding.severity.upper()}{column}: {finding.title} — {finding.message}")
    if args.html: print(f"Informe HTML: {args.html}")
    if args.json: print(f"Resultado JSON: {args.json}")
    return 1 if errors or (args.fail_on_warning and warnings) else 0
