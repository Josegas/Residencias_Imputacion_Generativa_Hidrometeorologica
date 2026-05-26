"""
Generación de secuencias temporales (ventanas deslizantes) — RES-114

Convierte un DataFrame de series temporales por estación en arrays de
ventanas deslizantes compatibles con modelos de imputación secuencial
(BRITS, SAITS, CSDI, LSTM/GRU, VAE/Autoencoders).

Uso como módulo:
    from sequence_generator import SequenceGenerator, TimeSeriesDataset

    gen = SequenceGenerator(window_size=30, stride=7, max_gap_days=365)
    seqs, day_diffs, meta, stations = gen.generate(df, variables, date_col, station_col, log)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

if TYPE_CHECKING:
    import torch


class SequenceGenerator:
    """
    Genera ventanas deslizantes de longitud fija sobre series temporales
    multivariadas por estación.

    Por cada estación se respeta el orden cronológico y se filtran ventanas
    que crucen brechas temporales mayores a max_gap_days (discontinuidades
    en la cobertura de la estación).

    Args:
        window_size: Número de filas por ventana (mínimo 2).
        stride: Desplazamiento entre ventanas consecutivas.
        max_gap_days: Brecha máxima (días calendario) permitida entre
            dos filas consecutivas dentro de una misma ventana.
    """

    def __init__(self, window_size: int, stride: int, max_gap_days: int) -> None:
        if window_size < 2:
            raise ValueError("window_size debe ser >= 2")
        if stride < 1:
            raise ValueError("stride debe ser >= 1")
        self.window_size = window_size
        self.stride = stride
        self.max_gap_days = max_gap_days

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def generate(
        self,
        df: pd.DataFrame,
        variables: list[str],
        date_col: str,
        station_col: str,
        log: logging.Logger,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, list[str]]:
        """
        Procesa todas las estaciones del DataFrame.

        Returns:
            sequences : (N_total, window_size, n_features) float32 — valores
                        con NaN donde el dato es faltante.
            day_diffs : (N_total, window_size) float32 — días calendario
                        entre filas consecutivas dentro de la ventana.
            meta      : (N_total, 2) int64 — [station_idx, start_date_ordinal].
            stations  : lista de códigos de estación en el mismo orden que
                        los índices guardados en meta.
        """
        stations = sorted(df[station_col].unique())
        station_to_idx = {s: i for i, s in enumerate(stations)}

        all_seqs: list[np.ndarray] = []
        all_diffs: list[np.ndarray] = []
        all_meta: list[np.ndarray] = []

        for station in stations:
            df_st = (
                df[df[station_col] == station]
                .sort_values(date_col)
                .reset_index(drop=True)
            )
            T = len(df_st)

            if T < self.window_size:
                log.debug(
                    f"  [{station}] {T} filas < window_size={self.window_size}, omitida"
                )
                continue

            dates = df_st[date_col].values.astype("datetime64[D]")
            values = df_st[variables].values.astype(np.float32)

            day_diffs_raw = np.diff(dates.astype(np.int64)).astype(np.float32)

            seqs, diffs, start_dates = self._extract_windows(
                values, day_diffs_raw, dates
            )

            if seqs is None:
                log.debug(
                    f"  [{station}] Sin ventanas válidas (todos los gaps "
                    f"> {self.max_gap_days} días)"
                )
                continue

            N = len(seqs)
            meta = np.stack(
                [
                    np.full(N, station_to_idx[station], dtype=np.int64),
                    start_dates.astype(np.int64),
                ],
                axis=1,
            )

            all_seqs.append(seqs)
            all_diffs.append(diffs)
            all_meta.append(meta)

            log.info(f"  [{station}] filas={T:,} → ventanas={N:,}")

        if not all_seqs:
            return None, None, None, stations

        return (
            np.concatenate(all_seqs, axis=0),
            np.concatenate(all_diffs, axis=0),
            np.concatenate(all_meta, axis=0),
            stations,
        )

    # ------------------------------------------------------------------
    # Lógica interna
    # ------------------------------------------------------------------

    def _extract_windows(
        self,
        values: np.ndarray,
        day_diffs_raw: np.ndarray,
        dates: np.ndarray,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
        """
        Extrae ventanas válidas de una única serie de estación.

        Una ventana que comienza en posición s es válida si ninguna de las
        transiciones internas (de fila t a t+1, con s < t < s+window_size)
        supera max_gap_days.

        Returns (sequences, day_diffs, start_dates) o (None, None, None).
        """
        T, _ = values.shape
        ws = self.window_size

        if T < ws:
            return None, None, None

        # valid_trans[t] = True  ↔  la transición desde la fila t-1 hasta t
        # tiene day_diff <= max_gap_days.  La primera fila no tiene transición previa.
        valid_trans = np.ones(T, dtype=bool)
        valid_trans[1:] = day_diffs_raw <= self.max_gap_days

        # Para ws=1 no hay transiciones internas (siempre válido).
        # Para ws>=2 necesitamos sliding_window_view sobre valid_trans[1:].
        if ws == 1:
            all_starts = np.arange(0, T, self.stride)
            valid_starts = all_starts
        else:
            # trans_windows[s] = [valid_trans[s+1], ..., valid_trans[s+ws-1]]
            # shape: (T-ws+1, ws-1)
            trans_windows = sliding_window_view(valid_trans[1:], ws - 1)
            valid_mask = np.all(trans_windows, axis=1)  # (T-ws+1,)

            all_starts = np.arange(0, T - ws + 1, self.stride)
            valid_starts = all_starts[valid_mask[all_starts]]

        if len(valid_starts) == 0:
            return None, None, None

        # Extracción vectorizada con indexación avanzada
        idx = valid_starts[:, None] + np.arange(ws)[None, :]  # (N, ws)
        seqs = values[idx]  # (N, ws, F)

        # day_diffs por ventana: la posición 0 de cada ventana recibe el
        # gap desde la fila anterior (o 0 si la ventana comienza al inicio).
        all_diffs_padded = np.concatenate([[0.0], day_diffs_raw])  # (T,)
        diffs = all_diffs_padded[idx]  # (N, ws)

        start_dates = dates[valid_starts]  # (N,)

        return seqs, diffs, start_dates


# ---------------------------------------------------------------------------
# Dataset PyTorch para uso durante entrenamiento
# ---------------------------------------------------------------------------

class TimeSeriesDataset:
    """
    Dataset PyTorch para series temporales con máscaras de imputación.

    Carga los tensores pre-construidos (.pt) y sirve tuplas
    (X, mask, delta) listas para DataLoader.

    Compatibilidad de entrada por modelo:
        BRITS  → dict con keys "X", "mask", "delta"
        SAITS  → tensor X con máscara separada
        CSDI   → misma estructura, se adapta en el modelo
        LSTM/GRU → solo X (máscara opcional en loss)
        VAE/Autoencoders → X + mask (ELBO loss enmascarado)

    Args:
        X_path     : Ruta al tensor X_*.pt  (N, T, F) float32.
        mask_path  : Ruta al tensor mask_*.pt (N, T, F) float32.
        delta_path : Ruta al tensor delta_*.pt (N, T, F) float32.
        device     : Dispositivo de destino ("cpu" o "cuda").
    """

    def __init__(
        self,
        X_path: str | Path,
        mask_path: str | Path,
        delta_path: str | Path,
        device: str = "cpu",
    ) -> None:
        try:
            import torch
        except ImportError as exc:
            raise ImportError(
                "PyTorch no está instalado. Ejecuta: pip install torch"
            ) from exc

        def _load(path: str) -> "torch.Tensor":
            try:
                return torch.load(path, weights_only=True).to(device)
            except TypeError:
                # PyTorch < 2.0 no acepta weights_only
                return torch.load(path).to(device)

        self._X     = _load(str(X_path))
        self._mask  = _load(str(mask_path))
        self._delta = _load(str(delta_path))

        if not (self._X.shape == self._mask.shape == self._delta.shape):
            raise ValueError(
                f"X {self._X.shape}, mask {self._mask.shape} y delta "
                f"{self._delta.shape} deben tener la misma forma."
            )

    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._X.shape[0]

    def __getitem__(self, idx: int) -> dict:
        return {
            "X": self._X[idx],
            "mask": self._mask[idx],
            "delta": self._delta[idx],
        }

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self._X.shape)

    @property
    def n_sequences(self) -> int:
        return self._X.shape[0]

    @property
    def window_size(self) -> int:
        return self._X.shape[1]

    @property
    def n_features(self) -> int:
        return self._X.shape[2]

    def get_dataloader(
        self,
        batch_size: int = 32,
        shuffle: bool = True,
        num_workers: int = 0,
    ):
        """Devuelve un DataLoader configurado para este dataset."""
        try:
            from torch.utils.data import DataLoader, TensorDataset
        except ImportError as exc:
            raise ImportError("PyTorch no está instalado.") from exc

        dataset = TensorDataset(self._X, self._mask, self._delta)
        return DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            pin_memory=(self._X.device.type == "cpu"),
        )
