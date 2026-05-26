"""
Validación de tensores en PyTorch — RES-116

Verifica que los tensores generados por tensor_builder.py cumplen
los requisitos de entrada de los modelos de imputación:

  1. Shapes correctos  : (N, window_size, n_features) para X, mask, delta
  2. Dtypes             : float32 para X/mask/delta, int64 para meta
  3. Sin NaN en X      : los NaN deben estar reemplazados por 0
  4. Máscara binaria   : solo valores 0 y 1 en mask
  5. Delta no negativo : delta >= 0 en todas las posiciones
  6. Consistencia       : X y mask con shape idéntico
  7. DataLoader         : carga un batch sin errores de dimensión

Uso:
    python "Construcción de Tensores/validate_tensors.py"
    python "Construcción de Tensores/validate_tensors.py" --config path/to/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy  # noqa: F401 — debe importarse antes que torch para evitar conflicto de threading MKL
import yaml

ROOT = Path(__file__).resolve().parent.parent

PASS = "PASS"
FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Helpers de logging
# ---------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Checks individuales
# ---------------------------------------------------------------------------

def check_shape(tensor, expected_ndim: int, expected_dim1: int, expected_dim2: int,
                name: str, log: logging.Logger) -> bool:
    """Verifica (N, expected_dim1, expected_dim2)."""
    if tensor.ndim != expected_ndim:
        log.error(f"  {FAIL} {name}: ndim={tensor.ndim}, esperado {expected_ndim}")
        return False
    if tensor.shape[1] != expected_dim1:
        log.error(
            f"  {FAIL} {name}: dim1={tensor.shape[1]}, esperado {expected_dim1} "
            f"(window_size)"
        )
        return False
    if tensor.shape[2] != expected_dim2:
        log.error(
            f"  {FAIL} {name}: dim2={tensor.shape[2]}, esperado {expected_dim2} "
            f"(n_features)"
        )
        return False
    log.info(f"  {PASS} shape {name}: {tuple(tensor.shape)}")
    return True


def check_dtype(tensor, expected_dtype, name: str, log: logging.Logger) -> bool:
    if tensor.dtype != expected_dtype:
        log.error(f"  {FAIL} dtype {name}: {tensor.dtype}, esperado {expected_dtype}")
        return False
    log.info(f"  {PASS} dtype {name}: {tensor.dtype}")
    return True


def check_no_nan(tensor, name: str, log: logging.Logger) -> bool:
    import torch
    if torch.isnan(tensor).any():
        nan_count = torch.isnan(tensor).sum().item()
        log.error(f"  {FAIL} {name}: contiene {nan_count:,} NaN (deben ser 0)")
        return False
    log.info(f"  {PASS} {name}: sin NaN")
    return True


def check_mask_binary(
    mask, name: str, log: logging.Logger,
    obs_val: float = 1.0, miss_val: float = 0.0,
) -> bool:
    unique_vals = mask.unique().tolist()
    invalid = [v for v in unique_vals if v not in (miss_val, obs_val)]
    if invalid:
        log.error(
            f"  {FAIL} {name}: valores fuera de {{{miss_val},{obs_val}}}: {invalid}"
        )
        return False
    obs_pct = mask.mean().item() * 100.0
    log.info(f"  {PASS} {name}: binaria — {obs_pct:.1f}% observados")
    return True


def check_delta_nonneg(delta, name: str, log: logging.Logger) -> bool:
    import torch
    if (delta < 0).any():
        neg_count = (delta < 0).sum().item()
        log.error(f"  {FAIL} {name}: {neg_count:,} valores negativos")
        return False
    max_val = delta.max().item()
    log.info(f"  {PASS} {name}: no negativo — máximo={max_val:.0f} días")
    return True


def check_shape_consistency(X, mask, delta, split: str, log: logging.Logger) -> bool:
    if X.shape != mask.shape:
        log.error(f"  {FAIL} consistencia {split}: X{X.shape} ≠ mask{mask.shape}")
        return False
    if X.shape != delta.shape:
        log.error(f"  {FAIL} consistencia {split}: X{X.shape} ≠ delta{delta.shape}")
        return False
    log.info(f"  {PASS} consistencia shapes X/mask/delta: {tuple(X.shape)}")
    return True


def check_dataloader(
    X, mask, delta, split: str, log: logging.Logger, batch_size: int = 32
) -> bool:
    """Crea un DataLoader y recupera un batch completo sin errores."""
    try:
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        log.warning(f"  SKIP DataLoader {split}: torch.utils.data no disponible")
        return True

    dataset = TensorDataset(X, mask, delta)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    batch_X, batch_mask, batch_delta = next(iter(loader))

    expected_batch = min(batch_size, len(dataset))
    if batch_X.shape[0] != expected_batch:
        log.error(
            f"  {FAIL} DataLoader {split}: batch_size={batch_X.shape[0]}, "
            f"esperado {expected_batch}"
        )
        return False
    if batch_X.shape[1:] != X.shape[1:]:
        log.error(
            f"  {FAIL} DataLoader {split}: dims del batch incorrectas "
            f"{batch_X.shape[1:]} ≠ {X.shape[1:]}"
        )
        return False

    log.info(
        f"  {PASS} DataLoader {split}: batch X={tuple(batch_X.shape)} | "
        f"mask={tuple(batch_mask.shape)} | delta={tuple(batch_delta.shape)}"
    )
    return True


def check_meta_shape(meta, split: str, N: int, log: logging.Logger) -> bool:
    import torch
    if meta.ndim != 2 or meta.shape[1] != 2:
        log.error(f"  {FAIL} meta_{split}: shape={tuple(meta.shape)}, esperado ({N}, 2)")
        return False
    if meta.dtype != torch.int64:
        log.error(f"  {FAIL} meta_{split}: dtype={meta.dtype}, esperado int64")
        return False
    log.info(f"  {PASS} meta_{split}: {tuple(meta.shape)} int64")
    return True


# ---------------------------------------------------------------------------
# Validación de un split
# ---------------------------------------------------------------------------

def validate_split(
    split_name: str,
    cfg: dict,
    window_size: int,
    n_features: int,
    log: logging.Logger,
    obs_val: float = 1.0,
    miss_val: float = 0.0,
    batch_size: int = 32,
) -> tuple[bool, dict]:
    """
    Valida todos los tensores de un split.

    Returns:
        (all_pass, summary_dict)
    """
    import torch

    out = cfg["output"]
    X_path     = ROOT / out[f"X_{split_name}"]
    mask_path  = ROOT / out[f"mask_{split_name}"]
    delta_path = ROOT / out[f"delta_{split_name}"]
    meta_path  = ROOT / out[f"meta_{split_name}"]

    for p in [X_path, mask_path, delta_path, meta_path]:
        if not p.exists():
            log.error(f"  {FAIL} Archivo no encontrado: {p}")
            return False, {}

    def _load(path: Path) -> "torch.Tensor":
        try:
            return torch.load(str(path), weights_only=True)
        except TypeError:
            return torch.load(str(path))

    X     = _load(X_path)
    mask  = _load(mask_path)
    delta = _load(delta_path)
    meta  = _load(meta_path)

    N = X.shape[0] if X.ndim >= 1 else 0

    results = [
        check_shape(X,     3, window_size, n_features, f"X_{split_name}",     log),
        check_shape(mask,  3, window_size, n_features, f"mask_{split_name}",  log),
        check_shape(delta, 3, window_size, n_features, f"delta_{split_name}", log),
        check_dtype(X,     torch.float32,  f"X_{split_name}",     log),
        check_dtype(mask,  torch.float32,  f"mask_{split_name}",  log),
        check_dtype(delta, torch.float32,  f"delta_{split_name}", log),
        check_no_nan(X,    f"X_{split_name}",     log),
        check_mask_binary(mask,  f"mask_{split_name}",  log, obs_val, miss_val),
        check_delta_nonneg(delta, f"delta_{split_name}", log),
        check_shape_consistency(X, mask, delta, split_name, log),
        check_meta_shape(meta, split_name, N, log),
        check_dataloader(X, mask, delta, split_name, log, batch_size),
    ]

    all_pass = all(results)
    n_pass = sum(results)
    n_fail = len(results) - n_pass

    summary = {
        "split":       split_name,
        "n_secuencias": N,
        "shape_X":     str(tuple(X.shape)),
        "checks_pass": n_pass,
        "checks_fail": n_fail,
        "resultado":   PASS if all_pass else FAIL,
        "obs_pct":     round(float(mask.mean()) * 100, 2),
        "delta_max":   round(float(delta.max()), 1),
    }

    return all_pass, summary


# ---------------------------------------------------------------------------
# Pipeline de validación
# ---------------------------------------------------------------------------

def run(config_path: Path) -> bool:
    cfg = load_config(config_path)
    log = setup_logging()

    variables   = cfg["input"]["variables"]
    window_size = cfg["sequence"]["window_size"]
    n_features  = len(variables)
    obs_val     = float(cfg["masks"]["observed_value"])
    miss_val    = float(cfg["masks"]["missing_value"])
    batch_size  = cfg["validation"]["batch_size"]

    log.info("=" * 60)
    log.info("Validación de Tensores — PyTorch")
    log.info(f"window_size={window_size} | n_features={n_features} {variables}")
    log.info(f"mask: obs={obs_val} miss={miss_val} | batch_size={batch_size}")
    log.info("=" * 60)

    overall_pass = True
    summaries: list[dict] = []

    for split_name in cfg["splits"]:
        log.info(f"\n{'─'*50}")
        log.info(f"Split: {split_name.upper()}")
        log.info(f"{'─'*50}")

        split_pass, summary = validate_split(
            split_name, cfg, window_size, n_features, log,
            obs_val=obs_val, miss_val=miss_val, batch_size=batch_size,
        )
        overall_pass = overall_pass and split_pass
        summaries.append(summary)

        verdict = PASS if split_pass else FAIL
        log.info(f"  → {verdict} ({summary.get('checks_pass',0)} checks OK)")

    # --- Tabla resumen -------------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("RESUMEN DE VALIDACIÓN")
    log.info(f"{'Split':<8} {'N sec':>10} {'Shape X':<26} {'Obs%':>7} {'Resultado':>10}")
    log.info("─" * 65)
    for s in summaries:
        log.info(
            f"{s['split']:<8} {s.get('n_secuencias',0):>10,} "
            f"{s.get('shape_X',''):<26} {s.get('obs_pct',0):>6.1f}%  "
            f"{s.get('resultado','?'):>10}"
        )

    log.info("=" * 60)
    verdict = "TODAS LAS VALIDACIONES PASARON" if overall_pass else "HAY FALLOS EN LA VALIDACIÓN"
    log.info(f"RESULTADO FINAL: {verdict}")
    log.info("=" * 60)

    return overall_pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validación de tensores PyTorch para imputación hidrometeorológica"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Ruta al archivo de configuración YAML",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    success = run(args.config)
    sys.exit(0 if success else 1)
