"""Pipeline — ejecutar etapas del pipeline con logs en tiempo real."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st
import yaml

from utils import ROOT, LOGO_PATH, PIPELINE_DIR, get_pipeline, archive_reports

st.set_page_config(page_title="Pipeline · HydroImpute", layout="wide")

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

st.title("Pipeline")
st.markdown(
    "Ejecuta el pipeline completo o etapas individuales. "
    "El log de ejecución se muestra en tiempo real."
)

# ---------------------------------------------------------------------------
# Cargar configuración del pipeline
# ---------------------------------------------------------------------------

pipeline_cfg_path = PIPELINE_DIR / "config.yaml"
try:
    with pipeline_cfg_path.open(encoding="utf-8") as f:
        pipeline_cfg = yaml.safe_load(f)
    stages = pipeline_cfg.get("stages", [])
except Exception as exc:
    st.error(f"No se pudo leer la configuración del pipeline: {exc}")
    st.stop()

# ---------------------------------------------------------------------------
# Selector de etapas
# ---------------------------------------------------------------------------

st.subheader("Seleccionar etapas")

run_all = st.checkbox("Ejecutar todas las etapas", value=True)

selected_ids: list[int] = []
if not run_all:
    for stage in stages:
        check_out = ROOT / stage.get("check_output", "__none__")
        done = check_out.exists()
        label = (
            f"Etapa {stage['id']:02d} — {stage['name']} "
            f"{'[OK]' if done else ''}"
        )
        if st.checkbox(label, value=False, key=f"stage_{stage['id']}"):
            selected_ids.append(stage["id"])

st.divider()

# ---------------------------------------------------------------------------
# Opciones de ejecución
# ---------------------------------------------------------------------------

st.subheader("Opciones")
force = st.checkbox(
    "Forzar re-ejecución",
    value=False,
    help="Ejecuta aunque los archivos de salida ya existan (--force).",
)

st.divider()

# ---------------------------------------------------------------------------
# Ejecución con streaming de logs
# ---------------------------------------------------------------------------

if st.button("Ejecutar pipeline", type="primary", use_container_width=True):
    run_script = PIPELINE_DIR / "run_pipeline.py"
    if not run_script.exists():
        st.error(f"Script no encontrado: {run_script}")
        st.stop()

    cmd = [sys.executable, str(run_script)]
    if force:
        cmd.append("--force")
    if not run_all and selected_ids:
        if len(selected_ids) == 1:
            cmd += ["--only-stage", str(selected_ids[0])]
        else:
            cmd += ["--from-stage", str(min(selected_ids))]

    st.info(f"Ejecutando: `{' '.join(cmd)}`")

    log_area   = st.empty()
    status_bar = st.empty()
    full_log   = ""

    archived = archive_reports(ROOT)
    if archived:
        full_log += f"=== Reportes anteriores archivados en:\n    {archived}\n\n"
        log_area.code(full_log, language="")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
        )

        for line in iter(process.stdout.readline, ""):
            full_log += line
            log_area.code(full_log[-4000:], language="")

        process.stdout.close()
        return_code = process.wait()

        if return_code == 0:
            status_bar.success("Pipeline completado exitosamente.")
        else:
            status_bar.error(f"Pipeline terminó con código de error {return_code}.")

        if "etapa omitida" in full_log and not force:
            st.warning(
                "Una o más etapas fueron omitidas porque ya tienen salida. "
                "Para re-ejecutarlas, activa **Forzar re-ejecución** y ejecuta de nuevo."
            )

    except Exception as exc:
        st.error(f"Error al ejecutar el pipeline: {exc}")

st.divider()

# ---------------------------------------------------------------------------
# Estado actual de las etapas
# ---------------------------------------------------------------------------

st.subheader("Estado actual de las etapas")

first_pending = next(
    (s for s in stages if not (ROOT / s.get("check_output", "__none__")).exists()),
    None,
)
if first_pending is None:
    st.info(
        "Todas las etapas están completadas. "
        "Para volver a ejecutarlas activa **Forzar re-ejecución** antes de iniciar."
    )
elif first_pending["id"] == stages[0]["id"]:
    st.info("Ninguna etapa ha sido ejecutada aún. Ejecuta el pipeline completo.")
else:
    st.warning(
        f"Continúa desde **Etapa {first_pending['id']:02d} · {first_pending['name']}**. "
        "No es necesario forzar re-ejecución — las etapas anteriores ya están completadas."
    )

for stage in stages:
    check_out = ROOT / stage.get("check_output", "__none__")
    done = check_out.exists()
    estado = "Completada" if done else "Pendiente"
    st.markdown(f"**Etapa {stage['id']:02d}** — {stage['name']} &nbsp; *{estado}*")

st.divider()

# ---------------------------------------------------------------------------
# Descarga de resultados
# ---------------------------------------------------------------------------

import io
import zipfile

st.subheader("Descarga de resultados")

export_dir = ROOT / "data/export"
csv_path   = export_dir / "dataset_imputado.csv"
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
