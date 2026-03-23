# core/belt.py
from __future__ import annotations
from .constants import (
    DX_WITHIN_PAIR_M, DX_BETWEEN_PAIRS_M,
    DX_GAP_M6_M7, DX_GAP_M16_M17, DX_GAP_M18_M19,
    INSERT_HALF_RANGE_M,
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
        rear_x = it.front_x - it.length
        if it.front_x > zone_min and rear_x < zone_max:
            return False
    return True


def find_best_insert_x(items: list, x_center: float, length: float,
                        gap: float, half_range: float = INSERT_HALF_RANGE_M) -> float | None:
    """
    Busca el punto óptimo de inducción (front_x) dentro del rango
    [x_center - half_range,  x_center + half_range].

    x_center es el punto nominal de inducción de la mesa (st.x).
    El bulto tiene su front_x dentro de ese rango.
    front_x mínimo absoluto = length (para que rear_x >= 0 en la cinta).

    Candidatos evaluados:
      - el centro del rango (o front_x mínimo si el centro queda fuera)
      - justo después de cada item vecino: it.front_x + gap + length
      - justo antes  de cada item vecino: it.rear_x  - gap

    Elige el candidato válido que maximiza el hueco mínimo a los vecinos,
    con pequeña penalización por alejarse del centro.

    Devuelve el front_x óptimo, o None si no cabe en ningún punto del rango.
    """
    fx_min   = max(length, x_center - half_range)          # rear_x no puede ser < 0
    fx_max   = max(length, x_center + half_range)          # idem
    fx_ideal = max(fx_min, min(fx_max, x_center))          # punto preferido dentro del rango

    if fx_min > fx_max:
        return None

    # Items que pueden interferir con cualquier punto del rango
    zone_min = fx_min - length - gap
    zone_max = fx_max + gap
    relevant = [it for it in items if it.front_x > zone_min and it.rear_x < zone_max]

    # Candidatos: punto ideal + puntos óptimos junto a cada item vecino
    candidates: list[float] = [fx_ideal]
    for it in relevant:
        candidates.append(it.front_x + gap + length)    # justo detrás del item
        candidates.append(it.rear_x  - gap)             # justo delante del item

    best_x: float | None = None
    best_score = -1e18

    for fx in candidates:
        if fx < fx_min or fx > fx_max:
            continue
        if not can_insert(relevant, fx, length, gap):
            continue

        min_dist = min(
            (min(abs(fx - it.front_x), abs(fx - length - (it.front_x - it.length)))
             for it in relevant),
            default=half_range,
        )
        score = min_dist - abs(fx - fx_ideal) * 0.05

        if best_x is None or score > best_score:
            best_x = fx
            best_score = score

    return best_x
