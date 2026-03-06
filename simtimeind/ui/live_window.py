# ui/live_window.py
# ---------------------------------------------------------------
# Ventana de simulación en vivo.
# Responsabilidad: loop de tick, coordinación Engine ↔ Renderer.
# No contiene lógica de física ni de grabación.
# ---------------------------------------------------------------

from __future__ import annotations
import time
import tkinter as tk

from ..core.engine import Engine
from ..core.recorder import save as save_record
from ..core.constants import (
    CANVAS_W, CANVAS_H, DT_S,
    COLOR_BG, COLOR_PANEL_BG, COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
)
from .canvas_renderer import CanvasRenderer


class LiveWindow:
    """Ventana principal de simulación live."""

    def __init__(self, engine: Engine, speed: float, view: str,
                 record_path: str | None = None):
        self.eng         = engine
        self.speed       = float(speed)
        self.view        = view
        self.record_path = record_path

        # vista
        if view == "tail":
            self.view_start = max(0.0, engine.last_x - 18.0)
        else:
            self.view_start = 0.0
        self.view_end = engine.belt_end_m
        self.scale    = (CANVAS_W - 120) / max(1e-9, self.view_end - self.view_start)

        # ── tkinter ─────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title(f"SimTimeInd  ·  {engine.n} mesas  ·  {speed}×")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(
            self.root, width=CANVAS_W, height=CANVAS_H,
            bg=COLOR_BG, highlightthickness=0,
        )
        self.canvas.pack()

        # barra de control
        ctrl = tk.Frame(self.root, bg=COLOR_PANEL_BG, height=34)
        ctrl.pack(fill="x")

        btn_style = dict(
            bg="#2A2E38", fg=COLOR_TEXT_SECONDARY,
            relief="flat", padx=14, pady=4,
            font=("Helvetica", 10),
            activebackground="#3A3F4B",
            activeforeground="#E8ECF2",
            cursor="hand2",
        )

        tk.Button(ctrl, text="▶/⏸  Pausa",
                  command=self._toggle_pause, **btn_style).pack(side="left", padx=4, pady=3)

        tk.Label(ctrl, text="Velocidad:", bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Helvetica", 10)).pack(side="left")
        self._speed_var = tk.DoubleVar(value=self.speed)
        tk.Spinbox(
            ctrl, from_=0.1, to=50.0, increment=0.5,
            textvariable=self._speed_var, width=5,
            bg="#2A2E38", fg="#E8ECF2", relief="flat",
            font=("Helvetica", 10),
            buttonbackground="#3A3F4B",
        ).pack(side="left", padx=(2, 16))

        self._status_var = tk.StringVar(value="▶  Simulando…")
        tk.Label(ctrl, textvariable=self._status_var, bg=COLOR_PANEL_BG,
                 fg=COLOR_TEXT_SECONDARY, font=("Consolas", 9)).pack(side="right", padx=10)

        # renderer
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
            view_label=view,
        )

        self._last   = time.perf_counter()
        self._acc    = 0.0
        self._saved  = False
        self._paused = False
        self._tick_n = 0
        self._last_snap_t   = -1.0   # tiempo simulado del ultimo snapshot mostrado
        self._display_snap  = None   # snapshot congelado para el panel

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._status_var.set("⏸  Pausado" if self._paused else "▶  Simulando…")

    def run(self) -> None:
        self._schedule_tick()
        self.root.mainloop()

    def _schedule_tick(self) -> None:
        self.root.after(16, self._tick)

    def _tick(self) -> None:
        now     = time.perf_counter()
        real_dt = now - self._last
        self._last = now

        if not self._paused:
            self.speed = float(self._speed_var.get())
            self._acc += real_dt * self.speed
            steps = min(int(self._acc / DT_S), 150)
            if steps > 0:
                self.eng.step(steps)
                self._acc -= steps * DT_S

        snap = self.eng.snapshot()
        self._tick_n += 1

        # actualizar snapshot del panel cada 1s de tiempo simulado
        if self._display_snap is None or (snap.t - self._last_snap_t) >= 1.0:
            self._display_snap = snap
            self._last_snap_t  = snap.t

        self.renderer.draw(self._display_snap, self.eng.items, self._tick_n)

        # grabación al finalizar
        if (self.eng.t >= self.eng.duration_s
                and self.record_path and not self._saved):
            save_record(self.eng, self.record_path)
            self._saved = True
            self.root.title(self.root.title() + "  ✅")
            self._status_var.set("✅  Grabación guardada")

        self._schedule_tick()