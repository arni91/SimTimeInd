# ui/canvas_renderer.py
from __future__ import annotations

from ..core.constants import (
    CANVAS_W, CANVAS_H, BELT_Y,
    TOTE_WIDTH_MM, BOX_WIDTH_MM,
    PANEL_Y, PANEL_H,
    COLOR_BG, COLOR_BELT, COLOR_BELT_HL,
    COLOR_BOX, COLOR_TOTE,
    COLOR_STATION_OK, COLOR_STATION_CRIT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_GOOD, COLOR_TEXT_BAD, COLOR_TEXT_WARN,
    COLOR_PANEL_BG, COLOR_PANEL_BORDER, COLOR_GRID,
    COLOR_KPI_TOTE,
    WAIT_BLOCKED_THRESHOLD_S,
    BELT_SPEED_MPM, TOTE_LEN_M, BOX_MEAN_M, BOX_MIN_M, BOX_MAX_M,
    MOTOR_POSITIONS_M, MOTOR_SPEED_MPM,
    CYCLE_MEAN_M01_M07_S, CYCLE_MEAN_M08_M14_S, CYCLE_MEAN_M15_M21_S,
    M22_CYCLE_MEAN_S, M22_PKG_H,
    SIM_MEAN_CYCLE_S, SIM_TOTAL_TOTES_H, SIM_TOTAL_BOXES_H, SIM_TOTAL_H,
    _MEAN_PKG_PER_CYCLE,
)
from ..core.models import SimSnapshot
from ..utils.formatting import fmt_time_min, fmt_delta, color_delta

_FONT_MONO_SM  = ("Consolas", 9)
_FONT_MONO_MD  = ("Consolas", 11)
_FONT_MONO_LG  = ("Consolas", 14, "bold")
_FONT_SANS_SM  = ("Helvetica", 9)
_FONT_SANS_XS  = ("Helvetica", 8)
_FONT_LABEL_SM = ("Helvetica", 8)
_FONT_LABEL_MD = ("Helvetica", 10)
_FONT_TIMER    = ("Consolas", 8, "bold")

_WAIT_SHOW_S             = 2.0
_ACTIVE_WAIT_THRESHOLD_S = 2.0

_COL_TOTE_PREP  = "#7A5010"
_COL_BOX_PREP   = "#104878"
_COL_WAIT_BG    = "#5A1010"
_COL_MOTOR      = "#00C8A7"   # teal para motores
_COL_MOTOR_BG   = "#00201A"
_INFO_BAR_H    = 22
_INFO_BAR_Y    = 8

# Factor de amplificación visual para la altura de bultos y cinta
# Debe ser pequeño para que la cubeta (600mm largo) sea más ancha que alta (400mm)
_VISUAL_SCALE = 1.0


class CanvasRenderer:

    def __init__(self, canvas, view_start, view_end, scale, station_list,
                 push_enabled, effective_gap_m, target_total_h, target_boxes_h,
                 target_totes_h, duration_s, warmup_s=0.0, view_label="full"):
        self.canvas       = canvas
        self.view_start   = view_start
        self.view_end     = view_end
        self.scale        = scale
        self.stations     = station_list
        self.push_enabled = push_enabled
        self.eff_gap_m    = effective_gap_m
        self.tgt_total    = target_total_h
        self.tgt_boxes    = target_boxes_h
        self.tgt_totes    = target_totes_h
        self.duration_s   = duration_s
        self.warmup_s     = warmup_s
        self.view_label   = view_label
        self._tick        = 0
        self._replay_cycle_mean: float = 0.0

    def _px(self, x_m):
        return int(60 + (x_m - self.view_start) * self.scale)

    def _in_view(self, x_m):
        return self.view_start - 1.0 <= x_m <= self.view_end + 1.0

    def _item_half_h(self, kind: str) -> int:
        width_m = (TOTE_WIDTH_MM if kind == "tote" else BOX_WIDTH_MM) / 1000.0
        return max(6, int(round(width_m * self.scale * _VISUAL_SCALE / 2)))

    def _belt_half_h(self) -> int:
        return self._item_half_h("tote") + 8

    def draw(self, snap, items, tick=0, counter_snap=None):
        self._tick = tick
        c = self.canvas
        c.delete("all")
        self._draw_background()
        self._draw_info_bar()
        self._draw_belt()
        self._draw_counter_marker(snap)
        self._draw_items(items)
        self._draw_motors()
        self._draw_stations(snap)
        self._draw_dimension_lines()
        self._draw_kpi_panel(snap, counter_snap or snap)
        self._draw_footer(snap)

    def _draw_background(self):
        c = self.canvas
        c.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill=COLOR_BG, outline="")

    def _draw_info_bar(self):
        c = self.canvas
        y, bh = _INFO_BAR_Y, _INFO_BAR_H
        c.create_rectangle(0, y, CANVAS_W, y + bh, fill="#0D1018", outline="")
        c.create_line(0, y + bh, CANVAS_W, y + bh, fill=COLOR_PANEL_BORDER, width=1)

        belt_mps = BELT_SPEED_MPM / 60.0
        info = [
            ("Cinta",   f"{BELT_SPEED_MPM:.0f} m/min  ({belt_mps:.2f} m/s)"),
            ("Cubeta",  f"{TOTE_LEN_M*1000:.0f} mm"),
            ("Paquete", f"{BOX_MEAN_M*1000:.0f} mm media  ({BOX_MIN_M*1000:.0f}-{BOX_MAX_M*1000:.0f} mm)"),
            ("Gap",     f"{self.eff_gap_m*1000:.0f} mm"),
            ("Push",    "ON (gap 0mm si no cabe)" if self.push_enabled else "OFF"),
            ("Buffer",  "1 cubeta/mesa"),
        ]
        cx = 12
        ty = y + bh // 2
        for label, val in info:
            c.create_text(cx, ty, text=label + ":", fill=COLOR_TEXT_SECONDARY,
                          font=_FONT_SANS_XS, anchor="w")
            cx += len(label) * 6 + 6
            c.create_text(cx, ty, text=val, fill=COLOR_TEXT_PRIMARY,
                          font=_FONT_SANS_XS, anchor="w")
            cx += len(val) * 6 + 20

    def _draw_belt(self):
        c = self.canvas
        x0, x1 = self._px(self.view_start), self._px(self.view_end)
        by, h = BELT_Y, self._belt_half_h()
        c.create_rectangle(x0, by - h, x1, by + h, fill=COLOR_BELT, outline=COLOR_BELT_HL, width=1)
        c.create_line(x0, by, x1, by, fill="#252830", width=1, dash=(4, 8))

    def _draw_counter_marker(self, snap):
        if not self._in_view(snap.counter_x_m):
            return
        c = self.canvas
        px = self._px(snap.counter_x_m)
        by = BELT_Y
        h  = self._belt_half_h()

        # Contador: color blanco/neutro — no azul (paquetes) ni naranja (cubetas)
        _COL_COUNTER = COLOR_TEXT_PRIMARY   # blanco neutro

        c.create_line(px, by - h - 30, px, by + h + 30,
                      fill=_COL_COUNTER, width=2, dash=(6, 4))

        top_w = 86
        c.create_rectangle(px - top_w//2, by - h - 44, px + top_w//2, by - h - 26,
                            fill=COLOR_PANEL_BG, outline=_COL_COUNTER, width=1)
        c.create_text(px, by - h - 35, text="CONTADOR", fill=_COL_COUNTER,
                      font=("Consolas", 8, "bold"), anchor="center")

        total_txt = f"{snap.counted_total}"
        p_txt     = f"P:{snap.counted_boxes}"
        c_txt     = f"C:{snap.counted_totes}"
        box_w  = max(110, len(total_txt) * 9 + 20)
        num_y1 = by + h + 30
        num_y2 = by + h + 46
        c.create_rectangle(px - box_w//2, num_y1 - 12, px + box_w//2, num_y2 + 10,
                            fill="#0D1018", outline=_COL_COUNTER, width=1)
        c.create_text(px, num_y1, text=total_txt,
                      fill=_COL_COUNTER, font=("Consolas", 11, "bold"), anchor="center")
        # P: en azul (paquetes), C: en naranja (cubetas)
        c.create_text(px - 6, num_y2, text=p_txt,
                      fill=COLOR_BOX,  font=("Consolas", 8), anchor="e")
        c.create_text(px + 6, num_y2, text=c_txt,
                      fill=COLOR_TOTE, font=("Consolas", 8), anchor="w")

    def _draw_items(self, items):
        c  = self.canvas
        by = BELT_Y
        for it in items:
            if not (self._in_view(it.front_x) or self._in_view(it.rear_x)):
                continue
            fx  = self._px(it.front_x)
            rx  = self._px(it.rear_x)
            ih  = self._item_half_h(it.kind)
            col = COLOR_BOX if it.kind == "box" else COLOR_TOTE
            # borde oscuro para separar bultos aunque estén a gap=0
            c.create_rectangle(rx, by - ih, fx, by + ih,
                                fill=col, outline="#111418", width=1)
            # franja superior para dar definición
            hi = max(2, ih // 4)
            c.create_rectangle(rx + 1, by - ih + 1, fx - 1, by - ih + hi,
                                fill=_lighten(col, 35), outline="")

    def _draw_stations(self, snap):
        c  = self.canvas
        by = BELT_Y

        # Dimensiones de los recuadros de ítem debajo de cada mesa
        BW, BH, BGAP = 34, 22, 3   # ancho celda, alto, separación vertical entre boxes
        BM = 2                      # margen horizontal → recuadro dibujado = BW-2*BM = 30px

        wait_map  = {sid: (acc_s, bn, wn)
                     for sid, x, acc_s, bn, wn in snap.wait_per_station}
        timer_map = {sid: (tp, bp, tw, ep, eb)
                     for sid, _w, tp, bp, tw, ep, eb in snap.station_timers}

        for i, st in enumerate(self.stations):
            sid      = st.sid if hasattr(st, "sid") else st["sid"]
            x_m      = st.x  if hasattr(st, "x")   else float(st["x"])
            pkg_only = getattr(st, "packages_only", False)
            if not self._in_view(x_m):
                continue
            px   = self._px(x_m)
            pair = i % 2

            acc_s, blocked_now, wait_now_s = wait_map.get(sid, (0.0, False, 0.0))
            tote_prep_s, box_prep_s, tote_wait_s, *_ = timer_map.get(sid, (-1.0, -1.0, -1.0, -1.0, 0))

            is_blocked  = wait_now_s >= WAIT_BLOCKED_THRESHOLD_S
            col_line    = COLOR_STATION_CRIT if is_blocked else COLOR_STATION_OK
            col_text    = COLOR_STATION_CRIT if is_blocked else COLOR_TEXT_SECONDARY
            lw          = 3 if is_blocked else 2

            # ── Línea vertical de la mesa (cuerpo gris) ──────────────
            c.create_line(px, by - 52, px, by + 52, fill=col_line, width=lw)
            c.create_oval(px - 5, by - 5, px + 5, by + 5, fill=col_line, outline="")

            # ── Etiqueta de mesa (posición original) ─────────────────
            label_y = by - (68 + pair * 16)
            c.create_text(px, label_y, text=sid,
                          fill=col_text, font=_FONT_LABEL_MD, anchor="center")
            if pkg_only:
                c.create_text(px, label_y - 13, text="solo P", fill=COLOR_BOX,
                              font=("Helvetica", 7, "bold"), anchor="center")

            # ── Offset horizontal para no solapar mesas contiguas ────
            # Si la mesa de la izquierda está a <1.5m → desplazar a la derecha
            # Si la mesa de la derecha está a <1.5m  → desplazar a la izquierda
            CLOSE = 1.5   # m — umbral de "mesas contiguas"
            SHIFT = 6     # px — desplazamiento lateral
            box_off = 0
            if i > 0:
                xp = self.stations[i-1].x if hasattr(self.stations[i-1], "x") else float(self.stations[i-1]["x"])
                if x_m - xp < CLOSE:
                    box_off += SHIFT
            if i < len(self.stations) - 1:
                xn = self.stations[i+1].x if hasattr(self.stations[i+1], "x") else float(self.stations[i+1]["x"])
                if xn - x_m < CLOSE:
                    box_off -= SHIFT

            # ── Recuadros de ítem DEBAJO del cinturón ────────────────
            slot = [0]

            def _item_box(timer_s, fill_col, text_col="#FFFFFF", label="",
                          _px=px, _off=box_off):
                s = slot[0]
                cx  = _px + _off
                bx0 = cx - (BW - 2 * BM) // 2
                by0 = by + 57 + s * (BH + BGAP)
                by1 = by0 + BH
                c.create_rectangle(bx0, by0, bx0 + BW - 2 * BM, by1,
                                   fill=fill_col, outline="#111418", width=1)
                txt = f"{label}{timer_s:.0f}s" if timer_s >= 0 else label
                c.create_text(cx, (by0 + by1) // 2, text=txt,
                              fill=text_col, font=_FONT_TIMER, anchor="center")
                slot[0] += 1

            if not pkg_only:
                # Recuadro de CUBETA: naranja normal, rojo si bloqueada
                if tote_prep_s >= 0:
                    if is_blocked:
                        _item_box(wait_now_s, COLOR_STATION_CRIT, "#FFFFFF")
                    else:
                        _item_box(tote_prep_s, COLOR_TOTE, "#1A1D23")

                # Recuadro de PAQUETE (solo si hay un paquete más reciente que la cubeta)
                if box_prep_s >= 0:
                    if is_blocked:
                        _item_box(wait_now_s, COLOR_STATION_CRIT, "#FFFFFF")
                    else:
                        _item_box(box_prep_s, COLOR_BOX, "#FFFFFF")
            else:
                # M22: solo paquetes, recuadro azul
                if tote_prep_s >= 0:
                    if is_blocked:
                        _item_box(wait_now_s, COLOR_STATION_CRIT, "#FFFFFF")
                    else:
                        _item_box(tote_prep_s, COLOR_BOX, "#FFFFFF")

    def _draw_motors(self):
        c    = self.canvas
        by   = BELT_Y
        bh   = self._belt_half_h()
        box_h   = 16
        box_w   = 74
        box_top = by - 238          # caja encima de los nombres de mesas
        line_y1 = box_top + box_h   # base de la caja
        line_y2 = by - bh - 2       # toca el borde superior de la cinta
        fnt     = ("Helvetica", 7)

        for i, x_m in enumerate(MOTOR_POSITIONS_M):
            if not self._in_view(x_m):
                continue
            px          = self._px(x_m)
            num         = i + 1
            theoretical = (num == 1)
            col = _lighten(_COL_MOTOR, -25) if theoretical else _COL_MOTOR

            # línea vertical desde caja hasta cinta
            dash = (4, 3) if theoretical else None
            kw   = dict(fill=col, width=1)
            if dash:
                kw["dash"] = dash
            c.create_line(px, line_y1, px, line_y2, **kw)

            # pequeño tick en la cinta
            c.create_line(px - 4, line_y2, px + 4, line_y2, fill=col, width=2)

            # caja con etiqueta y velocidad
            bx = px - box_w // 2
            c.create_rectangle(bx, box_top, bx + box_w, box_top + box_h,
                                fill=_COL_MOTOR_BG, outline=col, width=1)
            c.create_text(px, box_top + box_h // 2,
                          text=f"M{num}  {MOTOR_SPEED_MPM:.0f}m/min",
                          fill=col, font=fnt, anchor="center")

    def _draw_dimension_lines(self):
        c  = self.canvas
        by = BELT_Y
        xs = [st.x if hasattr(st, "x") else float(st["x"]) for st in self.stations]
        if len(xs) < 2:
            return

        col_dim   = "#4A5568"
        col_text  = "#6B7A94"
        col_total = "#8896AA"
        tick_h    = 6
        fnt_sm    = ("Consolas", 7)
        fnt_tot   = ("Consolas", 7, "bold")

        for i in range(len(xs) - 1):
            x0m, x1m = xs[i], xs[i + 1]
            if not (self._in_view(x0m) or self._in_view(x1m)):
                continue
            px0, px1  = self._px(x0m), self._px(x1m)
            row_y     = by - 285
            c.create_line(px0, row_y, px1, row_y, fill=col_dim, width=1)
            c.create_line(px0, row_y - tick_h, px0, row_y + tick_h, fill=col_dim, width=1)
            c.create_line(px1, row_y - tick_h, px1, row_y + tick_h, fill=col_dim, width=1)
            mid = (px0 + px1) // 2
            c.create_text(mid, row_y - 5, text=f"{x1m - x0m:.2f}m",
                          fill=col_text, font=fnt_sm, anchor="s")

        if self._in_view(xs[0]) or self._in_view(xs[-1]):
            px_first = self._px(xs[0])
            px_last  = self._px(xs[-1])
            tot_y    = by - 320
            c.create_line(px_first, tot_y, px_last, tot_y, fill=col_total, width=1)
            c.create_line(px_first, tot_y - tick_h - 2, px_first, tot_y + tick_h + 2,
                          fill=col_total, width=1)
            c.create_line(px_last,  tot_y - tick_h - 2, px_last,  tot_y + tick_h + 2,
                          fill=col_total, width=1)
            mid_tot = (px_first + px_last) // 2
            c.create_text(mid_tot, tot_y - 5,
                          text=f"M1-M22 = {xs[-1] - xs[0]:.2f} m",
                          fill=col_total, font=fnt_tot, anchor="s")

    def _draw_kpi_panel(self, snap, counter_snap):
        c = self.canvas
        py, ph, pw = PANEL_Y, PANEL_H, CANVAS_W
        c.create_rectangle(0, py, pw, py + ph, fill=COLOR_PANEL_BG, outline="")
        c.create_line(0, py, pw, py, fill=COLOR_PANEL_BORDER, width=2)
        col1_x = pw // 3   # ~520  PRODUCCION | RENDIMIENTO
        col3_x = 1120       #       RENDIMIENTO | ESPERAS

        # Anchos de contenido: PRODUCCIÓN ~380px, RENDIMIENTO ~322px (solo teórico)
        prod_w = 390
        rend_w = 322
        prod_x = (col1_x - prod_w) // 2
        rend_x = col1_x + (col3_x - col1_x - rend_w) // 2
        wait_x = col3_x + (pw - col3_x - 400) // 2

        self._kpi_production(snap, counter_snap, x=prod_x, y=py + 12)
        c.create_line(col1_x, py + 10, col1_x, py + ph - 10, fill=COLOR_PANEL_BORDER, width=1)
        self._kpi_rendimiento(snap, x=rend_x, y=py + 12)
        c.create_line(col3_x, py + 10, col3_x, py + ph - 10, fill=COLOR_PANEL_BORDER, width=1)
        self._kpi_waits(snap, x=wait_x, y=py + 12)

    def _kpi_production(self, snap, counter_snap, x, y):
        c = self.canvas

        # ── cabecera: título + objetivos de referencia ──────────────
        c.create_text(x, y + 7, text="PRODUCCION  objetivo:",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")
        ox = x + 170
        for tgt_val, col, lbl in [
            (int(self.tgt_total), COLOR_TEXT_GOOD, ""),
            (int(self.tgt_boxes), COLOR_BOX,       "P:"),
            (int(self.tgt_totes), COLOR_KPI_TOTE,  "C:"),
        ]:
            c.create_text(ox, y + 7, text=lbl, fill=COLOR_TEXT_SECONDARY,
                          font=_FONT_SANS_XS, anchor="w")
            c.create_text(ox + len(lbl) * 6 + 2, y + 7, text=str(tgt_val),
                          fill=col, font=_FONT_MONO_SM, anchor="w")
            ox += len(lbl) * 6 + len(str(tgt_val)) * 8 + 14
        y += 18

        # ── cabeceras de columna ─────────────────────────────────────
        bw = 250
        c.create_text(x + bw + 55, y + 6, text="contados",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_XS, anchor="e")
        c.create_text(x + bw + 130, y + 6, text="diferencia",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_XS, anchor="w")
        y += 22

        rows = [
            ("TOTAL",    counter_snap.counted_total, int(self.tgt_total), COLOR_TEXT_GOOD),
            ("PAQUETES", counter_snap.counted_boxes, int(self.tgt_boxes), COLOR_BOX),
            ("CUBETAS",  counter_snap.counted_totes, int(self.tgt_totes), COLOR_KPI_TOTE),
        ]

        bh = 24
        for label, counted, tgt, col in rows:
            # ── barra de progreso: contador / objetivo ───────────────
            fp = min(int(counted / max(1, tgt) * bw), bw)
            c.create_rectangle(x, y, x + bw, y + bh, fill="#1E2128", outline="")
            c.create_rectangle(x, y, x + fp, y + bh,
                               fill=_alpha_color(col, 0.30), outline="")
            c.create_text(x + 6, y + 12, text=label,
                          fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")

            # ── contador: número grande ──────────────────────────────
            c.create_text(x + bw + 55, y + 12, text=str(counted),
                          fill=col, font=_FONT_MONO_LG, anchor="e")

            # ── delta: contador vs objetivo total ────────────────────
            cnt_delta = counted - tgt
            cnt_dcol  = (COLOR_TEXT_GOOD if cnt_delta >= 0 else COLOR_TEXT_BAD)
            delta_txt = (f"+{cnt_delta}" if cnt_delta >= 0 else str(cnt_delta))
            c.create_text(x + bw + 130, y + 12, text=delta_txt,
                          fill=cnt_dcol, font=_FONT_MONO_SM, anchor="w")

            y += bh + 6

    def _kpi_rendimiento(self, snap, x, y):
        """Panel RENDIMIENTO OPERARIO con tabla M01-M21/mesa + Σ M01-M21 + M22 + TOTAL."""
        c = self.canvas

        COL_CICLO = COLOR_TEXT_PRIMARY
        COL_CUB   = COLOR_TOTE
        COL_PAQ   = COLOR_BOX
        COL_TOT   = COLOR_TEXT_GOOD
        COL_LINE  = COLOR_PANEL_BORDER

        O_CL  =   0;  O_TC  =  90;  O_TB  = 155;  O_TP  = 215
        O_TT  = 272
        TW = O_TT + 50   # table right edge (offset from x)

        # ── Título ────────────────────────────────────────────────────
        c.create_text(x, y, text="RENDIMIENTO OPERARIO",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 14

        # ── Sub-cabecera TEÓRICO ───────────────────────────────────────
        t_ctr = x + (O_TC + O_TT + 40) // 2
        c.create_text(t_ctr, y, text="TEÓRICO",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_XS, anchor="n")
        y += 14
        c.create_line(x + O_TC, y, x + TW, y, fill=COL_LINE, width=1)
        y += 3

        # ── Cabeceras de columna ──────────────────────────────────────
        c.create_text(x + O_CL, y, text="mesas",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_XS, anchor="nw")
        for col, hdr, clr in [
            (O_TC, "ciclo", COL_CICLO), (O_TB, "cub/h", COL_CUB),
            (O_TP, "paq/h", COL_PAQ),  (O_TT, "tot/h", COL_TOT),
        ]:
            c.create_text(x + col, y, text=hdr, fill=clr,
                          font=_FONT_SANS_XS, anchor="nw")
        y += 12
        c.create_line(x, y, x + TW, y, fill=COL_LINE, width=1)
        y += 3

        def _teo_ciclo(idx):
            if idx >= 14: return CYCLE_MEAN_M15_M21_S
            if idx >= 7:  return CYCLE_MEAN_M08_M14_S
            return CYCLE_MEAN_M01_M07_S

        RH = 24   # row height

        def _draw_row(label, lbl_clr, lbl_fnt,
                      teo_c, teo_b, teo_p, teo_t,
                      show_cub=True, d_fnt=None):
            nonlocal y
            if d_fnt is None:
                d_fnt = ("Consolas", 9)
            mid = y + RH // 2
            c.create_text(x + O_CL, mid, text=label, fill=lbl_clr, font=lbl_fnt, anchor="w")
            c.create_text(x + O_TC, mid, text=f"{teo_c:.1f}s", fill=COL_CICLO, font=d_fnt, anchor="w")
            c.create_text(x + O_TB, mid,
                          text="—" if not show_cub else f"{teo_b:.0f}",
                          fill=COLOR_TEXT_SECONDARY if not show_cub else COL_CUB,
                          font=d_fnt, anchor="w")
            c.create_text(x + O_TP, mid, text=f"{teo_p:.0f}", fill=COL_PAQ, font=d_fnt, anchor="w")
            c.create_text(x + O_TT, mid, text=f"{teo_t:.0f}", fill=COL_TOT, font=d_fnt, anchor="w")
            y += RH
            c.create_line(x, y, x + TW, y, fill=COL_LINE, width=1)
            y += 3

        m0121 = [(sid, idx, tc, bc, cc)
                 for sid, idx, tc, bc, cc, po in snap.station_production if not po]
        m22   = [(sid, idx, tc, bc, cc)
                 for sid, idx, tc, bc, cc, po in snap.station_production if po]

        n21 = max(1, len(m0121))

        teo_ciclo_avg = sum(_teo_ciclo(idx) for _, idx, *_ in m0121) / n21
        teo_cub_pm    = sum(3600.0 / _teo_ciclo(idx) for _, idx, *_ in m0121) / n21
        teo_paq_pm    = teo_cub_pm * _MEAN_PKG_PER_CYCLE
        teo_tot_pm    = teo_cub_pm + teo_paq_pm

        sub_t_cub = teo_cub_pm * n21;  sub_t_paq = teo_paq_pm * n21;  sub_t_tot = teo_tot_pm * n21

        fnt_sm   = _FONT_SANS_XS
        fnt_bold = ("Helvetica", 9, "bold")
        dat_bold = ("Consolas", 9, "bold")

        # Fila 1: M01-M21 por mesa
        _draw_row("M01-M21 /mesa", COLOR_TEXT_SECONDARY, fnt_sm,
                  teo_ciclo_avg, teo_cub_pm, teo_paq_pm, teo_tot_pm)

        # Fila 2: Σ M01-M21
        _draw_row("Σ M01-M21", COLOR_TEXT_SECONDARY, fnt_sm,
                  teo_ciclo_avg, sub_t_cub, sub_t_paq, sub_t_tot)

        # Fila 3: M22
        if m22:
            _draw_row("M22", COLOR_TEXT_SECONDARY, fnt_sm,
                      M22_CYCLE_MEAN_S, 0.0, M22_PKG_H, M22_PKG_H,
                      show_cub=False)

        # Fila 4: TOTAL  (negrita)
        tot_t_cub = sub_t_cub
        tot_t_paq = sub_t_paq + M22_PKG_H
        tot_t_tot = tot_t_cub + tot_t_paq
        _draw_row("TOTAL", COLOR_TEXT_PRIMARY, fnt_bold,
                  SIM_MEAN_CYCLE_S, tot_t_cub, tot_t_paq, tot_t_tot,
                  d_fnt=dat_bold)

    def _kpi_waits(self, snap, x, y):
        c = self.canvas
        c.create_text(x, y, text="ESPERAS  (bloqueo induccion)",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 14
        total_s   = snap.wait_total_s
        total_col = (COLOR_TEXT_GOOD if total_s < 60 else
                     COLOR_TEXT_WARN if total_s < 300 else COLOR_TEXT_BAD)
        c.create_text(x,       y, text="Total acumulado (Sigma mesas)",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        c.create_text(x + 280, y, text=_fmt_hms(total_s),
                      fill=total_col, font=_FONT_MONO_LG, anchor="nw")
        y += 20
        right_edge = CANVAS_W - 20
        c.create_line(x, y, right_edge, y, fill=COLOR_PANEL_BORDER, width=1)
        y += 5

        stations_wait = list(snap.wait_per_station)
        groups = [
            stations_wait[0:7],
            stations_wait[7:14],
            stations_wait[14:21],
            stations_wait[21:],
        ]
        col_w = (right_edge - x) // 4
        row_h = 13

        for ci, group in enumerate(groups):
            if not group:
                continue
            cx, cy = x + ci * col_w, y
            for sid, _, acc_s, bn, wn in group:
                if cy + row_h > PANEL_Y + PANEL_H - 4:
                    break
                acc_col = (COLOR_TEXT_BAD  if acc_s >= 600
                           else COLOR_TEXT_WARN if acc_s >= 300
                           else COLOR_TEXT_PRIMARY)
                c.create_text(cx,      cy, text=sid,             fill=COLOR_TEXT_SECONDARY, font=_FONT_LABEL_SM, anchor="nw")
                c.create_text(cx + 34, cy, text=_fmt_hms(acc_s), fill=acc_col,              font=_FONT_LABEL_SM, anchor="nw")
                cy += row_h


    def update_bar(self, bar_canvas, time_label, snap):
        """Actualiza la barra de progreso tkinter externa (fuera del canvas principal)."""
        w = bar_canvas.winfo_width()
        h = bar_canvas.winfo_height()
        if w < 2:
            return
        _COL_WARMUP_ZONE = "#1E1A2E"
        _COL_WARMUP_PROG = "#6B5B95"
        _COL_WARMUP_LINE = "#8B7BB5"
        _COL_BAR_NORMAL  = "#546E7A"
        prog = snap.t / max(1, self.duration_s)
        bar_canvas.delete("all")
        # fondo
        bar_canvas.create_rectangle(0, 0, w, h, fill="#252830", outline="")
        # zona calentamiento
        if self.warmup_s > 0:
            wfrac   = self.warmup_s / max(1, self.duration_s)
            wpx     = int(w * wfrac)
            bar_canvas.create_rectangle(0, 0, wpx, h, fill=_COL_WARMUP_ZONE, outline="")
        # progreso
        fill_col = _COL_WARMUP_PROG if snap.in_warmup else _COL_BAR_NORMAL
        bar_canvas.create_rectangle(0, 0, int(w * prog), h, fill=fill_col, outline="")
        # marcador
        if self.warmup_s > 0:
            wfrac = self.warmup_s / max(1, self.duration_s)
            mx    = int(w * wfrac)
            bar_canvas.create_line(mx, 0, mx, h, fill=_COL_WARMUP_LINE, width=2)
        # leyenda Paquete/Cubeta (derecha de la barra)
        sw, sh = 10, 8
        sy = (h - sh) // 2
        # Cubeta (naranja)
        cx = w - 8
        bar_canvas.create_rectangle(cx - sw, sy, cx, sy + sh,
                                    fill=COLOR_TOTE, outline="")
        bar_canvas.create_text(cx - sw - 4, h // 2, text="Cubeta",
                               fill="#9AA0AA", font=("Consolas", 8), anchor="e")
        # Paquete (azul)
        cx2 = cx - sw - 4 - 52
        bar_canvas.create_rectangle(cx2 - sw, sy, cx2, sy + sh,
                                    fill=COLOR_BOX, outline="")
        bar_canvas.create_text(cx2 - sw - 4, h // 2, text="Paquete",
                               fill="#9AA0AA", font=("Consolas", 8), anchor="e")

        # texto de tiempo en el label
        t_prod = max(0.0, snap.t - self.warmup_s)
        txt = (f"{fmt_time_min(snap.t)} / {fmt_time_min(self.duration_s)}"
               f"   medicion: {fmt_time_min(t_prod)}"
               f"   mesas={len(self.stations)}")
        time_label.config(text=txt)

    def _draw_footer(self, snap):
        c = self.canvas
        bar_x, bar_y = 60, PANEL_Y - 18
        bar_w, bar_h = CANVAS_W - 120, 6
        prog = snap.t / max(1, self.duration_s)

        lx, ly = CANVAS_W - 220, bar_y - 20
        c.create_rectangle(lx,       ly, lx + 16,  ly + 12, fill=COLOR_BOX,  outline="")
        c.create_text(lx + 22,  ly + 6, text="Paquete", fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")
        c.create_rectangle(lx + 100, ly, lx + 116, ly + 12, fill=COLOR_TOTE, outline="")
        c.create_text(lx + 122, ly + 6, text="Cubeta",  fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")

        # ── Barra de progreso ────────────────────────────────────────
        _COL_WARMUP_ZONE = "#1E1A2E"   # fondo zona calentamiento (morado muy oscuro)
        _COL_WARMUP_PROG = "#6B5B95"   # progreso durante calentamiento (morado)
        _COL_WARMUP_LINE = "#8B7BB5"   # marcador vertical
        _COL_BAR_NORMAL  = "#546E7A"   # progreso normal (gris azulado)

        c.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                           fill="#252830", outline="")

        # Zona de calentamiento: fondo morado oscuro
        if self.warmup_s > 0:
            warmup_frac = self.warmup_s / max(1, self.duration_s)
            warmup_px   = int(bar_w * warmup_frac)
            c.create_rectangle(bar_x, bar_y, bar_x + warmup_px, bar_y + bar_h,
                               fill=_COL_WARMUP_ZONE, outline="")

        # Progreso actual
        fill_col = _COL_WARMUP_PROG if snap.in_warmup else _COL_BAR_NORMAL
        c.create_rectangle(bar_x, bar_y, bar_x + int(bar_w * prog), bar_y + bar_h,
                           fill=fill_col, outline="")

        # Marcador vertical en el límite del calentamiento (sin texto)
        if self.warmup_s > 0:
            warmup_frac = self.warmup_s / max(1, self.duration_s)
            mx = bar_x + int(bar_w * warmup_frac)
            c.create_line(mx, bar_y - 4, mx, bar_y + bar_h + 4,
                          fill=_COL_WARMUP_LINE, width=2)

        # Texto de tiempo
        t_prod = max(0.0, snap.t - self.warmup_s)
        tiempo_txt = (f"  {fmt_time_min(snap.t)} / {fmt_time_min(self.duration_s)}"
                      f"   |   medicion: {fmt_time_min(t_prod)}"
                      f"   |   mesas={len(self.stations)}")
        c.create_text(bar_x, bar_y - 18,
                      text=tiempo_txt,
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_MONO_SM, anchor="w")


def _lighten(hex_col, amount):
    try:
        return (f"#{max(0, min(255, int(hex_col[1:3], 16) + amount)):02X}"
                f"{max(0, min(255, int(hex_col[3:5], 16) + amount)):02X}"
                f"{max(0, min(255, int(hex_col[5:7], 16) + amount)):02X}")
    except Exception:
        return hex_col


def _alpha_color(hex_col, alpha):
    try:
        bg  = (0x1A, 0x1D, 0x23)
        r, g, b = int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)
        return (f"#{int(bg[0] + (r - bg[0]) * alpha):02X}"
                f"{int(bg[1] + (g - bg[1]) * alpha):02X}"
                f"{int(bg[2] + (b - bg[2]) * alpha):02X}")
    except Exception:
        return hex_col


def _fmt_hms(s):
    s = max(0.0, s)
    h, m, ss = int(s // 3600), int((s % 3600) // 60), int(s % 60)
    if h > 0: return f"{h}h {m:02d}m {ss:02d}s"
    if m > 0: return f"{m}m {ss:02d}s"
    return f"{ss}s"