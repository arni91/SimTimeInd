# core/constants.py
# ---------------------------------------------------------------
# Todas las constantes físicas y por defecto del simulador.
# NO modificar salvo cambios validados en planta.
# ---------------------------------------------------------------

# ── Cinta ───────────────────────────────────────────────────────
BELT_SPEED_MPM: float = 22.0       # m/min
DT_S: float = 0.05                 # paso de simulación (s)

# ── Geometría de mesas ──────────────────────────────────────────
DX_WITHIN_PAIR_M: float   = 1.10   # distancia entre las 2 mesas juntas
DX_BETWEEN_PAIRS_M: float = 2.74   # distancia entre pares consecutivos (general)
DX_GAP_M6_M7: float       = 4.54   # excepcion: distancia entre M6 y M7
DX_GAP_M16_M17: float     = 4.59   # excepcion: distancia entre M16 y M17
DX_GAP_M18_M19: float     = 4.59   # excepcion: distancia entre M18 y M19

# ── Dimensiones de ítems ────────────────────────────────────────
TOTE_LEN_M: float   = 0.600       # longitud cubeta vacía (X)
TOTE_WIDTH_MM: int  = 400         # ancho cubeta (Y) en mm
BOX_MEAN_M: float   = 0.179       # media longitud paquete (X)
BOX_WIDTH_MM: int   = 395         # ancho paquete (Y) en mm — cabe dentro cubeta
BOX_SD_M_DEFAULT: float = 0.030
BOX_MIN_M: float    = 0.100
BOX_MAX_M: float    = 0.400

# ── Targets de producción (bultos/h) ────────────────────────────
TARGET_TOTAL_H: float = 2700.0
TARGET_BOXES_H: float = 1500.0
TARGET_TOTES_H: float = 1200.0

# ── Gaps de inducción ───────────────────────────────────────────
STANDARD_GAP_M: float  = 0.05       # gap sin empuje
PUSH_GAP_M: float      = 0.0        # gap con empuje activado
PUSH_ENABLED_DEFAULT: bool = True

RETRY_CHECK_S: float = DT_S                  # cadencia de reintento de inserción
INSERT_HALF_RANGE_M: float = 0.75            # rango búsqueda de hueco en cinta por banda (todas las mesas)

# ── Defaults operario ───────────────────────────────────────────
# ── Probabilidad de paquetes por cubeta ─────────────────────────
# Cada ciclo normal induce 1 cubeta + entre 1 y 3 paquetes según estas probs.
# Cambia estos valores para ajustar cuántos paquetes lleva cada cubeta de media.
P2_DEFAULT: float = 0.117   # probabilidad de inducir 2 paquetes en un ciclo (11.7 %)
P3_DEFAULT: float = 0.0     # probabilidad de inducir 3 paquetes en un ciclo  ( 0 %)
                            # → probabilidad de 1 paquete = 1 - P2 - P3 = 88.3 %

# Media de paquetes por ciclo (calculado automático, no tocar):
_MEAN_PKG_PER_CYCLE: float = (
    1.0 * (1.0 - P2_DEFAULT - P3_DEFAULT) +     # 88.3 % × 1 paq
    2.0 * P2_DEFAULT +                          # 11.7 % × 2 paq
    3.0 * P3_DEFAULT                            #  0.0 % × 3 paq
)                                               # con p2=0.117, p3=0.0  →  1.117 paquetes/ciclo de media

# ── 4 zonas de producción ────────────────────────────────────────
# Las mesas normales (M01–M21) hacen: 1 ciclo = 1 cubeta + paquetes.
# ← MODIFICAR: solo el tiempo de ciclo en segundos de cada zona.
#    El resto se calcula automáticamente.

ZONE1_N: int = 7   # número de mesas en zona 1  (M01–M07)
ZONE2_N: int = 7   # número de mesas en zona 2  (M08–M14)
ZONE3_N: int = 7   # número de mesas en zona 3  (M15–M21)

#   Zona 1: M01–M07
CYCLE_MEAN_M01_M07_S: float = 63.0                                  # ← ciclo medio (s)
ZONE1_TOTES_H:        float = 3600.0 / CYCLE_MEAN_M01_M07_S         #   cubetas/h por mesa
ZONE1_BOXES_H:        float = ZONE1_TOTES_H * _MEAN_PKG_PER_CYCLE   #   paquetes/h por mesa
ZONE1_TOTAL_TOTES_H:  float = ZONE1_TOTES_H * ZONE1_N               #   cubetas/h zona total
ZONE1_TOTAL_BOXES_H:  float = ZONE1_BOXES_H  * ZONE1_N              #   paquetes/h zona total

#   Zona 2: M08–M14
CYCLE_MEAN_M08_M14_S: float = 63.0                                  # ← ciclo medio (s)
ZONE2_TOTES_H:        float = 3600.0 / CYCLE_MEAN_M08_M14_S
ZONE2_BOXES_H:        float = ZONE2_TOTES_H * _MEAN_PKG_PER_CYCLE
ZONE2_TOTAL_TOTES_H:  float = ZONE2_TOTES_H * ZONE2_N
ZONE2_TOTAL_BOXES_H:  float = ZONE2_BOXES_H  * ZONE2_N

#   Zona 3: M15–M21
CYCLE_MEAN_M15_M21_S: float = 63.0                                  # ← ciclo medio (s)
ZONE3_TOTES_H:        float = 3600.0 / CYCLE_MEAN_M15_M21_S
ZONE3_BOXES_H:        float = ZONE3_TOTES_H * _MEAN_PKG_PER_CYCLE
ZONE3_TOTAL_TOTES_H:  float = ZONE3_TOTES_H * ZONE3_N
ZONE3_TOTAL_BOXES_H:  float = ZONE3_BOXES_H  * ZONE3_N

CYCLE_SD_S:  float = 0.0        # desviación estándar del tiempo de ciclo (s)
                                # controla cuánto varía el ciclo de un operario a otro
CYCLE_MIN_S: float = 30.0       # tiempo de ciclo mínimo absoluto (s) — ningún operario va más rápido
CYCLE_MAX_S: float = 120.0      # tiempo de ciclo máximo absoluto (s) — ningún operario va más lento

# ── Defaults arranque ───────────────────────────────────────────
START_AT_S: float      = 0.5        # tiempo de arranque antes de empezar a contar producción  
START_STAGGER_S: float = 60         # tiempo entre arranques de operarios (si se arranca con todos operativos)

# ── Defaults EXE (ejecución directa sin argumentos) ─────────────
EXE_STATIONS: int     = 22
EXE_SPEED: float      = 1.0
EXE_DURATION_S: float = 3900.0   # 65 min: 5 min calentamiento + 60 min medición
EXE_SEED: int         = 42
EXE_VIEW: str         = "full"
EXE_RECORD_PATH       = None

# ── Calentamiento ────────────────────────────────────────────────
# Los primeros WARMUP_S segundos la simulación corre pero no cuenta
# producción. Las métricas empiezan a partir de t = WARMUP_S.
WARMUP_S: float = 300.0           # 5 min de calentamiento

# ── UI / Visual ─────────────────────────────────────────────────
CANVAS_W: int  = 1560
CANVAS_H: int  = 840

# Zona cinta
BELT_Y: int     = 380                   # Y central de la cinta en píxeles
ITEM_HALF_H: int      = 18              # semialtura referencia
TOTE_HALF_H: int      = 18              # cubeta: altura visual
BOX_HALF_H: int       = 18              # paquete: misma altura que cubeta

# Zona de métricas (panel inferior)
PANEL_H: int    = 320                   # altura del panel de KPIs bajo la cinta
PANEL_Y: int    = CANVAS_H - PANEL_H

# Esperas visibles en cinta
WAIT_BLOCKED_THRESHOLD_S: float = 2.0   # umbral para colorear mesa en rojo

# Colores corporativos
COLOR_BG        = "#1A1D23"
COLOR_BELT      = "#3A3F4B"
COLOR_BELT_HL   = "#4A5060"
COLOR_BOX       = "#3B9EF5"             # paquete → azul
COLOR_TOTE      = "#F5A623"             # cubeta  → naranja
COLOR_STATION_OK   = "#A0AAB8"
COLOR_STATION_WARN = "#F5A623"
COLOR_STATION_CRIT = "#E84040"
COLOR_TEXT_PRIMARY  = "#E8ECF2"
COLOR_TEXT_SECONDARY = "#7A8499"
COLOR_TEXT_GOOD     = "#4CAF82"
COLOR_TEXT_BAD      = "#E84040"
COLOR_TEXT_WARN     = "#F5A623"
COLOR_PANEL_BG      = "#12141A"
COLOR_PANEL_BORDER  = "#2E3340"
COLOR_GRID          = "#252830"

COLOR_KPI_TOTAL  = "#3B9EF5"
COLOR_KPI_BOX    = "#4CAF82"
COLOR_KPI_TOTE   = "#F5A623"

# ── Punto de conteo de producción ────────────────────────────────
# Posición en metros donde se cuentan los ítems para producción/h
# M22 está en 38.65 m — por defecto 3 m después de la última mesa
COUNTER_X_M: float = 50.00   # ~5m despues de M22

# ── M22: mesa solo-paquetes ──────────────────────────────────────
# M22 induce solo paquetes (sin cubeta vacia).
# ← MODIFICAR: M22_PKG_H; ciclo y totales se calculan solos.
M22_PACKAGES_ONLY: bool  = True        # activar modo solo-paquetes en M22
M22_PKG_H:         float = 160.0       # ← paquetes/hora de M22
M22_CYCLE_MEAN_S:  float = 3600.0 / M22_PKG_H           # ciclo medio (s) — calculado
M22_CYCLE_MIN_S:   float = M22_CYCLE_MEAN_S * 0.65      # ciclo mínimo  (~65 % de la media)
M22_CYCLE_MAX_S:   float = M22_CYCLE_MEAN_S * 1.55      # ciclo máximo  (~155 % de la media)
M22_TOTAL_BOXES_H: float = M22_PKG_H                    # paquetes/h totales M22 (1 sola mesa)
M22_TOTAL_TOTES_H: float = 0.0                          # cubetas/h M22 = 0 (nunca induce cubetas)

# ── TOTAL SIMULACIÓN (calculado automático) ──────────────────────
SIM_TOTAL_TOTES_H: float = (ZONE1_TOTAL_TOTES_H +
                             ZONE2_TOTAL_TOTES_H +
                             ZONE3_TOTAL_TOTES_H +
                             M22_TOTAL_TOTES_H)        # cubetas/h totales
SIM_TOTAL_BOXES_H: float = (ZONE1_TOTAL_BOXES_H +
                             ZONE2_TOTAL_BOXES_H +
                             ZONE3_TOTAL_BOXES_H +
                             M22_TOTAL_BOXES_H)        # paquetes/h totales
SIM_TOTAL_H:       float = SIM_TOTAL_TOTES_H + SIM_TOTAL_BOXES_H  # bultos/h totales

# Ciclo medio teórico ponderado por número de ciclos/h (incluye M22)
# Fórmula: Σ(N_i × 3600) / Σ(ciclos_i/h) = (22 mesas × 3600) / (totes/h + pkg_M22/h)
_SIM_N_TOTAL:     int   = ZONE1_N + ZONE2_N + ZONE3_N + 1           # total mesas incl. M22 = 22
_SIM_CYCLES_H:    float = SIM_TOTAL_TOTES_H + M22_PKG_H             # ciclos/h totales = 1200+160 = 1360
SIM_MEAN_CYCLE_S: float = (_SIM_N_TOTAL * 3600.0) / _SIM_CYCLES_H   # ≈ 58.2 s
# (valores teóricos sin esperas en cinta ni variabilidad)

# ── Motores cinta transportadora ─────────────────────────────────
# Posiciones en metros respecto al punto de inducción de M01 (0 m)
# Motor 1 es teórico (antes de M01), los demás son físicos
MOTOR_POSITIONS_M: list = [-1.000, 7.950, 19.710, 31.610, 43.480]
MOTOR_SPEED_MPM:   float = 22.0   # velocidad de todos los motores (m/min)