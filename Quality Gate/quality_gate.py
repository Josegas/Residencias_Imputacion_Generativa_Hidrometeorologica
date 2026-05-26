"""
quality_gate.py
===============
Quality Gate CRISP-ML(Q) — Etapa 8 del pipeline (RES-35)

Verifica la calidad del dataset procesado antes de ejecutar el módulo
de imputación. Evalúa criterios críticos (detienen el pipeline si fallan)
y criterios de advertencia (se registran pero no bloquean).

Criterios CRÍTICOS
------------------
- physical_limits        : ningún valor observado fuera de rangos físicos
- min_valid_obs          : cada estación tiene >= min_valid_obs_per_station
- tmax_gte_tmin_observed : tmax >= tmin en todos los pares observados

Criterios WARNING
-----------------
- missing_rate      : tasa de faltantes por variable dentro del umbral
- kpss_stationarity : las series preservan estacionariedad (KPSS α=0.05)

Uso
---
    python "Quality Gate/quality_gate.py"
    python "Quality Gate/quality_gate.py" --config ruta/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from statsmodels.tsa.stattools import kpss

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

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
    return logging.getLogger("quality_gate")


# ---------------------------------------------------------------------------
# Scalers — inverse transform para verificaciones en escala original
# ---------------------------------------------------------------------------

def _load_scalers(cfg: dict) -> dict:
    """Carga los scalers desde models/scalers/ para invertir la normalización."""
    scalers_dir = ROOT / cfg["scalers"]["dir"]
    scalers = {}
    for var in cfg["variables"]:
        pkl = scalers_dir / f"{cfg['scalers']['prefix']}{var}.pkl"
        if pkl.exists():
            with pkl.open("rb") as f:
                scalers[var] = pickle.load(f)
    return scalers


def _to_original_scale(df: pd.DataFrame, variables: list[str],
                        scalers: dict) -> pd.DataFrame:
    """Devuelve un DataFrame con las variables en escala original."""
    df_orig = df.copy()
    for var in variables:
        if var not in scalers or var not in df.columns:
            continue
        col = df[var].values.reshape(-1, 1)
        valid = ~np.isnan(col.ravel())
        if valid.any():
            df_orig.loc[valid, var] = scalers[var].inverse_transform(
                col[valid].reshape(-1, 1)
            ).ravel()
    return df_orig


# ---------------------------------------------------------------------------
# Verificaciones críticas
# ---------------------------------------------------------------------------

def check_physical_limits(df: pd.DataFrame, variables: list[str],
                           limits: dict, log: logging.Logger) -> tuple[bool, list[dict]]:
    """Verifica que ningún valor observado esté fuera de los límites físicos."""
    rows = []
    passed = True
    for var in variables:
        if var not in limits or var not in df.columns:
            continue
        lo = limits[var].get("min")
        hi = limits[var].get("max")
        col = df[var].dropna()
        n_below = int((col < lo).sum()) if lo is not None else 0
        n_above = int((col > hi).sum()) if hi is not None else 0
        n_violations = n_below + n_above
        ok = n_violations == 0
        if not ok:
            passed = False
            log.error(
                f"[CRÍTICO] physical_limits {var}: "
                f"{n_below} valores < {lo}, {n_above} valores > {hi}"
            )
        else:
            log.info(f"[OK]      physical_limits {var}: sin violaciones")
        rows.append({
            "criterio": "physical_limits", "variable": var,
            "resultado": "PASS" if ok else "FAIL",
            "detalle": f"n_below={n_below}, n_above={n_above}",
        })
    return passed, rows


def check_min_valid_obs(df: pd.DataFrame, col_sta: str, variables: list[str],
                        min_obs: int, log: logging.Logger) -> tuple[bool, list[dict]]:
    """Verifica que cada estación tenga suficientes observaciones válidas."""
    rows = []
    insuficientes = []
    for sta, grp in df.groupby(col_sta):
        valid = grp[variables].notna().any(axis=1).sum()
        if valid < min_obs:
            insuficientes.append(sta)
    passed = len(insuficientes) == 0
    if not passed:
        log.error(
            f"[CRÍTICO] min_valid_obs: {len(insuficientes)} estaciones con "
            f"< {min_obs} obs válidas: {insuficientes[:10]}{'...' if len(insuficientes)>10 else ''}"
        )
    else:
        log.info(f"[OK]      min_valid_obs: todas las estaciones >= {min_obs} obs")
    rows.append({
        "criterio": "min_valid_obs", "variable": "all",
        "resultado": "PASS" if passed else "FAIL",
        "detalle": f"estaciones_insuficientes={len(insuficientes)}",
    })
    return passed, rows


def check_tmax_gte_tmin_observed(df: pd.DataFrame, variables: list[str],
                                  log: logging.Logger) -> tuple[bool, list[dict]]:
    """Verifica tmax >= tmin en todos los pares observados."""
    if "tmax" not in variables or "tmin" not in variables:
        return True, []
    both = df[["tmax", "tmin"]].dropna()
    inverted = (both["tmax"] < both["tmin"]).sum()
    passed = int(inverted) == 0
    if not passed:
        log.error(
            f"[CRÍTICO] tmax_gte_tmin_observed: {inverted} pares observados "
            "con tmax < tmin — dato corrupto no resuelto por cleaning."
        )
    else:
        log.info(f"[OK]      tmax_gte_tmin_observed: sin inversiones")
    return passed, [{
        "criterio": "tmax_gte_tmin_observed", "variable": "tmax/tmin",
        "resultado": "PASS" if passed else "FAIL",
        "detalle": f"pares_invertidos={inverted}",
    }]


# ---------------------------------------------------------------------------
# Verificaciones de advertencia
# ---------------------------------------------------------------------------

def check_missing_rate(df: pd.DataFrame, variables: list[str],
                        thresholds: dict, log: logging.Logger) -> list[dict]:
    """Calcula tasa de faltantes por variable y avisa si supera el umbral."""
    rows = []
    for var in variables:
        if var not in df.columns:
            continue
        rate = df[var].isna().mean()
        threshold = thresholds.get(var, 1.0)
        ok = rate <= threshold
        level = "OK     " if ok else "WARNING"
        log.info(
            f"[{level}] missing_rate {var}: {rate:.1%} "
            f"({'<= ' if ok else '> '}{threshold:.0%})"
        )
        rows.append({
            "criterio": "missing_rate", "variable": var,
            "resultado": "PASS" if ok else "WARNING",
            "detalle": f"rate={rate:.4f}, threshold={threshold:.4f}",
        })
    return rows


def check_kpss_stationarity(df: pd.DataFrame, col_sta: str, variables: list[str],
                             significance: float, station_threshold: float,
                             log: logging.Logger) -> list[dict]:
    """
    Aplica KPSS por variable sobre una muestra representativa de estaciones.
    Reporta la tasa de preservación de estacionariedad.
    """
    rows = []
    for var in variables:
        if var not in df.columns:
            continue
        preserved = 0
        total = 0
        for _, grp in df.groupby(col_sta):
            series = grp[var].dropna()
            if len(series) < 30:
                continue
            try:
                _, p_val, _, _ = kpss(series.values, regression="c", nlags="auto")
                total += 1
                if p_val > significance:
                    preserved += 1
            except Exception:
                pass
        rate = preserved / total if total > 0 else 0.0
        ok = rate >= station_threshold
        level = "OK     " if ok else "WARNING"
        log.info(
            f"[{level}] kpss {var}: {preserved}/{total} estaciones "
            f"estacionarias ({rate:.1%})"
        )
        rows.append({
            "criterio": "kpss_stationarity", "variable": var,
            "resultado": "PASS" if ok else "WARNING",
            "detalle": f"preserved={preserved}, total={total}, rate={rate:.4f}",
        })
    return rows


# ---------------------------------------------------------------------------
# Visualizaciones
# ---------------------------------------------------------------------------

def _plot_results(report_rows: list[dict], cfg: dict, log: logging.Logger) -> None:
    """Genera figuras de resumen del Quality Gate y las guarda en reports/quality_gate/figuras/."""
    if not _HAS_MPL:
        log.warning("matplotlib no disponible — figuras omitidas.")
        return

    fig_dir = (ROOT / cfg["output"]["report"]).parent / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)

    COLOR = {"PASS": "#2e7d32", "WARNING": "#ef6c00", "FAIL": "#c62828"}
    df = pd.DataFrame(report_rows)

    # ── Fig 1: Estado por criterio/variable ──────────────────────────────────
    labels  = [f"{r['criterio']}  [{r['variable']}]" for _, r in df.iterrows()]
    colors  = [COLOR.get(r["resultado"], "#90a4ae") for _, r in df.iterrows()]
    fig, ax = plt.subplots(figsize=(10, max(4, len(df) * 0.45)))
    bars    = ax.barh(labels, [1] * len(df), color=colors, height=0.6)
    for bar, (_, r) in zip(bars, df.iterrows()):
        ax.text(0.5, bar.get_y() + bar.get_height() / 2,
                r["resultado"], ha="center", va="center",
                color="white", fontweight="bold", fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Quality Gate — Estado por criterio", fontsize=12, pad=12)
    ax.invert_yaxis()
    plt.tight_layout()
    fig.savefig(fig_dir / "qg_criterios.png", dpi=150)
    plt.close(fig)
    log.info(f"  figura: {(fig_dir / 'qg_criterios.png').relative_to(ROOT)}")

    # ── Fig 2: Tasa de faltantes vs umbral ──────────────────────────────────
    mr = df[df["criterio"] == "missing_rate"].copy()
    if not mr.empty:
        mr["rate"]      = mr["detalle"].str.extract(r"rate=([\d.]+)").astype(float)
        mr["threshold"] = mr["detalle"].str.extract(r"threshold=([\d.]+)").astype(float)
        x   = list(range(len(mr)))
        w   = 0.35
        fig, ax = plt.subplots(figsize=(7, 4))
        b1 = ax.bar([i - w / 2 for i in x], mr["rate"] * 100, w,
                    label="Tasa real (%)", color="#1565c0")
        ax.bar([i + w / 2 for i in x], mr["threshold"] * 100, w,
               label="Umbral máximo (%)", color="#90a4ae", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(mr["variable"].tolist())
        ax.set_ylabel("Tasa de faltantes (%)")
        ax.set_title("Tasa de faltantes vs umbral máximo por variable")
        ax.legend()
        ax.set_ylim(0, 110)
        for bar in b1:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=8)
        plt.tight_layout()
        fig.savefig(fig_dir / "qg_missing_rate.png", dpi=150)
        plt.close(fig)
        log.info(f"  figura: {(fig_dir / 'qg_missing_rate.png').relative_to(ROOT)}")

    # ── Fig 3: Estacionariedad KPSS ─────────────────────────────────────────
    kp = df[df["criterio"] == "kpss_stationarity"].copy()
    if not kp.empty:
        kp["rate"]   = kp["detalle"].str.extract(r"rate=([\d.]+)").astype(float)
        colors_kp    = [COLOR.get(r["resultado"], "#90a4ae") for _, r in kp.iterrows()]
        fig, ax = plt.subplots(figsize=(7, 4))
        bars = ax.bar(kp["variable"].tolist(), kp["rate"] * 100, color=colors_kp)
        threshold_pct = int(cfg["kpss_station_threshold"] * 100)
        ax.axhline(threshold_pct, color="#c62828", linestyle="--", linewidth=1.2,
                   label=f"Umbral {threshold_pct}%")
        ax.set_ylabel("Estaciones estacionarias (%)")
        ax.set_title("Estacionariedad KPSS por variable (pre-imputación)")
        ax.set_ylim(0, 110)
        ax.legend()
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=9)
        plt.tight_layout()
        fig.savefig(fig_dir / "qg_kpss.png", dpi=150)
        plt.close(fig)
        log.info(f"  figura: {(fig_dir / 'qg_kpss.png').relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quality Gate CRISP-ML(Q) — verificación pre-imputación"
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()

    cfg = _load_config(args.config)
    log = _setup_logging(cfg)

    log.info("=" * 60)
    log.info("INICIO — Quality Gate CRISP-ML(Q)")
    log.info("=" * 60)

    input_path = ROOT / cfg["input"]["dataset"]
    if not input_path.exists():
        log.error(f"Dataset no encontrado: {input_path}")
        log.error("Ejecuta primero las etapas 1-7 del pipeline.")
        sys.exit(1)

    df = pd.read_parquet(input_path)
    log.info(f"Dataset cargado : {input_path.relative_to(ROOT)}")
    log.info(f"Filas           : {len(df):,}  |  Columnas: {list(df.columns)}")

    variables = cfg["variables"]
    col_sta   = cfg["columns"]["station"]
    report_rows: list[dict] = []
    critical_failures = 0

    # Inverse-transform para verificaciones que requieren escala original
    scalers = _load_scalers(cfg)
    if scalers:
        log.info(f"Scalers cargados : {list(scalers.keys())}")
        df_orig = _to_original_scale(df, variables, scalers)
    else:
        log.warning("Scalers no encontrados — verificaciones en escala escalada.")
        df_orig = df

    # ── Criterios CRÍTICOS ──────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Criterios CRÍTICOS (en escala original)")
    log.info("-" * 40)

    passed, rows = check_physical_limits(
        df_orig, variables, cfg["physical_limits"], log
    )
    report_rows.extend(rows)
    if not passed:
        critical_failures += 1

    passed, rows = check_min_valid_obs(
        df, col_sta, variables, cfg["min_valid_obs_per_station"], log
    )
    report_rows.extend(rows)
    if not passed:
        critical_failures += 1

    passed, rows = check_tmax_gte_tmin_observed(df_orig, variables, log)
    report_rows.extend(rows)
    if not passed:
        critical_failures += 1

    # ── Criterios WARNING ───────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Criterios WARNING")
    log.info("-" * 40)

    rows = check_missing_rate(df, variables, cfg["missing_rate_thresholds"], log)
    report_rows.extend(rows)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rows = check_kpss_stationarity(
            df, col_sta, variables, cfg["kpss_significance"],
            cfg["kpss_station_threshold"], log
        )
    report_rows.extend(rows)

    # ── Guardar reporte ─────────────────────────────────────────────────────
    report_path = ROOT / cfg["output"]["report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report_rows).to_csv(report_path, index=False)
    log.info(f"Reporte guardado: {report_path.relative_to(ROOT)}")

    # ── Figuras ─────────────────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Generando figuras")
    log.info("-" * 40)
    _plot_results(report_rows, cfg, log)

    # ── Resultado final ─────────────────────────────────────────────────────
    log.info("=" * 60)
    if critical_failures > 0:
        log.error(
            f"QUALITY GATE FALLIDO — {critical_failures} criterio(s) crítico(s) "
            "no superado(s). Corrige los errores antes de continuar."
        )
        log.info("=" * 60)
        sys.exit(1)
    else:
        log.info("QUALITY GATE SUPERADO — dataset aprobado para imputación.")
        log.info("=" * 60)


if __name__ == "__main__":
    main()
