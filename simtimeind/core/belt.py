# core/belt.py
from __future__ import annotations
from .constants import (
    DX_WITHIN_PAIR_M, DX_BETWEEN_PAIRS_M,
    DX_GAP_M6_M7, DX_GAP_M16_M17, DX_GAP_M18_M19,
)

_SPECIAL_GAPS: dict[int, float] = {
    6:  DX_GAP_M6_M7,
    16: DX_GAP_M16_M17,
    18: DX_GAP_M18_M19,
}


def build_station_positions(n: int) -> list[float]:
    xs = [0.0]
    for i in range(2, n + 1):
        mesa_from = i - 1
        if mesa_from in _SPECIAL_GAPS:
            inc = _SPECIAL_GAPS[mesa_from]
        elif i % 2 == 0:
            inc = DX_WITHIN_PAIR_M
        else:
            inc = DX_BETWEEN_PAIRS_M
        xs.append(xs[-1] + inc)
    return xs


def can_insert(items: list, x: float, length: float, gap: float) -> bool:
    """
    Comprueba si un ítem de longitud `length` puede insertarse con front_x=x.
    El nuevo ítem ocupa [x - length, x] en la cinta.
    Hay conflicto si cualquier item existente solapa la zona [x-length-gap, x+gap].
    """
    zone_min = x - length - gap
    zone_max = x + gap
    for it in items:
        if it.front_x > zone_min and it.rear_x < zone_max:
            return False
    return True


def find_best_insert_x(items: list, x_center: float, length: float,
                        gap: float, half_range: float = 0.50) -> float | None:
    """
    Busca el punto óptimo de inducción (front_x) dentro del rango
    [x_center - half_range,  x_center + half_range].

    x_center es el punto nominal de inducción de la mesa (st.x).
    El bulto se puede inducir en cualquier front_x dentro de ese rango.

    Candidatos evaluados:
      - el centro exacto (x_center)
      - justo después de cada item vecino: front_x = it.front_x + gap + length
      - justo antes  de cada item vecino: front_x = it.rear_x  - gap

    Elige el candidato válido que maximiza el hueco mínimo a los vecinos,
    con pequeña penalización por alejarse del centro.

    Devuelve el front_x óptimo, o None si no cabe en ningún punto del rango.
    """
    fx_min = x_center - half_range   # front_x mínimo permitido
    fx_max = x_center + half_range   # front_x máximo permitido

    # Items que pueden interferir con cualquier punto del rango
    zone_min = fx_min - length - gap
    zone_max = fx_max + gap
    relevant = [it for it in items if it.front_x > zone_min and it.rear_x < zone_max]

    # Candidatos: centro + puntos óptimos junto a cada item vecino
    candidates: list[float] = [x_center]
    for it in relevant:
        candidates.append(it.front_x + gap + length)  # justo detrás del item
        candidates.append(it.rear_x  - gap)            # justo delante del item

    best_x: float | None = None
    best_score = -1e18

    for fx in candidates:
        # debe estar dentro del rango de inducción
        if fx < fx_min or fx > fx_max:
            continue
        if not can_insert(items, fx, length, gap):
            continue

        # maximizar el hueco mínimo a los vecinos
        min_dist = min(
            (min(abs(fx - it.front_x), abs(fx - length - it.rear_x))
             for it in relevant),
            default=half_range,
        )
        # penalizar alejarse del centro
        score = min_dist - abs(fx - x_center) * 0.01

        if best_x is None or score > best_score:
            best_x = fx
            best_score = score

    return best_x