# utils/formatting.py
# ---------------------------------------------------------------
# Funciones de formato de texto reutilizables en toda la UI.
# ---------------------------------------------------------------


def fmt_time_min(t_s: float) -> str:
    m = int(t_s // 60)
    s = int(t_s % 60)
    return f"{m:02d}:{s:02d}"


def fmt_wait_short(wait_s: float) -> str:
    """Etiqueta compacta para mostrar bajo cada mesa."""
    if wait_s < 1.0:
        return ""
    if wait_s < 60:
        return f"{wait_s:.0f}s"
    return f"{wait_s/60:.1f}m"


def fmt_delta(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.0f}"


def fmt_rate(rate: float) -> str:
    return f"{rate:.0f}"


def color_delta(delta: float, good_color: str, bad_color: str, neutral: str = "#A0AAB8") -> str:
    if delta > 20:
        return good_color
    if delta < -20:
        return bad_color
    return neutral