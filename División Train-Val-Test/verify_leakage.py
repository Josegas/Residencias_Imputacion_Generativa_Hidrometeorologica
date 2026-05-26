"""
Verificación de ausencia de leakage — RES-111

Script standalone que carga los tres conjuntos generados por split.py
y ejecuta un conjunto exhaustivo de pruebas para garantizar que no existe
fuga de información entre train, val y test.

Uso:
    python "División Train-Val-Test/verify_leakage.py"
    python "División Train-Val-Test/verify_leakage.py" --config path/to/config.yaml

Retorna código 0 si todas las pruebas pasan; código 1 si hay fallos.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Pruebas de leakage
# ---------------------------------------------------------------------------

def check_date_intersection(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    station_col: str,
    date_col: str,
) -> list[str]:
    """
    Prueba 1: Ninguna (station_col, date_col) aparece en más de un conjunto.
    Comprueba los tres pares: train/val, train/test, val/test.
    """
    errors = []
    key = [station_col, date_col]

    tr_keys = set(map(tuple, train[key].itertuples(index=False, name=None)))
    va_keys = set(map(tuple, val[key].itertuples(index=False, name=None)))
    te_keys = set(map(tuple, test[key].itertuples(index=False, name=None)))

    for pair_label, a, b in [
        ("train ∩ val",   tr_keys, va_keys),
        ("train ∩ test",  tr_keys, te_keys),
        ("val ∩ test",    va_keys, te_keys),
    ]:
        overlap = a & b
        if overlap:
            errors.append(
                f"SOLAPAMIENTO {pair_label}: {len(overlap):,} pares ({station_col}, {date_col}) comunes"
            )

    return errors


def check_temporal_order(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    station_col: str,
    date_col: str,
) -> list[str]:
    """
    Prueba 2: Para cada estación, el orden cronológico debe ser estricto:
      max(train.date) < min(val.date)
      max(val.date)   < min(test.date)
    """
    errors = []
    stations = sorted(set(train[station_col].unique()) &
                      set(val[station_col].unique())  &
                      set(test[station_col].unique()))

    for st in stations:
        tr_max = train[train[station_col] == st][date_col].max()
        va_min = val[val[station_col] == st][date_col].min()
        va_max = val[val[station_col] == st][date_col].max()
        te_min = test[test[station_col] == st][date_col].min()

        if tr_max >= va_min:
            errors.append(
                f"[{st}] max(train)={tr_max.date()} >= min(val)={va_min.date()}"
            )
        if va_max >= te_min:
            errors.append(
                f"[{st}] max(val)={va_max.date()} >= min(test)={te_min.date()}"
            )

    return errors


def check_coverage(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    original: pd.DataFrame,
    station_col: str,
    date_col: str,
) -> list[str]:
    """
    Prueba 3: La unión de los tres conjuntos contiene exactamente los mismos
    registros que el dataset original para cada estación incluida.
    """
    errors = []
    included = set(train[station_col].unique())
    key = [station_col, date_col]

    combined = pd.concat([train, val, test])
    combined_keys = set(map(tuple, combined[key].itertuples(index=False, name=None)))
    original_keys = set(
        map(tuple,
            original[original[station_col].isin(included)][key]
            .itertuples(index=False, name=None))
    )

    missing_from_splits = original_keys - combined_keys
    extra_in_splits     = combined_keys - original_keys

    if missing_from_splits:
        errors.append(
            f"COBERTURA INCOMPLETA: {len(missing_from_splits):,} registros originales "
            "no aparecen en ningún conjunto"
        )
    if extra_in_splits:
        errors.append(
            f"REGISTROS EXTRA: {len(extra_in_splits):,} registros en splits "
            "que no existen en el dataset original"
        )

    return errors


def check_proportions(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    train_ratio: float,
    val_ratio: float,
    tolerance: float,
) -> list[str]:
    """
    Prueba 4: Las proporciones globales no se desvían más de `tolerance`
    de los ratios configurados.
    """
    errors = []
    total = len(train) + len(val) + len(test)

    actual_train = len(train) / total
    actual_val   = len(val)   / total
    actual_test  = len(test)  / total
    test_ratio   = 1.0 - train_ratio - val_ratio

    for name, actual, expected in [
        ("train", actual_train, train_ratio),
        ("val",   actual_val,   val_ratio),
        ("test",  actual_test,  test_ratio),
    ]:
        if abs(actual - expected) > tolerance:
            errors.append(
                f"PROPORCIÓN {name}: real={actual:.3f} esperada={expected:.3f} "
                f"(desviación={abs(actual-expected):.3f} > tolerancia={tolerance})"
            )

    return errors


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run(config_path: Path) -> bool:
    cfg = load_config(config_path)

    date_col    = cfg["input"]["date_col"]
    station_col = cfg["input"]["station_col"]

    print("=" * 60)
    print("Verificación de leakage — RES-111")
    print("=" * 60)

    # Cargar conjuntos
    train = pd.read_parquet(ROOT / cfg["output"]["train_parquet"])
    val   = pd.read_parquet(ROOT / cfg["output"]["val_parquet"])
    test  = pd.read_parquet(ROOT / cfg["output"]["test_parquet"])

    for df in [train, val, test]:
        df[date_col] = pd.to_datetime(df[date_col])

    print(f"  train: {len(train):,} filas | val: {len(val):,} | test: {len(test):,}")

    original_path = ROOT / cfg["input"]["dataset_path"]
    original = pd.read_parquet(original_path)
    original[date_col] = pd.to_datetime(original[date_col])

    all_errors = []

    # Prueba 1 — intersección de fechas
    print("\n[1/4] Intersección de fechas entre conjuntos...")
    e1 = check_date_intersection(train, val, test, station_col, date_col)
    all_errors.extend(e1)
    print(f"      {'PASS' if not e1 else 'FAIL — ' + str(len(e1)) + ' problema(s)'}")
    for err in e1:
        print(f"      ✗ {err}")

    # Prueba 2 — orden temporal por estación
    print("\n[2/4] Orden temporal estricto por estación...")
    e2 = check_temporal_order(train, val, test, station_col, date_col)
    all_errors.extend(e2)
    print(f"      {'PASS' if not e2 else 'FAIL — ' + str(len(e2)) + ' problema(s)'}")
    for err in e2:
        print(f"      ✗ {err}")

    # Prueba 3 — cobertura completa
    print("\n[3/4] Cobertura completa respecto al dataset original...")
    e3 = check_coverage(train, val, test, original, station_col, date_col)
    all_errors.extend(e3)
    print(f"      {'PASS' if not e3 else 'FAIL — ' + str(len(e3)) + ' problema(s)'}")
    for err in e3:
        print(f"      ✗ {err}")

    # Prueba 4 — proporciones globales
    tolerance = cfg["leakage"]["proportion_tolerance"]
    print(f"\n[4/4] Proporciones globales (tolerancia ±{tolerance*100:.0f}%)...")
    e4 = check_proportions(
        train, val, test,
        cfg["split"]["train_ratio"],
        cfg["split"]["val_ratio"],
        tolerance,
    )
    all_errors.extend(e4)
    print(f"      {'PASS' if not e4 else 'FAIL — ' + str(len(e4)) + ' problema(s)'}")
    for err in e4:
        print(f"      ✗ {err}")

    # Resultado final
    print("\n" + "=" * 60)
    n_stations = train[station_col].nunique()
    total = len(train) + len(val) + len(test)
    print(f"Estaciones verificadas: {n_stations}")
    print(f"Registros totales:      {total:,}  "
          f"(train={len(train)/total:.1%} | val={len(val)/total:.1%} | test={len(test)/total:.1%})")

    if all_errors:
        print(f"\nRESULTADO: FAIL — {len(all_errors)} problema(s) detectado(s)")
        print("=" * 60)
        return False

    print("\nRESULTADO: PASS — Sin leakage detectado entre conjuntos")
    print("=" * 60)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verifica ausencia de leakage entre train/val/test")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Ruta al archivo de configuración YAML",
    )
    args = parser.parse_args()
    ok = run(args.config)
    sys.exit(0 if ok else 1)
