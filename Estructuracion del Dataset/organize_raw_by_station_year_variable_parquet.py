import argparse
import csv
import yaml
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as _f:
    CFG = yaml.safe_load(_f)

RAW_DIR = PROJECT_ROOT.joinpath(*CFG["paths"]["raw_subpath"])
OUT_DIR = PROJECT_ROOT.joinpath(*CFG["paths"]["out_subpath"])
INDEX_PATH = OUT_DIR / CFG["paths"]["index_filename"]

EXPECTED_VARS = CFG["variables"]["expected"]


def station_id_from_filename(name: str) -> str:
    base = name
    for ext in [CFG["station_files"]["file_extension"]]:
        base = base.replace(ext, "")
    for prefix in CFG["station_files"]["strip_prefixes"]:
        base = base.replace(prefix, "")
    return base.strip()


def find_table_start_line(txt_path: Path) -> int:
    marker = CFG["parsing"]["table_header_marker"]
    encoding = CFG["parsing"]["encoding"]
    enc_errors = CFG["parsing"]["encoding_errors"]
    with txt_path.open("r", encoding=encoding, errors=enc_errors) as f:
        for i, line in enumerate(f):
            if line.strip().startswith(marker):
                return i
    raise ValueError(
        f"No encontré encabezado de tabla '{marker}' en {txt_path.name}")


def parse_station_txt(txt_path: Path) -> pd.DataFrame:
    p = CFG["parsing"]
    start = find_table_start_line(txt_path)

    skip = start + 1 + p["header_skip_after_marker"]
    df = pd.read_csv(
        txt_path,
        sep=p["separator"],
        engine=p["csv_engine"],
        skiprows=skip,
        header=None,
        names=p["column_names"],
        na_values=p["na_values"],
    )

    date_col = p["column_names"][0]
    date_regex = p["date_regex"]
    df = df[df[date_col].astype(str).str.match(date_regex, na=False)].copy()
    df[date_col] = pd.to_datetime(
        df[date_col], format=p["date_format"], errors="coerce")

    for col in EXPECTED_VARS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=[date_col]).sort_values(
        date_col).reset_index(drop=True)
    return df


def ensure_out_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def init_index():
    out_enc = CFG["output"]["encoding"]
    if not INDEX_PATH.exists():
        with INDEX_PATH.open("w", newline="", encoding=out_enc) as f:
            w = csv.writer(f)
            w.writerow(CFG["index"]["columns"])


def check_parquet_engine():
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def append_index(rows):
    out_enc = CFG["output"]["encoding"]
    with INDEX_PATH.open("a", newline="", encoding=out_enc) as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)


def main():
    parser = argparse.ArgumentParser(
        description="Etapa 2 — Estructuración del dataset hidrometeorológico."
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help=(
            "Directorio de salida para las particiones parquet e índice "
            "(ruta relativa a la raíz del proyecto o absoluta). "
            "Por defecto usa el configurado en config.yaml (datos CONAGUA). "
            "Pasar 'data/interim/organized_external/estado=sin' con --external "
            "para aislar datos externos sin tocar el directorio CONAGUA."
        ),
    )
    args = parser.parse_args()

    # Si se indica --output-dir, sobreescribir rutas de salida globales.
    # Esto garantiza que datos externos nunca contaminen organized/ (CONAGUA).
    global OUT_DIR, INDEX_PATH
    if args.output_dir:
        OUT_DIR = (
            PROJECT_ROOT / args.output_dir
            if not Path(args.output_dir).is_absolute()
            else Path(args.output_dir)
        )
        INDEX_PATH = OUT_DIR / CFG["paths"]["index_filename"]

    ensure_out_dirs()
    init_index()

    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"RAW_DIR:      {RAW_DIR}")
    print(f"OUT_DIR:      {OUT_DIR}")

    has_pyarrow = check_parquet_engine()
    if not has_pyarrow:
        print("ERROR: Falta 'pyarrow' para guardar Parquet.")
        print("Instálalo con:  pip install pyarrow")
        print("O con conda:    conda install -c conda-forge pyarrow")
        return

    glob_pattern = CFG["station_files"]["glob_pattern"]
    txt_files = list(RAW_DIR.glob(glob_pattern))
    if not txt_files:
        print(f"No encontré '{glob_pattern}' en:\n{RAW_DIR}")
        return

    out = CFG["output"]
    date_col = CFG["parsing"]["column_names"][0]
    year_col = out["year_partition_prefix"]
    station_prefix = out["station_partition_prefix"]
    value_col = out["value_column"]

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

        df[year_col] = df[date_col].dt.year
        variables = [c for c in df.columns if c not in (date_col, year_col)]

        for year, df_y in df.groupby(year_col):
            year_dir = (
                OUT_DIR
                / f"{station_prefix}={station_id}"
                / f"{year_col}={int(year)}"
            )
            year_dir.mkdir(parents=True, exist_ok=True)

            for var in variables:
                out_df = df_y[[date_col, var]].rename(
                    columns={var: value_col}).reset_index(drop=True)

                out_csv = year_dir / f"{var.lower()}.csv"
                out_parquet = year_dir / f"{var.lower()}.parquet"

                out_df.to_csv(out_csv, index=False)
                out_df.to_parquet(out_parquet, index=False)

                missing_pct = float(out_df[value_col].isna().mean() * 100.0)
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
            f"[OK] Estación {station_id}: {len(df)} filas, años={df[year_col].nunique()}")

    append_index(index_rows)
    print(f"\nListo\nÍndice generado en:\n{INDEX_PATH}")
    print(f"Salida organizada en:\n{OUT_DIR}")


if __name__ == "__main__":
    main()
