"""
export.py
=========
Análisis y Exportación — Etapa 12 del pipeline

Genera el dataset imputado final en formato CSV y un resumen estadístico
en Excel con múltiples hojas. Produce también un reporte de exportación.

Salidas
-------
- data/export/dataset_imputado.csv          Dataset completo (1.6M filas)
- data/export/resumen_estadistico.xlsx      Estadísticas resumidas (4 hojas)
- reports/exportacion/export_report.csv     Manifiesto de exportación

Uso
---
    python "Análisis y Exportación/export.py"
    python "Análisis y Exportación/export.py" --config ruta/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT       = SCRIPT_DIR.parent
CONFIG     = SCRIPT_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Config y logging
# ---------------------------------------------------------------------------

def _load_config(path: Path = CONFIG) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _setup_logging(cfg: dict) -> logging.Logger:
    log_dir  = ROOT / cfg["output"]["log_dir"]
    log_file = log_dir / cfg["output"]["log_file"]
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("export")


# ---------------------------------------------------------------------------
# Estadísticas globales
# ---------------------------------------------------------------------------

def compute_global_stats(df: pd.DataFrame, variables: list[str],
                          log: logging.Logger) -> pd.DataFrame:
    """Media, std, percentiles, min, max por variable."""
    rows = []
    for var in variables:
        s = df[var].dropna()
        rows.append({
            "variable": var,
            "n_total":      len(df),
            "n_validos":    int(s.count()),
            "n_nan":        int(df[var].isna().sum()),
            "mean":         round(float(s.mean()), 4),
            "std":          round(float(s.std()),  4),
            "min":          round(float(s.min()),  4),
            "p05":          round(float(s.quantile(0.05)), 4),
            "p25":          round(float(s.quantile(0.25)), 4),
            "p50":          round(float(s.quantile(0.50)), 4),
            "p75":          round(float(s.quantile(0.75)), 4),
            "p95":          round(float(s.quantile(0.95)), 4),
            "max":          round(float(s.max()),  4),
        })
        log.info(
            f"  {var:6s}: n={s.count():,}  mean={s.mean():.3f}  "
            f"std={s.std():.3f}  min={s.min():.3f}  max={s.max():.3f}"
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Estadísticas por estación
# ---------------------------------------------------------------------------

def compute_station_stats(df: pd.DataFrame, variables: list[str],
                           col_sta: str, log: logging.Logger) -> pd.DataFrame:
    """Media y cobertura por estación y variable."""
    rows = []
    for sta, grp in df.groupby(col_sta):
        for var in variables:
            s       = grp[var]
            n_total = len(s)
            n_valid = int(s.count())
            n_nan   = int(s.isna().sum())
            rows.append({
                "estacion":       sta,
                "variable":       var,
                "n_total":        n_total,
                "n_validos":      n_valid,
                "n_nan":          n_nan,
                "cobertura":      round(n_valid / n_total, 4) if n_total > 0 else 0.0,
                "mean":           round(float(s.mean()), 4) if n_valid > 0 else None,
                "std":            round(float(s.std()),  4) if n_valid > 1 else None,
            })
    log.info(f"  Estadísticas por estación calculadas ({df[col_sta].nunique()} estaciones)")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cobertura por variable
# ---------------------------------------------------------------------------

def compute_coverage_stats(df: pd.DataFrame, variables: list[str],
                            log: logging.Logger) -> pd.DataFrame:
    """NaN residual y tasa de llenado por variable."""
    rows = []
    for var in variables:
        n_total = len(df)
        n_nan   = int(df[var].isna().sum())
        n_valid = n_total - n_nan
        rows.append({
            "variable":       var,
            "n_total":        n_total,
            "n_validos":      n_valid,
            "n_nan_residual": n_nan,
            "tasa_cobertura": round(n_valid / n_total, 6) if n_total > 0 else 0.0,
        })
        log.info(
            f"  {var:6s}: {n_valid:,} válidos / {n_total:,} total  "
            f"({n_nan:,} NaN residuales, {n_valid/n_total:.2%} cobertura)"
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Resumen anual
# ---------------------------------------------------------------------------

def compute_annual_summary(df: pd.DataFrame, variables: list[str],
                            col_date: str, log: logging.Logger) -> pd.DataFrame:
    """Media anual por variable a lo largo del período completo."""
    df = df.copy()
    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
    df["_year"]  = df[col_date].dt.year
    rows = []
    for var in variables:
        annual = df.groupby("_year")[var].agg(["mean", "std", "count"]).reset_index()
        annual.columns = ["anio", f"mean_{var}", f"std_{var}", f"n_{var}"]
        if not rows:
            base = annual
        else:
            base = base.merge(annual, on="anio", how="outer")
        rows.append(var)
    log.info(f"  Resumen anual calculado ({df['_year'].nunique()} años)")
    return base.sort_values("anio").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Exportación CSV combinado
# ---------------------------------------------------------------------------

def export_csv(df: pd.DataFrame, path: Path, cfg: dict,
               log: logging.Logger) -> None:
    sep = cfg.get("csv_separator", ",")
    enc = cfg.get("csv_encoding", "utf-8")
    df.to_csv(path, index=False, sep=sep, encoding=enc)
    size_mb = path.stat().st_size / 1024 / 1024
    log.info(f"  CSV exportado: {path.relative_to(ROOT)}  ({size_mb:.1f} MB, {len(df):,} filas)")


# ---------------------------------------------------------------------------
# Exportación CSV por estación  (misma convención que processed/csv/)
# ---------------------------------------------------------------------------

def export_per_station(df: pd.DataFrame, out_dir: Path, col_sta: str,
                       cfg: dict, log: logging.Logger) -> int:
    """
    Guarda un CSV por estación en out_dir/estacion=XXXXX.csv,
    con la misma convención de nombres que data/processed/csv/.
    Devuelve el número de estaciones exportadas.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sep = cfg.get("csv_separator", ",")
    enc = cfg.get("csv_encoding", "utf-8")
    n   = 0
    for sta, grp in df.groupby(col_sta, sort=True):
        fname = out_dir / f"estacion={sta}.csv"
        grp.drop(columns=[col_sta]).sort_values(
            cfg["columns"]["date"]
        ).to_csv(fname, index=False, sep=sep, encoding=enc)
        n += 1
    log.info(
        f"  {n} CSVs por estación → {out_dir.relative_to(ROOT)}/"
        f"  ({n} archivos, ~{(out_dir.stat().st_size/1024/1024):.1f} MB total)"
    )
    return n


# ---------------------------------------------------------------------------
# Exportación Excel (estadísticas)
# ---------------------------------------------------------------------------

def export_excel(df_global: pd.DataFrame, df_station: pd.DataFrame,
                 df_cov: pd.DataFrame, df_annual: pd.DataFrame,
                 path: Path, log: logging.Logger) -> None:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        log.warning("openpyxl no disponible — Excel omitido. Instalar: pip install openpyxl")
        return

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_global.to_excel(writer,  sheet_name="Estadísticas globales", index=False)
        df_station.to_excel(writer, sheet_name="Por estación",          index=False)
        df_cov.to_excel(writer,     sheet_name="Cobertura por variable", index=False)
        df_annual.to_excel(writer,  sheet_name="Resumen anual",          index=False)

    size_kb = path.stat().st_size / 1024
    log.info(f"  Excel exportado: {path.relative_to(ROOT)}  ({size_kb:.0f} KB, 4 hojas)")


# ---------------------------------------------------------------------------
# Reporte de exportación
# ---------------------------------------------------------------------------

def build_export_report(df: pd.DataFrame, cfg: dict, variables: list[str],
                         csv_path: Path, excel_path: Path) -> pd.DataFrame:
    rows = [
        {"artefacto": "dataset_imputado.csv",    "ruta": str(csv_path.relative_to(ROOT)),
         "filas": len(df), "columnas": len(df.columns),
         "tamano_mb": round(csv_path.stat().st_size / 1024 / 1024, 2) if csv_path.exists() else None,
         "descripcion": "Dataset imputado completo"},
        {"artefacto": "resumen_estadistico.xlsx", "ruta": str(excel_path.relative_to(ROOT)),
         "filas": None, "columnas": None,
         "tamano_mb": round(excel_path.stat().st_size / 1024 / 1024, 3) if excel_path.exists() else None,
         "descripcion": "Estadísticas resumidas — 4 hojas"},
    ]
    for var in variables:
        rows.append({
            "artefacto": f"variable:{var}", "ruta": None,
            "filas": int(df[var].count()), "columnas": None,
            "tamano_mb": None,
            "descripcion": f"Valores válidos en dataset final",
        })
    rows.append({
        "artefacto": "timestamp",
        "ruta":      None,
        "filas":     None,
        "columnas":  None,
        "tamano_mb": None,
        "descripcion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Análisis y Exportación — Etapa 12")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()

    cfg = _load_config(args.config)
    log = _setup_logging(cfg)

    export_dir = ROOT / cfg["output"]["export_dir"]
    report_dir = ROOT / cfg["output"]["report_dir"]
    export_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    variables = cfg["variables"]
    col_sta   = cfg["columns"]["station"]
    col_date  = cfg["columns"]["date"]

    # --- Carga ---
    imp_path = ROOT / cfg["input"]["imputed"]
    log.info(f"Cargando dataset imputado: {imp_path.name}  ({imp_path.stat().st_size/1e6:.1f} MB)")
    df = pd.read_parquet(imp_path)
    log.info(f"  {len(df):,} filas · {df[col_sta].nunique()} estaciones · {len(df.columns)} columnas")

    # --- Estadísticas ---
    log.info("=== Estadísticas globales ===")
    df_global = compute_global_stats(df, variables, log)

    log.info("=== Estadísticas por estación ===")
    df_station = compute_station_stats(df, variables, col_sta, log)

    log.info("=== Cobertura por variable ===")
    df_cov = compute_coverage_stats(df, variables, log)

    log.info("=== Resumen anual ===")
    df_annual = compute_annual_summary(df, variables, col_date, log)

    # --- Exportar CSV combinado ---
    log.info("=== Exportando CSV combinado ===")
    csv_path = ROOT / cfg["output"]["csv_file"]
    export_csv(df, csv_path, cfg, log)

    # --- Exportar CSV por estación ---
    log.info("=== Exportando CSV por estación ===")
    sta_dir = ROOT / cfg["output"]["per_station_dir"]
    n_sta = export_per_station(df, sta_dir, col_sta, cfg, log)

    # --- Exportar Excel ---
    log.info("=== Exportando Excel ===")
    excel_path = ROOT / cfg["output"]["excel_file"]
    export_excel(df_global, df_station, df_cov, df_annual, excel_path, log)

    # --- Reporte de exportación ---
    df_report = build_export_report(df, cfg, variables, csv_path, excel_path)
    # Agregar entrada de por_estacion al reporte
    df_report = pd.concat([df_report, pd.DataFrame([{
        "artefacto":   f"por_estacion/ ({n_sta} archivos)",
        "ruta":        str(sta_dir.relative_to(ROOT)),
        "filas":       len(df),
        "columnas":    len(df.columns) - 1,
        "tamano_mb":   round(sum(f.stat().st_size for f in sta_dir.iterdir()) / 1024 / 1024, 1),
        "descripcion": f"Un CSV por estación — convención estacion=XXXXX.csv",
    }])], ignore_index=True)
    rep_path  = ROOT / cfg["output"]["export_report"]
    df_report.to_csv(rep_path, index=False)
    log.info(f"Reporte exportación → {rep_path.relative_to(ROOT)}")

    log.info("=== Exportación completada ===")


if __name__ == "__main__":
    main()
