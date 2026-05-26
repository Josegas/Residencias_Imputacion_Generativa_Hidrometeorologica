"""
ingest_external.py
==================
Convierte un archivo plano (CSV, Excel, Parquet) con columnas
  estacion, date, precip, evap, tmax, tmin
a la estructura de particiones parquet que espera la Etapa 3 (cleaning.py).

Estructura de salida en data/interim/organized_external/estado=sin/
(directorio aislado — nunca toca organized/ que contiene datos CONAGUA):
  estacion=XXXXX/
    anio=YYYY/
      variable=precip/part0.parquet
      variable=evap/part0.parquet
      variable=tmax/part0.parquet
      variable=tmin/part0.parquet
  _index.csv

Cada partición parquet tiene exactamente dos columnas: date, value.

Uso:
    python "Pipeline Reproducible/ingest_external.py" --input datos.csv
    python "Pipeline Reproducible/ingest_external.py" --input datos.xlsx --force
    python "Pipeline Reproducible/ingest_external.py" --input datos.parquet --force

Después de la ingestión, ejecutar el pipeline con --external para que las
etapas 3-5 usen los directorios externos y preserven los scalers originales:
    python "Pipeline Reproducible/run_pipeline.py" --from-stage 3 --skip-stages 1,2,6,7 --force --external
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT        = Path(__file__).resolve().parent.parent

# Directorio exclusivo para datos externos — nunca toca organized/ (datos CONAGUA).
# Las etapas 3, 4 y 5 en modo --external leen desde aquí.
INTERIM_DIR = ROOT / "data" / "interim" / "organized_external" / "estado=sin"
INDEX_PATH  = INTERIM_DIR / "_index.csv"
VARIABLES   = ["precip", "evap", "tmax", "tmin"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ingest_external")


# ---------------------------------------------------------------------------
# Lectura del archivo de entrada
# ---------------------------------------------------------------------------

def _read_input(path: Path) -> pd.DataFrame:
    name = path.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(path)
    if name.endswith(".txt"):
        # Detecta el separador automáticamente (tabulador, coma, punto y coma, espacio)
        return pd.read_csv(path, sep=None, engine="python")
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    if name.endswith(".parquet"):
        return pd.read_parquet(path)
    raise ValueError(f"Formato no soportado: {path.suffix}. Use CSV, TXT, Excel o Parquet.")


def _validate_columns(df: pd.DataFrame) -> None:
    required = ["estacion", "date"] + VARIABLES
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en el archivo: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Ingesta principal
# ---------------------------------------------------------------------------

def ingest(input_path: Path, force: bool = False) -> int:
    """
    Convierte el archivo plano a particiones parquet compatibles con la Etapa 3.
    Retorna el número de particiones escritas.
    """
    if INDEX_PATH.exists() and not force:
        log.warning(
            f"El índice ya existe: {INDEX_PATH}\n"
            "Usa --force para sobreescribir con los nuevos datos."
        )
        return 0

    log.info(f"Leyendo archivo: {input_path}")
    df = _read_input(input_path)

    _validate_columns(df)

    # Normalizar tipos
    df["date"]     = pd.to_datetime(df["date"], errors="coerce")
    df             = df.dropna(subset=["date"])
    df["estacion"] = df["estacion"].astype(str).str.zfill(5)
    df["anio"]     = df["date"].dt.year

    n_stations = df["estacion"].nunique()
    log.info(f"Estaciones: {n_stations} | Registros: {len(df):,}")
    log.info(f"Período: {df['date'].min().date()} → {df['date'].max().date()}")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict] = []
    n_written  = 0

    for station in sorted(df["estacion"].unique()):
        df_sta = df[df["estacion"] == station]

        for year in sorted(df_sta["anio"].unique()):
            df_yr = df_sta[df_sta["anio"] == year]

            for var in VARIABLES:
                part = (
                    df_yr[["date", var]]
                    .rename(columns={var: "value"})
                    .copy()
                )
                part["date"]  = part["date"].astype("datetime64[ns]")
                part["value"] = pd.to_numeric(part["value"], errors="coerce")

                out_dir = (
                    INTERIM_DIR
                    / f"estacion={station}"
                    / f"anio={year}"
                    / f"variable={var}"
                )
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "part0.parquet"
                part.to_parquet(out_path, index=False)

                missing_pct = round(float(part["value"].isna().mean() * 100), 3)
                index_rows.append({
                    "station"      : station,
                    "year"         : year,
                    "variable"     : var,
                    "path_parquet" : str(out_path),
                    "rows"         : len(part),
                    "missing_pct"  : missing_pct,
                })
                n_written += 1

    pd.DataFrame(index_rows).to_csv(INDEX_PATH, index=False, encoding="utf-8")

    log.info(f"Particiones escritas: {n_written:,}")
    log.info(f"Índice guardado en  : {INDEX_PATH}")
    log.info("Ingestión completada. Continúa con la Etapa 3 del pipeline.")
    return n_written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta de datos externos al pipeline hidrometeorológico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", required=True,
        help="Ruta al archivo de entrada (CSV, Excel o Parquet).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Sobreescribe el índice y las particiones si ya existen.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        log.error(f"Archivo no encontrado: {input_path}")
        sys.exit(1)

    try:
        n = ingest(input_path, force=args.force)
        sys.exit(0 if n > 0 else 1)
    except Exception as exc:
        log.error(f"Error en ingestión: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
