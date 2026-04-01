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
    idx: int = 0          # índice 0-based (M01=0 … M22=21)

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

    # ── buffer de 2 cubetas ───────────────────────────────────────
    tote_queue_extra: list  = field(default_factory=list)   # buffer slot 2 (cubeta ciclo N+1)
    cycle_queue: list       = field(default_factory=list)   # ciclos normales pendientes o en curso
    last_pkg_sched_t: float = -1.0   # t cuando el último paquete del ciclo está preparado
    next_cycle_seq: int     = 0
    active_cycle_id: int    = -1
    active_cycle_slot: int  = 0

    # ── plan del ciclo actual (set en _plan_new_cycle) ───────────
    # Tiempos absolutos de inicio y fin de preparación de cada item.
    # Cada temporizador empieza cuando acaba el anterior (secuencial),
    # independientemente de si el item anterior pudo inducirse o no.
    plan_tote_start: float = -1.0   # t cuando empieza la preparación de la cubeta
    plan_tote_ready: float = -1.0   # t cuando la cubeta estará lista para inducir
    plan_box1_start: float = -1.0   # t cuando empieza la prep del paquete 1 (= plan_tote_ready)
    plan_box1_ready: float = -1.0   # t cuando el paquete 1 estará listo
    plan_box2_start: float = -1.0   # t cuando empieza la prep del paquete 2 (= plan_box1_ready)
    plan_box2_ready: float = -1.0   # t cuando el paquete 2 estará listo (-1 si no hay)
    plan_n_boxes:    int   = 0      # número de paquetes planificados en este ciclo

    # ── paquetes: cola independiente ─────────────────────────────
    box_queue: list        = field(default_factory=list)  # [ready_t, ...]
    box_next_try_t: float  = 0.0
    # prep timer del paquete actual: (prep_start_t, ready_t)
    box_prep_start: float  = -1.0   # cuando el operario empieza a preparar este paquete
    box_current_ready_t: float = -1.0  # cuando estará listo para inducir

    # ── modo especial ────────────────────────────────────────────
    packages_only: bool     = False   # True → solo paquetes (sin cubeta), p.ej. M22

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

    # ── métodos de ciclo ─────────────────────────────────────────
    def commit_cycle_stats(self) -> float:
        """Registra las estadísticas del ciclo completado. Devuelve la duración."""
        T = float(self.cycle_T)
        self.cycle_count += 1
        self.cycle_sum_s += T
        self.cycle_min_s  = min(self.cycle_min_s, T)
        self.cycle_max_s  = max(self.cycle_max_s, T)
        return T

    def record_block_start(self, t: float) -> None:
        if self.blocked_since < 0:
            self.blocked_since = t

    def record_block_end(self, t: float) -> None:
        if self.blocked_since >= 0:
            self.blocked_intervals.append((self.blocked_since, t))
            self.blocked_since = -1.0

    def accumulated_wait_s(self, t_now: float) -> float:
        acc = sum(max(0.0, b - a) for a, b in self.blocked_intervals)
        if self.blocked_since >= 0:
            acc += max(0.0, t_now - self.blocked_since)
        return acc


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

    # Formato por estación:
    # (sid, wait_now_s,
    #  plan_tote_start, plan_tote_ready, tote_induced,      # slot 1: cubeta
    #  plan_box1_start, plan_box1_ready, box1_induced,      # slot 2: paquete 1
    #  plan_box2_start, plan_box2_ready, box2_induced)      # slot 3: paquete 2
    # Los tiempos son absolutos (s). -1.0 = slot no activo.
    # tote_induced / box_induced: True si ya fue inducido en este ciclo.
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

    # tasa por ventana deslizante (últimos 60s)
    rate_window_total_h: float = 0.0
    rate_window_boxes_h: float = 0.0
    rate_window_totes_h: float = 0.0

    # boxes insertados solo por M22 (para separar su tasa de M01-M21)
    inserted_boxes_m22: int    = 0

    # producción por estación: [(sid, idx, tote_count, box_count, cycle_count, packages_only)]
    station_production: list   = field(default_factory=list)

    # calentamiento
    warmup_s:  float = 0.0    # duración del calentamiento (s)
    in_warmup: bool  = False  # True mientras t < warmup_s
