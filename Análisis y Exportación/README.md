# Análisis y Exportación — Etapa 12 del pipeline

Genera el dataset imputado final en formatos listos para el usuario (CSV combinado + 173 CSVs por estación + Excel con estadísticas resumidas) y produce un manifiesto de exportación.

**Responsable:** Científico de datos  
**Dependencia:** Etapa 11 (Monitoreo) — `data/imputed/dataset_imputado.parquet` disponible

> Esta etapa es la **etapa 12** del pipeline automatizado. Se ejecuta automáticamente al correr `run_pipeline.py`, o de forma independiente con `python "Análisis y Exportación/export.py"`.

---

## ¿Qué hace?

Carga `dataset_imputado.parquet` (artefacto interno de la Etapa 9) y genera cuatro grupos de salidas:

1. **CSV combinado** (`data/export/dataset_imputado.csv`): dataset completo con ~1.6 M filas, listo para análisis externos.
2. **CSVs por estación** (`data/export/por_estacion/estacion=XXXXX.csv`): un archivo por cada una de las 173 estaciones, con la convención Hive de nombres consistente con `data/processed/csv/`.
3. **Excel de estadísticas** (`data/export/resumen_estadistico.xlsx`): cuatro hojas con estadísticas resumidas.
4. **Reporte de exportación** (`reports/exportacion/export_report.csv`): manifiesto con rutas, tamaños y conteo de artefactos generados.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `export.py` | Script principal de exportación y análisis |
| `config.yaml` | Rutas de entrada/salida, separador CSV, configuración de hojas Excel |
| `README.md` | Este archivo |

---

## Uso

```bash
# Ejecución estándar
python "Análisis y Exportación/export.py"

# Config alternativo
python "Análisis y Exportación/export.py" --config ruta/config.yaml
```

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Dataset imputado | `data/imputed/dataset_imputado.parquet` | `Imputación Generativa/impute.py` |

---

## Salidas generadas

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| CSV combinado | `data/export/dataset_imputado.csv` | Dataset completo — entrega principal al usuario |
| CSVs por estación | `data/export/por_estacion/estacion=XXXXX.csv` | 173 archivos, uno por estación |
| Excel estadísticas | `data/export/resumen_estadistico.xlsx` | Resumen en 4 hojas (ver abajo) |
| Reporte de exportación | `reports/exportacion/export_report.csv` | Manifiesto: rutas, tamaños y conteo de artefactos |
| Log | `reports/exportacion/_logs/exportacion_run.log` | Registro completo de ejecución |

---

## Estadísticas generadas (Excel)

| Hoja | Contenido |
|------|-----------|
| `Estadísticas globales` | Media, std, min, max y percentiles (p05, p25, p50, p75, p95) por variable |
| `Por estación` | Media, std, n válidos, n NaN y cobertura por estación y variable |
| `Cobertura por variable` | NaN residual y tasa de cobertura global por variable |
| `Resumen anual` | Media anual por variable a lo largo del período histórico completo |

> El Excel contiene únicamente estadísticas resumidas. El dataset completo (~1.6 M filas) supera el límite de filas de Excel y se entrega en CSV.

---

## Organización de la entrega

```
data/export/
├── dataset_imputado.csv          ← dataset completo (todas las estaciones)
├── resumen_estadistico.xlsx      ← estadísticas resumidas (4 hojas)
└── por_estacion/
    ├── estacion=25001.csv
    ├── estacion=25002.csv
    ├── ...
    └── estacion=25XXX.csv        ← 173 archivos (una fila por día)
```

La convención `estacion=XXXXX.csv` es consistente con `data/processed/csv/` (estilo Hive), facilitando la integración con herramientas de análisis como Pandas, Polars o DuckDB.

---

## Configuración (`config.yaml`)

```yaml
input:
  imputed: "data/imputed/dataset_imputado.parquet"

output:
  export_dir:      "data/export"
  csv_file:        "data/export/dataset_imputado.csv"
  per_station_dir: "data/export/por_estacion"
  excel_file:      "data/export/resumen_estadistico.xlsx"
  report_dir:      "reports/exportacion"
  export_report:   "reports/exportacion/export_report.csv"

csv_separator: ","
csv_encoding:  "utf-8"

variables: [precip, evap, tmax, tmin]

columns:
  station: "estacion"
  date:    "date"
```

---

## Requisitos

```bash
pip install pandas numpy pyarrow pyyaml openpyxl
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
