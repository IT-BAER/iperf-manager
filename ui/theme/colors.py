# -*- coding: utf-8 -*-
"""Dracula-inspired color palette for iperf_manager UI.

Provides named color constants used by QSS themes, chart styling,
and delegate painting.  All values are hex strings (#RRGGBB / #RRGGBBAA).

Official Dracula spec: https://draculatheme.com/contribute
"""

from __future__ import annotations

# ── Dracula Dark base palette ────────────────────────────────────────
BACKGROUND = "#282a36"
CURRENT    = "#44475a"   # current line / surface
FOREGROUND = "#f8f8f2"
COMMENT    = "#6272a4"
CYAN       = "#8be9fd"
GREEN      = "#50fa7b"
ORANGE     = "#ffb86c"
PINK       = "#ff79c6"
PURPLE     = "#bd93f9"
RED        = "#ff5555"
YELLOW     = "#f1fa8c"

# Extended surface shades (Dracula-derived)
SURFACE0   = "#343746"   # slightly lighter than BACKGROUND
SURFACE1   = "#44475a"   # == CURRENT
SURFACE2   = "#565a6e"   # hover highlight
MANTLE     = "#21222c"   # darker than BACKGROUND
CRUST      = "#191a21"   # darkest

# Text hierarchy
TEXT       = FOREGROUND   # #f8f8f2
SUBTEXT1   = "#e2e2e8"   # slightly muted
SUBTEXT0   = "#c0c0ca"
OVERLAY2   = "#a0a0b0"
OVERLAY1   = "#8888a0"
OVERLAY0   = COMMENT      # #6272a4

# Backward-compat aliases used by chart imports
BLUE       = CYAN         # #8be9fd
LAVENDER   = PURPLE       # #bd93f9
MAUVE      = PINK         # #ff79c6
PEACH      = ORANGE       # #ffb86c
TEAL       = "#50fac8"    # green-cyan blend
SKY        = "#80d4ff"    # lighter cyan
SAPPHIRE   = "#6eb5ff"    # blue tone
FLAMINGO   = "#ffb0c0"    # light pink
ROSEWATER  = "#ffd5d5"
MAROON     = "#e06060"
BASE       = BACKGROUND   # #282a36

# ── Dracula Light palette ───────────────────────────────────────────
LATTE_BACKGROUND = "#f8f8f2"
LATTE_FOREGROUND = "#282a36"
LATTE_CURRENT    = "#e8e8f0"
LATTE_COMMENT    = "#7970a9"
LATTE_CYAN       = "#0097a7"
LATTE_GREEN      = "#2e7d32"
LATTE_ORANGE     = "#e65100"
LATTE_PINK       = "#c2185b"
LATTE_PURPLE     = "#7c4dff"
LATTE_RED        = "#d50000"
LATTE_YELLOW     = "#f57f17"

LATTE_SURFACE0   = "#e0e0e8"
LATTE_SURFACE1   = "#d0d0dc"
LATTE_SURFACE2   = "#c0c0cc"
LATTE_BASE       = LATTE_BACKGROUND   # #f8f8f2
LATTE_MANTLE     = "#ededf5"
LATTE_CRUST      = "#e4e4ec"

LATTE_TEXT       = LATTE_FOREGROUND    # #282a36
LATTE_SUBTEXT1   = "#3c3c50"
LATTE_SUBTEXT0   = "#50506a"
LATTE_OVERLAY2   = "#6a6a80"
LATTE_OVERLAY1   = "#7e7e94"

# Backward-compat aliases for light theme
LATTE_BLUE       = LATTE_PURPLE    # #7c4dff
LATTE_LAVENDER   = "#9575cd"
LATTE_RED        = LATTE_RED       # #d50000
LATTE_PEACH      = LATTE_ORANGE    # #e65100
LATTE_YELLOW     = LATTE_YELLOW    # #f57f17
LATTE_GREEN      = LATTE_GREEN     # #2e7d32
LATTE_TEAL       = "#00897b"
LATTE_ROSEWATER  = "#ad1457"

# ── Semantic aliases (dark theme) ───────────────────────────────────
BG_PRIMARY   = BACKGROUND   # #282a36
BG_SECONDARY = MANTLE       # #21222c
BG_TERTIARY  = SURFACE0     # #343746
BG_WIDGET    = SURFACE0     # #343746
BG_HEADER    = CURRENT      # #44475a
BG_SELECTED  = SURFACE2     # #565a6e
BG_HOVER     = CURRENT      # #44475a

FG_PRIMARY   = TEXT          # #f8f8f2
FG_SECONDARY = SUBTEXT1     # #e2e2e8
FG_MUTED     = OVERLAY1     # #8888a0
FG_DISABLED  = COMMENT      # #6272a4

BORDER       = CURRENT      # #44475a
BORDER_FOCUS = PURPLE        # #bd93f9
BORDER_LIGHT = SURFACE2     # #565a6e

ACCENT       = PURPLE        # #bd93f9
ACCENT_HOVER = PINK          # #ff79c6
SUCCESS      = GREEN         # #50fa7b
WARNING      = YELLOW        # #f1fa8c
ERROR        = RED           # #ff5555
INFO         = CYAN          # #8be9fd

# ── Chart series colors (high-contrast on dark bg) ─────────────────
CHART_COLORS = [
    CYAN,       # #8be9fd
    RED,        # #ff5555
    GREEN,      # #50fa7b
    ORANGE,     # #ffb86c
    PINK,       # #ff79c6
    TEAL,       # #50fac8
    YELLOW,     # #f1fa8c
    FLAMINGO,   # #ffb0c0
    SKY,        # #80d4ff
    PURPLE,     # #bd93f9
    SAPPHIRE,   # #6eb5ff
    ROSEWATER,  # #ffd5d5
]

# ── Status indicator colors ─────────────────────────────────────────
STATUS_IDLE     = COMMENT    # #6272a4
STATUS_RUNNING  = GREEN      # #50fa7b
STATUS_ERROR    = RED        # #ff5555
STATUS_WARNING  = YELLOW     # #f1fa8c
STATUS_DISABLED = SURFACE2   # #565a6e

# ── Threshold / alert colors ───────────────────────────────────────
THRESHOLD_LINE = RED         # #ff5555
THRESHOLD_FILL = "#ff555540" # RED with 25% alpha

# ── Table-specific ──────────────────────────────────────────────────
TABLE_ROW_ALT  = SURFACE0    # #343746
TABLE_ROW_EVEN = MANTLE      # #21222c
TABLE_GRID     = CURRENT     # #44475a
TABLE_HEADER   = CURRENT     # #44475a
TABLE_SELECTED = SURFACE2    # #565a6e
TABLE_HOVER    = CURRENT     # #44475a

# ── Light theme semantic aliases ────────────────────────────────────
LIGHT_BG_PRIMARY   = LATTE_BASE       # #f8f8f2
LIGHT_BG_SECONDARY = LATTE_MANTLE     # #ededf5
LIGHT_BG_WIDGET    = "#ffffff"
LIGHT_BG_HEADER    = LATTE_SURFACE1   # #d0d0dc
LIGHT_BG_SELECTED  = LATTE_SURFACE2   # #c0c0cc
LIGHT_FG_PRIMARY   = LATTE_TEXT       # #282a36
LIGHT_FG_SECONDARY = LATTE_SUBTEXT1   # #3c3c50
LIGHT_ACCENT       = LATTE_PURPLE     # #7c4dff
LIGHT_BORDER       = LATTE_SURFACE1   # #d0d0dc
