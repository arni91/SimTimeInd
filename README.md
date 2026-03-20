# 🏭 SimTimeInd v3

> **Simulador 2D de cinta de inducción con interfaz visual en tiempo real**
> Desarrollado para análisis de rendimiento operativo en instalaciones de intralogística.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![UI](https://img.shields.io/badge/UI-Tkinter-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-Proprietary-red)

---

## 📋 Tabla de contenidos

1. [Descripción](#descripción)
2. [Tecnologías](#tecnologías)
3. [Arquitectura y diseño](#arquitectura-y-diseño)
4. [Modelo de simulación](#modelo-de-simulación)
5. [Interfaz visual](#interfaz-visual)
6. [Instalación y uso](#instalación-y-uso)
7. [Opciones CLI](#opciones-cli)
8. [Compilar como ejecutable](#compilar-como-ejecutable)

---

## 📦 Descripción

SimTimeInd simula el comportamiento de una **cinta de inducción de paquetería** con hasta 22 mesas de operarios. Modela el ciclo de trabajo de cada operario (preparación de cubetas y paquetes, inducción en cinta, esperas por falta de hueco), el flujo de ítems a 22 m/min, y las métricas de producción en tiempo real: bultos/hora, cubetas/hora, paquetes/hora y tiempos de espera.

El simulador permite tres modos de operación:

- **Live** — pre-calcula la simulación completa al arrancar y permite navegar libremente por el tiempo con un slider, pausar y cambiar velocidad.
- **Batch** — sin UI, máxima velocidad, guarda la grabación en `.sim.gz`.
- **Replay** — reproduce grabaciones `.sim.gz` existentes.

---

## 🛠️ Tecnologías

| Tecnología | Uso |
|------------|-----|
| 🐍 **Python 3.10+** | Lenguaje principal |
| 🖼️ **Tkinter** (stdlib) | UI gráfica — Canvas 2D, scrollbars, zoom, slider |
| 🎲 **random** (stdlib) | Generación estocástica de ciclos y longitudes |
| 💾 **gzip + json** (stdlib) | Serialización de grabaciones `.sim.gz` |
| ⌨️ **argparse** (stdlib) | Interfaz de línea de comandos |
| 🧩 **dataclasses** (stdlib) | Modelos de datos tipados |
| 🔍 **bisect** (stdlib) | Búsqueda O(log n) en arrays de eventos para scrubbing |
| 📦 **PyInstaller** | Compilación a `.exe` standalone para Windows |

> ✅ Sin dependencias externas. Solo librería estándar de Python.

---

## 🏗️ Arquitectura y diseño

El proyecto aplica principios **SOLID** con separación estricta en tres capas:

```
SimTimeInd_v3/
├── main.py                       🚀 Punto de entrada — CLI / menú interactivo
└── simtimeind/
    ├── core/                     🧠 Dominio puro — sin UI ni I/O
    │   ├── constants.py              fuente única de verdad (constantes físicas)
    │   ├── models.py                 dataclasses: Item · Station · SimSnapshot
    │   ├── belt.py                   geometría de la cinta y búsqueda de huecos
    │   ├── engine.py                 motor de simulación paso a paso
    │   └── recorder.py              serialización / deserialización .sim.gz
    ├── ui/                       🖥️ Presentación — sin lógica de negocio
    │   ├── canvas_renderer.py        renderizado 2D completo cada tick
    │   ├── live_window.py            ventana live: batch precompute + scrubbing
    │   └── replay_window.py          reproducción de grabaciones
    └── utils/
        └── formatting.py         🔧 Helpers de formato y color
```

### 🔁 Flujo de datos

```
Engine ──step()──► eventos[]  ──to_dict()──► dict record
                                                  │
                              _setup_record() ◄───┘
                                    │
                              _snapshot_at(t)  ←── slider / tick
                                    │
                              SimSnapshot ──draw()──► CanvasRenderer
```

La UI nunca accede al estado interno de `Engine` durante la reproducción: todo el histórico está en arrays de prefijos que permiten reconstruir cualquier instante en O(log n).

### ✅ Principios SOLID aplicados

| Principio | Aplicación concreta |
|-----------|---------------------|
| **S** – Single Responsibility | `engine.py` solo simula · `recorder.py` solo graba · `canvas_renderer.py` solo dibuja · `belt.py` solo calcula huecos |
| **O** – Open/Closed | Nuevos paneles KPI en `CanvasRenderer` sin modificar `Engine` |
| **L** – Liskov | `_FakeStation` en replay es sustituible por `Station` en el renderer |
| **I** – Interface Segregation | `Engine` solo expone `snapshot()` hacia la UI; la UI nunca accede al estado interno |
| **D** – Dependency Inversion | La UI depende de `SimSnapshot` (DTO puro), no de `Engine` directamente |

---

## 🎮 Modelo de simulación

### 🏭 Zonas de producción

| Zona | Mesas | Ciclo medio | Descripción |
|------|-------|-------------|-------------|
| Zona 1 | M01–M07 | configurable (default 60 s) | 7 mesas normales |
| Zona 2 | M08–M14 | configurable (default 60 s) | 7 mesas normales |
| Zona 3 | M15–M21 | configurable (default 60 s) | 7 mesas normales |
| M22 | solo paquetes | 22.5 s (160 paq/h) | sin cubeta vacía |

### ⏱️ Ciclo operario (M01–M21)

Cada ciclo de duración `T` sigue esta secuencia:

| Fracción | Evento |
|----------|--------|
| 0 % | Inicio — operario comienza a preparar la cubeta |
| 8–13 % | Cubeta lista → intenta inducir en cinta |
| 45 / 67 / 90 % | Paquetes listos (1, 2 o 3 según probabilidades) |
| 100 % | Nuevo ciclo cuando: cubeta inductada + paquetes inductados + tiempo cumplido |

**Distribución de paquetes por ciclo:**

| k paquetes | Probabilidad |
|------------|--------------|
| 1 paquete | 88.3 % |
| 2 paquetes | 11.7 % |
| 3 paquetes | 0.0 % |

### ⏳ Fase de calentamiento (warmup)

Los primeros **5 minutos** de simulación son de calentamiento: la cinta funciona pero los ítems producidos no cuentan en el contador de producción ni se registran tiempos de espera. La medición efectiva comienza en `t = 300 s`.

### 📊 Variabilidad del ciclo

Cada operario tiene un ciclo propio muestreado de una distribución normal `N(mean, sd)` truncada en `[min, max]`. Con `sd = 3 s` sobre una media de 60 s, el coeficiente de variación es ~10 %, produciendo resultados distintos en cada ejecución.

### 📍 Punto de conteo

Los ítems se cuentan al cruzar `x = 50.0 m` (~5 m después de M22). Solo se cuentan ítems cuyo tiempo de cruce supera el warmup.

### 🎨 Colores semánticos

| Elemento | Color |
|----------|-------|
| Paquetes (boxes) | Azul `#3B9EF5` |
| Cubetas vacías (totes) | Naranja `#F5A623` |
| Producción / bueno | Verde `#4CAF82` |
| Bloqueo activo | Rojo `#E84040` |
| Motores de cinta | Teal `#00C8A7` |

---

## 🖥️ Interfaz visual

### 📐 Zonas de la ventana

**Barra superior** — parámetros de la instalación: velocidad de cinta, gap, dimensiones de ítems, buffer.

**Zona de cinta** — representación 2D con paquetes (azul) y cubetas (naranja) deslizándose, indicadores de estado por mesa (gris = normal, rojo = bloqueada), posición de motores (líneas teal) y cotas de distancia entre mesas.

**Panel KPI inferior** — tres columnas:

| Columna | Contenido |
|---------|-----------|
| **PRODUCCIÓN** | Barras de progreso total / paquetes / cubetas vs target; contador de ítems al punto de medición; barra de tiempo con zona warmup (morado) |
| **RENDIMIENTO OPERARIO** | Tabla TEÓRICO vs PRÁCTICO: M01-M21/mesa · Σ M01-M21 · M22 · TOTAL; valores actualizados cada segundo |
| **ESPERAS** | Tiempo total acumulado, media por mesa, peor mesa, desglose por estación |

**Barra de control** — Play/Pausa, multiplicador de velocidad (0.1×–50×) y slider de tiempo para navegar a cualquier instante de la simulación.

### 🔍 Zoom y navegación

| Acción | Resultado |
|--------|-----------|
| Redimensionar ventana | Canvas scrollable con barras autohide |
| `Ctrl + Rueda ↑` | Zoom in (hasta 4×) |
| `Ctrl + Rueda ↓` | Zoom out (hasta 0.3×) |
| `Rueda ↑/↓` | Scroll vertical |
| Slider "Tiempo (min)" | Salta a cualquier instante sin recalcular |

### ⏩ Scrubbing (navegación temporal)

Al abrir la ventana, la simulación se pre-calcula completa en segundo plano mostrando "Simulando...". Al terminar, el slider queda habilitado. Arrastrar el slider reconstruye el estado de la cinta en O(log n) usando arrays de prefijos sobre los eventos — sin re-simular.

---

## 🚀 Instalación y uso

```bash
# Simulación en vivo (configuración por defecto, semilla aleatoria)
python main.py

# Con parámetros personalizados
python main.py --stations 22 --duration 3900 --speed 2.0 --push

# Modo batch — sin UI, máxima velocidad, guarda grabación
python main.py --stations 22 --duration 3900 --no_ui --push --record out.sim.gz

# Reproducir grabación
python main.py --replay out.sim.gz
python main.py --replay          # abre selector de archivo
```

---

## ⚙️ Opciones CLI

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--stations` | `22` | Número de mesas (1–22) |
| `--duration` | `3900` | Duración simulada en segundos (65 min) |
| `--seed` | aleatorio | Semilla aleatoria; omitir para resultados distintos cada vez |
| `--speed` | `1.0` | Multiplicador de velocidad de visualización |
| `--view` | `full` | `full` = toda la cinta · `tail` = últimas mesas |
| `--push` / `--no_push` | `push` | Modo de empuje (gap 0 mm / 50 mm) |
| `--cycle_mean` | `60.0` | Ciclo medio operario en segundos (zonas 1–3) |
| `--cycle_sd` | `3.0` | Desviación estándar del ciclo en segundos |
| `--cycle_min` | `30.0` | Ciclo mínimo absoluto en segundos |
| `--cycle_max` | `120.0` | Ciclo máximo absoluto en segundos |
| `--p2` | `0.117` | Probabilidad de 2 paquetes por ciclo |
| `--p3` | `0.0` | Probabilidad de 3 paquetes por ciclo |
| `--box_sd_mm` | `30.0` | Desviación estándar longitud de paquete en mm |
| `--target_total_h` | `2700` | Target total bultos/hora |
| `--target_boxes_h` | `1500` | Target paquetes/hora |
| `--target_totes_h` | `1200` | Target cubetas vacías/hora |
| `--record` | — | Ruta de salida `.sim.gz` |
| `--no_ui` | — | Modo batch sin ventana gráfica |
| `--replay` | — | Ruta de grabación a reproducir |

---

## 📦 Compilar como ejecutable

```bash
pip install pyinstaller
build.bat
```

Genera `dist/SimTimeInd.exe` — ejecutable standalone sin Python instalado.

---

*🏭 Desarrollado por Dexter Intralogistics (amari) — uso interno.*
