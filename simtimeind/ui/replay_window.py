# ui/replay_window.py
# ---------------------------------------------------------------
# Ventana de reproducción (replay) de grabaciones .sim.gz.
# Responsabilidad: reproducir eventos grabados con barra de tiempo.
# ---------------------------------------------------------------

from __future__ import annotations
import bisect
import time
import tkinter as tk

from ..core.constants import (
    CANVAS_W, CANVAS_H, DT_S,
    BELT_SPEED_MPM, TOTE_LEN_M, BOX_MAX_M,
    COLOR_BG, COLOR_PANEL_BG, COLOR_TEXT_SECONDARY, COLOR_KPI_TOTAL,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
)
from ..core.models import SimSnapshot, Item
from ..utils.formatting import fmt_time_min
from .canvas_renderer import CanvasRenderer


class _FakeStation:
    """Wrapper mínimo para que CanvasRenderer funcione con datos de replay."""
    def __init__(self, sid: str, x: float):
        self.sid = sid
        self.x   = x


class ReplayWindow:
    """Ventana de replay con barra de tiempo en minutos."""

    def __init__(self, record: dict, view: str):
        self.rec      = record
        self.meta     = record.get("meta", {})
        self.view     = view

        self._stations_raw  = record["stations"]
        self._blocked_raw   = record["blocked_intervals"]
        self._events        = record["events"]

        self.duration_s   = float(self.meta.get("duration_s", 3600.0))
        self.duration_min = self.duration_s / 60.0
        self.belt_speed_mps = float(self.meta.get("belt_speed_mpm", BELT_SPEED_MPM)) / 60.0
        self.belt_end_m   = float(self.meta.get("belt_end_m", 0.0))

        # posiciones de mesas
        self._station_objs = [
            _FakeStation(s["sid"], float(s["x"])) for s in self._stations_raw
        ]
        self.last_x = self._station_objs[-1].x

        # vista
        if view == "tail":
            self.view_start = max(0.0, self.last_x - 18.0)
        else:
            self.view_start = 0.0
        self.view_end = self.belt_end_m
        self.scale    = (CANVAS_W - 120) / max(1e-9, self.view_end - self.view_start)

        # índice de tiempos de eventos para bisect
        self._ev_t = [e[0] for e in self._events]

        # prefijos para conteo rápido
        self._pref_total = [0]
        self._pref_box   = [0]
        self._pref_tote  = [0]
        for e in self._events:
            k = int(e[2])
            self._pref_total.append(self._pref_total[-1] + 1)
            self._pref_box.append(  self._pref_box[-1]   + (1 if k == 0 else 0))
            self._pref_tote.append( self._pref_tote[-1]  + (1 if k == 1 else 0))

        # targets
        self._tgt_total = float(self.meta.get("target_total_h", TARGET_TOTAL_H))
        self._tgt_boxes = float(self.meta.get("target_boxes_h", TARGET_BOXES_H))
        self._tgt_totes = float(self.meta.get("target_totes_h", TARGET_TOTES_H))

        # ── tkinter ─────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("SimTimeInd  ·  REPLAY")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(
            self.root, width=CANVAS_W, height=CANVAS_H,
            bg=COLOR_BG, highlightthickness=0,
        )
        self.canvas.pack()

        # barra de control
        ctrl = tk.Frame(self.root, bg=COLOR_PANEL_BG)
        ctrl.pack(fill="x")

        btn_style = dict(
            bg="#2A2E38", fg=COLOR_TEXT_SECONDARY,
            relief="flat", padx=12, pady=4,
            font=("Helvetica", 10),
            activebackground="#3A3F4B", activeforeground="#E8ECF2",
            cursor="hand2",
        )
        self._btn_play = tk.Button(ctrl, text="▶  Reproducir",
                                   command=self._toggle_play, **btn_style)
        self._btn_play.pack(side="left", padx=4, pady=3)

        tk.Label(ctrl, text="Velocidad:", bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Helvetica", 10)).pack(side="left")
        self._speed_var = tk.DoubleVar(value=1.0)
        tk.Spinbox(ctrl, from_=0.1, to=50.0, increment=0.5,
                   textvariable=self._speed_var, width=5,
                   bg="#2A2E38", fg="#E8ECF2", relief="flat",
                   font=("Helvetica", 10),
                   buttonbackground="#3A3F4B").pack(side="left", padx=(2, 16))

        tk.Label(ctrl, text="Tiempo (min):", bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Helvetica", 10)).pack(side="left")
        self._t_var = tk.DoubleVar(value=0.0)
        self._slider = tk.Scale(
            ctrl, from_=0.0, to=self.duration_min, resolution=0.05,
            orient="horizontal", length=CANVAS_W - 420,
            variable=self._t_var, command=self._on_slider,
            bg=COLOR_PANEL_BG, fg=COLOR_TEXT_SECONDARY,
            troughcolor="#2A2E38", highlightthickness=0,
            relief="flat",
        )
        self._slider.pack(side="left", fill="x", expand=True, padx=8)

        # renderer
        self.renderer = CanvasRenderer(
            canvas=self.canvas,
            view_start=self.view_start,
            view_end=self.view_end,
            scale=self.scale,
            station_list=self._station_objs,
            push_enabled=bool(self.meta.get("push_enabled", False)),
            effective_gap_m=float(self.meta.get("effective_gap_m", 0.10)),
            target_total_h=self._tgt_total,
            target_boxes_h=self._tgt_boxes,
            target_totes_h=self._tgt_totes,
            duration_s=self.duration_s,
            view_label=view,
        )
        # parchar cycle_mean_s en el renderer usando meta
        cyc = self.meta.get("cycle_stats_total", {})
        self.renderer._replay_cycle_mean = float(cyc.get("mean_s", 0.0))

        self._playing = False
        self._last    = time.perf_counter()

        self._draw_at(0.0)

    # ────────────────────────────────────────────────────────────
    # Controles
    # ────────────────────────────────────────────────────────────

    def _on_slider(self, _) -> None:
        self._draw_at(float(self._t_var.get()) * 60.0)

    def _toggle_play(self) -> None:
        self._playing = not self._playing
        self._btn_play.config(text="⏸  Pausa" if self._playing else "▶  Reproducir")
        self._last = time.perf_counter()
        if self._playing:
            self._play_tick()

    def _play_tick(self) -> None:
        if not self._playing:
            return
        now    = time.perf_counter()
        dt     = now - self._last
        self._last = now

        t_min = float(self._t_var.get()) + dt * float(self._speed_var.get()) / 60.0
        if t_min >= self.duration_min:
            t_min = self.duration_min
            self._playing = False
            self._btn_play.config(text="▶  Reproducir")

        self._t_var.set(t_min)
        self._draw_at(t_min * 60.0)
        self.root.after(16, self._play_tick)

    # ────────────────────────────────────────────────────────────
    # Construcción del snapshot para el renderer
    # ────────────────────────────────────────────────────────────

    def _snapshot_at(self, t_s: float) -> tuple[SimSnapshot, list[Item]]:
        t_s = max(1e-9, t_s)
        idx = bisect.bisect_right(self._ev_t, t_s)

        n_total = self._pref_total[idx]
        n_box   = self._pref_box[idx]
        n_tote  = self._pref_tote[idx]

        rate_total = n_total / t_s * 3600.0
        rate_boxes = n_box   / t_s * 3600.0
        rate_totes = n_tote  / t_s * 3600.0

        cyc = self.meta.get("cycle_stats_total", {})
        cyc_mean  = float(cyc.get("mean_s", 0.0))
        cyc_min   = float(cyc.get("min_s",  0.0))
        cyc_max   = float(cyc.get("max_s",  0.0))
        cyc_count = int(cyc.get("count",   0))

        # esperas acumuladas hasta t_s
        wait_total = 0.0
        wait_per   = []
        for i, st in enumerate(self._station_objs):
            intervals = [(float(a), float(b)) for a, b in self._blocked_raw[i]]
            acc = 0.0
            blocked_now = False
            wait_now    = 0.0
            for a, b in intervals:
                if t_s <= a:
                    continue
                d = max(0.0, min(b, t_s) - a)
                acc += d
                if a <= t_s <= b:
                    blocked_now = True
                    wait_now    = t_s - a
            wait_total += acc
            wait_per.append((st.sid, st.x, acc, blocked_now, wait_now))

        snap = SimSnapshot(
            t=t_s,
            inserted_total=n_total,
            inserted_boxes=n_box,
            inserted_totes=n_tote,
            rate_total_h=rate_total,
            rate_boxes_h=rate_boxes,
            rate_totes_h=rate_totes,
            cycle_count=cyc_count,
            cycle_mean_s=cyc_mean,
            cycle_min_s=cyc_min,
            cycle_max_s=cyc_max,
            wait_total_s=wait_total,
            wait_per_station=wait_per,
        )

        # reconstruir ítems visibles en la cinta
        max_len     = max(float(self.meta.get("tote_len_m", TOTE_LEN_M)),
                          float(self.meta.get("box_max_m",  BOX_MAX_M)))
        travel_time = (self.belt_end_m + max_len) / max(1e-9, self.belt_speed_mps)
        t0 = max(0.0, t_s - travel_time - 2.0)
        i0 = bisect.bisect_left(self._ev_t, t0)

        items = []
        for e in self._events[i0:idx]:
            ev_t, st_idx, kind_code, length, _ = e
            dt    = t_s - ev_t
            x0    = float(self._stations_raw[int(st_idx)]["x"])
            front = x0 + self.belt_speed_mps * dt
            rear  = front - float(length)
            if rear > self.belt_end_m:
                continue
            items.append(Item(
                kind="box" if int(kind_code) == 0 else "tote",
                front_x=front,
                length=float(length),
            ))

        return snap, items

    def _draw_at(self, t_s: float) -> None:
        snap, items = self._snapshot_at(t_s)
        self.renderer.draw(snap, items)

    # ────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()