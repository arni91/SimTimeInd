#!/usr/bin/env python3
# main.py
# ---------------------------------------------------------------
# Punto de entrada de SimTimeInd v2.
#
# LIVE:
#   python main.py --stations 22 --duration 3600 --speed 1.0 --push
#
# GRABAR (sin UI):
#   python main.py --stations 22 --duration 3600 --no_ui --push --record out.sim.gz
#
# REPLAY:
#   python main.py --replay out.sim.gz
#   python main.py --replay          (abre selector de archivo)
#
# EXE directo (PyInstaller):
#   pyinstaller --noconfirm --clean --onefile --windowed --name SimTimeInd main.py
# ---------------------------------------------------------------

import sys
import argparse

# ── compatibilidad con PyInstaller --onefile ─────────────────────────────────
import os
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS  # type: ignore[attr-defined]
    sys.path.insert(0, _base)

# ── imports del proyecto ─────────────────────────────────────────────────────
from simtimeind.core.constants import (
    EXE_STATIONS, EXE_SPEED, EXE_DURATION_S, EXE_SEED, EXE_VIEW, EXE_RECORD_PATH,
    START_AT_S, START_STAGGER_S,
    CYCLE_MEAN_S, CYCLE_SD_S, CYCLE_MIN_S, CYCLE_MAX_S,
    P2_DEFAULT, P3_DEFAULT, BOX_SD_M_DEFAULT,
    PUSH_ENABLED_DEFAULT,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    DT_S,
)
from simtimeind.core.engine import Engine
from simtimeind.core.recorder import save as save_record, load as load_record


def _choose_file() -> str | None:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Selecciona fichero .sim.gz",
        filetypes=[("Grabación SimTimeInd", "*.sim.gz"),
                   ("Gzip", "*.gz"),
                   ("Todos", "*.*")],
    )
    root.destroy()
    return path or None


def _build_engine(args) -> Engine:
    push = PUSH_ENABLED_DEFAULT
    if hasattr(args, "push")    and args.push:    push = True
    if hasattr(args, "no_push") and args.no_push: push = False

    return Engine(
        stations       = args.stations,
        duration_s     = args.duration,
        seed           = args.seed,
        start_at_s     = args.start_at,
        start_stagger_s= args.start_stagger,
        cycle_mean_s   = args.cycle_mean,
        cycle_sd_s     = args.cycle_sd,
        cycle_min_s    = args.cycle_min,
        cycle_max_s    = args.cycle_max,
        p2             = args.p2,
        p3             = args.p3,
        box_sd_m       = max(0.0, args.box_sd_mm / 1000.0),
        push_enabled   = push,
        target_total_h = args.target_total_h,
        target_boxes_h = args.target_boxes_h,
        target_totes_h = args.target_totes_h,
    )


def _run_no_ui(eng: Engine, record_path: str | None) -> None:
    steps_total = int(eng.duration_s / DT_S) + 1
    chunk = 50_000
    done  = 0
    while done < steps_total:
        n = min(chunk, steps_total - done)
        eng.step(n)
        done += n

    if record_path:
        save_record(eng, record_path)
        print(f"✅  Grabación guardada: {record_path}")

    snap = eng.snapshot()
    print(f"SALIDA:  total≈{snap.rate_total_h:.0f}/h  |  "
          f"paquetes≈{snap.rate_boxes_h:.0f}/h  |  "
          f"cubetas≈{snap.rate_totes_h:.0f}/h")
    print(f"OPERARIO: mean≈{snap.cycle_mean_s:.1f}s  "
          f"min={snap.cycle_min_s:.1f}s  max={snap.cycle_max_s:.1f}s  "
          f"ciclos={snap.cycle_count}")
    print(f"DELTA:  total={snap.rate_total_h-eng.target_total_h:+.0f}/h  "
          f"paquetes={snap.rate_boxes_h-eng.target_boxes_h:+.0f}/h  "
          f"cubetas={snap.rate_totes_h-eng.target_totes_h:+.0f}/h")


def main() -> None:
    # ── EXE sin argumentos → live directo ───────────────────────
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        from simtimeind.ui.live_window import LiveWindow
        eng = Engine(
            stations=EXE_STATIONS, duration_s=EXE_DURATION_S, seed=EXE_SEED,
            start_at_s=START_AT_S, start_stagger_s=START_STAGGER_S,
            cycle_mean_s=CYCLE_MEAN_S, cycle_sd_s=CYCLE_SD_S,
            cycle_min_s=CYCLE_MIN_S,  cycle_max_s=CYCLE_MAX_S,
            p2=P2_DEFAULT, p3=P3_DEFAULT,
            push_enabled=PUSH_ENABLED_DEFAULT,
            target_total_h=TARGET_TOTAL_H,
            target_boxes_h=TARGET_BOXES_H,
            target_totes_h=TARGET_TOTES_H,
        )
        LiveWindow(eng, speed=EXE_SPEED, view=EXE_VIEW,
                   record_path=EXE_RECORD_PATH).run()
        return

    # ── Argumentos CLI ───────────────────────────────────────────
    ap = argparse.ArgumentParser(
        prog="simtimeind",
        description="Simulador de cinta de inducción v2",
    )

    ap.add_argument("--stations",      type=int,   default=22)
    ap.add_argument("--duration",      type=float, default=3600.0,
                    help="Duración total simulada (s)")
    ap.add_argument("--seed",          type=int,   default=42)
    ap.add_argument("--speed",         type=float, default=1.0,
                    help="Factor de velocidad de visualización")
    ap.add_argument("--view",          choices=["full", "tail"], default="full")

    ap.add_argument("--start_at",      type=float, default=START_AT_S)
    ap.add_argument("--start_stagger", type=float, default=START_STAGGER_S)

    ap.add_argument("--cycle_mean",    type=float, default=CYCLE_MEAN_S)
    ap.add_argument("--cycle_sd",      type=float, default=CYCLE_SD_S)
    ap.add_argument("--cycle_min",     type=float, default=CYCLE_MIN_S)
    ap.add_argument("--cycle_max",     type=float, default=CYCLE_MAX_S)

    ap.add_argument("--p2",            type=float, default=P2_DEFAULT,
                    help="Prob. de 2 paquetes por cubeta")
    ap.add_argument("--p3",            type=float, default=P3_DEFAULT,
                    help="Prob. de 3 paquetes por cubeta")
    ap.add_argument("--box_sd_mm",     type=float, default=BOX_SD_M_DEFAULT * 1000.0)

    ap.add_argument("--push",    action="store_true",
                    help="Activa empuje (gap efectivo = 0 mm)")
    ap.add_argument("--no_push", action="store_true",
                    help="Desactiva empuje (gap = 100 mm)")

    ap.add_argument("--target_total_h", type=float, default=TARGET_TOTAL_H)
    ap.add_argument("--target_boxes_h", type=float, default=TARGET_BOXES_H)
    ap.add_argument("--target_totes_h", type=float, default=TARGET_TOTES_H)

    ap.add_argument("--record",  type=str,   default=None,
                    help="Ruta de salida del fichero .sim.gz")
    ap.add_argument("--no_ui",   action="store_true",
                    help="Ejecuta sin UI (modo batch)")
    ap.add_argument("--replay",  nargs="?",  const="", default=None,
                    help="Reproduce una grabación .sim.gz")

    args = ap.parse_args()

    # ── REPLAY ───────────────────────────────────────────────────
    if args.replay is not None:
        from simtimeind.ui.replay_window import ReplayWindow
        path = args.replay
        if not path:
            path = _choose_file()
            if not path:
                print("No se seleccionó fichero. Saliendo.")
                return
        rec = load_record(path)
        ReplayWindow(rec, view=args.view).run()
        return

    # ── Validaciones ─────────────────────────────────────────────
    if args.p2 < 0 or args.p3 < 0 or (args.p2 + args.p3) > 1.0:
        ap.error("Probabilidades inválidas: 0 ≤ p2, p3 y p2+p3 ≤ 1")

    eng = _build_engine(args)

    # ── Sin UI ───────────────────────────────────────────────────
    if args.no_ui:
        _run_no_ui(eng, args.record)
        return

    # ── Live ─────────────────────────────────────────────────────
    from simtimeind.ui.live_window import LiveWindow
    LiveWindow(eng, speed=args.speed, view=args.view,
               record_path=args.record).run()


if __name__ == "__main__":
    main()
