"""
Drawing helpers for Vibe Control — black + neon-red palette.
"""

import pygame

# --- palette: deep black + neon red ---
COL_BG_TOP = (14, 14, 16)
COL_BG_BOT = (8, 8, 10)
COL_SURFACE = (22, 22, 26)
COL_SURFACE_HOVER = (34, 34, 40)
COL_BORDER = (48, 48, 54)
COL_TEXT = (240, 240, 242)
COL_TEXT_MUTED = (120, 120, 130)
COL_ACCENT = (255, 40, 60)        # neon red
COL_ACCENT_GLOW = (180, 20, 40)
COL_SUCCESS = (255, 55, 70)       # red-tinted for "active" states
COL_DANGER = (255, 40, 40)


def _blend(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def draw_vertical_gradient(surface, w, h, top=COL_BG_TOP, bottom=COL_BG_BOT):
    for y in range(h):
        t = y / max(h - 1, 1)
        c = _blend(top, bottom, t)
        pygame.draw.line(surface, c, (0, y), (w, y))


def draw_rounded_rect(surface, color, rect, radius=10, width=0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def draw_rounded_rect_alpha(surface, color, rect, radius=10, alpha=255):
    s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    r = (0, 0, rect.w, rect.h)
    ca = (*color[:3], alpha) if len(color) == 3 else color
    pygame.draw.rect(s, ca, r, border_radius=radius)
    surface.blit(s, rect.topleft)


def draw_pill(surface, font, text, rect, active=False, hover=False):
    bg = COL_ACCENT if active else (COL_SURFACE_HOVER if hover else COL_SURFACE)
    border = COL_ACCENT if active else COL_BORDER
    pygame.draw.rect(surface, bg, rect, border_radius=rect.h // 2)
    pygame.draw.rect(surface, border, rect, width=1, border_radius=rect.h // 2)
    c = (255, 255, 255) if active else COL_TEXT_MUTED
    surf = font.render(text, True, c)
    surface.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))


def draw_search_bar(surface, font, rect, title="Shortcuts", subtitle=None):
    pygame.draw.rect(surface, COL_SURFACE, rect, border_radius=12)
    pygame.draw.rect(surface, COL_BORDER, rect, width=1, border_radius=12)
    t = font.render(title, True, COL_TEXT)
    surface.blit(t, (rect.x + 14, rect.y + 10))
    if subtitle:
        s = font.render(subtitle, True, COL_TEXT_MUTED)
        surface.blit(s, (rect.x + 14, rect.y + 30))
