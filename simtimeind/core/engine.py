# core/engine.py
from __future__ import annotations
import random

from .constants import (
    BELT_SPEED_MPM, DT_S,
    TOTE_LEN_M, BOX_MEAN_M, BOX_SD_M_DEFAULT, BOX_MIN_M, BOX_MAX_M,
    STANDARD_GAP_M,
    RETRY_CHECK_S,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    COUNTER_X_M,
)
from .models import Item, Station, SimSnapshot
from .belt import build_station_positions, can_insert

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
            Station(sid=f"M{i+1:02d}", x=self.station_xs[i])
            for i in range(self.n)
        ]
        for st in self.stations:
            st.start_at = self.start_at_s + self.rng.random() * max(0.0, self.start_stagger_s)

        self.items  = []
        self.t      = 0.0
        self.inserted_total = 0
        self.inserted_boxes = 0
        self.inserted_totes = 0
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

    def _sample_box_length(self):
        for _ in range(30):
            v = self.rng.gauss(BOX_MEAN_M, max(1e-9, self.box_sd_m))
            if BOX_MIN_M <= v <= BOX_MAX_M:
                return v
        return BOX_MEAN_M

    def _sample_cycle_time(self):
        v = (self.rng.gauss(self.cycle_mean_s, self.cycle_sd_s)
             if self.cycle_sd_s > 0 else self.cycle_mean_s)
        return max(self.cycle_min_s, min(self.cycle_max_s, v))

    def _sample_packs_per_tote(self):
        r = self.rng.random()
        if r < self.p3:            return 3
        if r < self.p3 + self.p2:  return 2
        return 1

    def _commit_cycle_stats(self, st):
        T = float(st.cycle_T)
        st.cycle_count += 1;  st.cycle_sum_s += T
        st.cycle_min_s  = min(st.cycle_min_s, T)
        st.cycle_max_s  = max(st.cycle_max_s, T)
        self.cycle_count_total += 1;  self.cycle_sum_total += T
        self.cycle_min_total    = min(self.cycle_min_total, T)
        self.cycle_max_total    = max(self.cycle_max_total, T)

    def _plan_new_cycle(self, st):
        if st.cycles_started_once:
            self._commit_cycle_stats(st)
        else:
            st.cycles_started_once = True

        k  = self._sample_packs_per_tote()
        T  = self._sample_cycle_time()
        t0 = self.t

        # cubeta: lista entre 5-8s del inicio del ciclo
        tote_frac           = self.rng.uniform(_TOTE_RELEASE_FRAC_MIN, _TOTE_RELEASE_FRAC_MAX)
        st.tote_prep_start  = t0
        st.tote_ready_t     = t0 + tote_frac * T
        st.tote_next_try_t  = st.tote_ready_t
        st.tote_wait_start  = -1.0

        # paquetes: repartidos entre 45-90% del ciclo
        st.box_queue = []
        if k > 0:
            span = 0.90 - 0.45
            for i in range(k):
                frac = 0.45 + (i + 1) * (span / k)
                st.box_queue.append(t0 + frac * T)

        # timer P arranca cuando se induce la cubeta (se asigna en ese momento)
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
                if (st.tote_ready_t < 0
                        and not st.box_queue
                        and t >= st.cycle_start_t + st.cycle_T):
                    self._plan_new_cycle(st)

            for idx, st in enumerate(self.stations):
                if not st.started:
                    continue

                any_blocked = False

                # ── cubeta ───────────────────────────────────────
                if st.tote_ready_t >= 0 and t >= st.tote_ready_t:
                    if t >= st.tote_next_try_t:
                        # intento 1: gap normal (100mm)
                        inserted = False
                        if can_insert(self.items, st.x, TOTE_LEN_M, self.standard_gap_m):
                            inserted = True
                        # intento 2: push activo — comprimir items anteriores a gap=0
                        elif self.push_enabled and can_insert(self.items, st.x, TOTE_LEN_M, 0.0):
                            inserted = True
                        if inserted:
                            item_time = max(0.0, t - st.tote_ready_t)
                            st.tote_time_sum   += item_time
                            st.tote_time_count += 1
                            st.current_cycle_times.append(("tote", item_time))
                            self.items.append(Item("tote", st.x, TOTE_LEN_M))
                            self.inserted_total += 1
                            self.inserted_totes += 1
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
                        length = self._sample_box_length()
                        # intento 1: gap normal
                        inserted = False
                        if can_insert(self.items, st.x, length, self.standard_gap_m):
                            inserted = True
                        # intento 2: push
                        elif self.push_enabled and can_insert(self.items, st.x, length, 0.0):
                            inserted = True
                        if inserted:
                            ready_t   = st.box_queue.pop(0)
                            item_time = max(0.0, t - ready_t)
                            st.box_time_sum   += item_time
                            st.box_time_count += 1
                            st.current_cycle_times.append(("box", item_time))
                            self.items.append(Item("box", st.x, length))
                            self.inserted_total += 1
                            self.inserted_boxes += 1
                            self.events.append([t, idx, 0, float(length), 0])
                            st.box_next_try_t = t + RETRY_CHECK_S
                            # actualizar prep timer para el siguiente paquete
                            if st.box_queue:
                                st.box_prep_start      = t
                                st.box_current_ready_t = st.box_queue[0]
                            else:
                                st.box_prep_start      = -1.0
                                st.box_current_ready_t = -1.0
                        else:
                            any_blocked       = True
                            st.box_next_try_t = t + RETRY_CHECK_S

                if any_blocked:
                    if st.blocked_since < 0:
                        st.blocked_since = t
                else:
                    if st.blocked_since >= 0:
                        st.blocked_intervals.append((st.blocked_since, t))
                        st.blocked_since = -1.0

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
            acc = sum(max(0.0, b - a) for a, b in st.blocked_intervals)
            blocked_now = False;  wait_now = 0.0
            if st.blocked_since >= 0:
                w = max(0.0, self.t - st.blocked_since)
                acc += w;  blocked_now = True;  wait_now = w
            wait_total += acc
            wait_per.append((st.sid, st.x, acc, blocked_now, wait_now))

            tote_prep_s = max(0.0, self.t - st.tote_prep_start) if st.tote_prep_start >= 0 else -1.0
            tote_wait_s = max(0.0, self.t - st.tote_wait_start) if st.tote_wait_start >= 0 else -1.0
            box_prep_s  = max(0.0, self.t - st.box_prep_start)  if (st.box_prep_start >= 0 and st.box_queue) else -1.0

            st_timers.append((st.sid, wait_now, tote_prep_s, box_prep_s, tote_wait_s))

            tote_sum += st.tote_time_sum;  tote_cnt += st.tote_time_count
            box_sum  += st.box_time_sum;   box_cnt  += st.box_time_count
            cycle_times_list.append((st.sid, list(st.current_cycle_times)))

        mean_tote = tote_sum / tote_cnt if tote_cnt > 0 else 0.0
        mean_box  = box_sum  / box_cnt  if box_cnt  > 0 else 0.0

        # tasa basada en tiempo desde que llego el primer item al contador
        t_counted = max(1.0, self.t - self.counter_first_t) if self.counter_first_t >= 0 else 1.0
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
        )

    def finalize(self):
        for st in self.stations:
            if st.blocked_since >= 0:
                st.blocked_intervals.append((st.blocked_since, self.duration_s))
                st.blocked_since = -1.0