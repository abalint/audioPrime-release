"""Themeable color system — define a 5-color palette, get a full UI theme.

To try a new palette, add a Theme to THEMES and set ACTIVE_THEME to its name.
All backgrounds, borders, text, and accents are derived from the 5 palette colors.
"""

from dataclasses import dataclass, field


# ── Color utilities ──────────────────────────────────────────────────────────

def _hex_to_rgb(c: str) -> tuple[int, int, int]:
    h = c.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def darken(color: str, factor: float) -> str:
    """Darken a color.  factor 1.0 = unchanged, 0.0 = black."""
    r, g, b = _hex_to_rgb(color)
    return _rgb_to_hex(int(r * factor), int(g * factor), int(b * factor))


def lighten(color: str, factor: float) -> str:
    """Lighten a color.  factor 0.0 = unchanged, 1.0 = white."""
    r, g, b = _hex_to_rgb(color)
    return _rgb_to_hex(
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


# ── Theme dataclass ──────────────────────────────────────────────────────────

@dataclass
class Theme:
    """A full UI theme derived from 5 palette colors.

    Palette roles:
        primary   — buttons, progress bars, sliders, focus borders
        secondary — text selection, checked checkboxes
        accent    — title text, highlighted labels
        danger    — cancel / destructive actions
        highlight — section headers, decorative accents
    """

    name: str
    primary: str
    secondary: str
    accent: str
    danger: str
    highlight: str

    # ── derived (auto-computed in __post_init__, override by passing explicitly) ──
    bg: str = ""
    bg_surface: str = ""
    bg_deep: str = ""
    border: str = ""
    border_hover: str = ""
    text: str = ""
    text_muted: str = ""
    text_disabled: str = ""
    primary_hover: str = ""
    primary_pressed: str = ""
    primary_text: str = ""
    danger_hover: str = ""
    danger_text: str = ""
    surface_hover: str = ""
    link: str = ""

    def __post_init__(self):
        # Backgrounds — very dark shades of primary
        if not self.bg:
            self.bg = darken(self.primary, 0.08)
        if not self.bg_surface:
            self.bg_surface = darken(self.primary, 0.15)
        if not self.bg_deep:
            self.bg_deep = darken(self.primary, 0.05)

        # Borders
        if not self.border:
            self.border = darken(self.primary, 0.25)
        if not self.border_hover:
            self.border_hover = darken(self.primary, 0.40)

        # Text — tinted near-white from accent, muted from primary
        if not self.text:
            self.text = lighten(self.accent, 0.88)
        if not self.text_muted:
            self.text_muted = lighten(self.primary, 0.40)
        if not self.text_disabled:
            self.text_disabled = darken(self.primary, 0.45)

        # Button states
        if not self.primary_hover:
            self.primary_hover = darken(self.primary, 0.78)
        if not self.primary_pressed:
            self.primary_pressed = darken(self.primary, 0.60)
        if not self.primary_text:
            self.primary_text = self.bg_deep

        # Danger states
        if not self.danger_hover:
            self.danger_hover = lighten(self.danger, 0.25)
        if not self.danger_text:
            self.danger_text = self.bg_deep

        # Surfaces
        if not self.surface_hover:
            self.surface_hover = darken(self.primary, 0.20)

        # Links
        if not self.link:
            self.link = lighten(self.primary, 0.35)


# ── Theme presets ─────────────────────────────────────────────────────────────

THEMES: dict[str, Theme] = {
    "grey": Theme(
        name="grey",
        # Professional neutral — steel-blue accent on cool grey base
        primary="#4a6fa5",           # steel-blue — buttons, progress bars, sliders
        secondary="#6b8cba",         # lighter steel-blue — selections, checkboxes
        accent="#1e2a38",            # dark navy — titles, emphasized labels
        danger="#b03a2e",            # muted red — cancel/destructive actions
        highlight="#4a6fa5",         # steel-blue — section headers

        # Backgrounds: clearly layered — light grey base, white surfaces
        bg="#e8e8e8",                # light grey — main background
        bg_surface="#ffffff",        # white — input fields, cards (clearly distinct from bg)
        bg_deep="#d8d8d8",           # slightly darker grey — group box backgrounds

        # Borders: neutral greys
        border="#c0c0c0",            # medium grey — default borders
        border_hover="#4a6fa5",      # steel-blue — focused/hovered borders

        # Text: near-black on light grey — excellent contrast
        text="#1a1a1a",              # near-black — primary text
        text_muted="#606060",        # dark grey — secondary/muted text
        text_disabled="#aaaaaa",     # light grey — disabled text

        # Button states: steel-blue family
        primary_hover="#3a5f95",     # darker steel-blue — hover
        primary_pressed="#2a4f85",   # deepest steel-blue — pressed
        primary_text="#ffffff",      # white — text on steel-blue buttons

        # Danger states
        danger_hover="#922b21",      # darker muted red — hover
        danger_text="#ffffff",       # white — text on danger buttons

        # Surfaces
        surface_hover="#f0f0f0",     # pale grey — surface hover

        # Links
        link="#4a6fa5",              # steel-blue — links
    ),
    "terminal": Theme(
        name="terminal",
        # Classic hacker terminal — phosphor green on near-black
        primary="#00cc00",           # terminal green — buttons, progress bars, sliders
        secondary="#007700",         # dim green — selections, checkboxes
        accent="#00ff41",            # bright phosphor green — titles, emphasized labels
        danger="#cc3300",            # red-orange — cancel/destructive actions
        highlight="#00cc00",         # terminal green — section headers

        # Backgrounds: deep blacks with visible layering
        bg="#0d0d0d",                # near-black — main background
        bg_surface="#1a1a1a",        # dark charcoal — input fields, cards (distinct from bg)
        bg_deep="#080808",           # deepest black — group box backgrounds

        # Borders: dark green grid lines
        border="#1a4d1a",            # dark green — default borders
        border_hover="#00cc00",      # terminal green — focused/hovered borders

        # Text: phosphor green family
        text="#00ff41",              # bright phosphor green — primary text
        text_muted="#00aa00",        # dimmer green — secondary/muted text
        text_disabled="#1a5c1a",     # very dim green — disabled text

        # Button states: green family
        primary_hover="#00aa00",     # dimmer green — hover
        primary_pressed="#008800",   # even dimmer — pressed
        primary_text="#0d0d0d",      # near-black — text on green buttons (high contrast)

        # Danger states
        danger_hover="#aa2200",      # darker red-orange — hover
        danger_text="#0d0d0d",       # near-black — text on danger buttons

        # Surfaces
        surface_hover="#222222",     # slightly lighter black — surface hover

        # Links
        link="#00ff41",              # bright phosphor green — links
    ),
    "pastel": Theme(
        name="pastel",
        # ── 5-color palette (your provided colors) ──
        primary="#f4acb7",           # cherry-blossom — buttons, progress bars, sliders
        secondary="#ffcad4",         # pastel-pink — selections, checked checkboxes
        accent="#9d8189",            # dusty-mauve — titles (dark on light background)
        danger="#e89aa4",            # darkened cherry-blossom — cancel/destructive actions
        highlight="#ffcad4",         # pastel-pink — section headers, decorative accents

        # ── Explicit overrides for light theme (dark theme auto-derivation won't work) ──
        # Backgrounds: alabaster-grey (main) vs powder-petal (surfaces) — DIFFERENT!
        bg="#d8e2dc",                # alabaster-grey — main background (60% of UI)
        bg_surface="#ffe5d9",        # powder-petal — input fields, cards (30% of UI, distinct from bg!)
        bg_deep="#ccd6d0",           # slightly darker alabaster-grey — deep background for group boxes

        # Borders: soft dusty-mauve tints
        border="#baa7ac",            # lightened dusty-mauve — subtle borders
        border_hover="#f4acb7",      # cherry-blossom — interactive border highlight

        # Text: dusty-mauve (darkest color) for contrast on light backgrounds
        text="#9d8189",              # dusty-mauve — main text (good contrast on alabaster-grey)
        text_muted="#b59aa2",        # lightened dusty-mauve — muted text
        text_disabled="#d4c5c9",     # very light dusty-mauve — disabled text

        # Button states: cherry-blossom variations
        primary_hover="#e89aa4",     # darkened cherry-blossom — button hover
        primary_pressed="#dc8891",   # further darkened cherry-blossom — button pressed
        primary_text="#ffffff",      # white — text on cherry-blossom buttons (high contrast)

        # Danger states
        danger_hover="#dc8891",      # further darkened cherry-blossom
        danger_text="#ffffff",       # white — text on danger buttons

        # Surface interactions
        surface_hover="#ffd9c9",     # slightly darker powder-petal — hover state for surfaces

        # Links
        link="#f4acb7",              # cherry-blossom — links
    ),
    "burgundy": Theme(
        name="burgundy",
        # ── 5-color palette (your provided colors) ──
        primary="#f26157",           # vibrant-coral — buttons, progress bars, sliders
        secondary="#f1a66a",         # sandy-brown — selections, checked checkboxes
        accent="#f7ee7f",            # banana-cream — titles, emphasized text (brightest)
        danger="#a54657",            # dusty-mauve (rose-red) — cancel/destructive actions
        highlight="#f1a66a",         # sandy-brown — section headers, decorative accents

        # ── Explicit overrides for dark theme ──
        # Backgrounds: wine-plum (main) vs lightened wine-plum (surfaces) — DIFFERENT!
        bg="#582630",                # wine-plum — main background (darkest, 60% of UI)
        bg_surface="#6b3541",        # lightened wine-plum — input fields, cards (distinct from bg!)
        bg_deep="#4a1f28",           # darker wine-plum — deep background for group boxes

        # Borders: dusty-mauve tints
        border="#a54657",            # dusty-mauve — visible borders
        border_hover="#f26157",      # vibrant-coral — interactive border highlight

        # Text: banana-cream (brightest) for contrast on dark wine-plum
        text="#f7ee7f",              # banana-cream — main text (high contrast on wine-plum)
        text_muted="#f1a66a",        # sandy-brown — muted text (warm, softer)
        text_disabled="#8b5a64",     # muted dusty-mauve — disabled text

        # Button states: vibrant-coral variations
        primary_hover="#d95549",     # darkened vibrant-coral — button hover
        primary_pressed="#c0483d",   # further darkened vibrant-coral — button pressed
        primary_text="#f7ee7f",      # banana-cream — text on coral buttons (high contrast)

        # Danger states: dusty-mauve variations
        danger_hover="#8b3a47",      # darkened dusty-mauve
        danger_text="#f7ee7f",       # banana-cream — text on danger buttons

        # Surface interactions
        surface_hover="#7d4450",     # slightly lighter wine-plum — hover state for surfaces

        # Links
        link="#f1a66a",              # sandy-brown — links (warm accent)
    ),
}

ACTIVE_THEME = "grey"


def get_theme() -> Theme:
    return THEMES[ACTIVE_THEME]


# ── QSS stylesheet generator ─────────────────────────────────────────────────

def generate_stylesheet(theme: Theme | None = None) -> str:
    t = theme or get_theme()
    return f"""
QWidget {{
    background-color: {t.bg};
    color: {t.text};
    font-family: "Menlo", "Monaco", monospace;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {t.bg};
}}

QLabel {{
    background: transparent;
    color: {t.text};
    padding: 2px;
}}

QLabel#title {{
    font-size: 20px;
    font-weight: bold;
    color: {t.accent};
    padding: 8px 0px;
}}

QLineEdit {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {t.secondary};
}}

QLineEdit:focus {{
    border: 1px solid {t.primary};
}}

QPlainTextEdit {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {t.secondary};
}}

QPlainTextEdit:focus {{
    border: 1px solid {t.primary};
}}

QComboBox {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 200px;
}}

QComboBox:focus {{
    border: 1px solid {t.primary};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    selection-background-color: {t.secondary};
}}

QSpinBox {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {t.secondary};
}}

QSpinBox:focus {{
    border: 1px solid {t.primary};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {t.bg_surface};
    border: none;
    width: 16px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {t.surface_hover};
}}

QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {t.text_muted};
    width: 0px;
    height: 0px;
}}

QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.text_muted};
    width: 0px;
    height: 0px;
}}

QPushButton {{
    background-color: {t.primary};
    color: {t.primary_text};
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {t.primary_hover};
}}

QPushButton:pressed {{
    background-color: {t.primary_pressed};
}}

QPushButton:disabled {{
    background-color: {t.border};
    color: {t.text_disabled};
}}

QPushButton#cancel_btn {{
    background-color: {t.danger};
    color: {t.danger_text};
}}

QPushButton#cancel_btn:hover {{
    background-color: {t.danger_hover};
}}

QPushButton#secondary_btn {{
    background-color: {t.border};
    color: {t.text};
}}

QPushButton#secondary_btn:hover {{
    background-color: {t.border_hover};
}}

QSlider::groove:horizontal {{
    background: {t.border};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {t.primary};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

QSlider::sub-page:horizontal {{
    background: {t.primary};
    border-radius: 3px;
}}

QProgressBar {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border};
    border-radius: 6px;
    text-align: center;
    color: {t.text};
    height: 22px;
}}

QProgressBar::chunk {{
    background-color: {t.primary};
    border-radius: 5px;
}}

QCheckBox {{
    spacing: 8px;
    color: {t.text};
    padding: 4px 0px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {t.border};
    border-radius: 4px;
    background-color: {t.bg_surface};
}}

QCheckBox::indicator:hover {{
    border-color: {t.accent};
}}

QCheckBox::indicator:checked {{
    background-color: {t.secondary};
    border-color: {t.secondary};
    image: none;
}}

QGroupBox {{
    background-color: {t.bg_deep};
    border: 1px solid {t.bg_surface};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {t.highlight};
}}

QTextEdit {{
    background-color: {t.bg_surface};
    color: {t.text};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {t.secondary};
    font-family: "Menlo", "Monaco", monospace;
    font-size: 12px;
}}

QTextEdit:focus {{
    border: 1px solid {t.primary};
}}

QPushButton#reset_inactive {{
    background-color: {t.border};
    color: {t.text_muted};
}}

QPushButton#reset_active {{
    background-color: {t.danger};
    color: {t.danger_text};
    font-weight: bold;
}}

QPushButton#reset_active:hover {{
    background-color: {t.secondary};
}}

QPushButton#collapsible_header {{
    background-color: {t.bg_deep};
    color: {t.highlight};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 10px 12px;
    font-weight: bold;
    font-size: 13px;
    text-align: left;
}}

QPushButton#collapsible_header:hover {{
    background-color: {t.surface_hover};
    border-color: {t.border_hover};
}}

QTabWidget::pane {{
    border: 1px solid {t.bg_surface};
    border-radius: 8px;
    background-color: {t.bg};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {t.bg_surface};
    color: {t.text_muted};
    border: 1px solid {t.border};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 20px;
    margin-right: 2px;
    font-weight: bold;
}}

QTabBar::tab:selected {{
    background-color: {t.bg};
    color: {t.accent};
    border-color: {t.highlight};
}}

QTabBar::tab:hover:!selected {{
    background-color: {t.border};
}}
"""
