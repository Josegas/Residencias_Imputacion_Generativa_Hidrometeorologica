"""Datos propios — carga un archivo y ejecuta el pipeline completo."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from utils import ROOT, LOGO_PATH, PIPELINE_DIR, VARIABLES, VAR_LABELS, get_pipeline, archive_reports

INGEST_SCRIPT   = PIPELINE_DIR / "ingest_external.py"
PIPELINE_SCRIPT = PIPELINE_DIR / "run_pipeline.py"

# Directorio donde la Etapa 2 espera los .txt de CONAGUA
RAW_TXT_DIR = ROOT / "data" / "raw" / "conagua_smn" / "estado=sin" \
              / "fuente=normales_climatologicas" / "producto=diarios_txt"

# Flujo A — archivos planos (CSV / Excel / Parquet en escala original)
SKIP_PLANO   = "1,2,6,7"
FROM_PLANO   = "3"

# Flujo A2 — Parquet ya procesado (dataset_final.parquet, salida de Etapa 5)
FROM_PARQUET_PROC = "8"

# Flujo B — archivos .txt formato CONAGUA
SKIP_CONAGUA = "1,6,7"
FROM_CONAGUA = "2"

DATASET_FINAL_PATH = ROOT / "data" / "processed" / "dataset_final.parquet"

ETAPAS_PLANO = [
    (3, "Limpieza y validación"), (4, "Normalización"), (5, "Dataset final"),
    (8, "Quality Gate"), (9, "Imputación"), (10, "Validación"),
    (11, "Monitoreo"), (12, "Exportación"),
]
ETAPAS_PARQUET_PROC = [
    (8, "Quality Gate"), (9, "Imputación"), (10, "Validación"),
    (11, "Monitoreo"), (12, "Exportación"),
]
ETAPAS_CONAGUA = [
    (2, "Estructuración"), (3, "Limpieza y validación"), (4, "Normalización"),
    (5, "Dataset final"), (8, "Quality Gate"), (9, "Imputación"),
    (10, "Validación"), (11, "Monitoreo"), (12, "Exportación"),
]

st.set_page_config(page_title="Datos propios · HydroImpute", layout="wide")

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

st.title("Ejecutar con datos propios")
st.markdown(
    "Carga tu propio dataset y ejecuta el pipeline completo: "
    "limpieza, normalización, Quality Gate, imputación, validación y exportación."
)
st.info(
    "Las etapas de entrenamiento (División train-val-test y Construcción de tensores) "
    "se omiten automáticamente — el modelo BiGRU-opt ya está entrenado.",
    icon="ℹ️",
)

st.divider()

# ---------------------------------------------------------------------------
# Selector de formato de entrada
# ---------------------------------------------------------------------------

modo = st.radio(
    "Tipo de archivo",
    options=["Archivo plano (CSV / Excel / Parquet / TXT)", "Archivos .txt formato CONAGUA/SMN"],
    horizontal=True,
)
es_conagua = modo.startswith("Archivos")

if es_conagua:
    etapas_info = ETAPAS_CONAGUA
elif "parquet_procesado" in dir() and parquet_procesado:
    etapas_info = ETAPAS_PARQUET_PROC
else:
    etapas_info = ETAPAS_PLANO
st.caption(
    "Etapas que se ejecutarán: "
    + "  →  ".join(f"**{e}** {n}" for e, n in etapas_info)
)

st.divider()

# ---------------------------------------------------------------------------
# Paso 1 — Cargar datos
# ---------------------------------------------------------------------------

st.header("1 · Cargar datos")

if es_conagua:
    st.markdown(
        "Sube uno o varios archivos `.txt` de CONAGUA/SMN (un archivo por estación). "
        "El ID de estación se extrae automáticamente del nombre del archivo (`dia25001.txt → 25001`)."
    )
    uploaded_files = st.file_uploader(
        "Selecciona archivos .txt de CONAGUA",
        type=["txt"],
        accept_multiple_files=True,
    )
    uploaded = None
    if not uploaded_files:
        st.info("Sube al menos un archivo .txt para comenzar.")
        st.stop()
    names = [f.name for f in uploaded_files]
    duplicados = [n for n in set(names) if names.count(n) > 1]
    if duplicados:
        st.error(
            f"Hay archivos con nombre duplicado: **{', '.join(sorted(duplicados))}**. "
            "Cada estación debe aparecer una sola vez."
        )
        st.stop()

    n_files = len(uploaded_files)
    st.success(f"**{n_files} archivo{'s' if n_files != 1 else ''}** seleccionado{'s' if n_files != 1 else ''}.")

else:
    with st.expander("Formato requerido"):
        st.markdown(
            "| Columna | Tipo | Descripción |\n"
            "|---------|------|-------------|\n"
            "| `estacion` | str/int | ID de la estación |\n"
            "| `date` | fecha | YYYY-MM-DD |\n"
            "| `precip` | float | Precipitación en mm (`NaN` = faltante) |\n"
            "| `evap` | float | Evaporación en mm (`NaN` = faltante) |\n"
            "| `tmax` | float | Temperatura máxima en °C (`NaN` = faltante) |\n"
            "| `tmin` | float | Temperatura mínima en °C (`NaN` = faltante) |\n\n"
            "Los archivos `.txt` deben ser tablas planas con separador auto-detectado "
            "(coma, tabulador, punto y coma o espacio). "
            "Para archivos `.txt` en formato CONAGUA/SMN usa la otra opción del selector."
        )
    uploaded = st.file_uploader(
        "Selecciona un archivo CSV, Excel, Parquet o TXT (separador auto-detectado)",
        type=["csv", "xlsx", "xls", "parquet", "txt"],
    )
    uploaded_files = []
    parquet_procesado = False  # flag para Parquet ya procesado

    if uploaded is None:
        st.info("Sube un archivo para comenzar.")
        st.stop()

    es_parquet = uploaded.name.lower().endswith(".parquet")

    # ── Si es Parquet, preguntar qué tipo es ─────────────────────────────
    if es_parquet:
        tipo_parquet = st.radio(
            "¿Qué contiene este Parquet?",
            options=[
                "Datos en escala original (mm / °C) — igual que un CSV",
                "dataset_final.parquet ya procesado (salida de la Etapa 5)",
            ],
            help="Un Parquet plano empieza desde la Etapa 3 (limpieza + normalización). "
                 "Si ya es el dataset_final.parquet normalizado, entra directo en la Etapa 8 (Quality Gate).",
        )
        parquet_procesado = tipo_parquet.startswith("dataset_final")

    # ── Leer y validar ────────────────────────────────────────────────────
    try:
        name = uploaded.name.lower()
        if name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded)
        elif name.endswith((".xlsx", ".xls")):
            df_raw = pd.read_excel(uploaded)
        else:
            df_raw = pd.read_parquet(uploaded)
    except Exception as exc:
        st.error(f"No se pudo leer el archivo: {exc}")
        st.stop()

    if parquet_procesado:
        # Solo verificar que tenga algo legible, sin requerir columnas específicas
        st.success(
            f"**{len(df_raw):,} filas · {len(df_raw.columns)} columnas** — "
            "se copiará directamente como `dataset_final.parquet` y entrará en la Etapa 8."
        )
        with st.expander("Vista previa (primeras 20 filas)"):
            st.dataframe(df_raw.head(20), use_container_width=True)
    else:
        required_cols = ["estacion", "date"] + VARIABLES
        missing_cols  = [c for c in required_cols if c not in df_raw.columns]
        if missing_cols:
            st.error(f"Columnas faltantes: {', '.join(missing_cols)}")
            st.stop()

        df_raw["date"] = pd.to_datetime(df_raw["date"], errors="coerce")
        df_raw = df_raw.dropna(subset=["date"])

        n_sta     = df_raw["estacion"].nunique()
        fecha_ini = df_raw["date"].min().date()
        fecha_fin = df_raw["date"].max().date()
        st.success(
            f"**{len(df_raw):,} registros** · **{n_sta} estación{'es' if n_sta != 1 else ''}** "
            f"· período {fecha_ini} → {fecha_fin}"
        )
        with st.expander("Vista previa (primeras 50 filas)"):
            st.dataframe(df_raw.head(50), use_container_width=True)

        st.subheader("Valores faltantes por variable")
        falt_rows = []
        for var in VARIABLES:
            n_total = len(df_raw)
            n_nan   = int(df_raw[var].isna().sum())
            falt_rows.append({
                "Variable":      VAR_LABELS[var],
                "Total":         n_total,
                "NaN":           n_nan,
                "Cobertura (%)": round((n_total - n_nan) / n_total * 100, 2),
            })
        st.dataframe(pd.DataFrame(falt_rows), hide_index=True, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Paso 2 — Ejecutar pipeline
# ---------------------------------------------------------------------------

st.header("2 · Ejecutar pipeline")

if pipeline is None:
    st.error("El modelo BiGRU-opt no está disponible. Verifica que exista `models/optimizacion/bigru_opt.pt`.")
    st.stop()

source_key = (
    "_".join(f.name for f in uploaded_files)
    if es_conagua
    else f"{uploaded.name}_{len(df_raw)}_{parquet_procesado}"
)
if st.session_state.get("pipeline_source") != source_key:
    st.session_state["pipeline_ran"]    = False
    st.session_state["pipeline_source"] = source_key

st.warning(
    "Al ejecutar el pipeline con datos propios se sobreescribirán "
    "`data/processed/dataset_final.parquet` y el dataset imputado. "
    "Los datos intermedios de CONAGUA (organized/, cleaned/, scaled/) "
    "no se modifican. "
    "Los reportes anteriores se archivan automáticamente en `reports/archive/`."
)
confirmar = st.checkbox("Entendido, deseo continuar y sobreescribir los resultados existentes.")

if st.button("Ejecutar pipeline completo", type="primary", use_container_width=True, disabled=not confirmar):
    st.session_state["pipeline_ran"] = False

    log_area    = st.empty()
    status_area = st.empty()
    full_log    = [""]  # lista mutable para evitar nonlocal en scope de módulo

    def _append(text: str) -> None:
        full_log[0] += text
        log_area.code(full_log[0][-6000:], language="")

    # Directorio intermedio exclusivo para datos externos (nunca toca organized/)
    EXTERNAL_INTERIM = ROOT / "data" / "interim" / "organized_external" / "estado=sin"

    if es_conagua:
        # ── Flujo B: limpiar RAW_TXT_DIR y organized_external/, guardar .txt ──
        # Solo se limpian directorios externos; los datos CONAGUA en
        # organized/ y cleaned/ permanecen intactos.
        status_area.info("Preparando directorios externos y copiando archivos .txt...")
        if EXTERNAL_INTERIM.exists():
            shutil.rmtree(EXTERNAL_INTERIM)
            _append(f"=== Directorio externo limpiado:\n    {EXTERNAL_INTERIM}\n")
        if RAW_TXT_DIR.exists():
            shutil.rmtree(RAW_TXT_DIR)
            _append(f"=== Directorio raw limpiado:\n    {RAW_TXT_DIR}\n")
        RAW_TXT_DIR.mkdir(parents=True, exist_ok=True)
        for f in uploaded_files:
            (RAW_TXT_DIR / f.name).write_bytes(f.getvalue())
        _append(f"=== {len(uploaded_files)} archivo(s) .txt guardados en:\n    {RAW_TXT_DIR}\n\n")

        from_stage  = FROM_CONAGUA
        skip_stages = SKIP_CONAGUA
        use_external = True
        _append("=== Pipeline (etapas 2→5→8→12, modo --external) ===\n")

    elif parquet_procesado:
        # ── Flujo A2: Parquet ya procesado → copiar a dataset_final ──────
        # No usa directorios externos; entra directamente en etapa 8.
        status_area.info("Copiando Parquet como dataset_final.parquet...")
        DATASET_FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATASET_FINAL_PATH.write_bytes(uploaded.getvalue())
        _append(f"=== Parquet copiado a:\n    {DATASET_FINAL_PATH}\n\n")
        _append("=== Pipeline (etapas 8, 9, 10, 11, 12) ===\n")

        from_stage   = FROM_PARQUET_PROC
        skip_stages  = None
        use_external = False

    else:
        # ── Flujo A: ingestión de archivo plano (CSV / Excel / Parquet / TXT)
        # ingest_external.py escribe en organized_external/ (no toca organized/).
        status_area.info("Convirtiendo datos al formato del pipeline (directorio externo)...")
        tmp_dir  = ROOT / "data" / "raw" / "external"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        suffix   = Path(uploaded.name).suffix
        tmp_path = tmp_dir / f"input{suffix}"
        tmp_path.write_bytes(uploaded.getvalue())

        _append("=== Ingestión de datos externos ===\n")
        try:
            proc_ingest = subprocess.Popen(
                [sys.executable, str(INGEST_SCRIPT), "--input", str(tmp_path), "--force"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(ROOT),
            )
            for line in iter(proc_ingest.stdout.readline, ""):
                _append(line)
            proc_ingest.stdout.close()
            rc_ingest = proc_ingest.wait()
        except Exception as exc:
            status_area.error(f"Error en ingestión: {exc}")
            st.stop()

        if rc_ingest != 0:
            status_area.error("La ingestión falló. Revisa el log.")
            st.stop()

        from_stage   = FROM_PLANO
        skip_stages  = SKIP_PLANO
        use_external = True
        _append("\n=== Pipeline (etapas 3→5→8→12, modo --external) ===\n")

    # ── Archivar reportes anteriores ──────────────────────────────────────
    archived = archive_reports(ROOT)
    if archived:
        _append(f"=== Reportes anteriores archivados en:\n    {archived}\n\n")

    # ── Ejecutar pipeline ─────────────────────────────────────────────────
    status_area.info(f"Ejecutando pipeline desde etapa {from_stage}...")
    cmd = [sys.executable, str(PIPELINE_SCRIPT), "--from-stage", from_stage, "--force"]
    if use_external:
        cmd.append("--external")
    if skip_stages:
        cmd += ["--skip-stages", skip_stages]
    try:
        proc_pipe = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(ROOT),
        )
        for line in iter(proc_pipe.stdout.readline, ""):
            _append(line)
        proc_pipe.stdout.close()
        rc_pipe = proc_pipe.wait()
    except Exception as exc:
        status_area.error(f"Error al ejecutar el pipeline: {exc}")
        st.stop()

    if rc_pipe == 0:
        status_area.success("Pipeline completado exitosamente.")
        st.session_state["pipeline_ran"] = True
    else:
        status_area.error(f"El pipeline terminó con código de error {rc_pipe}. Revisa el log.")

st.divider()

# ---------------------------------------------------------------------------
# Paso 3 — Resultados
# ---------------------------------------------------------------------------

if st.session_state.get("pipeline_ran"):
    st.header("3 · Resultados")

    csv_path  = ROOT / "data" / "export" / "dataset_imputado.csv"
    rep_path  = ROOT / "reports" / "validacion_estadistica" / "metricas_imputacion.csv"

    if rep_path.exists():
        cov = pd.read_csv(rep_path)
        cov["variable"]      = cov["variable"].map(VAR_LABELS).fillna(cov["variable"])
        cov["tasa_cobertura"] = (cov["tasa_cobertura"] * 100).round(2)
        cov = cov.rename(columns={
            "variable":       "Variable",
            "nan_original":   "NaN originales",
            "nan_rellenados": "NaN rellenados",
            "nan_residual":   "NaN residuales",
            "tasa_cobertura": "Cobertura (%)",
        })
        cols_show = [c for c in ["Variable","NaN originales","NaN rellenados","NaN residuales","Cobertura (%)"] if c in cov.columns]
        st.subheader("Cobertura de imputación")
        st.dataframe(cov[cols_show], hide_index=True, use_container_width=True)

    st.info("Ve a la página **Resultados** para ver las figuras y reportes completos.", icon="ℹ️")

    st.subheader("Descarga de resultados")
    import io, zipfile
    export_dir = ROOT / "data" / "export"
    xlsx_path  = export_dir / "resumen_estadistico.xlsx"
    sta_dir    = export_dir / "por_estacion"

    col1, col2, col3, col4 = st.columns(4)

    if csv_path.exists():
        with open(csv_path, "rb") as f:
            col1.download_button(
                label="dataset_imputado.csv",
                data=f,
                file_name="dataset_imputado.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        col1.info("CSV no disponible")

    if xlsx_path.exists():
        with open(xlsx_path, "rb") as f:
            col2.download_button(
                label="resumen_estadistico.xlsx",
                data=f,
                file_name="resumen_estadistico.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        col2.info("Excel no disponible")

    if export_dir.exists() and any(export_dir.rglob("*")):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in export_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(export_dir))
        buf.seek(0)
        col3.download_button(
            label="export/ completo (.zip)",
            data=buf,
            file_name="export_completo.zip",
            mime="application/zip",
            use_container_width=True,
        )
    else:
        col3.info("ZIP no disponible")

    if sta_dir.exists() and any(sta_dir.iterdir()):
        buf_sta = io.BytesIO()
        with zipfile.ZipFile(buf_sta, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sta_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(sta_dir))
        buf_sta.seek(0)
        col4.download_button(
            label="por_estacion/ (.zip)",
            data=buf_sta,
            file_name="por_estacion.zip",
            mime="application/zip",
            use_container_width=True,
        )
    else:
        col4.info("por_estacion/ no disponible")
