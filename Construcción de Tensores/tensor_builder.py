"""
Construcción de Tensores — RES-113

Transforma los datasets preprocesados (train/val/test) en tensores PyTorch
compatibles con los modelos de imputación generativa:

  X_train, X_val, X_test       : (N, window_size, n_features)  — valores
  mask_train/val/test           : (N, window_size, n_features)  — 1=obs, 0=NaN
  delta_train/val/test          : (N, window_size, n_features)  — días desde
                                   última observación (para BRITS)
  meta_train/val/test           : (N, 2) — [station_idx, start_date_ordinal]

Framework: PyTorch
Modelos objetivo: BRITS, SAITS, CSDI, LSTM/GRU, VAE/Autoencoders

Uso:
    python "Construcción de Tensores/tensor_builder.py"
    python "Construcción de Tensores/tensor_builder.py" --config path/to/config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers de configuración y logging
# ---------------------------------------------------------------------------

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
# Pipeline por split
# ---------------------------------------------------------------------------

def process_split(
    split_name: str,
    parquet_path: Path,
    cfg: dict,
    log: logging.Logger,
) -> tuple[dict, list[str]]:
    """
    Carga un split, genera secuencias, máscaras y deltas, guarda los .pt.

    Returns:
        (metrics_dict, stations_list)
    """
    from sequence_generator import SequenceGenerator
    from mask_generator import MaskGenerator
    import torch

    variables   = cfg["input"]["variables"]
    date_col    = cfg["input"]["date_col"]
    station_col = cfg["input"]["station_col"]
    window_size = cfg["sequence"]["window_size"]
    stride      = cfg["sequence"]["stride"]
    max_gap     = cfg["sequence"]["max_gap_days"]
    obs_val     = cfg["masks"]["observed_value"]
    miss_val    = cfg["masks"]["missing_value"]

    log.info(f"Cargando: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    df[date_col] = pd.to_datetime(df[date_col])
    n_rows = len(df)
    n_stations = df[station_col].nunique()
    log.info(f"  {n_rows:,} filas | {n_stations} estaciones")

    # --- Generación de secuencias (RES-114) --------------------------------
    gen = SequenceGenerator(window_size=window_size, stride=stride, max_gap_days=max_gap)
    sequences, day_diffs, meta, stations = gen.generate(
        df, variables, date_col, station_col, log
    )

    if sequences is None:
        log.error(f"No se generaron secuencias para '{split_name}'. Abortando.")
        sys.exit(1)

    N = len(sequences)
    log.info(f"  Secuencias totales: {N:,} | shape: {sequences.shape}")

    # --- Generación de máscaras y delta (RES-115) --------------------------
    mask_gen = MaskGenerator(observed_value=obs_val, missing_value=miss_val)
    X, mask, delta = mask_gen.generate(sequences, day_diffs)

    obs_stats = mask_gen.mask_stats(mask, feature_names=variables)
    log.info("  Tasa de observación por variable:")
    for var, pct in obs_stats.items():
        log.info(f"    {var}: {pct:.1f}%")

    # --- Guardar tensores PyTorch -------------------------------------------
    out = cfg["output"]
    tensors = {
        f"X_{split_name}":     torch.from_numpy(X),
        f"mask_{split_name}":  torch.from_numpy(mask),
        f"delta_{split_name}": torch.from_numpy(delta),
        f"meta_{split_name}":  torch.from_numpy(meta),
    }

    for key, tensor in tensors.items():
        path = ROOT / out[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(tensor, path)
        size_mb = path.stat().st_size / 1_048_576
        log.info(f"  Guardado {key}: {path.name} ({size_mb:.1f} MB) shape={tuple(tensor.shape)}")

    metrics = {
        "split":          split_name,
        "input_filas":    n_rows,
        "estaciones":     n_stations,
        "n_secuencias":   N,
        "shape_X":        str(tuple(X.shape)),
        "shape_mask":     str(tuple(mask.shape)),
        "shape_delta":    str(tuple(delta.shape)),
        **{f"obs_{v}_pct": obs_stats.get(v, -1) for v in variables},
        "obs_global_pct": obs_stats.get("global", -1),
        "delta_max_dias": float(delta.max()),
    }
    return metrics, stations


# ---------------------------------------------------------------------------
# Orchestrador principal
# ---------------------------------------------------------------------------

def run(config_path: Path) -> None:
    cfg = load_config(config_path)
    log = setup_logging(ROOT / cfg["output"]["log_path"])

    log.info("=" * 60)
    log.info("Construcción de Tensores — inicio")
    log.info(f"Framework  : {cfg.get('framework', 'pytorch').upper()}")
    log.info(f"window_size: {cfg['sequence']['window_size']}")
    log.info(f"stride     : {cfg['sequence']['stride']}")
    log.info(f"max_gap    : {cfg['sequence']['max_gap_days']} días")
    log.info(f"variables  : {cfg['input']['variables']}")
    log.info("=" * 60)

    (ROOT / cfg["output"]["tensors_dir"]).mkdir(parents=True, exist_ok=True)

    report_rows: list[dict] = []
    all_stations: list[str] = []

    for split_name in cfg["splits"]:
        log.info(f"\n{'─'*50}")
        log.info(f"Split: {split_name.upper()}")
        log.info(f"{'─'*50}")

        parquet_path = ROOT / cfg["input"][f"{split_name}_parquet"]
        metrics, stations = process_split(split_name, parquet_path, cfg, log)
        report_rows.append(metrics)

        if not all_stations:
            all_stations = stations

    # --- Metadata JSON -------------------------------------------------------
    metadata = {
        "generado_en":   datetime.now().isoformat(timespec="seconds"),
        "framework":     cfg.get("framework", "pytorch"),
        "config": {
            "window_size":    cfg["sequence"]["window_size"],
            "stride":         cfg["sequence"]["stride"],
            "max_gap_days":   cfg["sequence"]["max_gap_days"],
            "variables":      cfg["input"]["variables"],
            "observed_value": cfg["masks"]["observed_value"],
            "missing_value":  cfg["masks"]["missing_value"],
        },
        "formato_tensores": {
            "X":     "(N, window_size, n_features) float32 — NaN reemplazado con 0",
            "mask":  "(N, window_size, n_features) float32 — 1=observado, 0=faltante",
            "delta": "(N, window_size, n_features) float32 — días desde última obs (BRITS)",
            "meta":  "(N, 2) int64 — [station_idx, start_date_ordinal_days]",
        },
        "compatibilidad_modelos": [
            "BRITS  — X, mask, delta (forward y backward en el modelo)",
            "SAITS  — X, mask",
            "CSDI   — X, mask",
            "LSTM/GRU — X (máscara en función de pérdida)",
            "VAE/Autoencoder — X, mask (VAE usa mask en el ELBO loss)",
        ],
        "n_features":    len(cfg["input"]["variables"]),
        "feature_names": cfg["input"]["variables"],
        "n_estaciones":  len(all_stations),
        "estaciones":    all_stations,
        "metricas_splits": report_rows,
    }

    meta_path = ROOT / cfg["output"]["metadata"]
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    log.info(f"\nMetadata JSON: {meta_path}")

    # --- Reporte CSV ---------------------------------------------------------
    report_df = pd.DataFrame(report_rows)
    report_path = ROOT / cfg["output"]["report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(report_path, index=False)
    log.info(f"Reporte CSV : {report_path}")

    # --- Resumen final -------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("Construcción completada exitosamente.")
    log.info(f"{'Split':<8} {'N sec':>10} {'Shape X':<26} {'Obs%':>7}")
    log.info("─" * 57)
    for row in report_rows:
        log.info(
            f"{row['split']:<8} {row['n_secuencias']:>10,} "
            f"{row['shape_X']:<26} {row['obs_global_pct']:>6.1f}%"
        )
    log.info("=" * 60)
    log.info(f"Tensores en: {ROOT / cfg['output']['tensors_dir']}")
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Construcción de tensores PyTorch — imputación hidrometeorológica"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Ruta al archivo de configuración YAML",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    run(args.config)
