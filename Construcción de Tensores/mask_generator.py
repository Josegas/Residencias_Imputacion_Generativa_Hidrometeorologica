"""
Generación y validación de máscaras para valores faltantes o imputados — RES-115

Implementa la convención de máscara estándar de los modelos BRITS, SAITS y CSDI:
  - mask[n, t, f] = 1  →  valor observado (no NaN)
  - mask[n, t, f] = 0  →  valor faltante o imputado (NaN)

Además calcula el tensor delta (días desde la última observación por variable),
requerido por BRITS para modelar la dinámica temporal de los datos faltantes.

Uso como módulo:
    from mask_generator import MaskGenerator

    gen = MaskGenerator()
    X, mask, delta = gen.generate(sequences, day_diffs)
"""

from __future__ import annotations

import numpy as np


class MaskGenerator:
    """
    Genera la máscara binaria de observación y el tensor delta temporal
    a partir de arrays de secuencias con NaN.

    Convention (BRITS / SAITS / CSDI):
        mask  = 1  →  observado
        mask  = 0  →  faltante
        delta[t, f] = días calendario transcurridos desde la última
                      observación del feature f hasta el paso t.

    Args:
        observed_value : Valor para posiciones observadas (default 1.0).
        missing_value  : Valor para posiciones faltantes (default 0.0).
    """

    def __init__(
        self,
        observed_value: float = 1.0,
        missing_value: float = 0.0,
    ) -> None:
        self.observed_value = float(observed_value)
        self.missing_value = float(missing_value)

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def generate(
        self,
        sequences: np.ndarray,
        day_diffs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Procesa un array de secuencias con posibles NaN.

        Args:
            sequences : (N, T, F) float32 — valores con NaN donde falta dato.
            day_diffs : (N, T) float32 — días calendario entre filas
                        consecutivas (posición 0 = 0, posición t = días
                        transcurridos desde la fila t-1).

        Returns:
            X     : (N, T, F) float32 — valores con NaN reemplazados por 0.
            mask  : (N, T, F) float32 — 1=observado, 0=faltante.
            delta : (N, T, F) float32 — días desde la última observación.
        """
        self._validate_inputs(sequences, day_diffs)

        mask = self._compute_mask(sequences)
        X = self._apply_mask(sequences, mask)
        delta = self._compute_delta(mask, day_diffs)

        return X, mask, delta

    # ------------------------------------------------------------------
    # Cálculo de máscara
    # ------------------------------------------------------------------

    def _compute_mask(self, sequences: np.ndarray) -> np.ndarray:
        """
        Máscara binaria: 1 donde el valor NO es NaN, 0 donde sí lo es.

        Para EVAP (38.7% NaN estructural por ausencia de sensor) y
        PRECIP/TMAX/TMIN (NaN puntuales), la máscara refleja con exactitud
        qué valores están disponibles para supervisión durante el entrenamiento.
        """
        observed = ~np.isnan(sequences)
        mask = np.where(observed, self.observed_value, self.missing_value)
        return mask.astype(np.float32)

    # ------------------------------------------------------------------
    # Sustitución de NaN en X
    # ------------------------------------------------------------------

    def _apply_mask(self, sequences: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Reemplaza NaN por 0 en las posiciones enmascaradas."""
        return np.where(mask == self.observed_value, sequences, 0.0).astype(np.float32)

    # ------------------------------------------------------------------
    # Delta temporal (BRITS-compatible)
    # ------------------------------------------------------------------

    def _compute_delta(
        self, mask: np.ndarray, day_diffs: np.ndarray
    ) -> np.ndarray:
        """
        Delta: días calendario transcurridos desde la última observación.

        Fórmula (Cao et al., 2018 — BRITS):
            delta[0, f]   = 0                              (sin historial)
            delta[t, f]   = day_diff_t                     si mask[t-1, f] = 1
            delta[t, f]   = delta[t-1, f] + day_diff_t    si mask[t-1, f] = 0

        Para series irregulares (gaps > 1 día), day_diff_t refleja los días
        calendario reales entre filas consecutivas, haciendo que delta acumule
        el tiempo real de ausencia en lugar de contar pasos unitarios.
        """
        N, T, F = mask.shape
        delta = np.zeros((N, T, F), dtype=np.float32)

        for t in range(1, T):
            dt = day_diffs[:, t : t + 1]        # (N, 1) → broadcast a (N, F)
            prev_observed = mask[:, t - 1, :]   # (N, F)
            # Observado en t-1:  delta[t] = dt
            # Faltante en t-1:   delta[t] = delta[t-1] + dt
            delta[:, t, :] = np.where(
                prev_observed == self.observed_value,
                dt,
                delta[:, t - 1, :] + dt,
            )

        return delta

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(sequences: np.ndarray, day_diffs: np.ndarray) -> None:
        if sequences.ndim != 3:
            raise ValueError(
                f"sequences debe tener ndim=3, se recibió ndim={sequences.ndim}"
            )
        N, T, _ = sequences.shape
        if day_diffs.shape != (N, T):
            raise ValueError(
                f"day_diffs debe tener shape ({N}, {T}), "
                f"se recibió {day_diffs.shape}"
            )

    # ------------------------------------------------------------------
    # Estadísticas de máscara (para logging / reporte)
    # ------------------------------------------------------------------

    @staticmethod
    def mask_stats(
        mask: np.ndarray,
        feature_names: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Retorna tasa de observación (%) por variable y global.

        Args:
            mask         : (N, T, F) float32.
            feature_names: nombres de variables (opcional).
        """
        _, _, F = mask.shape
        names = feature_names or [f"feat_{i}" for i in range(F)]
        stats: dict[str, float] = {}

        for f, name in enumerate(names):
            obs_rate = float(mask[:, :, f].mean()) * 100.0
            stats[name] = round(obs_rate, 2)

        stats["global"] = round(float(mask.mean()) * 100.0, 2)
        return stats
