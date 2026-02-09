# -*- coding: utf-8 -*-
"""ui.theme - QSS themes and color definitions.

Usage::

    from ui.theme import load_theme, colors

    app.setStyleSheet(load_theme("dark"))   # or "light"
"""

from pathlib import Path

_THEME_DIR = Path(__file__).parent


def load_theme(name: str = "dark") -> str:
    """Return the QSS stylesheet text for *name* ('dark' or 'light').

    Resolves ``url(theme://...)`` placeholders to absolute file paths
    so that image references (e.g. arrow SVGs) work regardless of CWD.
    """
    qss_file = _THEME_DIR / f"{name}.qss"
    if not qss_file.exists():
        raise FileNotFoundError(f"Theme file not found: {qss_file}")
    text = qss_file.read_text(encoding="utf-8")
    theme_path = _THEME_DIR.as_posix()
    return text.replace("url(theme://", f"url({theme_path}/")
