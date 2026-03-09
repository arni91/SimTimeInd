# ui/canvas_renderer.py
from __future__ import annotations

from ..core.constants import (
    CANVAS_W, CANVAS_H, BELT_Y, ITEM_HALF_H,
    TOTE_HALF_H, BOX_HALF_H, TOTE_WIDTH_MM, BOX_WIDTH_MM,
    PANEL_Y, PANEL_H,
    COLOR_BG, COLOR_BELT, COLOR_BELT_HL,
    COLOR_BOX, COLOR_TOTE,
    COLOR_STATION_OK, COLOR_STATION_CRIT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_GOOD, COLOR_TEXT_BAD, COLOR_TEXT_WARN,
    COLOR_PANEL_BG, COLOR_PANEL_BORDER, COLOR_GRID,
    COLOR_KPI_TOTAL, COLOR_KPI_BOX, COLOR_KPI_TOTE,
    WAIT_BLOCKED_THRESHOLD_S,
    BELT_SPEED_MPM, TOTE_LEN_M, BOX_MEAN_M, BOX_MIN_M, BOX_MAX_M,
)
from ..core.models import SimSnapshot
from ..utils.formatting import fmt_time_min, fmt_delta, fmt_rate, color_delta

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

_COL_TOTE_PREP = "#7A5010"
_COL_BOX_PREP  = "#104878"
_COL_WAIT_BG   = "#5A1010"
_INFO_BAR_H    = 22
_INFO_BAR_Y    = 8


class CanvasRenderer:

    def __init__(self, canvas, view_start, view_end, scale, station_list,
                 push_enabled, effective_gap_m, target_total_h, target_boxes_h,
                 target_totes_h, duration_s, view_label="full"):
        self.canvas       = canvas
        self.view_start   = view_start
        self.view_end     = view_end
        self.scale        = scale        # px/m — usado para calcular alturas Y proporcionales
        self.stations     = station_list
        self.push_enabled = push_enabled
        self.eff_gap_m    = effective_gap_m
        self.tgt_total    = target_total_h
        self.tgt_boxes    = target_boxes_h
        self.tgt_totes    = target_totes_h
        self.duration_s   = duration_s
        self.view_label   = view_label
        self._tick        = 0

    def _px(self, x_m):
        return int(60 + (x_m - self.view_start) * self.scale)

    def _in_view(self, x_m):
        return self.view_start - 1.0 <= x_m <= self.view_end + 1.0

    def _item_half_h(self, kind: str) -> int:
        """
        Semialtura en píxeles proporcional a los mm reales en Y.
        Cubeta y paquete: 400mm en Y.
        Usa self.scale (px/m) con factor de amplificación para visibilidad,
        garantizando siempre que X (600mm cubeta) > Y (400mm) visualmente.
        Factor 1.2 → 400mm * scale*1.2/2 ≈ 6-8px semialtura con escala full view.
        """
        width_m = (TOTE_WIDTH_MM if kind == "tote" else BOX_WIDTH_MM) / 1000.0
        return max(4, int(round(width_m * self.scale * 1.2 / 2)))

    def _belt_half_h(self) -> int:
        return self._item_half_h("tote") + 6

    def draw(self, snap, items, tick=0):
        self._tick = tick
        c = self.canvas
        c.delete("all")
        self._draw_background()
        self._draw_info_bar()
        self._draw_belt()
        self._draw_counter_marker(snap)
        self._draw_items(items)
        self._draw_stations(snap)
        self._draw_dimension_lines()
        self._draw_kpi_panel(snap)
        self._draw_footer(snap)

    def _draw_background(self):
        c = self.canvas
        c.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill=COLOR_BG, outline="")
        for y in range(0, CANVAS_H, 60):
            c.create_line(0, y, CANVAS_W, y, fill=COLOR_GRID, width=1)

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
        c.create_rectangle(x0, by-h+4, x1, by+h+6, fill="#0D0F14", outline="")
        c.create_rectangle(x0, by-h,   x1, by+h,   fill=COLOR_BELT, outline=COLOR_BELT_HL, width=1)
        c.create_line(x0, by-h, x1, by-h, fill="#5A6070", width=2)
        c.create_line(x0, by+h, x1, by+h, fill="#2A2E38", width=2)
        c.create_line(x0, by,   x1, by,   fill="#252830", width=1, dash=(4, 8))

    def _draw_counter_marker(self, snap):
        if not self._in_view(snap.counter_x_m):
            return
        c = self.canvas
        px = self._px(snap.counter_x_m)
        by = BELT_Y
        h = self._belt_half_h()

        c.create_line(px, by-h-30, px, by+h+30, fill="#F5A623", width=2, dash=(6, 4))

        top_w = 86
        c.create_rectangle(px-top_w//2, by-h-44, px+top_w//2, by-h-26,
                           fill="#2A2000", outline="#F5A623", width=1)
        c.create_text(px, by-h-35, text="CONTADOR", fill="#F5A623",
                      font=("Consolas", 8, "bold"), anchor="center")

        total_txt  = f"{snap.counted_total}"
        detail_txt = f"P:{snap.counted_boxes}  C:{snap.counted_totes}"
        box_w = max(96, len(total_txt)*9+20, len(detail_txt)*7+20)
        num_y1 = by + h + 50
        num_y2 = by + h + 66
        c.create_rectangle(px-box_w//2, num_y1-12, px+box_w//2, num_y2+10,
                           fill="#0D1018", outline="#F5A623", width=1)
        c.create_text(px, num_y1, text=total_txt,
                      fill="#F5A623", font=("Consolas", 11, "bold"), anchor="center")
        c.create_text(px, num_y2, text=detail_txt,
                      fill=COLOR_TEXT_SECONDARY, font=("Consolas", 8), anchor="center")

    def _draw_items(self, items):
        c = self.canvas
        by = BELT_Y
        for it in items:
            if not (self._in_view(it.front_x) or self._in_view(it.rear_x)):
                continue
            fx  = self._px(it.front_x)
            rx  = self._px(it.rear_x)
            ih  = self._item_half_h(it.kind)
            col = COLOR_BOX if it.kind == "box" else COLOR_TOTE
            c.create_rectangle(rx+2, by-ih+3, fx+2, by+ih+3, fill="#111418", outline="")
            c.create_rectangle(rx,   by-ih,   fx,   by+ih,   fill=col, outline="")
            c.create_rectangle(rx,   by-ih,   fx,   by-ih+3, fill=_lighten(col, 40), outline="")

    def _draw_stations(self, snap):
        c = self.canvas
        by = BELT_Y

        wait_map  = {sid: (acc_s, bn, wn)
                     for sid, x, acc_s, bn, wn in snap.wait_per_station}
        timer_map = {sid: (tp, bp, tw)
                     for sid, _w, tp, bp, tw in snap.station_timers}

        for i, st in enumerate(self.stations):
            sid = st.sid if hasattr(st, "sid") else st["sid"]
            x_m = st.x  if hasattr(st, "x")   else float(st["x"])
            if not self._in_view(x_m):
                continue
            px   = self._px(x_m)
            pair = i % 2

            acc_s, blocked_now, wait_now_s       = wait_map.get(sid,  (0.0, False, 0.0))
            tote_prep_s, box_prep_s, tote_wait_s = timer_map.get(sid, (-1.0, -1.0, -1.0))

            if blocked_now and wait_now_s >= WAIT_BLOCKED_THRESHOLD_S:
                col_line = COLOR_STATION_CRIT
                col_text = COLOR_STATION_CRIT
            else:
                col_line = COLOR_STATION_OK
                col_text = COLOR_TEXT_SECONDARY

            lw = 3 if (blocked_now and wait_now_s >= _ACTIVE_WAIT_THRESHOLD_S) else 2
            c.create_line(px, by-52, px, by+52, fill=col_line, width=lw)
            c.create_oval(px-5, by-5, px+5, by+5, fill=col_line, outline="")
            c.create_text(px, by-(68+pair*16), text=sid,
                          fill=col_text, font=_FONT_LABEL_MD, anchor="center")

            y_badges = by + 58 + pair * 16
            badges   = []
            if tote_prep_s >= 0:
                if tote_wait_s >= _WAIT_SHOW_S:
                    badges.append((f"C:{tote_wait_s:.0f}s", _COL_WAIT_BG,   COLOR_TEXT_BAD))
                else:
                    badges.append((f"C:{tote_prep_s:.0f}s", _COL_TOTE_PREP, COLOR_KPI_TOTE))
            if box_prep_s >= 0:
                badges.append((f"P:{box_prep_s:.0f}s", _COL_BOX_PREP, COLOR_KPI_BOX))

            if badges:
                bw_list = [max(len(t)*6+8, 28) for t, _, _ in badges]
                total_w = sum(bw_list) + (len(badges)-1)*3
                bx = px - total_w // 2
                for (txt, bg, fg), bw in zip(badges, bw_list):
                    c.create_rectangle(bx, y_badges-7, bx+bw, y_badges+7, fill=bg, outline="")
                    c.create_text(bx+bw//2, y_badges, text=txt, fill=fg,
                                  font=_FONT_TIMER, anchor="center")
                    bx += bw + 3

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
            x0m = xs[i];  x1m = xs[i + 1]
            if not (self._in_view(x0m) or self._in_view(x1m)):
                continue
            px0 = self._px(x0m);  px1 = self._px(x1m)
            row_y = by - 155 if (i % 2 == 0) else by - 171
            c.create_line(px0, row_y, px1, row_y, fill=col_dim, width=1)
            c.create_line(px0, row_y-tick_h, px0, row_y+tick_h, fill=col_dim, width=1)
            c.create_line(px1, row_y-tick_h, px1, row_y+tick_h, fill=col_dim, width=1)
            dist = x1m - x0m
            mid  = (px0 + px1) // 2
            c.create_text(mid, row_y-5, text=f"{dist:.2f}m",
                          fill=col_text, font=fnt_sm, anchor="s")

        if self._in_view(xs[0]) or self._in_view(xs[-1]):
            px_first = self._px(xs[0])
            px_last  = self._px(xs[-1])
            tot_y    = by - 191
            c.create_line(px_first, tot_y, px_last, tot_y, fill=col_total, width=1)
            c.create_line(px_first, tot_y-tick_h-2, px_first, tot_y+tick_h+2, fill=col_total, width=1)
            c.create_line(px_last,  tot_y-tick_h-2, px_last,  tot_y+tick_h+2, fill=col_total, width=1)
            total_dist = xs[-1] - xs[0]
            mid_tot    = (px_first + px_last) // 2
            c.create_text(mid_tot, tot_y-5,
                          text=f"M1-M22 = {total_dist:.2f} m",
                          fill=col_total, font=fnt_tot, anchor="s")

    def _draw_kpi_panel(self, snap):
        c = self.canvas
        py, ph, pw = PANEL_Y, PANEL_H, CANVAS_W
        c.create_rectangle(0, py, pw, py+ph, fill=COLOR_PANEL_BG, outline="")
        c.create_line(0, py, pw, py, fill=COLOR_PANEL_BORDER, width=2)
        self._kpi_production(snap, x=40,         y=py+12)
        c.create_line(pw//3,   py+10, pw//3,   py+ph-10, fill=COLOR_PANEL_BORDER, width=1)
        self._kpi_operator(snap,  x=pw//3+30,   y=py+12)
        c.create_line(pw*2//3, py+10, pw*2//3, py+ph-10, fill=COLOR_PANEL_BORDER, width=1)
        self._kpi_waits(snap,     x=pw*2//3+30, y=py+12)

    def _kpi_production(self, snap, x, y):
        c = self.canvas
        c.create_text(x, y, text="PRODUCCION  media /hora  (contador)",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 18
        rows = [
            ("TOTAL",    snap.counted_total_h, self.tgt_total, COLOR_KPI_TOTAL),
            ("PAQUETES", snap.counted_boxes_h, self.tgt_boxes, COLOR_KPI_BOX),
            ("CUBETAS",  snap.counted_totes_h, self.tgt_totes, COLOR_KPI_TOTE),
        ]
        for label, rate, tgt, col in rows:
            delta = rate - tgt
            dcol  = color_delta(delta, COLOR_TEXT_GOOD, COLOR_TEXT_BAD, COLOR_TEXT_WARN)
            bw, bh = 300, 22
            fp = min(int(rate / max(1, tgt) * bw), bw+40)
            c.create_rectangle(x, y, x+bw, y+bh, fill="#1E2128",                outline="")
            c.create_rectangle(x, y, x+fp,  y+bh, fill=_alpha_color(col, 0.25), outline="")
            c.create_text(x+6,   y+11, text=label,               fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")
            c.create_text(x+140, y+11, text=fmt_rate(rate),      fill=col,                  font=_FONT_MONO_LG, anchor="center")
            c.create_text(x+220, y+11, text=f"/{fmt_rate(tgt)}", fill=COLOR_TEXT_SECONDARY, font=_FONT_MONO_SM, anchor="w")
            c.create_text(x+296, y+11, text=fmt_delta(delta),    fill=dcol,                 font=_FONT_MONO_SM, anchor="e")
            y += bh + 6

    def _kpi_operator(self, snap, x, y):
        c = self.canvas
        c.create_text(x, y, text="OPERARIO",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 18
        mean = snap.cycle_mean_s
        mean_col = COLOR_TEXT_GOOD if mean <= 65 else COLOR_TEXT_WARN
        c.create_text(x,     y, text="Tiempo medio / cubeta",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        c.create_text(x+200, y, text=f"{mean:.1f} s" if mean > 0 else "---",
                      fill=mean_col, font=_FONT_MONO_LG, anchor="nw")
        y += 24
        c.create_text(x, y,
                      text=f"Min {snap.cycle_min_s:.0f}s   Max {snap.cycle_max_s:.0f}s   Obs. {snap.cycle_count}",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 18
        c.create_line(x+10, y, x+370, y, fill=COLOR_PANEL_BORDER, width=1)
        y += 8

        _TOTE_FRAC = (0.08 + 0.13) / 2.0
        tote_s = _TOTE_FRAC * mean
        box_s  = max(0.0, mean - tote_s)
        ref    = mean if mean > 0 else 1.0

        c.create_text(x, y, text="Desglose  (suman Tiempo medio / cubeta):",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 16

        tote_str = f"{tote_s:.1f} s" if mean > 0 else "---"
        tote_pct = f"{tote_s/ref*100:.0f}%" if mean > 0 else ""
        c.create_rectangle(x+8, y+2, x+20, y+12, fill=COLOR_TOTE, outline="")
        c.create_text(x+26,  y, text="Cubeta vacia",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        c.create_text(x+200, y, text=tote_str,
                      fill=COLOR_KPI_TOTE if mean > 0 else COLOR_TEXT_SECONDARY,
                      font=_FONT_MONO_MD, anchor="nw")
        c.create_text(x+255, y, text=tote_pct,
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 18

        box_str = f"{box_s:.1f} s" if mean > 0 else "---"
        box_pct = f"{box_s/ref*100:.0f}%" if mean > 0 else ""
        c.create_rectangle(x+8, y+2, x+20, y+12, fill=COLOR_BOX, outline="")
        c.create_text(x+26,  y, text="Paquetes",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        c.create_text(x+200, y, text=box_str,
                      fill=COLOR_KPI_BOX if mean > 0 else COLOR_TEXT_SECONDARY,
                      font=_FONT_MONO_MD, anchor="nw")
        c.create_text(x+255, y, text=box_pct,
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")

    def _kpi_waits(self, snap, x, y):
        c = self.canvas
        c.create_text(x, y, text="ESPERAS  (bloqueo induccion)",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        y += 14
        total_s   = snap.wait_total_s
        total_col = (COLOR_TEXT_GOOD if total_s < 60 else
                     COLOR_TEXT_WARN if total_s < 300 else COLOR_TEXT_BAD)
        c.create_text(x,     y, text="Total acumulado (Sigma mesas)",
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="nw")
        c.create_text(x+280, y, text=_fmt_hms(total_s),
                      fill=total_col, font=_FONT_MONO_LG, anchor="nw")
        y += 20
        right_edge = CANVAS_W - 20
        c.create_line(x, y, right_edge, y, fill=COLOR_PANEL_BORDER, width=1)
        y += 5

        stations_wait = list(snap.wait_per_station)
        n      = len(stations_wait)
        thirds = (n + 2) // 3
        col_w  = (right_edge - x) // 3
        row_h  = 13

        for ci in range(3):
            cx, cy = x + ci * col_w, y
            for sid, _, acc_s, bn, wn in stations_wait[ci*thirds: ci*thirds+thirds]:
                if cy + row_h > PANEL_Y + PANEL_H - 4:
                    break
                rc = (COLOR_STATION_CRIT
                      if bn and wn >= WAIT_BLOCKED_THRESHOLD_S
                      else COLOR_TEXT_SECONDARY)
                c.create_text(cx,    cy, text=sid,             fill=rc,                 font=_FONT_LABEL_SM, anchor="nw")
                c.create_text(cx+34, cy, text=_fmt_hms(acc_s), fill=COLOR_TEXT_PRIMARY, font=_FONT_LABEL_SM, anchor="nw")
                cy += row_h

    def _draw_footer(self, snap):
        c = self.canvas
        bar_x, bar_y = 60, PANEL_Y - 18
        bar_w, bar_h = CANVAS_W - 120, 6
        prog = snap.t / max(1, self.duration_s)

        lx, ly = CANVAS_W - 220, bar_y - 20
        c.create_rectangle(lx,     ly, lx+16,  ly+12, fill=COLOR_BOX,  outline="")
        c.create_text(lx+22,  ly+6, text="Paquete", fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")
        c.create_rectangle(lx+100, ly, lx+116, ly+12, fill=COLOR_TOTE, outline="")
        c.create_text(lx+122, ly+6, text="Cubeta",  fill=COLOR_TEXT_SECONDARY, font=_FONT_SANS_SM, anchor="w")

        c.create_rectangle(bar_x, bar_y, bar_x+bar_w,           bar_y+bar_h, fill="#252830",       outline="")
        c.create_rectangle(bar_x, bar_y, bar_x+int(bar_w*prog), bar_y+bar_h, fill=COLOR_KPI_TOTAL, outline="")
        c.create_text(bar_x, bar_y-6,
                      text=(f"  {fmt_time_min(snap.t)} / {fmt_time_min(self.duration_s)}"
                            f"   |   mesas={len(self.stations)}   |   vista={self.view_label}"),
                      fill=COLOR_TEXT_SECONDARY, font=_FONT_MONO_SM, anchor="w")


def _lighten(hex_col, amount):
    try:
        return (f"#{min(255,int(hex_col[1:3],16)+amount):02X}"
                f"{min(255,int(hex_col[3:5],16)+amount):02X}"
                f"{min(255,int(hex_col[5:7],16)+amount):02X}")
    except Exception:
        return hex_col


def _alpha_color(hex_col, alpha):
    try:
        bg = (0x1A, 0x1D, 0x23)
        r, g, b = int(hex_col[1:3],16), int(hex_col[3:5],16), int(hex_col[5:7],16)
        return (f"#{int(bg[0]+(r-bg[0])*alpha):02X}"
                f"{int(bg[1]+(g-bg[1])*alpha):02X}"
                f"{int(bg[2]+(b-bg[2])*alpha):02X}")
    except Exception:
        return hex_col


def _fmt_hms(s):
    s = max(0.0, s)
    h, m, ss = int(s//3600), int((s%3600)//60), int(s%60)
    if h > 0: return f"{h}h {m:02d}m {ss:02d}s"
    if m > 0: return f"{m}m {ss:02d}s"
    return f"{ss}s"