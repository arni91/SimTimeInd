# python sim2d.py --stations 22 --duration 3600 --speed 1.0 --view full --start_stagger 20


import argparse, time, random
from dataclasses import dataclass, field
import tkinter as tk

# =========================
# CONSTANTES (FIJAS)
# =========================
BELT_SPEED_MPM = 22.0
MIN_GAP_M = 0.10
INDUCTION_TIME_S = 0.40

# objetivo cliente (referencia, por hora)
TARGET_BOXES_H = 1500
TARGET_TOTES_H = 1200

# tiempos operario
PICK_S, PACK_S, CLOSE_S = 5.0, 25.0, 5.0
TASK_TIME_S = PICK_S + PACK_S + CLOSE_S  # 35s

DT_S = 0.05

# Layout: M1-M2 juntos, GAP, M3-M4 juntos, GAP...
DX_WITHIN_PAIR_M = 1.15
DX_BETWEEN_PAIRS_M = 2.60

# Longitudes
TOTE_LEN_M = 0.600
BOX_MEAN_M = 0.366
BOX_SD_M = 0.070
BOX_MIN_M = 0.200
BOX_MAX_M = 0.550

# Si no cabe con gap=100mm, intenta gap=0mm (operario "hace hueco")
ALLOW_SQUEEZE_GAP_TO_ZERO = True

# Visual
CANVAS_W, CANVAS_H = 1280, 440
BELT_Y = 220


# =========================
# MODELO
# =========================
@dataclass
class Item:
    kind: str          # "box" o "tote"
    front_x: float
    length: float

    @property
    def rear_x(self):
        return self.front_x - self.length


@dataclass
class Station:
    sid: str
    x: float

    # arranque
    start_at: float = 0.0
    started: bool = False

    # ciclo de preparación (35s)
    busy_remain: float = 0.0

    # inducción
    out_queue: list[str] = field(default_factory=list)  # ✅ nunca None
    next_induce_t: float = 0.0

    # bloqueo para visual
    blocked_now: bool = False
    blocked_since: float | None = None


def build_station_positions(n: int) -> list[float]:
    xs = [0.0]
    for i in range(2, n + 1):
        inc = DX_WITHIN_PAIR_M if (i % 2 == 0) else DX_BETWEEN_PAIRS_M
        xs.append(xs[-1] + inc)
    return xs


def can_insert(items: list[Item], x: float, length: float, gap: float) -> bool:
    """
    Nuevo bulto ocupa [x-length, x].
    Exige gap mínimo con el de detrás y el de delante.
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


# =========================
# SIM + UI
# =========================
class Sim2D:
    def __init__(self, stations: int, speed: float, duration_s: float, view: str, seed: int, start_stagger_s: float):
        self.n = stations
        self.speed = speed
        self.duration_s = duration_s
        self.view = view
        self.rng = random.Random(seed)

        self.station_xs = build_station_positions(stations)
        self.stations = [Station(sid=f"M{i+1:02d}", x=self.station_xs[i]) for i in range(stations)]
        self.last_x = self.station_xs[-1]

        # asigna arranque aleatorio 0..start_stagger_s
        for st in self.stations:
            st.start_at = self.rng.random() * max(0.0, start_stagger_s)
            st.started = False
            st.busy_remain = 0.0

        self.belt_speed_mps = BELT_SPEED_MPM / 60.0
        self.belt_end_m = self.last_x + 12.0

        if view == "tail":
            self.view_start = max(0.0, self.last_x - 18.0)
            self.view_end = self.belt_end_m
        else:
            self.view_start = 0.0
            self.view_end = self.belt_end_m

        self.scale = (CANVAS_W - 100) / max(1e-9, (self.view_end - self.view_start))

        self.items: list[Item] = []
        self.t = 0.0

        # contadores
        self.inserted_total = 0
        self.inserted_boxes = 0
        self.inserted_totes = 0
        self.squeeze_used = 0
        self.done_orders = 0

        # ratio determinista tote/box ~ 1200/1500 = 0.8
        self.tote_acc = 0

        # UI
        self.root = tk.Tk()
        self.root.title(f"Simulación 2D - {stations} mesas | speed={speed}x | view={view}")
        self.canvas = tk.Canvas(self.root, width=CANVAS_W, height=CANVAS_H, bg="white")
        self.canvas.pack()

        self._last = time.perf_counter()
        self._acc = 0.0

    def x_to_px(self, x_m: float) -> int:
        return int(50 + (x_m - self.view_start) * self.scale)

    def in_view(self, x_m: float) -> bool:
        return self.view_start <= x_m <= self.view_end

    def sample_box_length(self) -> float:
        for _ in range(20):
            v = self.rng.gauss(BOX_MEAN_M, BOX_SD_M)
            if BOX_MIN_M <= v <= BOX_MAX_M:
                return v
        return max(BOX_MIN_M, min(BOX_MAX_M, BOX_MEAN_M))

    def next_order_has_tote(self) -> bool:
        self.tote_acc += TARGET_TOTES_H
        if self.tote_acc >= TARGET_BOXES_H:
            self.tote_acc -= TARGET_BOXES_H
            return True
        return False

    def try_insert(self, st: Station, length: float) -> tuple[bool, bool]:
        if can_insert(self.items, st.x, length, MIN_GAP_M):
            return True, False
        if ALLOW_SQUEEZE_GAP_TO_ZERO and can_insert(self.items, st.x, length, 0.0):
            return True, True
        return False, False

    def step(self, steps: int):
        for _ in range(steps):
            if self.t >= self.duration_s:
                return

            dt = DT_S
            t = self.t

            # mover cinta
            dx = self.belt_speed_mps * dt
            for it in self.items:
                it.front_x += dx
            self.items = [it for it in self.items if it.rear_x <= self.belt_end_m]

            # lógica de mesas
            for st in self.stations:
                # aún no ha empezado
                if not st.started:
                    if t >= st.start_at:
                        st.started = True
                        st.busy_remain = TASK_TIME_S  # empieza a preparar
                    continue

                # si hay bultos pendientes, NO empieza otro pedido
                if st.out_queue:
                    continue

                # preparando pedido
                if st.busy_remain > 0:
                    st.busy_remain -= dt
                    if st.busy_remain <= 0:
                        # pedido listo => 1 caja (+ tote si toca)
                        st.out_queue.append("box")
                        if self.next_order_has_tote():
                            st.out_queue.append("tote")
                        self.done_orders += 1
                        st.next_induce_t = t
                    continue

                # si está libre y sin cola, arranca siguiente pedido (35s)
                st.busy_remain = TASK_TIME_S

            # inducir
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

                    # insertar
                    st.out_queue.pop(0)
                    self.items.append(Item(kind=kind, front_x=st.x, length=length))

                    self.inserted_total += 1
                    if kind == "box":
                        self.inserted_boxes += 1
                    else:
                        self.inserted_totes += 1
                    if squeezed:
                        self.squeeze_used += 1

                    st.next_induce_t = t + INDUCTION_TIME_S
                    st.blocked_since = None

                if (not st.blocked_now) and (not st.out_queue):
                    st.blocked_since = None

            self.t += dt

    def draw_tag(self, x: int, y: int, text: str, fg: str, font=("Arial", 10)):
        pad = 2
        tmp = self.canvas.create_text(x, y, text=text, fill=fg, font=font)
        bbox = self.canvas.bbox(tmp)
        if bbox:
            x1, y1, x2, y2 = bbox
            self.canvas.delete(tmp)
            self.canvas.create_rectangle(x1 - pad, y1 - pad, x2 + pad, y2 + pad, fill="white", outline="")
        self.canvas.create_text(x, y, text=text, fill=fg, font=font)

    def draw_hud(self):
        thr_h = (self.inserted_total / self.t) * 3600.0 if self.t > 1e-6 else 0.0
        thr_box_h = (self.inserted_boxes / self.t) * 3600.0 if self.t > 1e-6 else 0.0
        thr_tote_h = (self.inserted_totes / self.t) * 3600.0 if self.t > 1e-6 else 0.0

        hud = (
            f"CONST: v={BELT_SPEED_MPM:.1f} m/min | gap={MIN_GAP_M*1000:.0f}mm (squeeze->0mm={'ON' if ALLOW_SQUEEZE_GAP_TO_ZERO else 'OFF'})"
            f" | t_induce={INDUCTION_TIME_S:.2f}s | t_operario={TASK_TIME_S:.0f}s\n"
            f"LENGTH: caja~N({BOX_MEAN_M*1000:.0f}mm) | cubeta={TOTE_LEN_M*1000:.0f}mm\n"
            f"TARGET/h: cajas={TARGET_BOXES_H} | cubetas={TARGET_TOTES_H} | total={TARGET_BOXES_H+TARGET_TOTES_H}\n"
            f"REAL  : inserted={self.inserted_total} (caja={self.inserted_boxes}, cubeta={self.inserted_totes})"
            f" | rate≈{thr_h:.0f}/h (caja≈{thr_box_h:.0f}/h, cubeta≈{thr_tote_h:.0f}/h)"
            f" | squeeze_used={self.squeeze_used}"
        )
        self.canvas.create_text(60, 14, text=hud, anchor="nw", font=("Consolas", 10), fill="black")

        lx = CANVAS_W - 280
        self.canvas.create_rectangle(lx, 15, lx + 18, 33, fill="dodgerblue", outline="")
        self.canvas.create_text(lx + 25, 24, text="Caja / Paquete (AZUL)", anchor="w", font=("Arial", 10))
        self.canvas.create_rectangle(lx, 40, lx + 18, 58, fill="orange", outline="")
        self.canvas.create_text(lx + 25, 49, text="Cubeta vacía (NARANJA)", anchor="w", font=("Arial", 10))

    def draw(self):
        self.canvas.delete("all")

        # cinta
        self.canvas.create_line(50, BELT_Y, self.x_to_px(self.view_end), BELT_Y, width=8)

        # estaciones + waits
        for i, st in enumerate(self.stations):
            if not self.in_view(st.x):
                continue

            x = self.x_to_px(st.x)
            within_pair = i % 2

            color = "red" if st.blocked_now else "black"
            self.canvas.create_line(x, BELT_Y - 38, x, BELT_Y + 38, fill=color, width=2)

            # IDs arriba en 2 filas por par
            y_sid = BELT_Y - (110 + within_pair * 18)
            self.canvas.create_text(x, y_sid, text=st.sid, fill=color, font=("Arial", 11, "bold"))

            # wait abajo: 2 filas + offset horizontal para no pisarse dentro del par
            if st.blocked_now and st.blocked_since is not None:
                dx_wait = -40 if within_pair == 0 else +40
                y_wait = BELT_Y + (85 + within_pair * 22)
                wait_s = self.t - st.blocked_since
                self.draw_tag(x + dx_wait, y_wait, f"wait={wait_s:0.1f}s", fg="red", font=("Arial", 10))

        # bultos
        for it in self.items:
            if not (self.in_view(it.front_x) or self.in_view(it.rear_x)):
                continue
            fx = self.x_to_px(it.front_x)
            rx = self.x_to_px(it.rear_x)
            y1, y2 = BELT_Y - 14, BELT_Y + 14
            color = "dodgerblue" if it.kind == "box" else "orange"
            self.canvas.create_rectangle(rx, y1, fx, y2, fill=color, outline="")

        self.draw_hud()
        self.canvas.create_text(
            60, CANVAS_H - 18,
            text=f"t={self.t:0.1f}s / {self.duration_s:.0f}s | stations={self.n} | view={self.view}",
            anchor="w", font=("Consolas", 10)
        )
        self.root.update_idletasks()

    def run(self):
        def tick():
            now = time.perf_counter()
            real_dt = now - self._last
            self._last = now

            self._acc += real_dt * self.speed
            steps = int(self._acc / DT_S)
            if steps > 120:
                steps = 120

            if steps > 0:
                self.step(steps)
                self._acc -= steps * DT_S

            self.draw()
            self.root.after(16, tick)

        tick()
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", type=int, default=22)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=3600.0)  # 1h
    ap.add_argument("--view", choices=["full", "tail"], default="full")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--start_stagger", type=float, default=20.0, help="ventana de arranque aleatorio 0..N segundos")
    args = ap.parse_args()

    Sim2D(args.stations, args.speed, args.duration, args.view, args.seed, args.start_stagger).run()


if __name__ == "__main__":
    main()