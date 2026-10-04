# Data Quality Gate

**Valida la calidad de los datos antes de que entren a un pipeline.** Define reglas como contrato, ejecuta la revisión desde la terminal y comparte un informe HTML autocontenido con resultados por columna y errores accionables.

Proyecto de portafolio sobre ingeniería de datos y automatización, aplicado a exportaciones de inventario. Funciona con Python 3.10 o superior y no necesita dependencias externas.

## Funciones

- Contratos de datos versionables en JSON.
- Validación de esquema, tipos, campos obligatorios, unicidad, catálogos, expresiones regulares y rangos.
- Umbrales de valores vacíos configurables por columna, con severidad bloqueante o informativa.
- Reglas entre columnas para detectar inconsistencias de negocio, como existencias por debajo del mínimo.
- Perfilado de completitud, valores distintos, muestras y rangos numéricos.
- Detección de filas repetidas y registros con estructura inválida.
- Puntuación de calidad, severidad por hallazgo y códigos de salida para CI/CD.
- Informes HTML para personas y JSON para automatizaciones.
- Autodetección de comas, punto y coma, tabuladores y barras verticales en CSV.
- Motor implementado con la biblioteca estándar de Python.

## Inicio rápido

```bash
python3 -m quality_gate validate examples/inventory.csv \
  --contract examples/inventory.contract.json \
  --html reports/inventory.html \
  --json reports/inventory.json
```

Abre `reports/inventory.html` en el navegador. Es un reporte de un solo archivo que no depende de servicios externos.

El separador se detecta automáticamente. Para probar una exportación de Excel con punto y coma:

```bash
python3 -m quality_gate validate examples/inventory_excel.csv \
  --contract examples/inventory.contract.json \
  --delimiter semicolon \
  --html reports/inventory-excel.html
```

`--delimiter` también acepta `auto`, `comma`, `tab` y `pipe`.

Para ver cómo la puerta detecta errores intencionales: 

```bash
python3 -m quality_gate validate examples/inventory_with_issues.csv \
  --contract examples/inventory.contract.json \
  --html reports/inventory-errors.html
```

Este segundo comando devuelve el código `1` porque ese CSV contiene incumplimientos de demostración.

## Instalar el comando opcional

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e .
qualitygate validate examples/inventory.csv --contract examples/inventory.contract.json --html reports/inventory.html
```

## Integración en CI/CD

El proceso devuelve `0` si se cumple el contrato, `1` si hay errores de calidad y `2` si no se pueden procesar las entradas. El pipeline puede detener una publicación defectuosa:

```yaml
- name: Validar inventario
  run: >-
    python -m quality_gate validate data/inventory.csv
    --contract contracts/inventory.contract.json
    --json reports/quality.json
    --html reports/quality.html
```

Agrega `--fail-on-warning` para bloquear también ante advertencias. El JSON incluye las filas afectadas y ejemplos de líneas, sin copiar los valores completos a los registros del pipeline.

## Reglas del contrato

| Regla | Ejemplo | Propósito |
|---|---|---|
| `type` | `"integer"` | `string`, `integer`, `number`, `boolean`, `date` o `datetime` |
| `required` | `true` | Rechaza valores vacíos |
| `unique` | `true` | Requiere valores no vacíos sin duplicados |
| `allowed_values` | `["Motor", "Frenos"]` | Limita el campo a un catálogo |
| `regex` | `"^[A-Z]{3}-[0-9]{4}$"` | Valida el formato completo |
| `min` / `max` | `0` | Define límites numéricos |
| `max_missing_percent` | `25` | Tolera un porcentaje máximo de celdas vacías |
| `missing_severity` | `"warning"` | Define si exceder el umbral bloquea o solo advierte |
| `min_length` | `3` | Establece una longitud mínima de texto |
| `comparisons` | `existencia >= stock_minimo` | Compara dos columnas por fila con `==`, `!=`, `<`, `<=`, `>` o `>=` |

`minimum_rows` y `maximum_rows` controlan el tamaño del lote; `primary_key` documenta la llave de negocio. Las columnas extra generan advertencias y las columnas requeridas faltantes bloquean la validación. Para una columna opcional, `max_missing_percent` acepta un porcentaje de 0 a 100; `missing_severity` puede ser `error` o `warning` (por defecto, `error`).

Las reglas `comparisons` se declaran en el nivel superior del contrato. Las comparaciones de orden (`<`, `<=`, `>`, `>=`) requieren valores numéricos; `==` y `!=` comparan el texto de las celdas. Las filas con alguno de los dos valores vacío se omiten porque los campos obligatorios se revisan por separado. Cada regla acepta `severity` (`error` por defecto) y un `message` opcional:

```json
"comparisons": [
  {
    "left": "existencia",
    "operator": ">=",
    "right": "stock_minimo",
    "severity": "warning",
    "message": "La existencia está por debajo del stock mínimo."
  }
]
```

## Arquitectura

```text
CSV + contrato JSON → perfilado → reglas → puntuación → HTML + JSON
```

La lectura acepta UTF-8 y UTF-8 con BOM, y detecta separadores coma, punto y coma, tabulador y barra vertical. También puedes fijarlo con `--delimiter`. Las fechas se esperan en formato ISO 8601. El cálculo de calidad penaliza hallazgos de acuerdo con las filas afectadas y su severidad. El lote se procesa en memoria, por lo que está pensado para exportaciones pequeñas y medianas.

## Estructura

```text
quality_gate/       motor y CLI
examples/           contrato e inventarios de demostración
reports/            salidas locales excluidas de Git
```

## Tecnologías y licencia

Python 3.10+, biblioteca estándar, JSON, CSV y HTML/CSS. Licencia MIT; consulta [LICENSE](LICENSE).
