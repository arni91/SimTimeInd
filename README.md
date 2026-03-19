# SimTimeInd v3

> **Simulador 2D de cinta de inducción con interfaz visual en tiempo real**
> Desarrollado para análisis de rendimiento operativo en instalaciones de intralogística.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![UI](https://img.shields.io/badge/UI-Tkinter-orange)
![License](https://img.shields.io/badge/License-Proprietary-red)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

## Tabla de contenidos

1. [Descripción](#descripción)
2. [Tecnologías](#tecnologías)
3. [Arquitectura y diseño OOP](#arquitectura-y-diseño-oop)
4. [Diagrama UML](#diagrama-uml)
5. [Modelo de simulación](#modelo-de-simulación)
6. [Interfaz visual](#interfaz-visual)
7. [Instalación y uso](#instalación-y-uso)
8. [Opciones CLI](#opciones-cli)
9. [Compilar como ejecutable](#compilar-como-ejecutable)
10. [Estructura del proyecto](#estructura-del-proyecto)

---

## Descripción

SimTimeInd simula el comportamiento de una **cinta de inducción de paquetería** con hasta 22 mesas de operarios. Modela:

- El **ciclo de trabajo** de cada operario: preparación de cubetas vacías y paquetes, inducción en cinta, tiempos de espera por falta de hueco.
- El **flujo de ítems** por la cinta a 22 m/min con gap configurable y modo de empuje.
- Las **métricas de producción** en tiempo real: bultos/hora, cubetas/hora, paquetes/hora, ESPERAS.
- Comparación **teórico vs práctico** del rendimiento por zona y mesa.

El simulador permite ejecutar en modo live (con UI), en modo batch (sin UI, máxima velocidad) y reproducir grabaciones `.sim.gz`.

---

## Tecnologías

| Tecnología | Versión | Uso |
|------------|---------|-----|
| **Python** | 3.10+ | Lenguaje principal |
| **Tkinter** | stdlib | UI gráfica (Canvas 2D) |
| **random** | stdlib | Generación estocástica de ciclos y paquetes |
| **gzip + json** | stdlib | Serialización de grabaciones `.sim.gz` |
| **argparse** | stdlib | Interfaz de línea de comandos |
| **dataclasses** | stdlib | Modelos de datos inmutables y tipados |
| **PyInstaller** | 6.x | Compilación a `.exe` standalone (Windows) |

> Sin dependencias externas de terceros. Solo Python estándar.

---

## Arquitectura y diseño OOP

El proyecto sigue los principios **SOLID** y una separación estricta entre capas:

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py (CLI)                       │
│              Punto de entrada y orquestación                │
└───────────────────────┬─────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐
   │  core/      │ │  ui/        │ │  utils/          │
   │  Lógica pura│ │  Presentac. │ │  Helpers         │
   └─────────────┘ └─────────────┘ └──────────────────┘
```

### Principios SOLID aplicados

| Principio | Aplicación concreta |
|-----------|---------------------|
| **S** – Single Responsibility | `engine.py` solo simula. `recorder.py` solo guarda/carga. `canvas_renderer.py` solo dibuja. `belt.py` solo gestiona geometría. |
| **O** – Open/Closed | `CanvasRenderer` se puede extender sin modificar el motor. Nuevos paneles KPI sin tocar `Engine`. |
| **L** – Liskov | `_FakeStation` en `replay_window.py` es compatible con `Station` para el renderer, sin herencia forzada. |
| **I** – Interface Segregation | El motor expone únicamente `snapshot()` hacia la UI; la UI no accede nunca al estado interno de `Engine`. |
| **D** – Dependency Inversion | La UI depende de `SimSnapshot` (abstracción de datos), no de `Engine` directamente. |

### Patrón Observer (implícito)

`Engine.snapshot()` actúa como observable: produce una vista inmutable del estado en cada tick. `CanvasRenderer.draw()` consume ese snapshot sin acoplar al motor.

### Separación Core / UI

```
Engine ──snapshot()──► SimSnapshot ──draw()──► CanvasRenderer
  (Modelo)              (DTO puro)              (Vista)
```

---

## Diagrama UML

```
┌──────────────────────────────────────────────────────────────────────┐
│                         << dataclass >>                               │
│                             Item                                      │
├──────────────────────────────────────────────────────────────────────┤
│ + kind: str          ("box" | "tote")                                │
│ + front_x: float     posición del frente en la cinta (m)            │
│ + length: float      longitud del ítem (m)                          │
├──────────────────────────────────────────────────────────────────────┤
│ + rear_x: float      [property] front_x - length                    │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         << dataclass >>                               │
│                            Station                                    │
├──────────────────────────────────────────────────────────────────────┤
│ + sid: str               identificador (M01…M22)                     │
│ + x: float               posición en cinta (m)                       │
│ + idx: int               índice 0-based                              │
│ + cycle_start_t: float   inicio del ciclo actual (s)                 │
│ + cycle_T: float         duración planificada del ciclo (s)          │
│ + tote_ready_t: float    momento de disponibilidad de cubeta         │
│ + tote_prep_start: float inicio de preparación de cubeta             │
│ + tote_wait_start: float inicio de espera de hueco (cubeta)          │
│ + box_queue: list        cola de ready_t de paquetes                 │
│ + box_prep_start: float  inicio de preparación del paquete actual    │
│ + packages_only: bool    True = M22 (sin cubetas)                    │
│ + blocked_since: float   inicio del bloqueo activo (-1 = ninguno)    │
│ + cycle_count: int       ciclos completados                          │
├──────────────────────────────────────────────────────────────────────┤
│ + commit_cycle_stats() → float                                       │
│ + record_block_start(t)                                               │
│ + record_block_end(t)                                                 │
│ + accumulated_wait_s(t) → float                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         << dataclass >>                               │
│                          SimSnapshot                                  │
├──────────────────────────────────────────────────────────────────────┤
│ + t: float                  tiempo de simulación actual (s)          │
│ + inserted_total/boxes/totes: int  ítems inductados                 │
│ + rate_total/boxes/totes_h: float  tasas acumuladas (bultos/h)       │
│ + rate_window_*_h: float    tasa últimos 60 s (ventana deslizante)   │
│ + counted_*: int/float      contadores en punto de medición          │
│ + cycle_count/mean/min/max  estadísticas de ciclos                   │
│ + wait_total_s: float       ESPERAS total acumulado                  │
│ + station_timers: list      7-tupla por mesa para la UI              │
│ + station_production: list  producción por mesa                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                            Engine                                     │
├──────────────────────────────────────────────────────────────────────┤
│ - stations: list[Station]                                             │
│ - items: list[Item]                                                   │
│ - t: float                  reloj de simulación (s)                  │
│ - rng: random.Random        generador reproducible                   │
│ - _insert_window: deque     ventana deslizante 60 s                  │
│ + inserted_total/boxes/totes: int                                     │
│ + counted_total/boxes/totes: int  punto de conteo físico             │
├──────────────────────────────────────────────────────────────────────┤
│ + __init__(stations, duration_s, seed, ...)                           │
│ + step(n_steps)             avanza n pasos de DT_S segundos          │
│ + snapshot() → SimSnapshot  vista inmutable del estado               │
│ + finalize()                cierra intervalos de bloqueo             │
│ - _plan_new_cycle(st)       planifica tote + paquetes del ciclo N    │
│ - _sample_cycle_time(mean)  muestrea T con distribución uniforme     │
│ - _sample_packs_per_tote()  muestrea k paquetes (1/2/3)              │
│ - _sample_box_length()      muestrea longitud de paquete (normal)    │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         CanvasRenderer                                │
├──────────────────────────────────────────────────────────────────────┤
│ - canvas: tk.Canvas                                                   │
│ - scale: float              px/metro para la cinta                   │
│ - view_start/end: float     ventana de visión (m)                    │
│ - _zoom: float              factor de zoom (en LiveWindow)           │
├──────────────────────────────────────────────────────────────────────┤
│ + draw(snap, items, tick, counter_snap)   punto de entrada           │
│ - _draw_belt()              fondo y cinta                            │
│ - _draw_info_bar()          barra superior de parámetros             │
│ - _draw_motors()            posiciones de motores                    │
│ - _draw_items(items)        paquetes y cubetas sobre la cinta        │
│ - _draw_stations(snap)      líneas de mesa + badges verticales       │
│ - _draw_panel(snap)         panel KPI inferior (3 columnas)          │
│ - _kpi_production()         barras de producción vs target           │
│ - _kpi_rendimiento()        tabla TEÓRICO vs PRÁCTICO                │
│ - _kpi_waits()              tiempos de espera por mesa               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                          LiveWindow                                   │
├──────────────────────────────────────────────────────────────────────┤
│ - eng: Engine                                                         │
│ - renderer: CanvasRenderer                                            │
│ - _zoom: float              zoom actual de la ventana                │
│ - _paused: bool                                                       │
│ - _acc: float               acumulador de tiempo simulado            │
├──────────────────────────────────────────────────────────────────────┤
│ + run()                     inicia el bucle tkinter                  │
│ - _tick()                   avanza simulación + redibuja (16 ms)     │
│ - _on_zoom(event)           Ctrl+rueda → zoom 0.3×–4×               │
│ - _on_scroll_v(event)       rueda → scroll vertical                  │
│ - _toggle_pause()                                                     │
└──────────────────────────────────────────────────────────────────────┘

             LiveWindow ──usa──► Engine
             LiveWindow ──usa──► CanvasRenderer
             Engine     ──crea──► Station (×22)
             Engine     ──crea──► Item    (dinámico)
             Engine     ──produce──► SimSnapshot
             CanvasRenderer ──consume──► SimSnapshot
```

---

## Modelo de simulación

### Geometría de la instalación

```
  M01  M02  M03  M04  M05  M06  M07    M08 ... M14    M15 ... M21  M22
  |    |    |    |    |    |    |       |         |    |         |    |
◄─────────────────────────────── 22 m/min ────────────────────────────────►
  0m                                                                  ~47m
```

- Las mesas se agrupan en **pares** separados 1.10 m entre sí.
- Distancia entre pares: 2.74 m (excepciones en M6-M7, M16-M17, M18-M19: 4.54–4.59 m).
- **5 motores** en la cinta (posiciones: -1.0, 7.95, 19.71, 31.61, 43.48 m).

### Ciclo operario (M01–M21)

```
t₀          t₀+8%T      t₀+45%T   t₀+67%T  t₀+90%T        t₀+T
│            │            │         │         │               │
├────────────┼────────────┼─────────┼─────────┼───────────────┤
│ preparando │ ◄ CUBETA   │ PAQ 1   │ PAQ 2   │ PAQ 3         │
│ cubeta     │   lista    │  listo  │  listo  │   listo       │
└────────────┴────────────┴─────────┴─────────┴───────────────┘
              ↑                                               ↑
          intenta inducir                         nuevo ciclo (si inductado todo)
```

- **k paquetes por ciclo**: 1 (prob. 88.3%), 2 (prob. 11.7%), 3 (prob. 0%) — configurables.
- Nuevo ciclo: cuando cubeta inductada + todos los paquetes inductados + `t ≥ cycle_start + cycle_T`.

### Lógica de ESPERAS

El tiempo de espera **solo se acumula** cuando:
1. El operario ha **terminado de preparar** todos los ítems del ciclo (t ≥ 90% del ciclo).
2. Aún tiene al menos **1 ítem pendiente de inducir** (sin hueco en la cinta).

> Esto refleja el operario **ocioso** esperando para poder coger la siguiente cubeta.

### M22 — Mesa solo paquetes

Mesa especial sin cubeta vacía. Cadencia: `3600 / PKG_H` segundos/paquete (default: 160 paq/h → 22.5 s/paquete).

### Punto de conteo de producción

Los ítems se cuentan al cruzar `COUNTER_X_M = 50.0 m` (~5 m después de la última mesa). Genera las métricas de producción real.

### Colores semánticos

| Color | Hex | Elemento |
|-------|-----|----------|
| Azul | `#3B9EF5` | Paquetes (boxes) |
| Naranja | `#F5A623` | Cubetas vacías (totes) |
| Verde | `#4CAF82` | Totales / producción global |
| Blanco | `#E8ECF2` | Tiempos de ciclo (teórico y práctico) |
| Rojo | `#E84040` | Bloqueo activo / espera crítica |
| Teal | `#00C8A7` | Motores de la cinta |

---

## Interfaz visual

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Cinta: 22 m/min  │  Cubeta: 600mm  │  Paquete: 179mm media  │  ...   │  ← barra info
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  M1    M2    M3  ...  M7    M8  ...  M14   M15  ...  M21   M22         │  ← mesas
│  |     |     |         |    |         |    |          |     |           │
│  ════════════════════════════════════════════════════════════════════   │  ← cinta
│  [■■■] [  ] [■■■■■■]  [■] [■■■] [■■]  [■■■] ...                      │  ← ítems
│  C:12s      C:5s           C:38s                                        │  ← badges
│  P:3s       P:8s           P:18s                                        │
├─────────────────────────────────────────────────────────────────────────┤
│ PRODUCCIÓN         │ RENDIMIENTO OPERARIO   │ ESPERAS                   │  ← panel KPI
│ TOTAL  ████░░  847 │ TEÓRICO  │ PRÁCTICO   │                           │
│ PAQS   ███░░░  489 │ M01-M21  │ M01-M21    │                           │
│ CUBTAS ██░░░░  358 │ Σ M01-21 │ Σ M01-21   │                           │
│                    │ M22      │ M22        │                           │
│                    │ TOTAL    │ TOTAL      │                           │
└─────────────────────────────────────────────────────────────────────────┘
[Play/Pausa]  [Velocidad: 1.0×]                             [Simulando...]
```

### Badges por mesa (verticales)

Debajo de cada mesa se muestran los tiempos de preparación actuales:

| Badge | Color | Significado |
|-------|-------|-------------|
| `C:Xs` | Naranja | Cubeta preparándose (X segundos transcurridos) |
| `C:Xs` | Rojo | Cubeta esperando hueco en cinta (bloqueada) |
| `P:Xs` | Azul | Paquete preparándose / esperando inducir |

### Panel RENDIMIENTO OPERARIO

Tabla con columnas **TEÓRICO** (calculado desde constantes) y **PRÁCTICO** (medido en simulación):

| Columna | Descripción |
|---------|-------------|
| `ciclo` | Tiempo de ciclo medio (s) |
| `cub/h` | Cubetas por hora |
| `paq/h` | Paquetes por hora |
| `tot/h` | Total bultos por hora |

Filas: `M01-M21 /mesa` · `Σ M01-M21` · `M22` · `TOTAL`

### Zoom y navegación

| Acción | Resultado |
|--------|-----------|
| Redimensionar ventana | Canvas scrollable; la simulación no se redimensiona |
| `Ctrl + Rueda ↑/↓` | Zoom in/out (0.3× – 4×) |
| `Rueda ↑/↓` | Scroll vertical |
| Barra de scroll | Navegación horizontal/vertical |

> El zoom escala posiciones y formas; el texto permanece en tamaño original.

---

## Instalación y uso

### Requisitos

```bash
python --version  # 3.10+
# No requiere pip install — solo librería estándar de Python
```

### Simulación en vivo

```bash
python main.py
python main.py --stations 22 --duration 3600 --speed 1.0 --push
python main.py --stations 22 --speed 5.0 --view tail   # últimas mesas, 5x velocidad
```

### Modo batch (sin UI, máxima velocidad)

```bash
python main.py --stations 22 --duration 3600 --no_ui --push --record out_22.sim.gz
```

Salida de consola:
```
SALIDA:  total≈2691/h  |  paquetes≈1489/h  |  cubetas≈1202/h
OPERARIO: mean≈63.4s  min=30.0s  max=63.0s  ciclos=1274
DELTA:  total=-9/h  paquetes=-11/h  cubetas=+2/h
```

### Reproducir grabación

```bash
python main.py --replay out_22.sim.gz --view full
python main.py --replay          # abre selector de archivo gráfico
```

---

## Opciones CLI

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--stations` | 22 | Número de mesas (1–22) |
| `--duration` | 3600.0 | Duración simulada en segundos |
| `--seed` | 42 | Semilla aleatoria (reproducibilidad garantizada) |
| `--speed` | 1.0 | Multiplicador de velocidad de visualización |
| `--view` | `full` | `full` = toda la cinta · `tail` = últimas mesas |
| `--push` | activado | Gap efectivo = 0 mm (empuje activo) |
| `--no_push` | — | Gap = 50 mm (sin empuje) |
| `--cycle_mean` | 63.0 | Media del ciclo operario (s) — zonas 1-3 |
| `--cycle_sd` | 0.0 | Desviación estándar del ciclo (s) |
| `--cycle_min` | 30.0 | Ciclo mínimo absoluto (s) |
| `--cycle_max` | 120.0 | Ciclo máximo absoluto (s) |
| `--p2` | 0.117 | Probabilidad de 2 paquetes por ciclo |
| `--p3` | 0.0 | Probabilidad de 3 paquetes por ciclo |
| `--box_sd_mm` | 30.0 | Desviación estándar longitud de paquete (mm) |
| `--target_total_h` | 2700 | Target total bultos/hora |
| `--target_boxes_h` | 1500 | Target paquetes/hora |
| `--target_totes_h` | 1200 | Target cubetas vacías/hora |
| `--record` | — | Ruta de salida `.sim.gz` |
| `--no_ui` | — | Modo batch sin ventana |
| `--replay` | — | Ruta de grabación a reproducir |

---

## Compilar como ejecutable

```bash
pip install pyinstaller
build.bat
```

O manualmente:
```bash
pyinstaller --noconfirm --clean --onefile --windowed --name SimTimeInd main.py
```

Genera `dist/SimTimeInd.exe` — ejecutable standalone sin Python instalado.

---

## Estructura del proyecto

```
SimTimeInd_v3/
│
├── main.py                        ← Punto de entrada y CLI (argparse)
├── build.bat                      ← Script de compilación PyInstaller
├── README.md
│
└── simtimeind/
    ├── __init__.py
    │
    ├── core/                      ← Capa de dominio (sin UI, sin I/O)
    │   ├── constants.py           ← Constantes físicas y defaults (fuente única de verdad)
    │   ├── models.py              ← Dataclasses: Item, Station, SimSnapshot
    │   ├── belt.py                ← Geometría: posiciones de mesas, búsqueda de hueco
    │   ├── engine.py              ← Motor de simulación (stepping, ciclos, estadísticas)
    │   └── recorder.py            ← Serialización/deserialización .sim.gz (gzip+json)
    │
    ├── ui/                        ← Capa de presentación (tkinter)
    │   ├── canvas_renderer.py     ← Renderizado 2D completo en cada tick
    │   ├── live_window.py         ← Ventana live: bucle, zoom, scrollbars, controles
    │   └── replay_window.py       ← Ventana replay: barra de tiempo, navegación
    │
    └── utils/
        └── formatting.py          ← Helpers: fmt_time_min, fmt_rate, color_delta
```

---

## Constantes físicas principales (`constants.py`)

| Constante | Valor | Descripción |
|-----------|-------|-------------|
| `BELT_SPEED_MPM` | 22.0 m/min | Velocidad de la cinta |
| `DT_S` | 0.05 s | Paso de simulación |
| `TOTE_LEN_M` | 0.600 m | Longitud cubeta vacía |
| `BOX_MEAN_M` | 0.179 m | Longitud media paquete |
| `CYCLE_MEAN_M01_M07_S` | 63.0 s | Ciclo medio zonas 1-3 |
| `M22_PKG_H` | 160.0 paq/h | Cadencia de M22 |
| `COUNTER_X_M` | 50.0 m | Punto de medición de producción |
| `STANDARD_GAP_M` | 0.05 m | Gap mínimo entre ítems |

---

*Desarrollado por Dexter Intralogistics — uso interno.*
