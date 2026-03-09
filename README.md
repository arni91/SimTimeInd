# SimTimeInd v2

Simulador 2D de cinta de inducción con interfaz visual en tiempo real.

---

## Estructura del proyecto

```
simtimeind_project/
│
├── main.py                        ← Punto de entrada (CLI)
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
    │   ├── canvas_renderer.py     ← Dibuja cinta, ítems, mesas, panel KPI
    │   ├── live_window.py         ← Ventana de simulación en vivo
    │   └── replay_window.py       ← Ventana de reproducción con barra de tiempo
    │
    └── utils/
        └── formatting.py          ← Helpers de formato de texto/color
```

### Principios SOLID aplicados

| Principio | Aplicación |
|-----------|-----------|
| **S** – Single Responsibility | Cada módulo hace una sola cosa: `engine.py` simula, `recorder.py` guarda, `canvas_renderer.py` dibuja |
| **O** – Open/Closed | `CanvasRenderer` se puede extender sin modificar el motor |
| **L** – Liskov | `_FakeStation` en replay es compatible con `Station` para el renderer |
| **I** – Interface Segregation | El motor expone `snapshot()` limpio; la UI no accede al estado interno |
| **D** – Dependency Inversion | La UI depende de `SimSnapshot` (abstracción), no de `Engine` directamente |

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
| `--stations` | 22 | Número de mesas |
| `--duration` | 3600 | Duración simulada (s) |
| `--speed` | 1.0 | Factor de velocidad de reproducción |
| `--view` | full | `full` = toda la cinta, `tail` = últimas mesas |
| `--push` | activado | Gap efectivo = 0 mm (empuje) |
| `--no_push` | — | Gap = 100 mm (sin empuje) |
| `--cycle_mean` | 60 | Media del ciclo operario (s) |
| `--cycle_sd` | 6 | Desv. estándar del ciclo (s) |
| `--p2` | 0.25 | Prob. de 2 paquetes por cubeta |
| `--target_total_h` | 2700 | Target total bultos/hora |
| `--target_boxes_h` | 1500 | Target paquetes/hora |
| `--target_totes_h` | 1200 | Target cubetas vacías/hora |
| `--record` | — | Ruta de grabación .sim.gz |

---

## Interfaz visual

### Panel de cinta
- **Paquetes** → rectángulos **azules**
- **Cubetas vacías** → rectángulos **naranjas**
- **Mesas** → línea vertical con punto en la cinta
  - Gris: normal
  - Naranja: espera acumulada > 30 s
  - **Rojo**: bloqueada activamente > 3 s

### Información en cinta (por mesa)
- **Encima**: identificador de mesa (M01…M22)
- **Debajo**: tiempo de espera acumulado en badge de color
  - Badge oscuro: < 10 s
  - Badge amarillo: 10–60 s
  - Badge rojo: > 60 s
- **Badge rojo parpadeante**: bloqueo activo en curso

### Panel KPI inferior (3 columnas)
| Columna | Contenido |
|---------|-----------|
| PRODUCCIÓN | Barras de progreso total/paquetes/cubetas vs target, con delta |
| OPERARIO | Media de ciclo, min, max, total ciclos observados |
| ESPERAS | Total acumulado, media por mesa, peor mesa, últimas 4 mesas |

### Barra de progreso de tiempo
Barra azul en la parte inferior con el tiempo simulado actual.

---

## Compilar como .exe (Windows)
```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name SimTimeInd main.py
```

---

## Requisitos
- Python 3.10+
- tkinter (incluido en la instalación estándar de Python)
- Sin dependencias externas de terceros
