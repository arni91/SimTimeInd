#!/usr/bin/env python3
# main.py
# ---------------------------------------------------------------
# Punto de entrada de SimTimeInd v3.
#
# Uso rápido:
#   python main.py          → menú interactivo
#
# Uso avanzado con argumentos:
#   python main.py --stations 22 --duration 3600 --speed 1.0 --push
#   python main.py --no_ui --push --record out.sim.gz
#   python main.py --replay out.sim.gz
# ---------------------------------------------------------------

import sys
import os
import argparse

# ── compatibilidad con PyInstaller --onefile ─────────────────────────────────
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS  # type: ignore[attr-defined]
    sys.path.insert(0, _base)

# ── imports del proyecto ─────────────────────────────────────────────────────
from simtimeind.core.constants import (
    EXE_STATIONS, EXE_SPEED, EXE_DURATION_S, EXE_SEED, EXE_VIEW, EXE_RECORD_PATH,
    START_AT_S, START_STAGGER_S,
    CYCLE_MEAN_M01_M07_S, CYCLE_SD_S, CYCLE_MIN_S, CYCLE_MAX_S,
    P2_DEFAULT, P3_DEFAULT, BOX_SD_M_DEFAULT,
    PUSH_ENABLED_DEFAULT,
    TARGET_TOTAL_H, TARGET_BOXES_H, TARGET_TOTES_H,
    DT_S,
)
from simtimeind.core.engine import Engine
from simtimeind.core.recorder import save as save_record, load as load_record


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


def _ask(prompt: str, default: str) -> str:
    """Pregunta con valor por defecto entre corchetes."""
    val = input(f"  {prompt} [{default}]: ").strip()
    return val if val else default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  ✗ Introduce un número entero.")


def _ask_float(prompt: str, default: float) -> float:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print(f"  ✗ Introduce un número.")


def _build_engine(args) -> Engine:
    push = PUSH_ENABLED_DEFAULT
    if hasattr(args, "push")    and args.push:    push = True
    if hasattr(args, "no_push") and args.no_push: push = False

    return Engine(
        stations        = args.stations,
        duration_s      = args.duration,
        seed            = args.seed,
        start_at_s      = args.start_at,
        start_stagger_s = args.start_stagger,
        cycle_mean_s    = args.cycle_mean,
        cycle_sd_s      = args.cycle_sd,
        cycle_min_s     = args.cycle_min,
        cycle_max_s     = args.cycle_max,
        p2              = args.p2,
        p3              = args.p3,
        box_sd_m        = max(0.0, args.box_sd_mm / 1000.0),
        push_enabled    = push,
        target_total_h  = args.target_total_h,
        target_boxes_h  = args.target_boxes_h,
        target_totes_h  = args.target_totes_h,
    )


def _run_no_ui(eng: Engine, record_path: str | None) -> None:
    steps_total = int(eng.duration_s / DT_S) + 1
    chunk = 50_000
    done  = 0
    print(f"\n  Simulando {eng.duration_s:.0f} s en modo batch...", end="", flush=True)
    while done < steps_total:
        n = min(chunk, steps_total - done)
        eng.step(n)
        done += n
        pct = done / steps_total * 100
        print(f"\r  Simulando... {pct:.0f}%   ", end="", flush=True)
    print("\r  Simulación completada.          ")

    if record_path:
        save_record(eng, record_path)
        print(f"  ✅  Grabación guardada: {record_path}")

    snap = eng.snapshot()
    print(f"\n  {'─'*46}")
    print(f"  {'RESULTADOS':^46}")
    print(f"  {'─'*46}")
    print(f"  Total   : {snap.rate_total_h:>7.0f} bultos/h  (target {eng.target_total_h:.0f})")
    print(f"  Paquetes: {snap.rate_boxes_h:>7.0f} paq/h     (target {eng.target_boxes_h:.0f})")
    print(f"  Cubetas : {snap.rate_totes_h:>7.0f} cub/h     (target {eng.target_totes_h:.0f})")
    print(f"  Ciclo   : {snap.cycle_mean_s:>7.1f} s  (min {snap.cycle_min_s:.1f}  max {snap.cycle_max_s:.1f})")
    delta_t = snap.rate_total_h - eng.target_total_h
    signo   = "+" if delta_t >= 0 else ""
    print(f"  Delta   : {signo}{delta_t:.0f} bultos/h respecto al target")
    print(f"  {'─'*46}\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Menú interactivo
# ─────────────────────────────────────────────────────────────────────────────

def _menu_interactivo() -> None:
    """Menú principal cuando se ejecuta sin argumentos."""

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        SimTimeInd v3  —  Menú            ║")
    print("  ╚══════════════════════════════════════════╝")
    print()
    print("  1  →  Simulación en vivo (con ventana)")
    print("  2  →  Grabar simulación  (batch, sin ventana)")
    print("  3  →  Reproducir grabación (.sim.gz)")
    print("  4  →  Compilar ejecutable .exe")
    print("  0  →  Salir")
    print()

    opcion = input("  Elige una opción: ").strip()

    if opcion == "0":
        return

    elif opcion == "1":
        _menu_live()

    elif opcion == "2":
        _menu_grabar()

    elif opcion == "3":
        _menu_replay()

    elif opcion == "4":
        _menu_compilar()

    else:
        print("  ✗ Opción no válida.\n")


def _pedir_params_comunes() -> dict:
    """Pide los parámetros básicos comunes a live y batch."""
    print()
    estaciones = _ask_int("Número de mesas (1-22)", EXE_STATIONS)
    duracion   = _ask_float("Duración simulada (segundos)", EXE_DURATION_S)
    velocidad  = _ask_float("Velocidad de visualización (×)", EXE_SPEED)
    empuje_str = _ask("Empuje activado (s/n)", "s")
    empuje     = empuje_str.lower() not in ("n", "no")
    print()
    return dict(
        stations=estaciones,
        duration=duracion,
        speed=velocidad,
        push=empuje,
        no_push=not empuje,
        seed=EXE_SEED,
        start_at=START_AT_S,
        start_stagger=START_STAGGER_S,
        cycle_mean=CYCLE_MEAN_M01_M07_S,
        cycle_sd=CYCLE_SD_S,
        cycle_min=CYCLE_MIN_S,
        cycle_max=CYCLE_MAX_S,
        p2=P2_DEFAULT,
        p3=P3_DEFAULT,
        box_sd_mm=BOX_SD_M_DEFAULT * 1000.0,
        target_total_h=TARGET_TOTAL_H,
        target_boxes_h=TARGET_BOXES_H,
        target_totes_h=TARGET_TOTES_H,
    )


def _menu_live() -> None:
    print()
    print("  ── Simulación en vivo ──────────────────────")
    params = _pedir_params_comunes()

    class _Args:
        pass
    args = _Args()
    for k, v in params.items():
        setattr(args, k, v)
    args.view = "full"

    eng = _build_engine(args)
    from simtimeind.ui.live_window import LiveWindow
    LiveWindow(eng, speed=args.speed, view=args.view, record_path=None).run()


def _menu_grabar() -> None:
    print()
    print("  ── Grabar simulación (batch) ───────────────")
    params = _pedir_params_comunes()
    ruta = _ask("Ruta del fichero de salida", "grabacion.sim.gz")

    class _Args:
        pass
    args = _Args()
    for k, v in params.items():
        setattr(args, k, v)

    eng = _build_engine(args)
    _run_no_ui(eng, ruta)


def _menu_replay() -> None:
    print()
    print("  ── Reproducir grabación ────────────────────")
    print("  Abriendo selector de archivo...")
    path = _choose_file()
    if not path:
        print("  ✗ No se seleccionó ningún fichero.\n")
        return
    rec = load_record(path)
    from simtimeind.ui.replay_window import ReplayWindow
    ReplayWindow(rec, view="full").run()


def _menu_compilar() -> None:
    print()
    print("  ── Compilar ejecutable .exe ────────────────")
    print("  Comprobando PyInstaller...")
    ret = os.system("pyinstaller --version >nul 2>&1")
    if ret != 0:
        print("  ✗ PyInstaller no está instalado.")
        print("  Instálalo con:  pip install pyinstaller")
        print()
        return
    print("  Compilando SimTimeInd.exe (puede tardar 1-2 min)...")
    print()
    os.system(
        "pyinstaller --noconfirm --clean --onefile --windowed "
        "--name SimTimeInd main.py"
    )
    print()
    if os.path.exists("dist/SimTimeInd.exe"):
        print("  ✅  Compilado correctamente → dist/SimTimeInd.exe")
    else:
        print("  ✗  La compilación falló. Revisa los mensajes de PyInstaller.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:

    # ── EXE sin argumentos → live directo (sin menú de terminal) ────────────
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        from simtimeind.ui.live_window import LiveWindow
        eng = Engine(
            stations=EXE_STATIONS, duration_s=EXE_DURATION_S, seed=EXE_SEED,
            start_at_s=START_AT_S, start_stagger_s=START_STAGGER_S,
            cycle_mean_s=CYCLE_MEAN_M01_M07_S, cycle_sd_s=CYCLE_SD_S,
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

    # ── Sin argumentos → menú interactivo ───────────────────────────────────
    if len(sys.argv) == 1:
        _menu_interactivo()
        return

    # ── Con argumentos → CLI clásico ────────────────────────────────────────
    ap = argparse.ArgumentParser(
        prog="simtimeind",
        description="Simulador de cinta de inducción v3",
    )

    ap.add_argument("--stations",       type=int,   default=EXE_STATIONS)
    ap.add_argument("--duration",       type=float, default=EXE_DURATION_S)
    ap.add_argument("--seed",           type=int,   default=EXE_SEED)
    ap.add_argument("--speed",          type=float, default=EXE_SPEED)
    ap.add_argument("--view",           choices=["full", "tail"], default="full")
    ap.add_argument("--start_at",       type=float, default=START_AT_S)
    ap.add_argument("--start_stagger",  type=float, default=START_STAGGER_S)
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
        path = args.replay
        if not path:
            path = _choose_file()
            if not path:
                print("No se seleccionó fichero. Saliendo.")
                return
        rec = load_record(path)
        ReplayWindow(rec, view=args.view).run()
        return

    if args.p2 < 0 or args.p3 < 0 or (args.p2 + args.p3) > 1.0:
        ap.error("Probabilidades inválidas: 0 ≤ p2, p3 y p2+p3 ≤ 1")

    eng = _build_engine(args)

    if args.no_ui:
        _run_no_ui(eng, args.record)
        return

    from simtimeind.ui.live_window import LiveWindow
    LiveWindow(eng, speed=args.speed, view=args.view,
               record_path=args.record).run()


if __name__ == "__main__":
    main()
