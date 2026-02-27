# sim_core.py
from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Literal

# =========================
# CONSTANTES (FIJAS)
# =========================
BELT_SPEED_MPM = 22.0
MIN_GAP_M = 0.10
INDUCTION_TIME_S = 0.40

TARGET_BOXES_H = 1500
TARGET_TOTES_H = 1200

PICK_S, PACK_S, CLOSE_S = 5.0, 25.0, 5.0
TASK_TIME_S = PICK_S + PACK_S + CLOSE_S  # 35s

DT_S = 0.05

DX_WITHIN_PAIR_M = 1.15
DX_BETWEEN_PAIRS_M = 2.60

TOTE_LEN_M = 0.600
BOX_MEAN_M = 0.366
BOX_SD_M = 0.070
BOX_MIN_M = 0.200
BOX_MAX_M = 0.550

# squeeze
ALLOW_SQUEEZE_GAP_TO_ZERO_DEFAULT = True


@dataclass
class Item:
    kind: Literal["box", "tote"]
    front_x: float
    length: float

    @property
    def rear_x(self) -> float:
        return self.front_x - self.length


@dataclass
class Station:
    sid: str
    x: float

    start_at: float = 0.0
    started: bool = False
    busy_remain: float = 0.0

    out_queue: list[Literal["box", "tote"]] = field(default_factory=list)
    next_induce_t: float = 0.0

    blocked_now: bool = False
    blocked_since: float | None = None

    # métricas / logs
    blocked_intervals: list[tuple[float, float]] = field(default_factory=list)  # (start,end)
    inserted_boxes: int = 0
    inserted_totes: int = 0
    squeeze_used: int = 0


def build_station_positions(n: int) -> list[float]:
    xs = [0.0]
    for i in range(2, n + 1):
        inc = DX_WITHIN_PAIR_M if (i % 2 == 0) else DX_BETWEEN_PAIRS_M
        xs.append(xs[-1] + inc)
    return xs


def can_insert(items: list[Item], x: float, length: float, gap: float) -> bool:
    """
    Nuevo bulto ocupa [x-length, x].
    Exige gap mínimo con el de detrás y el de delante (en el instante actual).
    """
    new_front, new_rear = x, x - length
    behind_front = None
    ahead_rear = None

    for it in items:
        if it.front_x <= x:
            if behind_front is None or it.front_x > behind_front:
                behind_front = it.front_x
        else:
            r = it.rear_x
            if ahead_rear is None or r < ahead_rear:
                ahead_rear = r

    if behind_front is not None and (new_rear - behind_front) < gap:
        return False
    if ahead_rear is not None and (ahead_rear - new_front) < gap:
        return False
    return True


@dataclass
class SimConfig:
    stations: int = 22
    duration_s: float = 3600.0
    seed: int = 42
    start_stagger_s: float = 20.0
    allow_squeeze: bool = ALLOW_SQUEEZE_GAP_TO_ZERO_DEFAULT


@dataclass
class SimResults:
    cfg: SimConfig
    station_xs: list[float]
    belt_end_m: float
    events: list[dict]  # {t, kind, length, x, sid, squeezed}
    stations: list[Station]

    inserted_total: int
    inserted_boxes: int
    inserted_totes: int
    squeeze_used: int


class Simulator:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

        self.station_xs = build_station_positions(cfg.stations)
        self.stations = [Station(sid=f"M{i+1:02d}", x=self.station_xs[i]) for i in range(cfg.stations)]
        self.last_x = self.station_xs[-1]

        # belt geometry
        self.belt_speed_mps = BELT_SPEED_MPM / 60.0
        self.belt_end_m = self.last_x + 12.0

        # stagger start
        for st in self.stations:
            st.start_at = self.rng.random() * max(0.0, cfg.start_stagger_s)
            st.started = False
            st.busy_remain = 0.0

        # sim state
        self.items: list[Item] = []
        self.t = 0.0

        # counters
        self.events: list[dict] = []
        self.inserted_total = 0
        self.inserted_boxes = 0
        self.inserted_totes = 0
        self.squeeze_used = 0

        # deterministic tote ratio
        self.tote_acc = 0

    def sample_box_length(self) -> float:
        for _ in range(20):
            v = self.rng.gauss(BOX_MEAN_M, BOX_SD_M)
            if BOX_MIN_M <= v <= BOX_MAX_M:
                return v
        return max(BOX_MIN_M, min(BOX_MAX_M, BOX_MEAN_M))

    def next_order_has_tote(self) -> bool:
        # deterministic ~ 1200/1500 = 0.8
        self.tote_acc += TARGET_TOTES_H
        if self.tote_acc >= TARGET_BOXES_H:
            self.tote_acc -= TARGET_BOXES_H
            return True
        return False

    def try_insert(self, st: Station, length: float) -> tuple[bool, bool]:
        if can_insert(self.items, st.x, length, MIN_GAP_M):
            return True, False
        if self.cfg.allow_squeeze and can_insert(self.items, st.x, length, 0.0):
            return True, True
        return False, False

    def step(self, steps: int):
        for _ in range(steps):
            if self.t >= self.cfg.duration_s:
                return

            dt = DT_S
            t = self.t

            # move belt
            dx = self.belt_speed_mps * dt
            for it in self.items:
                it.front_x += dx
            self.items = [it for it in self.items if it.rear_x <= self.belt_end_m]

            # station production (orders)
            for st in self.stations:
                if not st.started:
                    if t >= st.start_at:
                        st.started = True
                        st.busy_remain = TASK_TIME_S
                    continue

                # if pending outputs, do not start another order
                if st.out_queue:
                    continue

                # preparing order
                if st.busy_remain > 0:
                    st.busy_remain -= dt
                    if st.busy_remain <= 0:
                        st.out_queue.append("box")
                        if self.next_order_has_tote():
                            st.out_queue.append("tote")
                        st.next_induce_t = t
                    continue

                # free and no queue -> start next order
                st.busy_remain = TASK_TIME_S

            # induction
            for st in self.stations:
                st.blocked_now = False

                while st.out_queue and t >= st.next_induce_t:
                    kind = st.out_queue[0]
                    length = self.sample_box_length() if kind == "box" else TOTE_LEN_M

                    ok, squeezed = self.try_insert(st, length)
                    if not ok:
                        st.blocked_now = True
                        if st.blocked_since is None:
                            st.blocked_since = t
                        break

                    # if it was blocked, close interval
                    if st.blocked_since is not None:
                        st.blocked_intervals.append((st.blocked_since, t))
                        st.blocked_since = None

                    # insert
                    st.out_queue.pop(0)
                    self.items.append(Item(kind=kind, front_x=st.x, length=length))

                    ev = {
                        "t": t,
                        "kind": kind,
                        "length": length,
                        "x": st.x,
                        "sid": st.sid,
                        "squeezed": squeezed,
                    }
                    self.events.append(ev)

                    self.inserted_total += 1
                    if kind == "box":
                        self.inserted_boxes += 1
                        st.inserted_boxes += 1
                    else:
                        self.inserted_totes += 1
                        st.inserted_totes += 1

                    if squeezed:
                        self.squeeze_used += 1
                        st.squeeze_used += 1

                    st.next_induce_t = t + INDUCTION_TIME_S

            self.t += dt

    def run(self) -> SimResults:
        steps_total = int(self.cfg.duration_s / DT_S)
        self.step(steps_total + 1)

        # close any ongoing block interval at end
        for st in self.stations:
            if st.blocked_since is not None:
                st.blocked_intervals.append((st.blocked_since, self.cfg.duration_s))
                st.blocked_since = None

        return SimResults(
            cfg=self.cfg,
            station_xs=self.station_xs,
            belt_end_m=self.belt_end_m,
            events=self.events,
            stations=self.stations,
            inserted_total=self.inserted_total,
            inserted_boxes=self.inserted_boxes,
            inserted_totes=self.inserted_totes,
            squeeze_used=self.squeeze_used,
        )