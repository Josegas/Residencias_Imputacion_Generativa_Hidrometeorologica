"""
División Train / Val / Test — RES-28 (subtareas RES-109, RES-110, RES-111)

Divide el dataset hidrometeorologico de Sinaloa en subconjuntos de
entrenamiento (70 %), validación (15 %) y prueba (15 %) respetando el
orden cronológico de cada serie de estación para evitar fuga de información.

Uso:
    python "División Train-Val-Test/split.py"
    python "División Train-Val-Test/split.py" --config path/to/config.yaml
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Helpers de configuración y logging
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lógica de partición
# ---------------------------------------------------------------------------

def split_station(
    df: pd.DataFrame,
    train_ratio: float,
    val_ratio: float,
    date_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Divide los registros de UNA estación de forma cronológica.

    El corte se calcula con floor() para que no haya registro asignado
    a más de un conjunto (boundary_mode = "floor").
    """
    df_sorted = df.sort_values(date_col).reset_index(drop=True)
    n = len(df_sorted)

    train_end = int(np.floor(n * train_ratio))
    val_end   = int(np.floor(n * (train_ratio + val_ratio)))

    # Garantía: al menos 1 registro en val y test si n es suficientemente grande
    train_end = max(1, min(train_end, n - 2))
    val_end   = max(train_end + 1, min(val_end, n - 1))

    train = df_sorted.iloc[:train_end].copy()
    val   = df_sorted.iloc[train_end:val_end].copy()
    test  = df_sorted.iloc[val_end:].copy()

    return train, val, test


def build_station_record(
    station: str,
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    total: int,
    date_col: str,
) -> dict:
    """Construye una fila para el split_index.csv."""
    def safe_min(s): return s[date_col].min() if len(s) > 0 else pd.NaT
    def safe_max(s): return s[date_col].max() if len(s) > 0 else pd.NaT

    return {
        "estacion":          station,
        "total_registros":   total,
        "n_train":           len(train),
        "n_val":             len(val),
        "n_test":            len(test),
        "pct_train":         round(len(train) / total * 100, 2),
        "pct_val":           round(len(val)   / total * 100, 2),
        "pct_test":          round(len(test)  / total * 100, 2),
        "train_start":       safe_min(train),
        "train_end":         safe_max(train),
        "val_start":         safe_min(val),
        "val_end":           safe_max(val),
        "test_start":        safe_min(test),
        "test_end":          safe_max(test),
    }


# ---------------------------------------------------------------------------
# Verificación de leakage (RES-111)
# ---------------------------------------------------------------------------

def verify_no_leakage(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    log: logging.Logger,
    date_col: str,
    station_col: str,
) -> bool:
    """
    Verifica la ausencia de fuga de información entre los tres conjuntos.

    Para cada estación comprueba:
      1. max(train.date) < min(val.date)    — orden temporal estricto
      2. max(val.date)   < min(test.date)   — orden temporal estricto
      3. Intersección de fechas vacía entre todos los pares

    Retorna True si no hay leakage.
    """
    log.info("=== Verificación de leakage ===")
    stations = train[station_col].unique()
    issues = []

    for station in stations:
        tr = train[train[station_col] == station][date_col]
        va = val[val[station_col] == station][date_col]
        te = test[test[station_col] == station][date_col]

        if len(tr) == 0 or len(va) == 0 or len(te) == 0:
            log.warning(f"[{station}] Un conjunto está vacío — se omite verificación")
            continue

        # Orden temporal
        if tr.max() >= va.min():
            msg = f"[{station}] ORDEN ROTO: max(train)={tr.max().date()} >= min(val)={va.min().date()}"
            issues.append(msg)
            log.error(msg)

        if va.max() >= te.min():
            msg = f"[{station}] ORDEN ROTO: max(val)={va.max().date()} >= min(test)={te.min().date()}"
            issues.append(msg)
            log.error(msg)

        # Intersección de fechas
        tr_set = set(tr)
        va_set = set(va)
        te_set = set(te)

        overlap_tv = tr_set & va_set
        overlap_tt = tr_set & te_set
        overlap_vt = va_set & te_set

        for overlap, label in [(overlap_tv, "train∩val"), (overlap_tt, "train∩test"), (overlap_vt, "val∩test")]:
            if overlap:
                msg = f"[{station}] SOLAPAMIENTO {label}: {len(overlap)} fechas comunes"
                issues.append(msg)
                log.error(msg)

    if issues:
        log.error(f"Se detectaron {len(issues)} problema(s) de leakage.")
        return False

    log.info(f"OK — {len(stations)} estaciones verificadas. Sin leakage detectado.")
    return True


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(config_path: Path) -> None:
    cfg   = load_config(config_path)
    log   = setup_logging(ROOT / cfg["output"]["log_path"])

    log.info("=" * 60)
    log.info("División Train / Val / Test — inicio")
    log.info(f"Configuración: {config_path}")
    log.info("=" * 60)

    # Parámetros de split
    train_ratio  = cfg["split"]["train_ratio"]
    val_ratio    = cfg["split"]["val_ratio"]
    test_ratio   = cfg["split"]["test_ratio"]
    min_records  = cfg["split"]["min_records_per_station"]

    # Esquema del dataset
    date_col    = cfg["input"]["date_col"]
    station_col = cfg["input"]["station_col"]
    variables   = cfg["input"]["variables"]

    log.info(f"Proporciones: train={train_ratio:.0%} | val={val_ratio:.0%} | test={test_ratio:.0%}")
    log.info(f"Estrategia: {cfg['split']['strategy']}")
    log.info(f"Mínimo de registros por estación: {min_records}")

    # ------------------------------------------------------------------ carga
    dataset_path = ROOT / cfg["input"]["dataset_path"]
    log.info(f"Cargando dataset: {dataset_path}")
    df = pd.read_parquet(dataset_path)
    df[date_col] = pd.to_datetime(df[date_col])
    log.info(f"  {len(df):,} registros | {df[station_col].nunique()} estaciones")

    # ---------------------------------------------------------- split por estación
    train_frames, val_frames, test_frames = [], [], []
    index_rows = []
    skipped = []

    stations = sorted(df[station_col].unique())
    log.info(f"Procesando {len(stations)} estaciones...")

    for station in stations:
        df_st = df[df[station_col] == station]
        n = len(df_st)

        if n < min_records:
            log.warning(f"  [{station}] Omitida: solo {n} registros (mínimo={min_records})")
            skipped.append({"estacion": station, "registros": n, "motivo": f"< {min_records} registros"})
            continue

        tr, va, te = split_station(df_st, train_ratio, val_ratio, date_col)

        train_frames.append(tr)
        val_frames.append(va)
        test_frames.append(te)
        index_rows.append(build_station_record(station, tr, va, te, n, date_col))

    log.info(f"  Estaciones incluidas: {len(index_rows)} | Omitidas: {len(skipped)}")

    # --------------------------------------------------------- consolidar splits
    log.info("Consolidando conjuntos...")
    train_df = pd.concat(train_frames, ignore_index=True)
    val_df   = pd.concat(val_frames,   ignore_index=True)
    test_df  = pd.concat(test_frames,  ignore_index=True)

    total = len(train_df) + len(val_df) + len(test_df)
    log.info(f"  train: {len(train_df):,} ({len(train_df)/total:.1%})")
    log.info(f"  val:   {len(val_df):,}   ({len(val_df)/total:.1%})")
    log.info(f"  test:  {len(test_df):,}  ({len(test_df)/total:.1%})")

    # --------------------------------------------------- verificación leakage
    leakage_ok = verify_no_leakage(train_df, val_df, test_df, log, date_col, station_col)
    if not leakage_ok:
        log.error("ABORTANDO: se detectó fuga de información entre conjuntos.")
        sys.exit(1)

    # ----------------------------------------------------------- guardar splits
    splits_dir = ROOT / cfg["output"]["splits_dir"]
    (splits_dir / "_logs").mkdir(parents=True, exist_ok=True)

    for name, frame, pq_key, csv_key in [
        ("train", train_df, "train_parquet", "train_csv"),
        ("val",   val_df,   "val_parquet",   "val_csv"),
        ("test",  test_df,  "test_parquet",  "test_csv"),
    ]:
        pq_path  = ROOT / cfg["output"][pq_key]
        csv_path = ROOT / cfg["output"][csv_key]
        pq_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(pq_path, index=False)
        frame.to_csv(csv_path,    index=False)
        log.info(f"  Guardado {name}: {pq_path.parent.name}/{pq_path.name} ({len(frame):,} filas)")

    # --------------------------------------------------------- split_index.csv
    index_df = pd.DataFrame(index_rows)
    index_path = ROOT / cfg["output"]["split_index"]
    index_df.to_csv(index_path, index=False)
    log.info(f"Índice guardado: {index_path}")

    # ---------------------------------------------------------- split_report.csv
    report = {
        "fecha_ejecucion":      datetime.now().isoformat(timespec="seconds"),
        "estrategia":           cfg["split"]["strategy"],
        "train_ratio":          train_ratio,
        "val_ratio":            val_ratio,
        "test_ratio":           test_ratio,
        "estaciones_incluidas": len(index_rows),
        "estaciones_omitidas":  len(skipped),
        "total_registros":      total,
        "n_train":              len(train_df),
        "n_val":                len(val_df),
        "n_test":               len(test_df),
        "pct_train_real":       round(len(train_df) / total * 100, 2),
        "pct_val_real":         round(len(val_df)   / total * 100, 2),
        "pct_test_real":        round(len(test_df)  / total * 100, 2),
        "leakage_detectado":    not leakage_ok,
        "train_rango_global":   f"{train_df[date_col].min().date()} / {train_df[date_col].max().date()}",
        "val_rango_global":     f"{val_df[date_col].min().date()} / {val_df[date_col].max().date()}",
        "test_rango_global":    f"{test_df[date_col].min().date()} / {test_df[date_col].max().date()}",
    }

    report_path = ROOT / cfg["output"]["split_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([report]).to_csv(report_path, index=False)
    log.info(f"Reporte guardado: {report_path}")

    # ----------------------------------------- resumen de faltantes por split
    log.info("--- Faltantes por conjunto ---")
    for name, frame in [("train", train_df), ("val", val_df), ("test", test_df)]:
        for col in variables:
            pct = frame[col].isna().mean() * 100
            log.info(f"  {name}.{col}: {pct:.2f}% faltantes")

    log.info("=" * 60)
    log.info("División completada exitosamente.")
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="División Train/Val/Test temporal por estación")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Ruta al archivo de configuración YAML",
    )
    args = parser.parse_args()
    run(args.config)
