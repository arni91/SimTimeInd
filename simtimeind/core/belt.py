# core/belt.py
from __future__ import annotations
from .constants import (
    DX_WITHIN_PAIR_M, DX_BETWEEN_PAIRS_M,
    DX_GAP_M6_M7, DX_GAP_M18_M19,
)

_SPECIAL_GAPS: dict[int, float] = {
    6:  DX_GAP_M6_M7,
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
    Comprueba si un ítem de longitud `length` puede insertarse en posición `x`.

    El nuevo ítem ocupa [x - length, x] en la cinta.
    Un ítem existente interfiere solo si su zona [rear_x, front_x] solapa
    con la zona de seguridad [x - length - gap, x + gap].

    Casos:
      - ítem ya pasó completamente (front_x <= x - length - gap): no interfiere
      - ítem aún no llegó (rear_x >= x + gap): no interfiere
      - cualquier otro caso: interfiere -> no se puede insertar
    """
    new_rear  = x - length
    zone_min  = new_rear - gap   # limite trasero de zona de seguridad
    zone_max  = x + gap          # limite delantero de zona de seguridad

    for it in items:
        # el item existente ocupa [it.rear_x, it.front_x]
        # interfiere si sus rangos se solapan con la zona de seguridad
        if it.front_x > zone_min and it.rear_x < zone_max:
            return False
    return True