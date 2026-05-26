"""
run_pipeline.py
===============
Pipeline reproducible end-to-end — Proyecto de Residencias Profesionales
Reconstrucción de Base de Datos Hidrometeorológica con IA (CRISP-ML(Q))

Laboratorio de Geomática y Teledetección
Autores: José Ángel García Pérez · Sebastián Verdugo Bermúdez

Automatiza las 12 etapas del pipeline: datos (1–7), quality gate (8),
imputación generativa (9), validación estadística (10), monitoreo del
modelo (11) y análisis y exportación (12). Las etapas de modelado
(Modelos Base, Generativos, Optimización) se documentan en notebooks
de experimentación y sus artefactos se verifican al final.

Uso:
    python "Pipeline Reproducible/run_pipeline.py"               # todas las etapas
    python "Pipeline Reproducible/run_pipeline.py" --from-stage 3
    python "Pipeline Reproducible/run_pipeline.py" --only-stage 6
    python "Pipeline Reproducible/run_pipeline.py" --force
    python "Pipeline Reproducible/run_pipeline.py" --list-stages

    # Datos externos — directorios aislados, scalers preservados
    python "Pipeline Reproducible/run_pipeline.py" --from-stage 3 --skip-stages 1,2,6,7 --force --external
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent        # Pipeline Reproducible/
ROOT       = SCRIPT_DIR.parent                      # raíz del proyecto
CONFIG     = SCRIPT_DIR / "config.yaml"

# ---------------------------------------------------------------------------
# Colores ANSI
# ---------------------------------------------------------------------------

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"


# ---------------------------------------------------------------------------
# Configuración y logging
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"pipeline_run_{ts}.log"

    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("pipeline")
    logger.info(f"Log guardado en: {log_file}")
    return logger


# ---------------------------------------------------------------------------
# Utilidades de presentación
# ---------------------------------------------------------------------------

def _banner(text: str) -> None:
    line = "─" * 70
    print(f"\n{_CYAN}{_BOLD}{line}{_RESET}")
    print(f"{_CYAN}{_BOLD}  {text}{_RESET}")
    print(f"{_CYAN}{_BOLD}{line}{_RESET}")


def _ok(msg: str)   -> None: log.info(f"{_GREEN}✔  {msg}{_RESET}")
def _warn(msg: str) -> None: log.warning(f"{_YELLOW}⚠  {msg}{_RESET}")
def _err(msg: str)  -> None: log.error(f"{_RED}✘  {msg}{_RESET}")


def _stage_header(stage: dict) -> None:
    total = len(CFG["stages"])
    _banner(f"Etapa {stage['id']:02d} / {total:02d} — {stage['name']}")
    log.info(stage["description"])


# ---------------------------------------------------------------------------
# Ejecución de un script Python
# ---------------------------------------------------------------------------

def _run_script(rel_path: str, label: str, extra_args: list[str] | None = None) -> bool:
    script = ROOT / rel_path
    if not script.exists():
        _err(f"Script no encontrado: {rel_path}")
        return False

    cmd = [sys.executable, str(script)] + (extra_args or [])
    log.info(f"Ejecutando: {rel_path}" + (f"  args: {extra_args}" if extra_args else ""))
    t0 = time.time()

    result = subprocess.run(cmd, cwd=str(ROOT))

    elapsed = time.time() - t0

    if result.returncode == 0:
        _ok(f"{label} completado en {elapsed:.1f}s")
        return True

    _err(f"{label} falló (código {result.returncode}) después de {elapsed:.1f}s")
    return False


# ---------------------------------------------------------------------------
# Argumentos extra por etapa en modo --external
#
# Cuando se procesan datos externos (no CONAGUA), cada etapa de datos debe
# leer y escribir en directorios aislados para no contaminar los datos
# originales de Sinaloa. Las etapas 8-12 no cambian porque siempre leen de
# data/processed/dataset_final.parquet, que la etapa 5 siempre escribe igual.
# ---------------------------------------------------------------------------

_EXTERNAL_STAGE_ARGS: dict[int, list[str]] = {
    # Etapa 2: escribir en organized_external/ en vez de organized/
    2: ["--output-dir", "data/interim/organized_external/estado=sin"],
    # Etapa 3: leer de organized_external/, escribir en cleaned_external/
    3: ["--input-dir",  "data/interim/organized_external/estado=sin",
        "--output-dir", "data/cleaned_external"],
    # Etapa 4: leer de cleaned_external/, escribir en scaled_external/,
    #          y NO re-ajustar los scalers (--transform-only)
    4: ["--input-dir",  "data/cleaned_external",
        "--output-dir", "data/scaled_external",
        "--transform-only"],
    # Etapa 5: leer de scaled_external/ (salida siempre → data/processed/)
    5: ["--input-dir",  "data/scaled_external"],
}


# ---------------------------------------------------------------------------
# Ejecución de una etapa
# ---------------------------------------------------------------------------

def _run_stage(stage: dict, force: bool = False,
               extra_args: list[str] | None = None) -> bool:
    _stage_header(stage)

    check = stage.get("check_output")
    if check and (ROOT / check).exists() and not force:
        _warn(
            f"Salida ya existe: {check}  →  etapa omitida"
            "  (usa --force para re-ejecutar)"
        )
        return True

    ok = _run_script(stage["script"], stage["name"], extra_args=extra_args)

    if ok and "post_script" in stage:
        log.info("Ejecutando verificación post-etapa...")
        ok = _run_script(stage["post_script"], f"{stage['name']} — verificación")

    return ok


# ---------------------------------------------------------------------------
# Verificación de artefactos de modelado
# ---------------------------------------------------------------------------

def _check_model_artifacts() -> None:
    _banner("Verificación de artefactos de modelado")
    log.info("Los notebooks de modelado se ejecutan manualmente.")
    log.info("Esta verificación comprueba que sus artefactos existan.")
    print()

    all_ok = True
    for artifact in CFG.get("model_artifacts", []):
        path = ROOT / artifact["path"]
        exists = path.exists()
        status = f"{_GREEN}OK{_RESET}" if exists else f"{_YELLOW}PENDIENTE{_RESET}"
        print(f"  [{status}]  {artifact['name']}")
        if not exists:
            print(f"          → Ejecuta los notebooks en: {artifact['notebooks_dir']}/")
            all_ok = False

    print()
    if all_ok:
        _ok("Todos los artefactos de modelado están presentes.")
    else:
        _warn("Algunos artefactos de modelado están pendientes (ver indicaciones arriba).")


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline reproducible CRISP-ML(Q) — Imputación Hidrometeorológica con IA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--from-stage", type=int, metavar="N",
        help="Empieza desde la etapa N (omite las anteriores).",
    )
    group.add_argument(
        "--only-stage", type=int, metavar="N",
        help="Ejecuta únicamente la etapa N.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-ejecuta etapas aunque su salida ya exista.",
    )
    parser.add_argument(
        "--list-stages", action="store_true",
        help="Muestra el estado de cada etapa y termina.",
    )
    parser.add_argument(
        "--skip-stages", type=str, metavar="N,N,...",
        help="Etapas a omitir, separadas por coma (ej. --skip-stages 6,7).",
    )
    parser.add_argument(
        "--external", action="store_true",
        help=(
            "Modo datos externos: pasa a las etapas 2-5 los directorios aislados "
            "(organized_external/, cleaned_external/, scaled_external/) para que "
            "no contaminen los datos CONAGUA originales. "
            "La etapa 4 usa --transform-only para preservar los scalers entrenados. "
            "Las etapas 8-12 no cambian (siempre leen de dataset_final.parquet)."
        ),
    )
    args = parser.parse_args()

    stages      = CFG["stages"]
    stages_by_id = {s["id"]: s for s in stages}
    max_id      = max(s["id"] for s in stages)

    if args.list_stages:
        print(f"\n{_BOLD}Etapas del pipeline (datos — automatizadas):{_RESET}\n")
        for s in stages:
            check = s.get("check_output")
            done  = f" {_GREEN}[OK]{_RESET}" if (check and (ROOT / check).exists()) else ""
            print(f"  {s['id']:>2}.  {_BOLD}{s['name']}{_RESET}{done}")
            print(f"        {s['description']}\n")

        print(f"{_BOLD}Artefactos de modelado (notebooks — ejecución manual):{_RESET}\n")
        for a in CFG.get("model_artifacts", []):
            path = ROOT / a["path"]
            done = f" {_GREEN}[OK]{_RESET}" if path.exists() else f" {_YELLOW}[PENDIENTE]{_RESET}"
            print(f"  {_BOLD}{a['name']}{_RESET}{done}")
            print(f"        Notebooks en: {a['notebooks_dir']}/\n")
        sys.exit(0)

    # Etapas a omitir
    skip_ids: set[int] = set()
    if args.skip_stages:
        try:
            skip_ids = {int(x.strip()) for x in args.skip_stages.split(",")}
        except ValueError:
            _err("--skip-stages debe ser una lista de números separados por coma (ej. 6,7).")
            sys.exit(1)

    # Seleccionar etapas
    if args.only_stage:
        if args.only_stage not in stages_by_id:
            _err(f"Etapa {args.only_stage} no existe. Usa --list-stages.")
            sys.exit(1)
        selected = [stages_by_id[args.only_stage]]
    elif args.from_stage:
        if args.from_stage not in stages_by_id:
            _err(f"Etapa {args.from_stage} no existe. Usa --list-stages.")
            sys.exit(1)
        selected = [s for s in stages if s["id"] >= args.from_stage]
    else:
        selected = stages

    if skip_ids:
        skipped_names = [s["name"] for s in stages if s["id"] in skip_ids]
        log.info(f"Etapas omitidas (--skip-stages): {sorted(skip_ids)} — {skipped_names}")
        selected = [s for s in selected if s["id"] not in skip_ids]

    # Cabecera
    _banner("Pipeline Reproducible — Imputación Hidrometeorológica con IA (CRISP-ML(Q))")
    log.info(f"Raíz del proyecto  : {ROOT}")
    log.info(f"Config             : {CONFIG.relative_to(ROOT)}")
    log.info(f"Etapas a ejecutar  : {[s['id'] for s in selected]}")
    log.info(f"Forzar re-ejecución: {args.force}")
    log.info(f"Modo externo       : {args.external}")
    log.info(f"Inicio             : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.external:
        log.info("Directorios externos activos:")
        for sid, eargs in _EXTERNAL_STAGE_ARGS.items():
            log.info(f"  Etapa {sid}: {eargs}")

    t_global = time.time()
    results: list[tuple[int, str, bool]] = []

    for stage in selected:
        extra = _EXTERNAL_STAGE_ARGS.get(stage["id"]) if args.external else None
        ok = _run_stage(stage, force=args.force, extra_args=extra)
        results.append((stage["id"], stage["name"], ok))
        if not ok:
            _err(f"Pipeline interrumpido en etapa {stage['id']} — {stage['name']}")
            _err("Corrige el error y reinicia desde esta etapa con:")
            _err(f'  python "Pipeline Reproducible/run_pipeline.py" --from-stage {stage["id"]}')
            break

    # Resumen
    elapsed_total = time.time() - t_global
    _banner("Resumen de ejecución")

    passed = sum(1 for _, _, ok in results if ok)
    failed = len(results) - passed

    for sid, name, ok in results:
        status = f"{_GREEN}PASS{_RESET}" if ok else f"{_RED}FAIL{_RESET}"
        print(f"  Etapa {sid:>2}  [{status}]  {name}")

    print()
    log.info(f"Etapas completadas : {passed} / {len(results)}")
    log.info(f"Tiempo total       : {elapsed_total / 60:.1f} min")

    if failed > 0:
        sys.exit(1)

    last_stage_ran = results[-1][0] if results else 0
    if last_stage_ran >= max_id:
        _check_model_artifacts()

    _ok("Pipeline de datos completado exitosamente.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Inicialización global (fuera de main para que --list-stages también la use)
# ---------------------------------------------------------------------------

CFG = _load_config()
log = _setup_logging(ROOT / CFG["logs"]["dir"])

if __name__ == "__main__":
    main()
