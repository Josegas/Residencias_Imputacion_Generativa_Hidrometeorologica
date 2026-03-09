import os
import csv
import pandas as pd
from pathlib import Path

# =========================
# CONFIG (ajusta tu ruta raíz)
# =========================
PROJECT_ROOT = r"C:\Users\Jose Garcia\Documents\10_SEMESTRE_TEC\RESIDENCIAS\Reconstruccion_de_Base_de_Datos_Nuestro"

RAW_DIR = (
    Path(PROJECT_ROOT)
    / "data"
    / "raw"
    / "conagua_smn"
    / "estado=sin"
    / "fuente=normales_climatologicas"
    / "producto=diarios_txt"
)

OUT_DIR = Path(PROJECT_ROOT) / "data" / "interim" / "organized" / "estado=sin"
INDEX_PATH = OUT_DIR / "_index.csv"

# Variables esperadas por tu encabezado
EXPECTED_VARS = ["PRECIP", "EVAP", "TMAX", "TMIN"]


def station_id_from_filename(name: str) -> str:
    # soporta dia25001.txt o 25001.txt
    base = name.replace(".txt", "")
    base = base.replace("dia", "")
    return base.strip()


def find_table_start_line(txt_path: Path) -> int:
    """Encuentra la línea (0-index) donde empieza la tabla: la línea que inicia con FECHA."""
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if line.strip().startswith("FECHA"):
                return i
    raise ValueError(
        f"No encontré encabezado de tabla 'FECHA' en {txt_path.name}")


def parse_station_txt(txt_path: Path) -> pd.DataFrame:
    """
    Lee el TXT del SMN/CONAGUA:
    - salta encabezado largo
    - lee tabla (tabulada)
    - convierte NULO a NaN
    - FECHA -> datetime
    - variables -> numérico
    Devuelve DF con columnas: date, PRECIP, EVAP, TMAX, TMIN (las que existan)
    """
    start = find_table_start_line(txt_path)

    df = pd.read_csv(
        txt_path,
        sep="\t",
        engine="python",
        skiprows=start,  # empieza en FECHA
        header=0,
        na_values=["NULO", "Nulo", "nulo", ""],
    )

    # Elimina columnas "Unnamed" causadas por tabs extra
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

    # Normaliza nombres
    df.columns = [str(c).strip() for c in df.columns]

    if "FECHA" not in df.columns:
        raise ValueError(
            f"Columnas encontradas: {df.columns.tolist()} (no aparece FECHA)")

    # Quita filas que no sean fecha válida (a veces se cuela la línea de unidades)
    df = df[df["FECHA"].astype(str).str.match(
        r"^\d{4}-\d{2}-\d{2}$", na=False)].copy()

    df["date"] = pd.to_datetime(
        df["FECHA"], format="%Y-%m-%d", errors="coerce")

    for col in EXPECTED_VARS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    keep = ["date"] + [c for c in EXPECTED_VARS if c in df.columns]
    df = df[keep].dropna(subset=["date"]).sort_values(
        "date").reset_index(drop=True)

    return df


def ensure_out_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def init_index():
    if not INDEX_PATH.exists():
        with open(INDEX_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["station", "year", "variable",
                       "path_parquet", "path_csv", "rows", "missing_pct"])


def check_parquet_engine():
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def append_index(rows):
    with open(INDEX_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)


def main():
    ensure_out_dirs()
    init_index()

    has_pyarrow = check_parquet_engine()
    if not has_pyarrow:
        print("ERROR: Falta 'pyarrow' para guardar Parquet.")
        print("Instálalo con:  pip install pyarrow")
        print("O con conda:    conda install -c conda-forge pyarrow")
        return

    txt_files = list(RAW_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No encontré .txt en:\n{RAW_DIR}")
        return

    print(f"Encontrados {len(txt_files)} archivos crudos en:\n{RAW_DIR}\n")
    index_rows = []

    for txt_path in txt_files:
        station_id = station_id_from_filename(txt_path.name)

        try:
            df = parse_station_txt(txt_path)
        except Exception as e:
            print(f"[FAIL] {txt_path.name}: {e}")
            continue

        if df.empty:
            print(f"[WARN] {txt_path.name}: sin registros válidos")
            continue

        df["year"] = df["date"].dt.year
        variables = [c for c in df.columns if c not in ("date", "year")]

        for year, df_y in df.groupby("year"):
            year_dir = OUT_DIR / f"estacion={station_id}" / f"year={int(year)}"
            year_dir.mkdir(parents=True, exist_ok=True)

            for var in variables:
                out_df = df_y[["date", var]].rename(
                    columns={var: "value"}).reset_index(drop=True)

                # paths
                out_csv = year_dir / f"{var.lower()}.csv"
                out_parquet = year_dir / f"{var.lower()}.parquet"

                # Guardado
                out_df.to_csv(out_csv, index=False)
                out_df.to_parquet(out_parquet, index=False)

                missing_pct = float(out_df["value"].isna().mean() * 100.0)
                index_rows.append([
                    station_id,
                    int(year),
                    var.lower(),
                    str(out_parquet),
                    str(out_csv),
                    len(out_df),
                    round(missing_pct, 3)
                ])

        print(
            f"[OK] Estación {station_id}: {len(df)} filas, años={df['year'].nunique()}")

    append_index(index_rows)
    print(f"\nListo \nÍndice generado en:\n{INDEX_PATH}")
    print(f"Salida organizada en:\n{OUT_DIR}")


if __name__ == "__main__":
    main()
