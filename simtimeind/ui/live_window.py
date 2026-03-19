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
        self._events         = rec.get("events", [])
        self._belt_speed_mps = float(meta.get("belt_speed_mpm", BELT_SPEED_MPM)) / 60.0
        self._belt_end_m     = float(meta.get("belt_end_m", self._engine_ref.belt_end_m))
        self._counter_x_m    = float(meta.get("counter_x_m", COUNTER_X_M))
        self._warmup_s       = float(meta.get("warmup_s", 0.0))

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
        # Prefijos de tote/box por estación
        self._st_ev_t   = st_ev_t
        self._st_pref_tote = []
        self._st_pref_box  = []
        for si in range(n_st):
            pt = [0]; pb = [0]
            for kc in st_ev_kc[si]:
                pt.append(pt[-1] + (1 if kc == 1 else 0))
                pb.append(pb[-1] + (1 if kc == 0 else 0))
            self._st_pref_tote.append(pt)
            self._st_pref_box.append(pb)
        # Detectar stations packages_only (M22: solo paquetes, sin cubetas)
        self._st_packages_only = [False] * n_st
        if n_st > 0:
            self._st_packages_only[-1] = True  # última mesa = M22

        count_events: list[tuple[float, int]] = []
        for e in self._events:
            ev_t  = float(e[0]); st_idx = int(e[1]); kc = int(e[2])
            if st_idx < 0 or st_idx >= len(self._stations_raw):
                continue
            x0 = float(self._stations_raw[st_idx]["x"])
            travel = max(0.0, self._counter_x_m - x0) / max(1e-9, self._belt_speed_mps)
            t_count = ev_t + travel
            if t_count >= self._warmup_s:   # no contar durante calentamiento
                count_events.append((t_count, kc))
        count_events.sort(key=lambda r: r[0])

        self._count_t = [r[0] for r in count_events]
        self._cpref_total = [0]; self._cpref_box = [0]; self._cpref_tote = [0]
        for _, kc in count_events:
            self._cpref_total.append(self._cpref_total[-1] + 1)
            self._cpref_box.append(self._cpref_box[-1] + (1 if kc == 0 else 0))
            self._cpref_tote.append(self._cpref_tote[-1] + (1 if kc == 1 else 0))

        self._counter_first_t = count_events[0][0] if count_events else -1.0

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

        # station_production: todos los eventos hasta t_floor (sin filtro warmup)
        station_production = []
        for si, st in enumerate(self._stations_raw):
            idx_st = bisect.bisect_right(self._st_ev_t[si], t_floor)
            tc = self._st_pref_tote[si][idx_st]
            bc = self._st_pref_box[si][idx_st]
            po = self._st_packages_only[si]
            cc = bc if po else tc   # ciclos = totes (o boxes para M22)
            station_production.append((st["sid"], si, tc, bc, cc, po))

        wait_total = 0.0; wait_per = []; station_timers = []
        for i, st in enumerate(self._stations_raw):
            raw = self._blocked_raw[i] if i < len(self._blocked_raw) else []
            acc = 0.0; wait_now = 0.0
            for a, b in raw:
                if t_s <= a: continue
                acc += max(0.0, min(b, t_s) - a)
                if a <= t_s <= b: wait_now = t_s - a
            wait_total += acc
            wait_per.append((st["sid"], st["x"], acc, False, wait_now))
            station_timers.append((st["sid"], wait_now, -1.0, -1.0, -1.0, -1.0, 0))

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
        travel_time = (self._belt_end_m + max_len) / max(1e-9, self._belt_speed_mps)
        t0 = max(0.0, t_s - travel_time - 2.0)
        i0 = bisect.bisect_left(self._ev_t, t0)

        items: list[Item] = []
        for e in self._events[i0:idx]:
            ev_t = float(e[0]); st_idx = int(e[1]); kc = int(e[2]); length = float(e[3])
            ix   = float(e[4]) if len(e) > 4 and float(e[4]) > 0 else None
            if st_idx < 0 or st_idx >= len(self._stations_raw): continue
            dt    = t_s - ev_t
            x0    = ix if ix is not None else float(self._stations_raw[st_idx]["x"])
            front = x0 + self._belt_speed_mps * dt
            if front - length > self._belt_end_m: continue
            items.append(Item(kind="box" if kc == 0 else "tote",
                              front_x=front, length=length))
        return snap, items

    # ── Controles ────────────────────────────────────────────────────

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
