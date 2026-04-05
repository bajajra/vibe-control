"""
Drawing helpers for Vibe Control — premium dark + neon-red palette.
"""

import pygame

# --- palette: deep black + neon red ---
COL_BG_TOP = (14, 14, 16)
COL_BG_BOT = (8, 8, 10)
COL_SURFACE = (22, 22, 26)
COL_SURFACE_HOVER = (34, 34, 40)
COL_SURFACE_RAISED = (30, 30, 36)
COL_BORDER = (48, 48, 54)
COL_BORDER_SUBTLE = (38, 38, 44)
COL_TEXT = (240, 240, 242)
COL_TEXT_MUTED = (120, 120, 130)
COL_TEXT_DIM = (80, 80, 88)
COL_ACCENT = (255, 40, 60)        # neon red
COL_ACCENT_GLOW = (180, 20, 40)
COL_ACCENT_SOFT = (255, 40, 60)   # for alpha-blended accents
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


def draw_inner_glow(surface, rect, color, radius=14, alpha=20):
    """Draw a soft inner glow that fades from top edge downward."""
    s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    fade_h = min(rect.h // 4, 30)
    for y in range(fade_h):
        t = 1.0 - (y / fade_h)
        a = int(alpha * t * t)  # quadratic falloff
        if a < 1:
            continue
        pygame.draw.line(s, (*color[:3], a), (radius, y), (rect.w - radius, y))
    surface.blit(s, rect.topleft)


def draw_card(surface, rect, radius=14, alpha=240, glow=False):
    """Draw a premium card with clean surface and subtle top edge highlight."""
    draw_rounded_rect_alpha(surface, COL_SURFACE, rect, radius=radius, alpha=alpha)
    # very subtle top edge highlight (1px line, not a band)
    edge_s = pygame.Surface((rect.w - radius * 2, 1), pygame.SRCALPHA)
    ew = edge_s.get_width()
    for x in range(ew):
        fade = min(x, ew - x) / max(ew * 0.2, 1)
        fade = min(fade, 1.0)
        edge_s.set_at((x, 0), (255, 255, 255, int(fade * 12)))
    surface.blit(edge_s, (rect.x + radius, rect.y + 1))
    # border
    pygame.draw.rect(surface, COL_BORDER_SUBTLE, rect, width=1, border_radius=radius)
    if glow:
        draw_inner_glow(surface, rect, COL_ACCENT, radius=radius, alpha=12)


def draw_frosted_panel(surface, rect, radius=12, alpha=235):
    """Draw a frosted glass panel (dark with slight translucency)."""
    s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(s, (20, 20, 24, alpha), (0, 0, rect.w, rect.h), border_radius=radius)
    # 1px top edge highlight
    ew = rect.w - radius * 2
    if ew > 0:
        for x in range(ew):
            fade = min(x, ew - x) / max(ew * 0.2, 1)
            fade = min(fade, 1.0)
            s.set_at((radius + x, 1), (255, 255, 255, int(fade * 10)))
    surface.blit(s, rect.topleft)
    pygame.draw.rect(surface, COL_BORDER, rect, width=1, border_radius=radius)


def draw_soft_divider(surface, x1, x2, y, color=None):
    """Draw a gradient divider that fades at edges."""
    if color is None:
        color = COL_BORDER_SUBTLE
    w = x2 - x1
    s = pygame.Surface((w, 1), pygame.SRCALPHA)
    for i in range(w):
        fade = min(i, w - i) / max(w * 0.15, 1)
        fade = min(fade, 1.0)
        a = int(fade * 80)
        s.set_at((i, 0), (*color[:3], a))
    surface.blit(s, (x1, y))


def draw_glow_circle(surface, center, radius, color=COL_ACCENT, intensity=60):
    """Draw a soft glow circle (for indicators, dots)."""
    s = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    cx, cy = radius * 2, radius * 2
    for r in range(radius * 2, radius, -1):
        t = (r - radius) / radius
        a = int(intensity * (1.0 - t) ** 2)
        pygame.draw.circle(s, (*color[:3], a), (cx, cy), r)
    pygame.draw.circle(s, color, (cx, cy), radius)
    surface.blit(s, (center[0] - radius * 2, center[1] - radius * 2))


def draw_pill(surface, font, text, rect, active=False, hover=False):
    if active:
        # solid accent fill, no highlight band
        pygame.draw.rect(surface, COL_ACCENT, rect, border_radius=rect.h // 2)
    else:
        bg = COL_SURFACE_HOVER if hover else COL_SURFACE
        pygame.draw.rect(surface, bg, rect, border_radius=rect.h // 2)
        pygame.draw.rect(surface, COL_BORDER_SUBTLE if not hover else COL_BORDER,
                         rect, width=1, border_radius=rect.h // 2)
    c = (255, 255, 255) if active else (COL_TEXT if hover else COL_TEXT_MUTED)
    surf = font.render(text, True, c)
    surface.blit(surf, (rect.centerx - surf.get_width() // 2,
                        rect.centery - surf.get_height() // 2))


def draw_search_bar(surface, font, rect, title="Shortcuts", subtitle=None):
    draw_frosted_panel(surface, rect, radius=12)
    t = font.render(title, True, COL_TEXT)
    surface.blit(t, (rect.x + 14, rect.y + 10))
    if subtitle:
        s = font.render(subtitle, True, COL_TEXT_MUTED)
        surface.blit(s, (rect.x + 14, rect.y + 30))


def draw_chip(surface, font, text, rect, color=COL_TEXT_MUTED, border_color=COL_BORDER,
              bg_color=None, active=False, hover=False):
    """Draw a small status chip/badge."""
    if bg_color is None:
        bg_color = (30, 30, 34)
    if active:
        bg_color = (*COL_ACCENT[:3],)
        border_color = COL_ACCENT
        color = (255, 255, 255)
    elif hover:
        bg_color = COL_SURFACE_HOVER
        border_color = COL_BORDER
        color = COL_TEXT
    draw_rounded_rect(surface, bg_color, rect, radius=rect.h // 2)
    pygame.draw.rect(surface, border_color, rect, width=1, border_radius=rect.h // 2)
    surf = font.render(text, True, color)
    surface.blit(surf, (rect.centerx - surf.get_width() // 2,
                        rect.centery - surf.get_height() // 2))


def draw_shadow(surface, rect, radius=12, offset=4, alpha=80):
    """Draw a soft drop shadow underneath a rect."""
    shadow_r = pygame.Rect(rect.x + offset, rect.y + offset, rect.w, rect.h)
    draw_rounded_rect_alpha(surface, (0, 0, 0), shadow_r, radius=radius, alpha=alpha)
