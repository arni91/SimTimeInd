#!/usr/bin/env python3
# main.py  —  SimTimeInd v3
# ---------------------------------------------------------------
# Uso:
#   python main.py          -> menu interactivo
#   python main.py --help   -> opciones CLI avanzadas
# ---------------------------------------------------------------

import sys
import os
import argparse
import subprocess

if getattr(sys, "frozen", False):
    _base = sys._MEIPASS  # type: ignore[attr-defined]
    sys.path.insert(0, _base)

from simtimeind.core.constants import (
    EXE_STATIONS, EXE_SPEED, EXE_DURATION_S, EXE_SEED, EXE_VIEW, EXE_RECORD_PATH,
    START_AT_S, START_STAGGER_S,
    CYCLE_MEAN_M01_M07_S, CYCLE_SD_S, CYCLE_MIN_S, CYCLE_MAX_S,
    P2_DEFAULT, P3_DEFAULT, BOX_SD_M_DEFAULT,
    PUSH_ENABLED_DEFAULT,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    WARMUP_S,
    DT_S,
)
from simtimeind.core.engine import Engine
from simtimeind.core.recorder import save as save_record, load as load_record


# ─────────────────────────────────────────────────────────────────────────────
#  Engine por defecto
# ─────────────────────────────────────────────────────────────────────────────

def _engine_default() -> Engine:
    return Engine(
        stations        = EXE_STATIONS,
        duration_s      = EXE_DURATION_S,
        seed            = EXE_SEED,
        start_at_s      = START_AT_S,
        start_stagger_s = START_STAGGER_S,
        cycle_mean_s    = CYCLE_MEAN_M01_M07_S,
        cycle_sd_s      = CYCLE_SD_S,
        cycle_min_s     = CYCLE_MIN_S,
        cycle_max_s     = CYCLE_MAX_S,
        p2              = P2_DEFAULT,
        p3              = P3_DEFAULT,
        push_enabled    = PUSH_ENABLED_DEFAULT,
        target_total_h  = TARGET_TOTAL_H,
        target_boxes_h  = TARGET_BOXES_H,
        target_totes_h  = TARGET_TOTES_H,
        warmup_s        = WARMUP_S,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Modo batch (sin UI)
# ─────────────────────────────────────────────────────────────────────────────

def _run_batch(eng: Engine, record_path: str | None) -> None:
    steps_total = int(eng.duration_s / DT_S) + 1
    chunk = 50_000
    done  = 0
    while done < steps_total:
        n = min(chunk, steps_total - done)
        eng.step(n)
        done += n
        pct = done / steps_total * 100
        print(f"\r  Simulando... {pct:.0f}%   ", end="", flush=True)
    print("\r  Completado.                     ")

    if record_path:
        save_record(eng, record_path)
        print(f"  OK  Grabacion guardada: {record_path}")

    snap = eng.snapshot()
    print()
    print(f"  {'-'*44}")
    print(f"  {'RESULTADOS':^44}")
    print(f"  {'-'*44}")
    print(f"  Total   : {snap.rate_total_h:>7.0f} bultos/h  (target {eng.target_total_h:.0f})")
    print(f"  Paquetes: {snap.rate_boxes_h:>7.0f} paq/h     (target {eng.target_boxes_h:.0f})")
    print(f"  Cubetas : {snap.rate_totes_h:>7.0f} cub/h     (target {eng.target_totes_h:.0f})")
    print(f"  Ciclo   : {snap.cycle_mean_s:>7.1f} s  "
          f"(min {snap.cycle_min_s:.1f}  max {snap.cycle_max_s:.1f})")
    delta = snap.rate_total_h - eng.target_total_h
    print(f"  Delta   : {'+' if delta >= 0 else ''}{delta:.0f} bultos/h")
    print(f"  {'-'*44}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  Selector de fichero
# ─────────────────────────────────────────────────────────────────────────────

def _choose_file() -> str | None:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Selecciona fichero .sim.gz",
        filetypes=[("Grabacion SimTimeInd", "*.sim.gz"),
                   ("Gzip", "*.gz"),
                   ("Todos", "*.*")],
    )
    root.destroy()
    return path or None


# ─────────────────────────────────────────────────────────────────────────────
#  Menu interactivo
# ─────────────────────────────────────────────────────────────────────────────

def _menu() -> None:
    print()
    print("  +------------------------------------------+")
    print("  |       SimTimeInd v3                      |")
    print("  +------------------------------------------+")
    print("  |  1  Simulacion en vivo (ventana)         |")
    print("  |  2  Grabar simulacion (batch)            |")
    print("  |  3  Reproducir grabacion (.sim.gz)       |")
    print("  |  4  Compilar ejecutable .exe             |")
    print("  |  0  Salir                                |")
    print("  +------------------------------------------+")
    print()

    opcion = input("  Opcion: ").strip()
    print()

    if opcion == "0":
        return

    elif opcion == "1":
        from simtimeind.ui.live_window import LiveWindow
        LiveWindow(_engine_default(), speed=EXE_SPEED, view=EXE_VIEW,
                   record_path=None).run()

    elif opcion == "2":
        ruta = input("  Nombre del fichero de salida [grabacion.sim.gz]: ").strip()
        if not ruta:
            ruta = "grabacion.sim.gz"
        print()
        _run_batch(_engine_default(), ruta)

    elif opcion == "3":
        print("  Abriendo selector de archivo...")
        path = _choose_file()
        if not path:
            print("  No se selecciono ningun fichero.")
            return
        rec = load_record(path)
        from simtimeind.ui.replay_window import ReplayWindow
        ReplayWindow(rec, view="full").run()

    elif opcion == "4":
        print("  Comprobando PyInstaller...")
        check = subprocess.run(
            ["pyinstaller", "--version"],
            capture_output=True,
        )
        if check.returncode != 0:
            print("  PyInstaller no encontrado.")
            print("  Instalalo con:  pip install pyinstaller")
            return
        print("  Compilando SimTimeInd.exe...")
        print()
        subprocess.run(
            ["pyinstaller", "--noconfirm", "--clean", "--onefile",
             "--windowed", "--name", "SimTimeInd", "main.py"]
        )
        print()
        if os.path.exists("dist/SimTimeInd.exe"):
            print("  OK  Compilado -> dist/SimTimeInd.exe")
        else:
            print("  Error en la compilacion. Revisa los mensajes anteriores.")
        print()

    else:
        print("  Opcion no valida.")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _build_engine_from_args(args) -> Engine:
    push = PUSH_ENABLED_DEFAULT
    if getattr(args, "push",    False): push = True
    if getattr(args, "no_push", False): push = False
    return Engine(
        stations        = args.stations,
        duration_s      = args.duration,
        seed            = args.seed,
        start_at_s      = START_AT_S,
        start_stagger_s = START_STAGGER_S,
        cycle_mean_s    = getattr(args, "cycle_mean", CYCLE_MEAN_M01_M07_S),
        cycle_sd_s      = getattr(args, "cycle_sd",   CYCLE_SD_S),
        cycle_min_s     = getattr(args, "cycle_min",  CYCLE_MIN_S),
        cycle_max_s     = getattr(args, "cycle_max",  CYCLE_MAX_S),
        p2              = getattr(args, "p2",          P2_DEFAULT),
        p3              = getattr(args, "p3",          P3_DEFAULT),
        box_sd_m        = getattr(args, "box_sd_mm",   BOX_SD_M_DEFAULT * 1000.0) / 1000.0,
        push_enabled    = push,
        target_total_h  = getattr(args, "target_total_h", TARGET_TOTAL_H),
        target_boxes_h  = getattr(args, "target_boxes_h", TARGET_BOXES_H),
        target_totes_h  = getattr(args, "target_totes_h", TARGET_TOTES_H),
    )


def main() -> None:

    # EXE sin argumentos -> live directo
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        from simtimeind.ui.live_window import LiveWindow
        LiveWindow(_engine_default(), speed=EXE_SPEED, view=EXE_VIEW,
                   record_path=EXE_RECORD_PATH).run()
        return

    # Sin argumentos -> menu interactivo
    if len(sys.argv) == 1:
        _menu()
        return

    # Con argumentos -> CLI clasico
    ap = argparse.ArgumentParser(prog="simtimeind",
                                 description="Simulador de cinta de induccion v3")
    ap.add_argument("--stations",       type=int,   default=EXE_STATIONS)
    ap.add_argument("--duration",       type=float, default=EXE_DURATION_S)
    ap.add_argument("--seed",           type=int,   default=EXE_SEED)
    ap.add_argument("--speed",          type=float, default=EXE_SPEED)
    ap.add_argument("--view",           choices=["full", "tail"], default="full")
    ap.add_argument("--cycle_mean",     type=float, default=CYCLE_MEAN_M01_M07_S)
    ap.add_argument("--cycle_sd",       type=float, default=CYCLE_SD_S)
    ap.add_argument("--cycle_min",      type=float, default=CYCLE_MIN_S)
    ap.add_argument("--cycle_max",      type=float, default=CYCLE_MAX_S)
    ap.add_argument("--p2",             type=float, default=P2_DEFAULT)
    ap.add_argument("--p3",             type=float, default=P3_DEFAULT)
    ap.add_argument("--box_sd_mm",      type=float, default=BOX_SD_M_DEFAULT * 1000.0)
    ap.add_argument("--push",           action="store_true")
    ap.add_argument("--no_push",        action="store_true")
    ap.add_argument("--target_total_h", type=float, default=TARGET_TOTAL_H)
    ap.add_argument("--target_boxes_h", type=float, default=TARGET_BOXES_H)
    ap.add_argument("--target_totes_h", type=float, default=TARGET_TOTES_H)
    ap.add_argument("--record",         type=str,   default=None)
    ap.add_argument("--no_ui",          action="store_true")
    ap.add_argument("--replay",         nargs="?",  const="", default=None)
    args = ap.parse_args()

    if args.replay is not None:
        from simtimeind.ui.replay_window import ReplayWindow
        path = args.replay or _choose_file()
        if not path:
            print("No se selecciono fichero.")
            return
        ReplayWindow(load_record(path), view=args.view).run()
        return

    eng = _build_engine_from_args(args)

    if args.no_ui:
        _run_batch(eng, args.record)
        return

    from simtimeind.ui.live_window import LiveWindow
    LiveWindow(eng, speed=args.speed, view=args.view,
               record_path=args.record).run()


if __name__ == "__main__":
    main()
