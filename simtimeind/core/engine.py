# core/engine.py
from __future__ import annotations
import random
from collections import deque

_RATE_WINDOW_S = 60.0   # ventana deslizante para tasa de producción

from .constants import (
    BELT_SPEED_MPM, DT_S,
    TOTE_LEN_M, BOX_MEAN_M, BOX_SD_M_DEFAULT, BOX_MIN_M, BOX_MAX_M,
    STANDARD_GAP_M,
    RETRY_CHECK_S,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    COUNTER_X_M,
    INSERT_HALF_RANGE_M,
    CYCLE_MEAN_M01_M07_S,
    CYCLE_MEAN_M08_M14_S,
    CYCLE_MEAN_M15_M21_S,
    M22_PACKAGES_ONLY,
    M22_CYCLE_MEAN_S,
    M22_CYCLE_MIN_S,
    M22_CYCLE_MAX_S,
)
from .models import Item, Station, SimSnapshot
from .belt import build_station_positions, find_best_insert_x

_TOTE_RELEASE_FRAC_MIN = 0.08
_TOTE_RELEASE_FRAC_MAX = 0.13
_TOTE_MAX_WAIT_S       = 2.0


class Engine:

    def __init__(
        self,
        stations: int,
        duration_s: float,
        seed: int,
        start_at_s: float,
        start_stagger_s: float,
        cycle_mean_s: float,
        cycle_sd_s: float,
        cycle_min_s: float,
        cycle_max_s: float,
        p2: float,
        p3: float,
        box_sd_m: float = BOX_SD_M_DEFAULT,
        push_enabled: bool = True,
        target_total_h: float = TARGET_TOTAL_H,
        target_boxes_h: float = TARGET_BOXES_H,
        target_totes_h: float = TARGET_TOTES_H,
    ):
        self.n               = int(stations)
        self.duration_s      = float(duration_s)
        self.rng             = random.Random(seed)
        self.start_at_s      = float(start_at_s)
        self.start_stagger_s = float(start_stagger_s)
        self.cycle_mean_s    = float(cycle_mean_s)
        self.cycle_sd_s      = float(cycle_sd_s)
        self.cycle_min_s     = float(cycle_min_s)
        self.cycle_max_s     = float(cycle_max_s)
        self.p2              = float(p2)
        self.p3              = float(p3)
        self.box_sd_m        = float(box_sd_m)
        self.push_enabled    = bool(push_enabled)
        self.standard_gap_m  = STANDARD_GAP_M
        self.effective_gap_m = STANDARD_GAP_M
        self.target_total_h  = float(target_total_h)
        self.target_boxes_h  = float(target_boxes_h)
        self.target_totes_h  = float(target_totes_h)

        self.station_xs     = build_station_positions(self.n)
        self.last_x         = self.station_xs[-1]
        self.belt_end_m     = self.last_x + 12.0
        self.belt_speed_mps = BELT_SPEED_MPM / 60.0

        self.stations = [
            Station(sid=f"M{i+1:02d}", x=self.station_xs[i], idx=i)
            for i in range(self.n)
        ]
        for st in self.stations:
            st.start_at = self.start_at_s + self.rng.random() * max(0.0, self.start_stagger_s)
        # M22 (idx=21): induce solo paquetes si la constante está activada
        if M22_PACKAGES_ONLY and self.n > 21:
            self.stations[21].packages_only = True

        self.items  = []
        self.t      = 0.0
        self.inserted_total    = 0
        self.inserted_boxes    = 0
        self.inserted_totes    = 0
        self.inserted_boxes_m22 = 0   # boxes solo de M22 (mesa solo-paquetes)
        self._insert_window: deque = deque()   # (t, kind) para tasa deslizante
        self.events         = []
        # contadores en punto de conteo (COUNTER_X_M)
        self.counted_total = 0
        self.counted_boxes = 0
        self.counted_totes = 0
        self.counter_x     = COUNTER_X_M
        self.counter_first_t = -1.0   # momento en que llego el primer item
        self.cycle_count_total = 0
        self.cycle_sum_total   = 0.0
        self.cycle_min_total   = 1e18
        self.cycle_max_total   = 0.0
        # orden de proceso de estaciones (se baraja cada tick para equidad)
        self._station_order: list[int] = list(range(self.n))

    def _sample_box_length(self):
        for _ in range(30):
            v = self.rng.gauss(BOX_MEAN_M, max(1e-9, self.box_sd_m))
            if BOX_MIN_M <= v <= BOX_MAX_M:
                return v
        return BOX_MEAN_M

    def _sample_cycle_time(self, mean_s: float, min_s: float | None = None, max_s: float | None = None):
        cmin = min_s if min_s is not None else self.cycle_min_s
        cmax = max_s if max_s is not None else self.cycle_max_s
        v = (self.rng.gauss(mean_s, self.cycle_sd_s)
             if self.cycle_sd_s > 0 else mean_s)
        return max(cmin, min(cmax, v))

    def _sample_packs_per_tote(self):
        r = self.rng.random()
        if r < self.p3:            return 3
        if r < self.p3 + self.p2:  return 2
        return 1

    def _commit_cycle_stats(self, st):
        T = st.commit_cycle_stats()
        self.cycle_count_total += 1
        self.cycle_sum_total   += T
        self.cycle_min_total    = min(self.cycle_min_total, T)
        self.cycle_max_total    = max(self.cycle_max_total, T)

    def _plan_new_cycle(self, st):
        if st.cycles_started_once:
            self._commit_cycle_stats(st)
        else:
            st.cycles_started_once = True

        t0 = self.t

        # ── M22 (packages_only): ciclo corto, sin cubeta ─────────────
        # El paquete se planifica al 100% del ciclo: la duración del ciclo (T ≈ 22.5s)
        # dicta directamente la cadencia → tasa ≈ 3600/22.5 = 160 pkg/h sin zona muerta.
        if st.packages_only:
            T = self._sample_cycle_time(M22_CYCLE_MEAN_S,
                                        min_s=M22_CYCLE_MIN_S,
                                        max_s=M22_CYCLE_MAX_S)
            st.tote_ready_t     = -1.0   # nunca hay cubeta
            st.tote_prep_start  = -1.0
            st.tote_wait_start  = -1.0
            st.tote_next_try_t  = 0.0
            # 1 paquete listo al final del ciclo (el propio ciclo_T es la cadencia)
            st.box_queue            = [t0 + T]
            st.box_prep_start       = t0   # el operario empieza a preparar ya
            st.box_current_ready_t  = st.box_queue[0]
            st.box_next_try_t       = 0.0
            st.cycle_start_t        = t0
            st.cycle_T              = T
            st.current_cycle_times  = []
            return

        # ── ciclo normal (M01–M21) ────────────────────────────────────
        k  = self._sample_packs_per_tote()
        # Zona 1: M01–M07 (idx 0–6)  |  Zona 2: M08–M14 (idx 7–13)
        # Zona 3: M15–M21 (idx 14–20)
        if st.idx >= 14:
            mean_s = CYCLE_MEAN_M15_M21_S
        elif st.idx >= 7:
            mean_s = CYCLE_MEAN_M08_M14_S
        else:
            mean_s = CYCLE_MEAN_M01_M07_S
        T  = self._sample_cycle_time(mean_s)

        # cubeta: lista entre 8-13% del inicio del ciclo
        tote_frac          = self.rng.uniform(_TOTE_RELEASE_FRAC_MIN, _TOTE_RELEASE_FRAC_MAX)
        st.tote_prep_start = t0
        st.tote_ready_t    = t0 + tote_frac * T
        st.tote_next_try_t = st.tote_ready_t
        st.tote_wait_start = -1.0

        # paquetes: cola fresca para este ciclo
        st.box_queue = []
        if k > 0:
            span = 0.90 - 0.45
            for i in range(k):
                frac = 0.45 + (i + 1) * (span / k)
                st.box_queue.append(t0 + frac * T)
        st.box_prep_start      = -1.0
        st.box_current_ready_t = st.box_queue[0] if st.box_queue else -1.0
        st.box_next_try_t      = 0.0

        st.cycle_start_t       = t0
        st.cycle_T             = T
        st.current_cycle_times = []

    def step(self, n_steps):
        for _ in range(n_steps):
            if self.t >= self.duration_s:
                return

            t  = self.t
            dx = self.belt_speed_mps * DT_S

            for it in self.items:
                it.front_x += dx
            # detectar ítems que cruzan el punto de conteo en este tick
            for it in self.items:
                if it.front_x >= self.counter_x and (it.front_x - dx) < self.counter_x:
                    if self.counter_first_t < 0:
                        self.counter_first_t = self.t
                    self.counted_total += 1
                    if it.kind == "box":  self.counted_boxes += 1
                    else:                 self.counted_totes += 1
            self.items = [it for it in self.items if it.rear_x <= self.belt_end_m]

            for st in self.stations:
                if not st.started:
                    if t >= st.start_at:
                        st.started = True
                        self._plan_new_cycle(st)
                    continue
                # Mesas normales: nuevo ciclo cuando tote inducido, paquetes inducidos, y ciclo_T cumplido
                if (not st.packages_only
                        and st.tote_ready_t < 0
                        and not st.box_queue
                        and t >= st.cycle_start_t + st.cycle_T):
                    self._plan_new_cycle(st)

            # Últimas mesas primero: tienen el belt más lleno y necesitan prioridad
            # Las primeras mesas tienen espacio casi vacío cerca suyo de todos modos
            self.rng.shuffle(self._station_order)
            for idx in sorted(self._station_order, reverse=True):
                st = self.stations[idx]
                if not st.started:
                    continue

                any_blocked = False

                half_range = INSERT_HALF_RANGE_M

                # ── cubeta ───────────────────────────────────────
                if st.tote_ready_t >= 0 and t >= st.tote_ready_t:
                    if t >= st.tote_next_try_t:
                        insert_x = find_best_insert_x(
                            self.items, st.x, TOTE_LEN_M, self.standard_gap_m,
                            half_range=half_range)
                        # si no cabe con gap normal, intentar con push (gap=0)
                        if insert_x is None and self.push_enabled:
                            insert_x = find_best_insert_x(
                                self.items, st.x, TOTE_LEN_M, 0.0,
                                half_range=half_range)
                        if insert_x is not None:
                            item_time = max(0.0, t - st.tote_ready_t)
                            st.tote_time_sum   += item_time
                            st.tote_time_count += 1
                            st.current_cycle_times.append(("tote", item_time))
                            self.items.append(Item("tote", insert_x, TOTE_LEN_M))
                            self.inserted_total += 1
                            self.inserted_totes += 1
                            self._insert_window.append((t, "tote"))
                            self.events.append([t, idx, 1, float(TOTE_LEN_M), 0])
                            st.tote_ready_t    = -1.0
                            st.tote_prep_start = -1.0
                            st.tote_wait_start = -1.0
                            if st.box_queue:
                                st.box_prep_start = t
                        else:
                            if st.tote_wait_start < 0:
                                st.tote_wait_start = t
                            wait_so_far = t - st.tote_wait_start
                            if wait_so_far >= _TOTE_MAX_WAIT_S:
                                any_blocked = True
                                if st.box_prep_start < 0 and st.box_queue:
                                    st.box_prep_start = t
                            st.tote_next_try_t = t + RETRY_CHECK_S

                # ── paquetes ─────────────────────────────────────
                if st.box_queue and t >= st.box_queue[0]:
                    if t >= st.box_next_try_t:
                        length: float = self._sample_box_length()
                        insert_x = find_best_insert_x(
                            self.items, st.x, length, self.standard_gap_m,
                            half_range=half_range)
                        # si no cabe con gap normal, intentar con push (gap=0)
                        if insert_x is None and self.push_enabled:
                            insert_x = find_best_insert_x(
                                self.items, st.x, length, 0.0,
                                half_range=half_range)
                        if insert_x is not None:
                            ready_t   = st.box_queue.pop(0)
                            item_time = max(0.0, t - ready_t)
                            st.box_time_sum   += item_time
                            st.box_time_count += 1
                            st.current_cycle_times.append(("box", item_time))
                            self.items.append(Item("box", insert_x, length))
                            self.inserted_total += 1
                            self.inserted_boxes += 1
                            if st.packages_only:
                                self.inserted_boxes_m22 += 1
                            self._insert_window.append((t, "box"))
                            self.events.append([t, idx, 0, float(length), 0])
                            st.box_next_try_t = t + RETRY_CHECK_S
                            if st.box_queue:
                                st.box_prep_start      = t
                                st.box_current_ready_t = st.box_queue[0]
                            else:
                                # último paquete del ciclo
                                st.box_prep_start      = -1.0
                                st.box_current_ready_t = -1.0
                                if st.tote_ready_t < 0 and st.packages_only:
                                    # M22 (solo-paquetes): reiniciar inmediatamente —
                                    # no hay tiempo muerto, el ciclo es solo la cadencia
                                    self._plan_new_cycle(st)
                                # Mesas normales (M01–M21): el bucle principal gestiona
                                # el reinicio vía last_pkg_sched_t / cycle_T
                        else:
                            any_blocked       = True
                            st.box_next_try_t = t + RETRY_CHECK_S

                # ESPERAS: solo cuando el operario ha acabado de preparar todo
                # (último ítem ha llegado a su ready_t) y le queda al menos 1 bulto
                # pendiente de inducir — es cuando no puede coger la siguiente cubeta.
                last_item_ready_t = st.cycle_start_t + 0.90 * st.cycle_T
                if st.tote_ready_t >= 0:
                    last_item_ready_t = max(last_item_ready_t, st.tote_ready_t)
                if st.box_queue:
                    last_item_ready_t = max(last_item_ready_t, max(st.box_queue))
                items_pending = st.tote_ready_t >= 0 or bool(st.box_queue)
                if t >= last_item_ready_t and items_pending:
                    st.record_block_start(t)
                else:
                    st.record_block_end(t)

            self.t += DT_S

    def snapshot(self):
        t    = max(1e-9, self.t)
        cnt  = self.cycle_count_total
        mean = (self.cycle_sum_total / cnt) if cnt > 0 else 0.0

        wait_total = 0.0
        wait_per   = []
        st_timers  = []
        tote_sum, tote_cnt = 0.0, 0
        box_sum,  box_cnt  = 0.0, 0
        cycle_times_list   = []

        for st in self.stations:
            blocked_now = st.blocked_since >= 0
            wait_now    = max(0.0, self.t - st.blocked_since) if blocked_now else 0.0
            acc         = st.accumulated_wait_s(self.t)
            wait_total += acc
            wait_per.append((st.sid, st.x, acc, blocked_now, wait_now))

            tote_prep_s = max(0.0, self.t - st.tote_prep_start) if st.tote_prep_start >= 0 else -1.0
            tote_wait_s = max(0.0, self.t - st.tote_wait_start) if st.tote_wait_start >= 0 else -1.0
            box_prep_s  = max(0.0, self.t - st.box_prep_start)  if (st.box_prep_start >= 0 and st.box_queue) else -1.0

            st_timers.append((st.sid, wait_now, tote_prep_s, box_prep_s, tote_wait_s, -1.0, 0))

            tote_sum += st.tote_time_sum;  tote_cnt += st.tote_time_count
            box_sum  += st.box_time_sum;   box_cnt  += st.box_time_count
            cycle_times_list.append((st.sid, list(st.current_cycle_times)))

        mean_tote = tote_sum / tote_cnt if tote_cnt > 0 else 0.0
        mean_box  = box_sum  / box_cnt  if box_cnt  > 0 else 0.0

        # tasa deslizante (últimos 60s de inserciones)
        cutoff = self.t - _RATE_WINDOW_S
        while self._insert_window and self._insert_window[0][0] < cutoff:
            self._insert_window.popleft()
        w_total = len(self._insert_window)
        w_boxes = sum(1 for _, k in self._insert_window if k == "box")
        w_totes = w_total - w_boxes
        rate_win_total_h = w_total / _RATE_WINDOW_S * 3600.0
        rate_win_boxes_h = w_boxes / _RATE_WINDOW_S * 3600.0
        rate_win_totes_h = w_totes / _RATE_WINDOW_S * 3600.0

        # tasa acumulada para el contador (se mantiene para el display del contador)
        if self.counter_first_t >= 0:
            t_counted = max(1.0, self.t - self.counter_first_t)
        else:
            t_counted = max(1.0, self.t)
        return SimSnapshot(
            t=self.t,
            inserted_total=self.inserted_total,
            inserted_boxes=self.inserted_boxes,
            inserted_totes=self.inserted_totes,
            rate_total_h=self.inserted_total / t * 3600.0,
            rate_boxes_h=self.inserted_boxes / t * 3600.0,
            rate_totes_h=self.inserted_totes / t * 3600.0,
            cycle_count=cnt,
            cycle_mean_s=mean,
            cycle_min_s=self.cycle_min_total if cnt > 0 else 0.0,
            cycle_max_s=self.cycle_max_total if cnt > 0 else 0.0,
            wait_total_s=wait_total,
            wait_per_station=wait_per,
            station_timers=st_timers,
            mean_tote_s=mean_tote,
            mean_box_s=mean_box,
            cycle_times_per_station=cycle_times_list,
            counted_total=self.counted_total,
            counted_boxes=self.counted_boxes,
            counted_totes=self.counted_totes,
            counted_total_h=self.counted_total / t_counted * 3600.0,
            counted_boxes_h=self.counted_boxes / t_counted * 3600.0,
            counted_totes_h=self.counted_totes / t_counted * 3600.0,
            counter_x_m=self.counter_x,
            rate_window_total_h=rate_win_total_h,
            rate_window_boxes_h=rate_win_boxes_h,
            rate_window_totes_h=rate_win_totes_h,
            inserted_boxes_m22=self.inserted_boxes_m22,
            station_production=[(st.sid, st.idx, st.tote_time_count,
                                  st.box_time_count, st.cycle_count, st.packages_only)
                                 for st in self.stations],
        )

    def finalize(self):
        for st in self.stations:
            if st.blocked_since >= 0:
                st.record_block_end(self.duration_s)