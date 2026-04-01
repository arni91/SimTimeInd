from __future__ import annotations

import bisect
import math
import time
import tkinter as tk
from typing import Any

from ..core.constants import (
    BELT_SPEED_MPM, BOX_MAX_M, TOTE_LEN_M, COUNTER_X_M,
    CANVAS_H, CANVAS_W,
    COLOR_BG, COLOR_PANEL_BG, COLOR_TEXT_SECONDARY,
    DT_S,
    MOTOR_POSITIONS_M, MOTOR_SPEEDS_MPM,
)
from ..core.engine import Engine
from ..core.models import Item, SimSnapshot
from ..core.recorder import save as save_record, to_dict as record_engine
from .canvas_renderer import CanvasRenderer


class LiveWindow:
    """Ventana principal de simulacion live con scrubbing instantaneo."""

    def __init__(
        self,
        engine: Engine,
        speed: float,
        view: str,
        record_path: str | None = None,
    ) -> None:
        self._engine_ref   = engine
        self.speed         = float(speed)
        self.view          = view
        self.record_path   = record_path
        self._ready        = False
        self._saved        = False

        if view == "tail":
            self.view_start = max(0.0, engine.last_x - 18.0)
        else:
            self.view_start = -2.0

        self.view_end = engine.belt_end_m
        self.scale    = (CANVAS_W - 120) / max(1e-9, self.view_end - self.view_start)

        self.root = tk.Tk()
        self.root.title(f"SimTimeInd - {engine.n} mesas - {speed}x")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(True, True)
        self.root.geometry(f"{CANVAS_W}x{CANVAS_H + 40}")

        # ── Layout grid (autohide scrollbars) ─────────────────────────
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        canvas_frame = tk.Frame(self.root, bg=COLOR_BG)
        canvas_frame.grid(row=0, column=0, sticky="nsew")

        hbar = tk.Scrollbar(self.root, orient="horizontal")
        vbar = tk.Scrollbar(self.root, orient="vertical")
        hbar.grid(row=2, column=0, sticky="ew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid_remove()
        vbar.grid_remove()

        def _xscroll(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                hbar.grid_remove()
            else:
                hbar.grid()
            hbar.set(first, last)

        def _yscroll(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                vbar.grid_remove()
            else:
                vbar.grid()
            vbar.set(first, last)

        self.canvas = tk.Canvas(
            canvas_frame,
            width=CANVAS_W, height=CANVAS_H,
            bg=COLOR_BG, highlightthickness=0,
            xscrollcommand=_xscroll,
            yscrollcommand=_yscroll,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(scrollregion=(0, 0, CANVAS_W, CANVAS_H))
        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)

        self._zoom = 1.0
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom)
        self.canvas.bind("<MouseWheel>",         self._on_scroll_v)

        ctrl = tk.Frame(self.root, bg=COLOR_PANEL_BG, height=34)
        ctrl.grid(row=1, column=0, columnspan=2, sticky="ew")

        btn_style: dict[str, Any] = {
            "bg": "#2A2E38", "fg": COLOR_TEXT_SECONDARY,
            "relief": "flat", "padx": 14, "pady": 4,
            "font": ("Helvetica", 10),
            "activebackground": "#3A3F4B", "activeforeground": "#E8ECF2",
            "cursor": "hand2",
        }

        tk.Button(ctrl, text="Play/Pausa",
                  command=self._toggle_pause, **btn_style
                  ).pack(side="left", padx=4, pady=3)

        tk.Label(ctrl, text="Velocidad:", bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Helvetica", 10)
                 ).pack(side="left")

        self._speed_var = tk.DoubleVar(value=self.speed)
        tk.Spinbox(ctrl, from_=0.1, to=50.0, increment=0.5,
                   textvariable=self._speed_var, width=5,
                   bg="#2A2E38", fg="#E8ECF2", relief="flat",
                   font=("Helvetica", 10), buttonbackground="#3A3F4B",
                   ).pack(side="left", padx=(2, 16))

        tk.Label(ctrl, text="Tiempo (min):", bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Helvetica", 10)
                 ).pack(side="left")

        self._dur        = engine.duration_s
        self._dur_min    = self._dur / 60.0
        self._t          = 0.0
        self._t_var      = tk.DoubleVar(value=0.0)
        self._slider     = tk.Scale(
            ctrl, from_=0.0, to=self._dur_min, resolution=0.05,
            orient="horizontal", length=CANVAS_W - 500,
            variable=self._t_var,
            bg=COLOR_PANEL_BG, fg=COLOR_TEXT_SECONDARY,
            troughcolor="#2A2E38", highlightthickness=0, relief="flat",
            state="disabled",
        )
        self._slider.pack(side="left", fill="x", expand=True, padx=8)
        self._slider.bind("<ButtonPress-1>",   lambda e: setattr(self, "_dragging", True))
        self._slider.bind("<ButtonRelease-1>", self._on_seek)
        self._dragging = False

        self._status_var = tk.StringVar(value="Calculando simulacion...")
        tk.Label(ctrl, textvariable=self._status_var,
                 bg=COLOR_PANEL_BG, fg=COLOR_TEXT_SECONDARY,
                 font=("Consolas", 9)).pack(side="right", padx=10)

        # Velocidades de motores usadas en la simulación
        self._motor_speeds_mpm: list[float] = [round(s * 60.0, 1) for s in engine.motor_speeds_mps]
        self._buffer_per_station = int(getattr(engine, "buffer_per_station", 1))

        self.renderer = CanvasRenderer(
            canvas=self.canvas,
            view_start=self.view_start,
            view_end=self.view_end,
            scale=self.scale,
            station_list=engine.stations,
            push_enabled=engine.push_enabled,
            effective_gap_m=engine.effective_gap_m,
            target_total_h=engine.target_total_h,
            target_boxes_h=engine.target_boxes_h,
            target_totes_h=engine.target_totes_h,
            duration_s=engine.duration_s,
            warmup_s=engine.warmup_s,
            view_label=view,
            buffer_per_station=self._buffer_per_station,
        )

        self._tick_n = 0
        self._paused = False
        self._last   = time.perf_counter()

        # Mensaje de carga centrado en el canvas
        self._loading_id = self.canvas.create_text(
            CANVAS_W // 2, CANVAS_H // 2,
            text="Simulando...",
            fill="#8B7BB5",
            font=("Helvetica", 28, "bold"),
            anchor="center",
        )

        # Lanzar batch tras primer frame (100ms para que la ventana pinte el canvas)
        self.root.after(100, self._run_batch)

    # ── Batch ────────────────────────────────────────────────────────

    def _run_batch(self) -> None:
        # Forzar repintado completo antes de bloquear el hilo con el cálculo
        self.root.update()
        eng = self._engine_ref
        steps = int(eng.duration_s / DT_S) + 1
        done  = 0
        while done < steps:
            n = min(50_000, steps - done)
            eng.step(n)
            done += n
            pct = done / steps * 100
            self._status_var.set(f"Calculando... {pct:.0f}%")
            if done % 200_000 == 0:
                self.root.update_idletasks()

        rec = record_engine(eng)
        self._setup_record(rec)
        self.canvas.delete(self._loading_id)
        self._ready = True
        self._slider.config(state="normal")
        self._status_var.set("Simulando...")
        self._last = time.perf_counter()

    def _setup_record(self, rec: dict) -> None:
        meta = rec.get("meta", {})
        self._stations_raw   = rec.get("stations", [])
        self._blocked_raw    = rec.get("blocked_intervals", [])
        self._plan_events_raw = rec.get("plan_events", [])
        self._events         = rec.get("events", [])
        self._count_events_raw = rec.get("count_events", [])
        self._belt_speed_mps = float(meta.get("belt_speed_mpm", BELT_SPEED_MPM)) / 60.0
        self._belt_end_m     = float(meta.get("belt_end_m", self._engine_ref.belt_end_m))
        self._counter_x_m    = float(meta.get("counter_x_m", COUNTER_X_M))
        self._warmup_s       = float(meta.get("warmup_s", 0.0))
        self._motor_positions_m = list(meta.get("motor_positions_m", list(MOTOR_POSITIONS_M)))
        loaded_speeds = list(meta.get("motor_speeds_mpm", list(MOTOR_SPEEDS_MPM)))
        self._motor_speeds_mps  = [s / 60.0 for s in loaded_speeds]
        self._motor_speeds_mpm  = loaded_speeds
        self._buffer_per_station = int(meta.get("buffer_per_station", self._buffer_per_station))
        if hasattr(self, "renderer"):
            self.renderer.motor_speeds_mpm = loaded_speeds
            self.renderer.buffer_per_station = self._buffer_per_station

        self._ev_t = [float(e[0]) for e in self._events]

        # Prefijos TOTALES (para visualización de items en cinta)
        self._pref_total = [0]; self._pref_box = [0]; self._pref_tote = [0]
        for e in self._events:
            kc = int(e[2])
            self._pref_total.append(self._pref_total[-1] + 1)
            self._pref_box.append(self._pref_box[-1] + (1 if kc == 0 else 0))
            self._pref_tote.append(self._pref_tote[-1] + (1 if kc == 1 else 0))

        # Prefijos POST-WARMUP (para tasas de producción reales)
        warmup = self._warmup_s
        self._prod_ev_t    = [float(e[0]) for e in self._events if float(e[0]) >= warmup]
        self._prod_ev_kc   = [int(e[2])   for e in self._events if float(e[0]) >= warmup]
        self._prod_pref_total = [0]; self._prod_pref_box = [0]; self._prod_pref_tote = [0]
        for kc in self._prod_ev_kc:
            self._prod_pref_total.append(self._prod_pref_total[-1] + 1)
            self._prod_pref_box.append(self._prod_pref_box[-1] + (1 if kc == 0 else 0))
            self._prod_pref_tote.append(self._prod_pref_tote[-1] + (1 if kc == 1 else 0))

        # Arrays por estación para station_production
        n_st = len(self._stations_raw)
        st_ev_t   = [[] for _ in range(n_st)]
        st_ev_kc  = [[] for _ in range(n_st)]
        for e in self._events:
            si = int(e[1])
            if 0 <= si < n_st:
                st_ev_t[si].append(float(e[0]))
                st_ev_kc[si].append(int(e[2]))
        # Prefijos de tote/box por estación + tiempos de eventos tote para timers
        self._st_ev_t      = st_ev_t
        self._st_pref_tote = []
        self._st_pref_box  = []
        self._st_tote_ev_t = []   # solo tiempos de eventos tote (kc=1) por estación
        self._st_box_ev_t  = []   # solo tiempos de eventos box  (kc=0) por estación
        # Post-warmup: para contar ciclos solo después del calentamiento
        self._st_ev_t_pw      = []
        self._st_pref_tote_pw = []
        self._st_pref_box_pw  = []
        for si in range(n_st):
            pt = [0]; pb = [0]
            tote_t = []; box_t = []
            pt_pw = [0]; pb_pw = [0]
            ev_t_pw = []
            for t_ev, kc in zip(st_ev_t[si], st_ev_kc[si]):
                pt.append(pt[-1] + (1 if kc == 1 else 0))
                pb.append(pb[-1] + (1 if kc == 0 else 0))
                if kc == 1: tote_t.append(t_ev)
                else:       box_t.append(t_ev)
                if t_ev >= warmup:
                    ev_t_pw.append(t_ev)
                    pt_pw.append(pt_pw[-1] + (1 if kc == 1 else 0))
                    pb_pw.append(pb_pw[-1] + (1 if kc == 0 else 0))
            self._st_pref_tote.append(pt)
            self._st_pref_box.append(pb)
            self._st_tote_ev_t.append(tote_t)
            self._st_box_ev_t.append(box_t)
            self._st_ev_t_pw.append(ev_t_pw)
            self._st_pref_tote_pw.append(pt_pw)
            self._st_pref_box_pw.append(pb_pw)
        # Detectar stations packages_only (M22: solo paquetes, sin cubetas)
        self._st_packages_only = [False] * n_st
        if n_st > 0:
            self._st_packages_only[-1] = True  # última mesa = M22

        self._st_plan_starts = [[] for _ in range(n_st)]
        self._st_plan_rows = [[] for _ in range(n_st)]
        for row in self._plan_events_raw:
            if len(row) < 10:
                continue
            st_idx = int(row[1])
            if 0 <= st_idx < n_st:
                self._st_plan_starts[st_idx].append(float(row[0]))
                if len(row) >= 12:
                    cycle_id = int(row[2])
                    slot_idx = int(row[3])
                    offset = 4
                    packages_only = bool(int(row[11]))
                elif len(row) >= 11:
                    cycle_id = int(row[2])
                    slot_idx = 0
                    offset = 3
                    packages_only = bool(int(row[10]))
                else:
                    cycle_id = len(self._st_plan_rows[st_idx])
                    slot_idx = 0
                    offset = 2
                    packages_only = bool(int(row[9]))
                self._st_plan_rows[st_idx].append({
                    "cycle_start": float(row[0]),
                    "cycle_id": cycle_id,
                    "slot_idx": slot_idx,
                    "tote_start": float(row[offset + 0]),
                    "tote_ready": float(row[offset + 1]),
                    "box1_start": float(row[offset + 2]),
                    "box1_ready": float(row[offset + 3]),
                    "box2_start": float(row[offset + 4]),
                    "box2_ready": float(row[offset + 5]),
                    "n_boxes": int(row[offset + 6]),
                    "packages_only": packages_only,
                })

        self._st_events_by_cycle: list[dict[int, dict[str, list[float]]]] = []
        for si in range(n_st):
            cycle_map: dict[int, dict[str, list[float]]] = {}
            for ev in self._events:
                if int(ev[1]) != si:
                    continue
                cycle_id = int(ev[5]) if len(ev) >= 6 else -1
                bucket = cycle_map.setdefault(cycle_id, {"tote": [], "box": []})
                kind = "tote" if int(ev[2]) == 1 else "box"
                bucket[kind].append(float(ev[0]))
            self._st_events_by_cycle.append(cycle_map)

        count_events: list[tuple[float, int]] = []
        if self._count_events_raw:
            for e in self._count_events_raw:
                if len(e) < 2:
                    continue
                count_events.append((float(e[0]), int(e[1])))
        else:
            for e in self._events:
                ev_t  = float(e[0]); st_idx = int(e[1]); kc = int(e[2])
                if st_idx < 0 or st_idx >= len(self._stations_raw):
                    continue
                x0 = float(self._stations_raw[st_idx]["x"])
                ix = float(e[4]) if len(e) > 4 and float(e[4]) > 0 else None
                x_start = ix if ix is not None else x0
                travel = self._time_to_reach(x_start, self._counter_x_m)
                t_count = ev_t + travel
                if t_count >= self._warmup_s:
                    count_events.append((t_count, kc))
            count_events.sort(key=lambda r: r[0])

        self._count_t = [r[0] for r in count_events]
        self._cpref_total = [0]; self._cpref_box = [0]; self._cpref_tote = [0]
        for _, kc in count_events:
            self._cpref_total.append(self._cpref_total[-1] + 1)
            self._cpref_box.append(self._cpref_box[-1] + (1 if kc == 0 else 0))
            self._cpref_tote.append(self._cpref_tote[-1] + (1 if kc == 1 else 0))

        self._counter_first_t = count_events[0][0] if count_events else -1.0

        # Índices de acceso rápido O(log n) para intervalos de bloqueo
        # _blk_starts[i]: lista de tiempos de inicio de cada intervalo de la estación i
        # _blk_prefix[i]: [0, d0, d0+d1, ...] — sumas acumuladas de duraciones
        n_st2 = len(self._stations_raw)
        self._blk_starts: list[list[float]] = []
        self._blk_prefix: list[list[float]] = []
        for i in range(n_st2):
            intervals = self._blocked_raw[i] if i < len(self._blocked_raw) else []
            starts  = [float(a) for a, b in intervals]
            prefix  = [0.0]
            for a, b in intervals:
                prefix.append(prefix[-1] + (float(b) - float(a)))
            self._blk_starts.append(starts)
            self._blk_prefix.append(prefix)

        cyc  = meta.get("cycle_stats_total", {})
        self._cyc_mean  = float(cyc.get("mean_s", 0.0))
        self._cyc_min   = float(cyc.get("min_s",  0.0))
        self._cyc_max   = float(cyc.get("max_s",  0.0))
        self._cyc_count = int(cyc.get("count",    0))

        self._tote_len = float(meta.get("tote_len_m", TOTE_LEN_M))
        self._box_max  = float(meta.get("box_max_m",  BOX_MAX_M))

    # ── Snapshot ─────────────────────────────────────────────────────

    def _snapshot_at(self, t_s: float) -> tuple[SimSnapshot, list[Item]]:
        t_s = max(1e-9, t_s)
        # t_floor: base en segundos enteros para que los valores sean estables 1s
        t_floor = max(1.0, math.floor(t_s))
        in_warmup = t_s < self._warmup_s

        idx = bisect.bisect_right(self._ev_t, t_s)

        # Producción PRÁCTICO: todos los eventos (incluye warmup), base = t_floor
        pidx = bisect.bisect_right(self._ev_t, t_floor)
        inserted_total = self._pref_total[pidx]
        inserted_boxes = self._pref_box[pidx]
        inserted_totes = self._pref_tote[pidx]

        # Contador (solo post-warmup, sin cambios)
        cidx = bisect.bisect_right(self._count_t, t_s)
        counted_total  = self._cpref_total[cidx]
        counted_boxes  = self._cpref_box[cidx]
        counted_totes  = self._cpref_tote[cidx]

        if self._counter_first_t >= 0.0 and t_s >= self._counter_first_t:
            t_cnt = max(1.0, t_s - self._counter_first_t)
        else:
            t_cnt = 1.0

        # station_production: tc/bc todos los eventos, cc solo post-warmup
        station_production = []
        for si, st in enumerate(self._stations_raw):
            idx_st = bisect.bisect_right(self._st_ev_t[si], t_floor)
            tc = self._st_pref_tote[si][idx_st]
            bc = self._st_pref_box[si][idx_st]
            po = self._st_packages_only[si]
            idx_pw = bisect.bisect_right(self._st_ev_t_pw[si], t_floor)
            tc_pw = self._st_pref_tote_pw[si][idx_pw]
            bc_pw = self._st_pref_box_pw[si][idx_pw]
            cc = bc_pw if po else tc_pw   # ciclos post-warmup
            station_production.append((st["sid"], si, tc, bc, cc, po))

        _TOTE_PREP_EST = 7.5   # estimación media de duración de preparación de cubeta (s)

        wait_total = 0.0; wait_per = []; station_timers = []
        for i, st in enumerate(self._stations_raw):
            raw     = self._blocked_raw[i] if i < len(self._blocked_raw) else []
            bstarts = self._blk_starts[i]
            bprefix = self._blk_prefix[i]

            # O(log n): acumulado hasta t_s usando sumas de prefijo
            blk_idx  = bisect.bisect_right(bstarts, t_s)   # primer intervalo con start > t_s
            acc      = bprefix[blk_idx]
            wait_now = 0.0
            if blk_idx > 0:
                a_last, b_last = raw[blk_idx - 1]
                if b_last > t_s:                            # intervalo activo: ajustar acc
                    acc     -= (b_last - t_s)
                    wait_now = t_s - a_last
            wait_total += acc
            wait_per.append((st["sid"], st["x"], acc, False, wait_now))
            plan_timer = self._station_timer_from_plan(i, t_s)
            if plan_timer is not None:
                station_timers.append((st["sid"], wait_now, *plan_timer))
                continue

            # ── Reconstruir estado de los 3 slots de preparación ─────
            tote_times = self._st_tote_ev_t[i]
            box_times  = self._st_box_ev_t[i]
            pkg_only   = self._st_packages_only[i]

            if pkg_only:
                # ── M22: solo paquetes, ciclo continuo ───────────────
                # Nunca muestra "OK" — en cuanto induce empieza el siguiente.
                idx_bx = bisect.bisect_right(box_times, t_s) - 1
                T_prev_box = box_times[idx_bx]     if idx_bx >= 0                 else None
                T_next_box = box_times[idx_bx + 1] if idx_bx + 1 < len(box_times) else None

                # Detectar intervalo de bloqueo activo (O(1), ya calculado arriba)
                blk_a = raw[blk_idx - 1][0] if wait_now > 0.0 else None

                if T_next_box is not None:
                    plan_box1_start = T_prev_box if T_prev_box is not None else 0.0
                    # Bloqueado: congelar en blk_a; sin bloqueo: contar hasta T_next_box
                    plan_box1_ready = blk_a if blk_a is not None else T_next_box
                    box1_induced    = False   # nunca OK
                else:
                    plan_box1_start = plan_box1_ready = -1.0
                    box1_induced    = False
                plan_tote_start = plan_tote_ready = -1.0; tote_induced  = False
                plan_box2_start = plan_box2_ready = -1.0; box2_induced  = False

            else:
                # ── M01–M21: ciclos cubeta + paquetes ────────────────
                idx_tp = bisect.bisect_right(tote_times, t_s) - 1
                T_last_tote = tote_times[idx_tp]     if idx_tp >= 0                       else None
                T_next_tote = tote_times[idx_tp + 1] if idx_tp + 1 < len(tote_times)      else None

                # Paquetes pertenecientes al ciclo actual [T_last_tote, T_next_tote)
                idx_bx0 = bisect.bisect_right(box_times, T_last_tote) if T_last_tote is not None else 0
                idx_bx1 = bisect.bisect_left(box_times, T_next_tote)  if T_next_tote is not None else len(box_times)
                cycle_boxes = box_times[idx_bx0:idx_bx1]

                # ¿Ciclo completo? Todos los paquetes del ciclo ya fueron inducidos
                cycle_complete = bool(cycle_boxes) and cycle_boxes[-1] <= t_s

                if T_last_tote is None:
                    # Primera cubeta del operario: aún preparándose antes del primer evento
                    T_first = tote_times[0] if tote_times else None
                    if T_first is not None:
                        plan_tote_start = max(0.0, T_first - _TOTE_PREP_EST)
                        plan_tote_ready = T_first
                    else:
                        plan_tote_start = plan_tote_ready = -1.0
                    tote_induced    = False
                    plan_box1_start = plan_box1_ready = -1.0; box1_induced = False
                    plan_box2_start = plan_box2_ready = -1.0; box2_induced = False

                elif cycle_complete and T_next_tote is not None:
                    blk_a = raw[blk_idx - 1][0] if wait_now > 0.0 else None

                    if blk_a is not None and T_next_tote > t_s:
                        # La estación está bloqueada y la próxima cubeta aún no se ha
                        # inductado. Esto ocurre cuando los paquetes se inductaron ANTES
                        # que su cubeta (congestión en M20/M21): cycle_complete se disparó
                        # prematuramente. Mostrar solo la cubeta congelada + bloqueo.
                        plan_tote_start = cycle_boxes[-1]
                        plan_tote_ready = blk_a
                        tote_induced    = False
                        plan_box1_start = plan_box1_ready = -1.0; box1_induced = False
                        plan_box2_start = plan_box2_ready = -1.0; box2_induced = False

                    else:
                        # ── CICLO COMPLETO: mostrar preparación de la nueva cubeta ──
                        T_new_start     = cycle_boxes[-1]
                        plan_tote_start = T_new_start
                        plan_tote_ready = T_new_start + _TOTE_PREP_EST
                        tote_induced    = (T_next_tote <= t_s)

                        # En cuanto acaba la prep de la cubeta, el paquete 1 empieza,
                        # independientemente de si la cubeta se ha inducido o no.
                        new_tote_ready = T_new_start + _TOTE_PREP_EST
                        if t_s >= new_tote_ready:
                            # Buscar los paquetes del nuevo ciclo (después de T_next_tote)
                            new_bx0 = bisect.bisect_right(box_times, T_next_tote)
                            new_boxes = box_times[new_bx0:new_bx0 + 2]  # máx 2 paquetes

                            if len(new_boxes) >= 1:
                                T_nb1 = new_boxes[0]
                                box1_induced    = (T_nb1 <= t_s)
                                plan_box1_start = new_tote_ready
                                plan_box1_ready = T_nb1 if box1_induced else (blk_a if blk_a is not None else T_nb1)
                            else:
                                plan_box1_start = plan_box1_ready = -1.0; box1_induced = False

                            if len(new_boxes) >= 2:
                                T_nb2 = new_boxes[1]
                                box2_induced    = (T_nb2 <= t_s)
                                plan_box2_start = new_boxes[0]
                                plan_box2_ready = T_nb2 if box2_induced else (blk_a if blk_a is not None else T_nb2)
                            else:
                                plan_box2_start = plan_box2_ready = -1.0; box2_induced = False
                        else:
                            plan_box1_start = plan_box1_ready = -1.0; box1_induced = False
                            plan_box2_start = plan_box2_ready = -1.0; box2_induced = False

                else:
                    # ── CICLO EN CURSO: cubeta ya inducida, paquetes pendientes ──
                    plan_tote_start = T_last_tote - _TOTE_PREP_EST
                    plan_tote_ready = T_last_tote
                    tote_induced    = True   # cubeta inducida en T_last_tote

                    # Detectar si la mesa está en un intervalo de bloqueo ahora mismo.
                    # blk_a = momento en que terminaron de prepararse TODOS los bultos
                    # del ciclo (= cuando empezó el bloqueo). Sirve para congelar los
                    # slots de items pendientes en vez de seguir contando.
                    blk_a = raw[blk_idx - 1][0] if wait_now > 0.0 else None

                    if len(cycle_boxes) >= 1:
                        T_box1       = cycle_boxes[0]
                        box1_induced = (T_box1 <= t_s)
                        plan_box1_start = T_last_tote
                        # Si pendiente y bloqueado: congelar en blk_a (fin de prep real)
                        # Si pendiente sin bloqueo: usar T_box1 (inducción inmediata a prep)
                        # Si inducido: usar T_box1 (correcto)
                        plan_box1_ready = T_box1 if box1_induced else (blk_a if blk_a is not None else T_box1)
                    else:
                        plan_box1_start = plan_box1_ready = -1.0; box1_induced = False

                    if len(cycle_boxes) >= 2:
                        T_box2       = cycle_boxes[1]
                        box2_induced = (T_box2 <= t_s)
                        plan_box2_start = cycle_boxes[0]
                        plan_box2_ready = T_box2 if box2_induced else (blk_a if blk_a is not None else T_box2)
                    else:
                        plan_box2_start = plan_box2_ready = -1.0; box2_induced = False

            station_timers.append((st["sid"], wait_now,
                                   plan_tote_start, plan_tote_ready, tote_induced,
                                   plan_box1_start, plan_box1_ready, box1_induced,
                                   plan_box2_start, plan_box2_ready, box2_induced,
                                   -1.0, -1.0, False,
                                   -1.0, -1.0, False,
                                   -1.0, -1.0, False))

        snap = SimSnapshot(
            t=t_floor,
            inserted_total=inserted_total,
            inserted_boxes=inserted_boxes,
            inserted_totes=inserted_totes,
            rate_total_h=inserted_total / t_floor * 3600.0,
            rate_boxes_h=inserted_boxes / t_floor * 3600.0,
            rate_totes_h=inserted_totes / t_floor * 3600.0,
            cycle_count=self._cyc_count,
            cycle_mean_s=self._cyc_mean,
            cycle_min_s=self._cyc_min,
            cycle_max_s=self._cyc_max,
            wait_total_s=wait_total,
            wait_per_station=wait_per,
            station_timers=station_timers,
            counted_total=counted_total,
            counted_boxes=counted_boxes,
            counted_totes=counted_totes,
            counted_total_h=counted_total  / t_cnt * 3600.0,
            counted_boxes_h=counted_boxes  / t_cnt * 3600.0,
            counted_totes_h=counted_totes  / t_cnt * 3600.0,
            counter_x_m=self._counter_x_m,
            warmup_s=self._warmup_s,
            in_warmup=in_warmup,
            station_production=station_production,
        )

        max_len     = max(self._tote_len, self._box_max)
        min_speed   = max(1e-9, min(self._motor_speeds_mps))
        travel_time = (self._belt_end_m + max_len) / min_speed
        t0 = max(0.0, t_s - travel_time - 2.0)
        i0 = bisect.bisect_left(self._ev_t, t0)

        items: list[Item] = []
        for e in self._events[i0:idx]:
            ev_t = float(e[0]); st_idx = int(e[1]); kc = int(e[2]); length = float(e[3])
            ix   = float(e[4]) if len(e) > 4 and float(e[4]) > 0 else None
            if st_idx < 0 or st_idx >= len(self._stations_raw): continue
            dt    = t_s - ev_t
            x0    = ix if ix is not None else float(self._stations_raw[st_idx]["x"])
            front = self._position_after(x0, dt)
            if front - length > self._belt_end_m: continue
            items.append(Item(kind="box" if kc == 0 else "tote",
                              front_x=front, length=length))
        items.sort(key=lambda it: it.front_x, reverse=True)
        for j in range(1, len(items)):
            leader = items[j - 1]
            follower = items[j]
            max_front = leader.rear_x
            if follower.front_x > max_front:
                follower.front_x = max_front
        return snap, items

    # ── Helpers de posición con velocidades por tramo ─────────────────

    def _motor_segment_index(self, x: float) -> int:
        pos = self._motor_positions_m
        n = len(pos)
        if n <= 1:
            return 0
        if x < pos[0]:
            return -1
        for i in range(n - 1, -1, -1):
            if x >= pos[i]:
                return i
        return n - 1

    def _position_after(self, x0: float, dt: float) -> float:
        """Posición de un ítem tras dt segundos desde x0, aplicando velocidades por motor."""
        x = x0
        t_rem = dt
        pos = self._motor_positions_m
        spd = self._motor_speeds_mps
        while t_rem > 1e-9:
            seg = self._motor_segment_index(x)
            speed = (BELT_SPEED_MPM / 60.0) if seg < 0 else spd[min(seg, len(spd) - 1)]
            if speed <= 0:
                break
            next_idx = seg + 1
            next_b = pos[next_idx] if 0 <= next_idx < len(pos) and pos[next_idx] > x else None
            if next_b is None:
                x += speed * t_rem
                break
            t_to_b = (next_b - x) / speed
            if t_to_b >= t_rem:
                x += speed * t_rem
                break
            x = next_b
            t_rem -= t_to_b
        return x

    def _time_to_reach(self, x0: float, target_x: float) -> float:
        """Tiempo (s) para que un ítem llegue de x0 a target_x con velocidades por motor."""
        if target_x <= x0:
            return 0.0
        t = 0.0
        x = x0
        pos = self._motor_positions_m
        spd = self._motor_speeds_mps
        remaining = target_x - x0
        while remaining > 1e-9:
            seg = self._motor_segment_index(x)
            speed = (BELT_SPEED_MPM / 60.0) if seg < 0 else spd[min(seg, len(spd) - 1)]
            if speed <= 0:
                return float('inf')
            next_idx = seg + 1
            next_b = pos[next_idx] if 0 <= next_idx < len(pos) and pos[next_idx] > x else None
            if next_b is None or next_b >= target_x:
                t += remaining / speed
                break
            dist_to_b = next_b - x
            t += dist_to_b / speed
            remaining -= dist_to_b
            x = next_b
        return t

    # ── Recalcular con nuevas velocidades de motor ────────────────────

    # ── Controles ────────────────────────────────────────────────────

    def _station_timer_from_plan(self, si: int, t_s: float):
        rows = self._st_plan_rows[si]
        if not rows:
            return None

        started = [row for row in rows if row["cycle_start"] <= t_s]
        if not started:
            return None

        def _cycle_slots(row: dict):
            events = self._st_events_by_cycle[si].get(row["cycle_id"], {"tote": [], "box": []})
            tote_induced = (not row["packages_only"]) and any(ev_t <= t_s for ev_t in events["tote"])
            box_count = sum(1 for ev_t in events["box"] if ev_t <= t_s)
            box1_induced = box_count > 0
            box2_induced = box_count > 1
            return (
                row["tote_start"], row["tote_ready"], tote_induced,
                row["box1_start"], row["box1_ready"], box1_induced,
                row["box2_start"], row["box2_ready"], box2_induced,
            )

        if started[-1]["packages_only"]:
            slot0_row = None
            slot1_row = None
            for row in started:
                if int(row.get("slot_idx", 0)) == 0:
                    slot0_row = row
                else:
                    slot1_row = row
            slot0 = _cycle_slots(slot0_row) if slot0_row is not None else (
                -1.0, -1.0, False, -1.0, -1.0, False, -1.0, -1.0, False
            )
            slot1 = _cycle_slots(slot1_row) if slot1_row is not None else (
                -1.0, -1.0, False, -1.0, -1.0, False, -1.0, -1.0, False
            )
            first_slots = (
                -1.0, -1.0, False,
                slot0[3], slot0[4], slot0[5],
                -1.0, -1.0, False,
            )
            second_slots = (
                -1.0, -1.0, False,
                slot1[3], slot1[4], slot1[5],
                -1.0, -1.0, False,
            )
        else:
            slot0_row = None
            slot1_row = None
            for row in started:
                if int(row.get("slot_idx", 0)) == 0:
                    slot0_row = row
                else:
                    slot1_row = row
            first_slots = _cycle_slots(slot0_row) if slot0_row is not None else (
                -1.0, -1.0, False, -1.0, -1.0, False, -1.0, -1.0, False
            )
            second_slots = _cycle_slots(slot1_row) if slot1_row is not None else (
                -1.0, -1.0, False, -1.0, -1.0, False, -1.0, -1.0, False
            )

        return first_slots + second_slots

    def _on_zoom(self, event) -> None:
        factor = 1.1 if event.delta > 0 else (1.0 / 1.1)
        self._zoom = max(0.3, min(4.0, self._zoom * factor))
        w = int(CANVAS_W * self._zoom); h = int(CANVAS_H * self._zoom)
        self.canvas.configure(scrollregion=(0, 0, w, h))

    def _on_scroll_v(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_seek(self, _event=None) -> None:
        self._dragging = False
        self._t = float(self._t_var.get()) * 60.0
        if self._ready:
            snap, items = self._snapshot_at(self._t)
            self._tick_n += 1
            self.renderer.draw(snap, items, self._tick_n, counter_snap=snap)
            if self._zoom != 1.0:
                self.canvas.scale("all", 0, 0, self._zoom, self._zoom)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._status_var.set("Pausado" if self._paused else "Simulando...")

    def run(self) -> None:
        self._schedule_tick()
        self.root.mainloop()

    def _schedule_tick(self) -> None:
        self.root.after(16, self._tick)

    def _read_speed(self) -> float:
        try:
            return max(0.1, float(self._speed_var.get()))
        except (tk.TclError, ValueError):
            self._speed_var.set(1.0)
            return 1.0

    def _tick(self) -> None:
        now     = time.perf_counter()
        real_dt = now - self._last
        self._last = now

        if self._ready and not self._paused:
            self._t = min(self._t + real_dt * self._read_speed(), self._dur)
            if not self._dragging:
                self._t_var.set(self._t / 60.0)

        if self._ready:
            snap, items = self._snapshot_at(self._t)
            self._tick_n += 1
            self.renderer.draw(snap, items, self._tick_n, counter_snap=snap)
            if self._zoom != 1.0:
                self.canvas.scale("all", 0, 0, self._zoom, self._zoom)

            if self._t >= self._dur and self.record_path and not self._saved:
                save_record(self._engine_ref, self.record_path)
                self._saved = True
                self.root.title(self.root.title() + " - OK")
                self._status_var.set("Grabacion guardada")

        self._schedule_tick()
