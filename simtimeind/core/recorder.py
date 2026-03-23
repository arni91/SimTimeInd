# core/recorder.py
# ---------------------------------------------------------------
# Responsabilidad única: serializar / deserializar grabaciones.
# Desacoplado del motor y de la UI.
# ---------------------------------------------------------------

from __future__ import annotations
import gzip, json, os

from .engine import Engine
from .constants import (
    BELT_SPEED_MPM, DT_S, TOTE_LEN_M, BOX_MEAN_M, BOX_MIN_M, BOX_MAX_M,
    STANDARD_GAP_M, DX_WITHIN_PAIR_M, DX_BETWEEN_PAIRS_M,
    RETRY_CHECK_S,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    MOTOR_POSITIONS_M, MOTOR_SPEEDS_MPM,
)


def to_dict(engine: Engine) -> dict:
    """Construye el dict de grabación en memoria (sin serializar a disco)."""
    engine.finalize()

    cycle_stats_st = []
    for st in engine.stations:
        mean = (st.cycle_sum_s / st.cycle_count) if st.cycle_count > 0 else 0.0
        cycle_stats_st.append({
            "sid":    st.sid,
            "count":  st.cycle_count,
            "mean_s": mean,
            "min_s":  st.cycle_min_s if st.cycle_count > 0 else 0.0,
            "max_s":  st.cycle_max_s if st.cycle_count > 0 else 0.0,
        })

    cnt  = engine.cycle_count_total
    mean = (engine.cycle_sum_total / cnt) if cnt > 0 else 0.0
    cycle_stats_total = {
        "count":  cnt,
        "mean_s": mean,
        "min_s":  engine.cycle_min_total if cnt > 0 else 0.0,
        "max_s":  engine.cycle_max_total if cnt > 0 else 0.0,
    }

    return {
        "meta": {
            "stations":             engine.n,
            "duration_s":           engine.duration_s,
            "dt_s":                 DT_S,
            "belt_speed_mpm":       BELT_SPEED_MPM,
            "standard_gap_m":       engine.standard_gap_m,
            "effective_gap_m":      engine.effective_gap_m,
            "push_enabled":         engine.push_enabled,
            "retry_check_s":        RETRY_CHECK_S,
            "tote_len_m":           TOTE_LEN_M,
            "box_mean_m":           BOX_MEAN_M,
            "box_sd_m":             engine.box_sd_m,
            "box_min_m":            BOX_MIN_M,
            "box_max_m":            BOX_MAX_M,
            "dx_within_pair_m":     DX_WITHIN_PAIR_M,
            "dx_between_pairs_m":   DX_BETWEEN_PAIRS_M,
            "belt_end_m":           engine.belt_end_m,
            "cycle_mean_s":         engine.cycle_mean_s,
            "cycle_sd_s":           engine.cycle_sd_s,
            "cycle_min_s":          engine.cycle_min_s,
            "cycle_max_s":          engine.cycle_max_s,
            "p2":                   engine.p2,
            "p3":                   engine.p3,
            "target_total_h":       engine.target_total_h,
            "target_boxes_h":       engine.target_boxes_h,
            "target_totes_h":       engine.target_totes_h,
            "warmup_s":             engine.warmup_s,
            "counter_x_m":          engine.counter_x if hasattr(engine, "counter_x") else 0.0,
            "cycle_stats_total":    cycle_stats_total,
            "cycle_stats_stations": cycle_stats_st,
            "mean_tote_s":          0.0,
            "mean_box_s":           0.0,
            "motor_positions_m":    list(getattr(engine, "motor_positions", MOTOR_POSITIONS_M)),
            "motor_speeds_mpm":     [s * 60.0 for s in getattr(engine, "motor_speeds_mps", [v/60 for v in MOTOR_SPEEDS_MPM])],
        },
        "stations": [
            {"sid": st.sid, "x": st.x, "start_at": st.start_at}
            for st in engine.stations
        ],
        "blocked_intervals": [
            [list(iv) for iv in st.blocked_intervals]
            for st in engine.stations
        ],
        "events": engine.events,
        "counters": {
            "inserted_total": engine.inserted_total,
            "inserted_boxes": engine.inserted_boxes,
            "inserted_totes": engine.inserted_totes,
        },
    }


def save(engine: Engine, path: str) -> None:
    """Exporta el estado completo del motor a un .sim.gz."""
    engine.finalize()

    cycle_stats_st = []
    for st in engine.stations:
        mean = (st.cycle_sum_s / st.cycle_count) if st.cycle_count > 0 else 0.0
        cycle_stats_st.append({
            "sid":    st.sid,
            "count":  st.cycle_count,
            "mean_s": mean,
            "min_s":  st.cycle_min_s if st.cycle_count > 0 else 0.0,
            "max_s":  st.cycle_max_s if st.cycle_count > 0 else 0.0,
        })

    cnt  = engine.cycle_count_total
    mean = (engine.cycle_sum_total / cnt) if cnt > 0 else 0.0
    cycle_stats_total = {
        "count":  cnt,
        "mean_s": mean,
        "min_s":  engine.cycle_min_total if cnt > 0 else 0.0,
        "max_s":  engine.cycle_max_total if cnt > 0 else 0.0,
    }

    record = {
        "meta": {
            "stations":           engine.n,
            "duration_s":         engine.duration_s,
            "dt_s":               DT_S,
            "belt_speed_mpm":     BELT_SPEED_MPM,
            "standard_gap_m":     engine.standard_gap_m,
            "effective_gap_m":    engine.effective_gap_m,
            "push_enabled":       engine.push_enabled,
            "retry_check_s":      RETRY_CHECK_S,
            "tote_len_m":         TOTE_LEN_M,
            "box_mean_m":         BOX_MEAN_M,
            "box_sd_m":           engine.box_sd_m,
            "box_min_m":          BOX_MIN_M,
            "box_max_m":          BOX_MAX_M,
            "dx_within_pair_m":   DX_WITHIN_PAIR_M,
            "dx_between_pairs_m": DX_BETWEEN_PAIRS_M,
            "belt_end_m":         engine.belt_end_m,
            "cycle_mean_s":       engine.cycle_mean_s,
            "cycle_sd_s":         engine.cycle_sd_s,
            "cycle_min_s":        engine.cycle_min_s,
            "cycle_max_s":        engine.cycle_max_s,
            "p2":                 engine.p2,
            "p3":                 engine.p3,
            "target_total_h":     engine.target_total_h,
            "target_boxes_h":     engine.target_boxes_h,
            "target_totes_h":     engine.target_totes_h,
            "cycle_stats_total":  cycle_stats_total,
            "cycle_stats_stations": cycle_stats_st,
            "motor_positions_m":  list(getattr(engine, "motor_positions", MOTOR_POSITIONS_M)),
            "motor_speeds_mpm":   [s * 60.0 for s in getattr(engine, "motor_speeds_mps", [v/60 for v in MOTOR_SPEEDS_MPM])],
        },
        "stations": [
            {"sid": st.sid, "x": st.x, "start_at": st.start_at}
            for st in engine.stations
        ],
        "blocked_intervals": [
            [list(iv) for iv in st.blocked_intervals]
            for st in engine.stations
        ],
        "events": engine.events,
        "counters": {
            "inserted_total": engine.inserted_total,
            "inserted_boxes": engine.inserted_boxes,
            "inserted_totes": engine.inserted_totes,
        },
    }

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(record, f)


def load(path: str) -> dict:
    """Carga un fichero .sim.gz y devuelve el dict raw."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)