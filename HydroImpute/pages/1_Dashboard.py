"""Dashboard — estado actual del pipeline y métricas clave."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from utils import ROOT, LOGO_PATH, VARIABLES, VAR_LABELS, get_pipeline

st.set_page_config(page_title="Dashboard · HydroImpute", layout="wide")

with st.sidebar:
    st.image(str(LOGO_PATH), width=110)
    st.title("HydroImpute")
    st.caption(
        "Imputación Generativa Hidrometeorológica\n"
        "Laboratorio de Geomática y Teledetección\n"
        "TECNM Campus Culiacán"
    )
    st.divider()
    pipeline = get_pipeline()
    if pipeline:
        st.success("Modelo BiGRU-opt listo")
    else:
        st.error("Modelo no disponible")

st.title("Dashboard")
st.markdown("Estado actual del pipeline y métricas clave de cada etapa.")

# ---------------------------------------------------------------------------
# Estado de etapas (check outputs)
# ---------------------------------------------------------------------------

STAGES = [
    (1,  "Obtención de datos crudos",      ROOT / "data/raw/conagua_smn/estado=sin/_meta/stations_sin.csv"),
    (2,  "Estructuración del dataset",      ROOT / "data/interim/organized"),
    (3,  "Validación y limpieza",           ROOT / "data/cleaned/organized"),
    (4,  "Preprocesamiento",                ROOT / "models/scalers/scaler_precip.pkl"),
    (5,  "Dataset Final Procesado",         ROOT / "data/processed/dataset_final.parquet"),
    (6,  "División Train-Val-Test",         ROOT / "data/splits/split_index.csv"),
    (7,  "Construcción de Tensores",        ROOT / "data/tensors/X_train.pt"),
    (8,  "Quality Gate",                    ROOT / "reports/quality_gate/quality_gate_report.csv"),
    (9,  "Imputación Generativa",           ROOT / "data/imputed/dataset_imputado.parquet"),
    (10, "Validación Estadística",          ROOT / "reports/validacion_estadistica/metricas_imputacion.csv"),
    (11, "Monitoreo del modelo",            ROOT / "reports/monitoreo/drift_report.csv"),
    (12, "Análisis y Exportación",          ROOT / "data/export/dataset_imputado.csv"),
]

st.subheader("Estado de las etapas")

cols = st.columns([1, 5, 2])
cols[0].markdown("**Etapa**")
cols[1].markdown("**Nombre**")
cols[2].markdown("**Estado**")

for stage_id, name, output in STAGES:
    done = Path(output).exists()
    c0, c1, c2 = st.columns([1, 5, 2])
    c0.markdown(f"**{stage_id:02d}**")
    c1.markdown(name)
    c2.markdown("**Completada**" if done else "Pendiente")

st.divider()

# ---------------------------------------------------------------------------
# Última ejecución del pipeline
# ---------------------------------------------------------------------------

st.subheader("Última ejecución del pipeline")
log_dir = ROOT / "data/pipeline_logs"
logs = sorted(log_dir.glob("pipeline_run_*.log"), reverse=True) if log_dir.exists() else []

if logs:
    last_log = logs[0]
    ts = last_log.stem.replace("pipeline_run_", "").replace("_", " ")
    st.markdown(f"**Fecha/hora:** `{ts}`")
    with st.expander("Ver log completo"):
        st.code(last_log.read_text(encoding="utf-8", errors="replace")[-5000:],
                language="")
else:
    st.info("No se han encontrado logs de ejecución del pipeline.")

st.divider()

# ---------------------------------------------------------------------------
# Métricas de cobertura (Etapa 10)
# ---------------------------------------------------------------------------

st.subheader("Cobertura de imputación (Etapa 10)")
cov_path = ROOT / "reports/validacion_estadistica/metricas_imputacion.csv"
if cov_path.exists():
    cov = pd.read_csv(cov_path)
    cov["variable"] = cov["variable"].map(VAR_LABELS).fillna(cov["variable"])
    cov["tasa_cobertura"] = (cov["tasa_cobertura"] * 100).round(2)
    cov = cov.rename(columns={
        "variable": "Variable",
        "nan_original": "NaN originales",
        "nan_rellenados": "NaN rellenados",
        "nan_residual": "NaN residuales",
        "tasa_cobertura": "Cobertura (%)",
    })
    cols_show = [c for c in ["Variable","NaN originales","NaN rellenados","NaN residuales","Cobertura (%)"] if c in cov.columns]
    st.dataframe(cov[cols_show], hide_index=True, use_container_width=True)
else:
    st.info("Ejecuta la Etapa 10 para ver métricas de cobertura.")

st.divider()

# ---------------------------------------------------------------------------
# Quality Gate (Etapa 8)
# ---------------------------------------------------------------------------

st.subheader("Quality Gate (Etapa 8)")
qg_path = ROOT / "reports/quality_gate/quality_gate_report.csv"
if qg_path.exists():
    qg = pd.read_csv(qg_path)
    n_pass = (qg["resultado"] == "PASS").sum()
    n_warn = (qg["resultado"] == "WARNING").sum()
    n_fail = (qg["resultado"] == "FAIL").sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("PASS", n_pass)
    c2.metric("WARNING", n_warn)
    c3.metric("FAIL", n_fail)
    with st.expander("Ver reporte completo"):
        st.dataframe(qg, hide_index=True, use_container_width=True)
else:
    st.info("Ejecuta la Etapa 8 para ver el reporte del Quality Gate.")

st.divider()

# ---------------------------------------------------------------------------
# Monitoreo PSI (Etapa 11)
# ---------------------------------------------------------------------------

st.subheader("Drift distribucional PSI (Etapa 11)")
drift_path = ROOT / "reports/monitoreo/drift_report.csv"
if drift_path.exists():
    drift = pd.read_csv(drift_path)
    last_decade = drift[drift["w_start"] == drift["w_start"].max()]
    alerts = last_decade[last_decade["psi_nivel"] == "CRITICAL"]
    if alerts.empty:
        st.success("Sin alertas de reentrenamiento en la ventana más reciente.")
    else:
        for _, row in alerts.iterrows():
            st.warning(
                f"RETRAIN ALERT — {row['variable']} "
                f"ventana {row['ventana']}: PSI={row['psi']:.4f}"
            )
    with st.expander("Ver reporte completo de drift"):
        st.dataframe(drift, hide_index=True, use_container_width=True)
else:
    st.info("Ejecuta la Etapa 11 para ver el reporte de monitoreo.")
