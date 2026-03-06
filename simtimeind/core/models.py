# core/models.py
from dataclasses import dataclass, field


@dataclass
class Item:
    kind: str
    front_x: float
    length: float

    @property
    def rear_x(self) -> float:
        return self.front_x - self.length


@dataclass
class Station:
    sid: str
    x: float

    start_at: float = 5.0
    started: bool   = False

    cycle_start_t: float = 0.0
    cycle_T: float       = 60.0

    # ── cubeta: cola independiente ───────────────────────────────
    tote_ready_t: float    = -1.0   # momento en que el operario la deja lista (-1=ninguna)
    tote_next_try_t: float = 0.0
    tote_wait_start: float = -1.0   # inicio de espera de hueco en cinta (-1=no espera)
    # inicio de preparación de la cubeta (cuando el operario empieza a trabajar en ella)
    tote_prep_start: float = -1.0

    # ── paquetes: cola independiente ─────────────────────────────
    box_queue: list        = field(default_factory=list)  # [ready_t, ...]
    box_next_try_t: float  = 0.0
    # prep timer del paquete actual: (prep_start_t, ready_t)
    box_prep_start: float  = -1.0   # cuando el operario empieza a preparar este paquete
    box_current_ready_t: float = -1.0  # cuando estará listo para inducir

    # ── bloqueos para stats ──────────────────────────────────────
    blocked_since: float    = -1.0
    blocked_intervals: list = field(default_factory=list)

    # ── stats ciclo ──────────────────────────────────────────────
    cycles_started_once: bool = False
    cycle_count: int          = 0
    cycle_sum_s: float        = 0.0
    cycle_min_s: float        = 1e18
    cycle_max_s: float        = 0.0

    # ── stats por tipo ───────────────────────────────────────────
    tote_time_sum: float  = 0.0
    tote_time_count: int  = 0
    box_time_sum: float   = 0.0
    box_time_count: int   = 0

    current_cycle_times: list = field(default_factory=list)


@dataclass
class SimSnapshot:
    t: float
    inserted_total: int
    inserted_boxes: int
    inserted_totes: int
    rate_total_h: float
    rate_boxes_h: float
    rate_totes_h: float
    cycle_count: int
    cycle_mean_s: float   # = media del ciclo completo (cubeta + paquetes)
    cycle_min_s: float
    cycle_max_s: float
    wait_total_s: float
    wait_per_station: list

    # [(sid, wait_now_s, tote_prep_s, box_prep_s), ...]
    # wait_now_s  : segundos esperando hueco actualmente (0 si no espera)
    # tote_prep_s : segundos que lleva preparando/esperando inducir la cubeta (-1 si ninguna)
    # box_prep_s  : segundos que lleva preparando/esperando inducir el paquete actual (-1 si ninguno)
    station_timers: list = field(default_factory=list)

    mean_tote_s: float = 0.0
    mean_box_s: float  = 0.0

    cycle_times_per_station: list = field(default_factory=list)

    # contadores en punto de conteo (COUNTER_X_M)
    counted_total: int     = 0
    counted_boxes: int     = 0
    counted_totes: int     = 0
    counted_total_h: float = 0.0
    counted_boxes_h: float = 0.0
    counted_totes_h: float = 0.0
    counter_x_m: float     = 0.0