# SimTimeInd v3

Simulador 2D de cinta de inducción con interfaz visual en tiempo real.

---

## Estructura del proyecto

```
SimTimeInd_v3/
│
├── main.py                        ← Punto de entrada (CLI)
├── build.bat                      ← Script de compilación a .exe
│
└── simtimeind/                    ← Paquete principal
    │
    ├── core/                      ← Lógica de negocio (sin UI)
    │   ├── constants.py           ← Todas las constantes físicas y de configuración
    │   ├── models.py              ← Dataclasses puros (Item, Station, SimSnapshot)
    │   ├── belt.py                ← Geometría de cinta y comprobación de gap
    │   ├── engine.py              ← Motor de simulación (paso a paso)
    │   └── recorder.py            ← Serialización / deserialización .sim.gz
    │
    ├── ui/                        ← Interfaces gráficas (tkinter)
    │   ├── canvas_renderer.py     ← Dibuja cinta, ítems, mesas, paneles KPI
    │   ├── live_window.py         ← Ventana de simulación en vivo (redimensionable + zoom)
    │   └── replay_window.py       ← Ventana de reproducción con barra de tiempo
    │
    └── utils/
        └── formatting.py          ← Helpers de formato de texto/color
```

---

## Modelo de simulación

### Mesas y zonas

| Zona | Mesas | Ciclo medio |
|------|-------|-------------|
| Zona 1 | M01–M07 | configurable (default 63 s) |
| Zona 2 | M08–M14 | configurable (default 63 s) |
| Zona 3 | M15–M21 | configurable (default 63 s) |
| M22 | solo paquetes | configurable (default 160 paq/h) |

### Ciclo operario (M01–M21)

1. **Cubeta vacía** lista al 8–13% del ciclo → operario intenta inductarla en la cinta.
2. **Paquetes** listos entre el 45–90% del ciclo (1–3 según probabilidades configurables).
3. El siguiente ciclo empieza cuando: cubeta inductada + todos los paquetes inductados + tiempo de ciclo cumplido.

### ESPERAS (bloqueos de inducción)

El tiempo de espera **solo se cuenta** cuando el operario ha terminado de preparar todos los ítems del ciclo (último ítem ≥ 90% del ciclo) y aún tiene al menos un bulto pendiente de inducir. Es decir: el operario está **ocioso esperando hueco en la cinta**, sin poder empezar la siguiente cubeta.

### Colores semánticos

| Color | Elemento |
|-------|----------|
| Azul `#3B9EF5` | Paquetes (cajas) |
| Naranja `#F5A623` | Cubetas vacías |
| Verde `#4CAF82` | Totales / producción global |
| Blanco | Tiempos de ciclo |

---

## Interfaz visual

### Cinta

- **Paquetes** → rectángulos azules
- **Cubetas vacías** → rectángulos naranjas
- **Mesas**: línea vertical + punto en cinta
  - Gris: operando con normalidad
  - **Rojo**: esperando hueco en cinta (bloqueo activo)
- **Badges verticales** bajo cada mesa:
  - `C:Xs` — cubeta preparándose / esperando (naranja; rojo si bloqueada)
  - `P:Xs` — paquete preparándose / esperando (azul)
- **Motores** de la cinta marcados con línea discontinua teal

### Panel KPI inferior (3 columnas)

| Columna | Contenido |
|---------|-----------|
| **PRODUCCIÓN** | Barras de progreso total/paquetes/cubetas vs target; contador en punto de medición; tasa últimos 60 s |
| **RENDIMIENTO OPERARIO** | Tabla TEÓRICO vs PRÁCTICO por fila: M01-M21/mesa · Σ M01-M21 · M22 · TOTAL |
| **ESPERAS** | Total acumulado, media por mesa, peor mesa, desglose por estación |

### Ventana redimensionable y zoom

- La ventana se puede redimensionar como cualquier carpeta del escritorio.
- **Scroll** con la rueda del ratón (vertical) o las barras de desplazamiento.
- **Zoom**: `Ctrl + rueda` para ampliar/reducir (rango 0.3× – 4×). Nota: el zoom escala posiciones; el tamaño del texto permanece fijo.

---

## Uso

### Simulación en vivo
```bash
python main.py --stations 22 --duration 3600 --speed 1.0 --push
```

### Grabar sin UI (modo batch rápido)
```bash
python main.py --stations 22 --duration 3600 --no_ui --push --record out_22.sim.gz
```

### Reproducir grabación
```bash
python main.py --replay out_22.sim.gz --view full
python main.py --replay          # abre selector de archivo
```

### Opciones principales

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--stations` | 22 | Número de mesas (M01…M22) |
| `--duration` | 3600 | Duración simulada (s) |
| `--speed` | 1.0 | Factor de velocidad de reproducción |
| `--view` | full | `full` = toda la cinta · `tail` = últimas mesas |
| `--push` | activado | Gap efectivo = 0 mm (empuje activo) |
| `--no_push` | — | Gap = 50 mm (sin empuje) |
| `--cycle_mean` | 63 | Media del ciclo operario (s) — zonas 1-3 |
| `--cycle_sd` | 0 | Desv. estándar del ciclo (s) |
| `--p2` | 0.117 | Prob. de 2 paquetes por cubeta |
| `--p3` | 0.0 | Prob. de 3 paquetes por cubeta |
| `--target_total_h` | 2700 | Target total bultos/hora |
| `--target_boxes_h` | 1500 | Target paquetes/hora |
| `--target_totes_h` | 1200 | Target cubetas vacías/hora |
| `--record` | — | Ruta de grabación .sim.gz |
| `--seed` | 42 | Semilla aleatoria (reproducibilidad) |

---

## Compilar como .exe (Windows)

```bash
pip install pyinstaller
build.bat
```

O manualmente:
```bash
pyinstaller --noconfirm --clean --onefile --windowed --name SimTimeInd main.py
```

---

## Requisitos

- Python 3.10+
- `tkinter` (incluido en la instalación estándar de Python en Windows)
- Sin dependencias externas de terceros
