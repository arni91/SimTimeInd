# core/constants.py
# ---------------------------------------------------------------
# Todas las constantes físicas y por defecto del simulador.
# NO modificar salvo cambios validados en planta.
# ---------------------------------------------------------------

# ── Cinta ───────────────────────────────────────────────────────
BELT_SPEED_MPM: float = 22.0       # m/min
DT_S: float = 0.05                 # paso de simulación (s)

# ── Geometría de mesas ──────────────────────────────────────────
DX_WITHIN_PAIR_M: float   = 1.10   # distancia entre las 2 mesas del par
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
STANDARD_GAP_M: float  = 0.1     # gap sin empuje
PUSH_GAP_M: float      = 0.0      # gap con empuje activado
PUSH_ENABLED_DEFAULT: bool = True

RETRY_CHECK_S: float = DT_S       # cadencia de reintento de inserción

# ── Defaults operario ───────────────────────────────────────────
CYCLE_MEAN_S: float = 60.0
CYCLE_SD_S: float   = 6.0
CYCLE_MIN_S: float  = 30.0
CYCLE_MAX_S: float  = 120.0

P2_DEFAULT: float = 0.25          # prob. 2 paquetes/cubeta
P3_DEFAULT: float = 0.00           # prob. 3 paquetes/cubeta

# ── Defaults arranque ───────────────────────────────────────────
START_AT_S: float      = 5.0
START_STAGGER_S: float = 10.0

# ── Defaults EXE (ejecución directa sin argumentos) ─────────────
EXE_STATIONS: int     = 22
EXE_SPEED: float      = 1.0
EXE_DURATION_S: float = 3600.0
EXE_SEED: int         = 42
EXE_VIEW: str         = "full"
EXE_RECORD_PATH       = None

# ── UI / Visual ─────────────────────────────────────────────────
CANVAS_W: int  = 1560
CANVAS_H: int  = 720

# Zona cinta
BELT_Y: int     = 390              # Y central de la cinta en píxeles
ITEM_HALF_H: int      = 18             # semialtura referencia
TOTE_HALF_H: int      = 18             # cubeta: altura visual
BOX_HALF_H: int       = 18             # paquete: misma altura que cubeta

# Zona de métricas (panel inferior)
PANEL_H: int    = 160              # altura del panel de KPIs bajo la cinta
PANEL_Y: int    = CANVAS_H - PANEL_H

# Esperas visibles en cinta
WAIT_BLOCKED_THRESHOLD_S: float = 3.0   # umbral para colorear mesa en rojo

# Colores corporativos
COLOR_BG        = "#1A1D23"
COLOR_BELT      = "#3A3F4B"
COLOR_BELT_HL   = "#4A5060"
COLOR_BOX       = "#3B9EF5"        # paquete → azul
COLOR_TOTE      = "#F5A623"        # cubeta  → naranja
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