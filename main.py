# -*- coding: utf-8 -*-
"""
SLENDERMAN: ESCAPE DEL BOSQUE
Juego de terror en Python + Pygame para Android (Pydroid 3).

Un solo archivo. Todo (arboles, personaje, Slenderman, sonidos) se genera por
codigo: no necesita imagenes, audios ni Internet.

CONTROLES (pantalla tactil):
  - Joystick virtual: toca en la mitad izquierda de la pantalla y arrastra.
  - CORRER: manten pulsado el boton grande de la derecha.
  - LUZ: enciende / apaga la linterna.
  - ABORDAR: aparece cuando estas junto al barco.
  - II: pausa.
(En PC tambien: WASD/flechas, SHIFT correr, F linterna, E interactuar.)
"""
import os
import sys
import math
import random
import array
import heapq
import asyncio

import pygame

# ----------------------------------------------------------------------------
# CONSTANTES
# ----------------------------------------------------------------------------
ANDROID = ("ANDROID_ROOT" in os.environ) and ("ANDROID_DATA" in os.environ)

WORLD_W, WORLD_H = 2800, 2200      # tamano del mapa (pixeles de mundo)
VIEW_H = 300                       # altura interna (horizontal)
VIEW_W_PORTRAIT = 260              # ancho interno (vertical)
TAU = 6.283185307179586

WALK_SPEED = 82.0
RUN_SPEED = 150.0
PLAYER_R = 6
ATTACK_R = 20.0
BOT_WALK = 80.0
BOT_RUN = 135.0

# Dificultades: velocidad de Slenderman, teletransportes, tiempo de aparicion,
# gasto de bateria/resistencia y, en el modo Slenderman, la vista y el miedo del bot.
DIFFS = [
    ("FÁCIL", dict(spd=0.82, tp=1.7, delay=1.5, bat=0.5, stam=0.75, bot_spd=0.85, bot_sight=260, bot_fear=200)),
    ("NORMAL", dict(spd=1.0, tp=1.0, delay=1.0, bat=0.75, stam=1.0, bot_spd=1.0, bot_sight=340, bot_fear=260)),
    ("DIFÍCIL", dict(spd=1.12, tp=0.75, delay=0.7, bat=1.0, stam=1.2, bot_spd=1.1, bot_sight=420, bot_fear=300)),
    ("PESADILLA", dict(spd=1.25, tp=0.55, delay=0.5, bat=1.3, stam=1.4, bot_spd=1.2, bot_sight=520, bot_fear=340)),
]

PHRASES = [
    "El bosque guarda silencio... hasta que vuelvas.",
    "Quien escapa del bosque, nunca deja de oírlo.",
    "No mires atrás: él siempre sabe dónde estás.",
    "Hasta la próxima noche, sobreviviente.",
    "La oscuridad espera. Paciente. Alta. Silenciosa.",
]

INTRO = [
    ("Una noche sin luna...", 3.0),
    ("Despiertas solo en un bosque que no recuerdas.", 3.6),
    ("Dicen que algo alto y silencioso vigila a quienes se pierden aquí.", 4.2),
    ("Hay un lago, un muelle y un barco.", 3.2),
    ("Escapa antes de que te encuentre.", 3.4),
]
TITLE_T = 3.6

# Estados de Slenderman
OCULTO, OBSERVANDO, DESAPARECIENDO, ACECHANDO, PERSIGUIENDO, ATAQUE = range(6)


# ----------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------
def I(v):
    return int(round(v))


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def in_rect(r, x, y):
    return r.left <= x < r.right and r.top <= y < r.bottom


def seg_dist(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0.0, 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


_fonts = {}
_txt = {}


def get_font(size):
    size = max(8, int(size))
    f = _fonts.get(size)
    if f is None:
        f = pygame.font.Font(None, size)
        _fonts[size] = f
    return f


def text_surf(t, size, col):
    k = (t, int(size), col)
    s = _txt.get(k)
    if s is None:
        if len(_txt) > 250:
            _txt.clear()
        s = get_font(size).render(t, True, col)
        _txt[k] = s
    return s


def wrap_text(text, size, maxw):
    f = get_font(size)
    lines = []
    cur = ''
    for wd in text.split(' '):
        t = (cur + ' ' + wd).strip()
        if f.size(t)[0] <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(surf, text, size, col, cx, cy, maxw, alpha=None):
    lines = wrap_text(text, size, maxw)
    lh = size * 0.9
    y = cy - lh * (len(lines) - 1) / 2.0
    for ln in lines:
        draw_text(surf, ln, size, col, center=(cx, y), alpha=alpha)
        y += lh


def draw_text(surf, t, size, col, center=None, topleft=None, shadow=True, alpha=None):
    s = text_surf(t, size, col)
    sh = text_surf(t, size, (0, 0, 0)) if shadow else None
    if alpha is not None and alpha < 255:
        s = s.copy()
        s.set_alpha(int(alpha))
        if sh is not None:
            sh = sh.copy()
            sh.set_alpha(int(alpha))
    r = s.get_rect()
    if center is not None:
        r.center = (I(center[0]), I(center[1]))
    elif topleft is not None:
        r.topleft = (I(topleft[0]), I(topleft[1]))
    if sh is not None:
        off = max(1, int(size * 0.05))
        surf.blit(sh, (r.x + off, r.y + off))
    surf.blit(s, r)
    return r


# ----------------------------------------------------------------------------
# DIBUJO PROCEDURAL
# ----------------------------------------------------------------------------
def draw_slender(surf, cx, by, h, frame=0):
    """Dibuja a Slenderman: muy alto y delgado, traje negro, cabeza blanca sin rostro."""
    lw = max(2, I(h * 0.03))
    suit = (14, 14, 18)
    edge = (52, 52, 66)
    sy = by - h * 0.80
    hip = by - h * 0.46
    sway = (0.0, 0.03, -0.03)[frame % 3] * h
    # piernas largas
    for sgn in (-1, 1):
        off = sway * sgn * 1.3
        hx = cx + sgn * h * 0.03
        kx = hx + off * 0.6
        ky = by - h * 0.24
        fx = hx + off
        for col, w in ((edge, lw + 2), (suit, lw)):
            pygame.draw.line(surf, col, (I(hx), I(hip)), (I(kx), I(ky)), w)
            pygame.draw.line(surf, col, (I(kx), I(ky)), (I(fx), I(by)), w)
    # brazos larguisimos (llegan a las rodillas)
    for sgn in (-1, 1):
        p0 = (cx + sgn * h * 0.085, sy + h * 0.015)
        p1 = (cx + sgn * h * 0.125 + sway * sgn, by - h * 0.50)
        p2 = (cx + sgn * h * 0.10 - sway * sgn, by - h * 0.24)
        for col, w in ((edge, lw + 2), (suit, lw)):
            pygame.draw.line(surf, col, (I(p0[0]), I(p0[1])), (I(p1[0]), I(p1[1])), w)
            pygame.draw.line(surf, col, (I(p1[0]), I(p1[1])), (I(p2[0]), I(p2[1])), w)
    # torso
    torso = [(I(cx - h * 0.085), I(sy)), (I(cx + h * 0.085), I(sy)),
             (I(cx + h * 0.06), I(hip)), (I(cx - h * 0.06), I(hip))]
    pygame.draw.polygon(surf, suit, torso)
    pygame.draw.polygon(surf, edge, torso, 1)
    # camisa blanca y corbata roja
    pygame.draw.polygon(surf, (205, 205, 210),
                        [(I(cx - h * 0.022), I(sy)), (I(cx + h * 0.022), I(sy)), (I(cx), I(sy + h * 0.13))])
    pygame.draw.line(surf, (120, 12, 12), (I(cx), I(sy + h * 0.02)), (I(cx), I(sy + h * 0.20)),
                     max(1, I(h * 0.014)))
    # cuello y cabeza blanca sin rostro
    pygame.draw.line(surf, (225, 225, 228), (I(cx), I(sy)), (I(cx), I(sy - h * 0.05)), max(2, I(h * 0.022)))
    hw = h * 0.058
    hh = h * 0.085
    top = by - h + 1
    pygame.draw.ellipse(surf, (240, 240, 242), (I(cx - hw), I(top), I(hw * 2), I(hh * 2)))


def draw_pine(surf, x, by, size, col):
    tw = max(2, size // 14)
    pygame.draw.rect(surf, col, (x - tw // 2, by - size // 5, tw, size // 5))
    for i in range(4):
        top = by - size + I(i * size * 0.17)
        bot = top + I(size * 0.36)
        half = I(size * (0.10 + 0.045 * i))
        pygame.draw.polygon(surf, col, [(x, top), (x - half, bot), (x + half, bot)])


def make_pine(w, h, rnd):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    pygame.draw.rect(s, (26, 19, 14), (cx - 3, h - 36, 6, 36))
    for i in range(4):
        top = I(h * 0.02 + i * h * 0.17)
        bot = I(h * 0.36 + i * h * 0.17)
        half = I(w * (0.22 + 0.07 * i))
        col = (8 + i * 2 + rnd.randint(0, 3), 26 + i * 4, 17 + i * 2)
        pygame.draw.polygon(s, col, [(cx, top), (cx - half, bot), (cx + half, bot)])
        lt = (col[0] + 6, col[1] + 12, col[2] + 8)
        pygame.draw.polygon(s, lt, [(cx, top), (cx + half, bot), (cx + half // 2, bot)])
    return s


def make_dead(w, h, rnd):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    pygame.draw.polygon(s, (30, 26, 25), [(cx - 5, h), (cx + 5, h), (cx + 2, 8), (cx - 2, 8)])
    for _ in range(7):
        y = rnd.randint(18, h - 30)
        d = rnd.choice((-1, 1))
        ln = rnd.randint(10, 22)
        ex = cx + d * ln
        ey = y - rnd.randint(8, 18)
        pygame.draw.line(s, (30, 26, 25), (cx, y), (ex, ey), 2)
        pygame.draw.line(s, (30, 26, 25), (ex, ey), (ex + d * rnd.randint(4, 9), ey - rnd.randint(4, 9)), 1)
    return s


def make_rock(w, h, rnd):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pts = []
    n = 9
    for i in range(n):
        a = TAU * i / n
        rx = w * 0.5 * rnd.uniform(0.82, 1.0)
        ry = h * 0.5 * rnd.uniform(0.82, 1.0)
        pts.append((I(w / 2 + math.cos(a) * rx), I(h / 2 + math.sin(a) * ry)))
    pygame.draw.polygon(s, (46, 48, 54), pts)
    top = [p for p in pts if p[1] < h * 0.55]
    if len(top) >= 3:
        pygame.draw.polygon(s, (66, 69, 78), top)
    pygame.draw.polygon(s, (28, 29, 33), pts, 1)
    return s


def make_cabin(rnd):
    s = pygame.Surface((124, 112), pygame.SRCALPHA)
    pygame.draw.rect(s, (46, 31, 21), (14, 54, 96, 54))
    for x in range(14, 110, 8):
        pygame.draw.line(s, (30, 20, 14), (x, 54), (x, 108))
    pygame.draw.polygon(s, (30, 22, 20), [(2, 58), (62, 8), (122, 58)])
    pygame.draw.polygon(s, (46, 36, 32), [(62, 8), (122, 58), (100, 58)])
    pygame.draw.rect(s, (34, 24, 22), (88, 16, 10, 22))
    pygame.draw.rect(s, (12, 8, 6), (54, 74, 18, 34))
    pygame.draw.rect(s, (120, 96, 50), (26, 70, 16, 14))
    pygame.draw.line(s, (30, 20, 14), (34, 70), (34, 84), 1)
    pygame.draw.line(s, (30, 20, 14), (26, 77), (42, 77), 1)
    pygame.draw.rect(s, (24, 16, 11), (14, 54, 96, 54), 2)
    return s


def make_tent(rnd):
    s = pygame.Surface((80, 56), pygame.SRCALPHA)
    pygame.draw.polygon(s, (44, 58, 42), [(4, 52), (40, 6), (76, 52)])
    pygame.draw.polygon(s, (58, 74, 54), [(40, 6), (76, 52), (58, 52)])
    pygame.draw.polygon(s, (10, 12, 10), [(30, 52), (40, 22), (50, 52)])
    pygame.draw.polygon(s, (22, 30, 22), [(4, 52), (40, 6), (76, 52)], 1)
    return s


def make_firebase():
    s = pygame.Surface((34, 16), pygame.SRCALPHA)
    for a in range(8):
        ang = TAU * a / 8
        pygame.draw.circle(s, (70, 72, 78), (17 + I(math.cos(ang) * 12), 9 + I(math.sin(ang) * 4)), 3)
    pygame.draw.line(s, (60, 38, 22), (9, 11), (25, 7), 3)
    pygame.draw.line(s, (60, 38, 22), (9, 7), (25, 11), 3)
    return s


def make_torch_item():
    s = pygame.Surface((12, 28), pygame.SRCALPHA)
    pygame.draw.line(s, (96, 62, 30), (6, 26), (6, 12), 3)
    pygame.draw.polygon(s, (255, 150, 40), [(6, 0), (1, 11), (11, 11)])
    pygame.draw.polygon(s, (255, 228, 120), [(6, 4), (3, 11), (9, 11)])
    return s


def make_bat_item():
    s = pygame.Surface((10, 14), pygame.SRCALPHA)
    pygame.draw.rect(s, (40, 170, 80), (1, 3, 8, 10))
    pygame.draw.rect(s, (215, 215, 215), (3, 0, 4, 3))
    pygame.draw.rect(s, (230, 230, 80), (1, 7, 8, 2))
    return s


def make_bush(w, h, rnd):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cols = [(10, 28, 18), (13, 36, 22), (17, 46, 27)]
    for _ in range(7):
        r = rnd.randint(h // 4, h // 2)
        x = rnd.randint(r, max(r, w - r))
        y = rnd.randint(h // 2, max(h // 2, h - r))
        pygame.draw.circle(s, rnd.choice(cols), (x, y), r)
    return s


class Art:
    """Todos los graficos pre-renderizados (se crean una sola vez)."""

    def __init__(self):
        rnd = random.Random(11)
        # arboles
        self.trees = [make_pine(44, 110, rnd), make_pine(52, 124, rnd), make_pine(38, 96, rnd),
                      make_pine(60, 140, rnd), make_dead(42, 110, rnd), make_dead(46, 100, rnd)]
        self.tree_r = [9, 10, 8, 11, 7, 7]
        self.rocks = [make_rock(34, 24, rnd), make_rock(26, 18, rnd), make_rock(44, 30, rnd)]
        self.rock_r = [12, 9, 15]
        self.bushes = [make_bush(32, 22, rnd), make_bush(26, 18, rnd), make_bush(36, 24, rnd)]
        self.bush_r = [10, 8, 11]
        self.cabin = [make_cabin(rnd)]
        self.tent = [make_tent(rnd)]
        self.firebase = [make_firebase()]
        self.sprites = [self.trees, self.rocks, self.bushes, self.cabin, self.tent, self.firebase]
        self.radii = [self.tree_r, self.rock_r, self.bush_r]
        self.torch_item = make_torch_item()
        self.bat_item = make_bat_item()
        # Slenderman (3 fotogramas) + version tenue (se ve entre la oscuridad)
        self.sl = []
        for f in range(3):
            s = pygame.Surface((46, 112), pygame.SRCALPHA)
            draw_slender(s, 23, 110, 104, f)
            self.sl.append(s)
        # suelo
        g = pygame.Surface((256, 256))
        g.fill((11, 21, 16))
        for _ in range(420):
            x = rnd.randint(0, 255)
            y = rnd.randint(0, 255)
            c = rnd.choice(((9, 18, 13), (13, 25, 18), (15, 28, 20), (8, 16, 15)))
            pygame.draw.rect(g, c, (x, y, rnd.randint(4, 14), rnd.randint(3, 8)))
        for _ in range(90):
            x = rnd.randint(0, 255)
            y = rnd.randint(0, 255)
            pygame.draw.line(g, (20, 40, 26), (x, y), (x + rnd.randint(-2, 2), y - rnd.randint(3, 7)), 1)
        self.ground = g
        # niebla
        self.fog = []
        for fw, fh in ((380, 220), (320, 190), (440, 240)):
            s = pygame.Surface((fw, fh), pygame.SRCALPHA)
            steps = 12
            for k in range(steps):
                f = k / float(steps)
                w2 = I(fw * (1 - f * 0.85))
                h2 = I(fh * (1 - f * 0.85))
                a = I(34 * (k + 1) / steps)
                pygame.draw.ellipse(s, (90, 105, 125, a), ((fw - w2) // 2, (fh - h2) // 2, w2, h2))
            self.fog.append(s)
        # brillo calido de la lampara del muelle
        gl = pygame.Surface((140, 140), pygame.SRCALPHA)
        for k in range(14):
            r = I(70 * (1 - k / 14.0))
            pygame.draw.circle(gl, (255, 185, 100, I(120 * (k + 1) / 14.0)), (70, 70), max(1, r))
        self.glow = gl
        self.glow_small = pygame.transform.smoothscale(gl, (64, 64))
        self.glow_big = pygame.transform.smoothscale(gl, (220, 220))
        # ruido de interferencia
        self.noise = []
        for _ in range(4):
            ns = pygame.Surface((128, 72))
            for y in range(72):
                for x in range(128):
                    v = rnd.randint(0, 255)
                    ns.set_at((x, y), (v, v, v))
            self.noise.append(ns)
        # mascaras de luz (linterna)
        self.make_lights()

    def make_lights(self):
        R = 150
        size = R * 2
        base = pygame.Surface((size, size), pygame.SRCALPHA)
        half = math.radians(31)
        layers = 14
        for k in range(layers):
            f = 1.0 - k / float(layers)
            r = R * f
            ha = half * (0.72 + 0.28 * f)
            alpha = I(238 * ((k + 1) / float(layers)) ** 0.75)
            pts = [(R, R)]
            for j in range(13):
                a = -ha + 2 * ha * j / 12.0
                pts.append((I(R + r * math.cos(a)), I(R + r * math.sin(a))))
            pygame.draw.polygon(base, (0, 0, 0, alpha), pts)
        small = pygame.transform.smoothscale(base, (size // 3, size // 3))
        base = pygame.transform.smoothscale(small, (size, size))
        self.cones = []
        self.n_cones = 24
        for i in range(self.n_cones):
            self.cones.append(pygame.transform.rotate(base, -i * 360.0 / self.n_cones))
        # halos alrededor del jugador
        self.halo_big = self._halo(62, 225)
        self.halo_small = self._halo(30, 150)
        self.halo_torch = self._halo(105, 235)

    def _halo(self, R, amax):
        s = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        n = 10
        for k in range(n):
            r = I(R * (1 - k / float(n)))
            pygame.draw.circle(s, (0, 0, 0, I(amax * (k + 1) / float(n))), (R, R), max(1, r))
        return s


# ----------------------------------------------------------------------------
# AUDIO (todo generado por codigo)
# ----------------------------------------------------------------------------
def _fade(buf, n):
    L = len(buf)
    n = min(n, L // 2)
    for i in range(n):
        g = i / float(n)
        buf[i] *= g
        buf[L - 1 - i] *= g


def _norm(buf, peak):
    m = 1e-9
    for v in buf:
        a = v if v >= 0 else -v
        if a > m:
            m = a
    k = peak / m
    return [int(v * k) for v in buf]


def gen_wind(rate):
    n = int(rate * 4)
    r = random.random
    a = b = 0.0
    buf = []
    for i in range(n):
        x = r() * 2 - 1
        a += 0.10 * (x - a)
        b += 0.08 * (a - b)
        ph = TAU * i / n
        env = (0.6 + 0.4 * math.sin(ph * 2 + 1.0)) * (0.75 + 0.25 * math.sin(ph * 3))
        buf.append(b * env)
    _fade(buf, 600)
    return _norm(buf, 9000)


def gen_drone(rate):
    n = int(rate * 6)
    tab = [math.sin(TAU * j / n) for j in range(n)]
    tones = ((330, 0.9), (350, 0.7), (495, 0.45), (700, 0.30), (165, 0.8))  # ciclos por bucle
    buf = []
    for i in range(n):
        v = 0.0
        for k, g in tones:
            v += g * tab[(i * k) % n]
        buf.append(v * (0.65 + 0.35 * tab[(i * 2) % n]))
    return _norm(buf, 8500)


def gen_near(rate):
    n = int(rate * 2)
    tab = [math.sin(TAU * j / n) for j in range(n)]
    r = random.random
    lp = 0.0
    buf = []
    for i in range(n):
        lp += 0.5 * ((r() * 2 - 1) - lp)
        am = 0.5 + 0.5 * tab[(i * 7) % n]
        tone = tab[(i * 3400) % n] * 0.22 + tab[(i * 3580) % n] * 0.22 + tab[(i * 88) % n] * 0.6
        buf.append(lp * 0.5 * (0.3 + 0.7 * am) + tone * am)
    _fade(buf, 300)
    return _norm(buf, 12000)


def gen_sting(rate):
    n = int(rate * 0.7)
    ph = 0.0
    buf = []
    for i in range(n):
        t = i / float(n)
        f = 1400 * (1 - t) + 180 * t
        ph += TAU * f / rate
        env = (1 - t) ** 1.5
        v = (math.sin(ph) * 0.5 + (random.random() * 2 - 1) * 0.5 + math.sin(ph * 1.5) * 0.3) * env
        if i < 200:
            v *= i / 200.0
        buf.append(v)
    return _norm(buf, 20000)


def gen_scream(rate):
    n = int(rate * 1.5)
    p1 = p2 = 0.0
    buf = []
    for i in range(n):
        t = i / float(n)
        f = 600 + 700 * math.sin(t * 9) + 500 * t
        p1 += f / rate
        p2 += f * 1.51 / rate
        saw = 2 * (p1 % 1.0) - 1
        saw2 = 2 * (p2 % 1.0) - 1
        env = min(1.0, i / 300.0) * (1 - t ** 3)
        v = (saw * 0.5 + saw2 * 0.4 + (random.random() * 2 - 1) * 0.6) * env * 2.2
        buf.append(max(-1.0, min(1.0, v)))
    return _norm(buf, 31000)


def gen_step(rate):
    n = int(rate * 0.09)
    lp = 0.0
    buf = []
    for i in range(n):
        lp += 0.25 * ((random.random() * 2 - 1) - lp)
        buf.append(lp * (1 - i / float(n)) ** 2)
    return _norm(buf, 9000)


def gen_creak(rate):
    n = int(rate * 0.8)
    ph = 0.0
    buf = []
    for i in range(n):
        t = i / float(n)
        f = 220 - 90 * t + 12 * math.sin(t * 60)
        ph += f / rate
        saw = 2 * (ph % 1.0) - 1
        env = math.sin(math.pi * t) ** 1.5
        buf.append((saw * 0.6 + (random.random() * 2 - 1) * 0.15) * env)
    return _norm(buf, 9000)


def gen_whisper(rate):
    n = int(rate * 1.1)
    lp = hp = 0.0
    buf = []
    for i in range(n):
        t = i / float(n)
        x = random.random() * 2 - 1
        lp += 0.55 * (x - lp)
        hp += 0.12 * (lp - hp)
        band = lp - hp
        am = 0.5 + 0.5 * math.sin(TAU * 6.5 * t + 2 * math.sin(TAU * 1.7 * t))
        env = math.sin(math.pi * t)
        buf.append(band * am * env)
    return _norm(buf, 11000)


class Audio:
    def __init__(self):
        self.ok = False
        self.master = 0.7
        self.near = 0.0
        self.snd = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 1024)
            self.rate, fmt, self.chn = pygame.mixer.get_init()
            if fmt == -16 and self.chn in (1, 2):
                pygame.mixer.set_num_channels(14)
                pygame.mixer.set_reserved(3)
                self.ok = True
        except Exception:
            self.ok = False

    def _sound(self, buf):
        a = array.array('h', buf)
        if self.chn == 2:
            b = array.array('h', bytes(len(a) * 4))
            b[0::2] = a
            b[1::2] = a
            a = b
        return pygame.mixer.Sound(buffer=a.tobytes())

    def build(self):
        if not self.ok:
            return
        try:
            r = self.rate
            self.snd['wind'] = self._sound(gen_wind(r))
            self.snd['drone'] = self._sound(gen_drone(r))
            self.snd['near'] = self._sound(gen_near(r))
            self.snd['sting'] = self._sound(gen_sting(r))
            self.snd['scream'] = self._sound(gen_scream(r))
            self.snd['step'] = self._sound(gen_step(r))
            self.snd['creak'] = self._sound(gen_creak(r))
            self.snd['whisper'] = self._sound(gen_whisper(r))
        except Exception:
            self.ok = False

    def play(self, name, vol=1.0):
        if not self.ok:
            return
        try:
            s = self.snd.get(name)
            if s is not None:
                s.set_volume(clamp(vol * self.master, 0.0, 1.0))
                s.play()
        except Exception:
            pass

    def ambient(self, on):
        if not self.ok:
            return
        try:
            if on:
                pygame.mixer.Channel(0).play(self.snd['wind'], loops=-1)
                pygame.mixer.Channel(1).play(self.snd['drone'], loops=-1)
                pygame.mixer.Channel(2).play(self.snd['near'], loops=-1)
                self.near = 0.0
                self.apply()
            else:
                for i in range(3):
                    pygame.mixer.Channel(i).stop()
        except Exception:
            pass

    def apply(self):
        if not self.ok:
            return
        try:
            pygame.mixer.Channel(0).set_volume(0.55 * self.master)
            pygame.mixer.Channel(1).set_volume(0.40 * self.master)
            pygame.mixer.Channel(2).set_volume(clamp(self.near * 0.8 * self.master, 0.0, 1.0))
        except Exception:
            pass

    def set_near(self, lvl):
        self.near = clamp(lvl, 0.0, 1.0)
        if self.ok:
            try:
                pygame.mixer.Channel(2).set_volume(clamp(self.near * 0.8 * self.master, 0.0, 1.0))
            except Exception:
                pass

    def set_master(self, v):
        self.master = clamp(v, 0.0, 1.0)
        self.apply()


# ----------------------------------------------------------------------------
# MUNDO: bosque, lago, muelle, colisiones
# ----------------------------------------------------------------------------
class World:
    CELL = 96

    def __init__(self, art):
        rnd = random.Random()
        self.art = art
        self.W, self.H = WORLD_W, WORLD_H
        self.dir = rnd.choice((1, -1))          # lago al este (1) o al oeste (-1)
        self.ph1 = rnd.uniform(0, TAU)
        self.ph2 = rnd.uniform(0, TAU)
        self.dock_y = rnd.randint(700, 1500)
        sx = self.shore_x(self.dock_y)
        if self.dir > 0:
            self.dock = pygame.Rect(I(sx - 110), self.dock_y - 22, 380, 44)
            self.dock_in = self.dock.left
            self.dock_out = self.dock.right
        else:
            self.dock = pygame.Rect(I(sx + 110 - 380), self.dock_y - 22, 380, 44)
            self.dock_in = self.dock.right
            self.dock_out = self.dock.left
        self.dock_zone = self.dock.inflate(60, 60)
        self.boat_x0 = self.dock_out + self.dir * 38
        self.boat_y = self.dock_y
        sxs = rnd.randint(220, 380)
        self.start = (sxs if self.dir > 0 else self.W - sxs, rnd.randint(600, 1600))
        self.grid = {}
        self.obs = []
        self.fires = []
        self.items = []
        self.clear = []
        self.hotspots = []
        self._pass = {}
        self.n_bats = 0
        self.paths = self._make_paths(rnd)
        self._features(rnd)
        self._populate(rnd)
        self.ripples = []
        for _ in range(160):
            y = rnd.uniform(0, self.H)
            x = self.shore_x(y) + self.dir * rnd.uniform(25, 600)
            self.ripples.append((x, y, rnd.uniform(0, TAU)))
        self.fog = []
        for _ in range(26):
            self.fog.append((rnd.uniform(0, self.W), rnd.uniform(0, self.H), rnd.randint(0, 2), rnd.uniform(3, 9)))

    def shore_x(self, y):
        s = 2260 + 45 * math.sin(y / 150.0 + self.ph1) + 22 * math.sin(y / 61.0 + self.ph2)
        return s if self.dir > 0 else self.W - s

    def in_water(self, x, y, pr=0):
        sx = self.shore_x(y)
        return (x + pr > sx) if self.dir > 0 else (x - pr < sx)

    def _make_paths(self, rnd):
        d = self.dir
        W = self.W

        def X(x):
            return x if d > 0 else W - x

        def mk(a, b, wob, steps=16):
            pts = []
            ph = rnd.uniform(0, TAU)
            fr = rnd.uniform(1.0, 2.2)
            for i in range(steps + 1):
                t = i / float(steps)
                x = a[0] + (b[0] - a[0]) * t
                y = a[1] + (b[1] - a[1]) * t
                y += math.sin(t * math.pi * fr * 2 + ph) * wob * math.sin(t * math.pi)
                x += math.cos(t * math.pi * fr * 1.5 + ph) * wob * 0.4 * math.sin(t * math.pi)
                pts.append((x, clamp(y, 70, self.H - 70)))
            return pts
        P = []
        P.append(mk(self.start, (X(1500), rnd.randint(500, 1700)), 220))
        P.append(mk((X(rnd.randint(900, 1300)), rnd.randint(150, 350)), (self.dock_in - d * 30, self.dock_y), 240))
        P.append(mk((X(rnd.randint(500, 900)), rnd.randint(1900, 2050)), (X(rnd.randint(1500, 1900)), rnd.randint(700, 1300)), 200))
        P.append(mk((X(1000), 1000), (X(1900), rnd.randint(1500, 1900)), 180))
        self.path_grid = {}
        for pts in P:
            for i in range(len(pts) - 1):
                ax, ay = pts[i]
                bx, by = pts[i + 1]
                n = max(1, int(math.hypot(bx - ax, by - ay) / 12))
                for j in range(n + 1):
                    qx = ax + (bx - ax) * j / n
                    qy = ay + (by - ay) * j / n
                    self.path_grid.setdefault((int(qx // 48), int(qy // 48)), []).append((qx, qy))
        return P

    def _near_path(self, x, y, d):
        cx = int(x // 48)
        cy = int(y // 48)
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for q in self.path_grid.get((gx, gy), ()):
                    if (q[0] - x) ** 2 + (q[1] - y) ** 2 < d * d:
                        return True
        return False

    def _insert(self, o):
        self.obs.append(o)
        self.grid.setdefault((int(o[0] // self.CELL), int(o[1] // self.CELL)), []).append(o)

    def _add(self, x, y, kind, var):
        self._insert((x, y, self.art.radii[kind][var], kind, var))

    def _add_raw(self, x, y, r, kind, var):
        self._insert((x, y, r, kind, var))

    def _free(self, x, y, d):
        cx = int(x // self.CELL)
        cy = int(y // self.CELL)
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for o in self.grid.get((gx, gy), ()):
                    if (o[0] - x) ** 2 + (o[1] - y) ** 2 < d * d:
                        return False
        return True

    def _features(self, rnd):
        """Cabana, campamento y objetos opcionales (distintos en cada partida)."""
        W, H = self.W, self.H
        sx, sy = self.start
        spots = []

        def spot(rad, min_start):
            for _ in range(500):
                x = rnd.uniform(260, W - 260)
                y = rnd.uniform(260, H - 260)
                if self.in_water(x, y, rad + 70):
                    continue
                if math.hypot(x - sx, y - sy) < min_start:
                    continue
                if in_rect(self.dock.inflate(700, 500), x, y):
                    continue
                ok = True
                for a, b, d in spots:
                    if math.hypot(x - a, y - b) < d + rad:
                        ok = False
                        break
                if not ok:
                    continue
                spots.append((x, y, rad))
                self.clear.append((x, y, rad))
                return (x, y)
            return None
        torch_pos = None
        bats = []
        c = spot(100, 600)
        if c:
            cx, cy = c
            for dx in (-36, -12, 12, 36):
                self._add_raw(cx + dx, cy - 8, 14, -1, 0)
            self._add_raw(cx, cy, 1, 3, 0)
            torch_pos = (cx - 26, cy + 26)
            self.hotspots.append((cx, cy))
        k = spot(85, 450)
        if k:
            kx, ky = k
            self._add_raw(kx - 14, ky - 6, 12, -1, 0)
            self._add_raw(kx + 14, ky - 6, 12, -1, 0)
            self._add_raw(kx, ky, 1, 4, 0)
            fx, fy = kx + 62, ky + 16
            self._add_raw(fx, fy, 9, 5, 0)
            self.fires.append((fx, fy))
            self._add(fx - 30, fy + 8, 1, 1)
            self._add(fx + 30, fy + 6, 1, 1)
            bats.append((kx - 34, ky + 30))
            self.hotspots.append((kx, ky))
        if torch_pos is None:
            torch_pos = spot(30, 300) or (sx + self.dir * 140, sy)
        while len(bats) < 3:
            p = spot(30, 300)
            if p is None:
                break
            bats.append(p)
        self.items.append(['torch', torch_pos[0], torch_pos[1], False])
        for b in bats:
            self.items.append(['bat', b[0], b[1], False])
        self.n_bats = len(bats)
        # puntos de acecho extra repartidos por el bosque
        for _ in range(120):
            if len(self.hotspots) >= 5:
                break
            x = rnd.uniform(300, W - 300)
            y = rnd.uniform(300, H - 300)
            if self.in_water(x, y, 150) or math.hypot(x - sx, y - sy) < 500:
                continue
            if any(math.hypot(x - a, y - b) < 450 for a, b in self.hotspots):
                continue
            self.hotspots.append((x, y))

    def _populate(self, rnd):
        W, H = self.W, self.H
        x = 24
        while x < W - 24:
            for by in (20 + rnd.randint(0, 12), H - 20 - rnd.randint(0, 12)):
                if not self.in_water(x, by, 50):
                    self._add(x + rnd.randint(-6, 6), by, 0, rnd.randint(0, 5))
            x += 36
        y = 24
        while y < H - 24:
            for bx in (20 + rnd.randint(0, 12), W - 20 - rnd.randint(0, 12)):
                if not self.in_water(bx, y, 50):
                    self._add(bx, y + rnd.randint(-6, 6), 0, rnd.randint(0, 5))
            y += 36
        sx, sy = self.start
        zone = self.dock.inflate(300, 200)

        def place(count, kind, nvar, spacing, tries_max):
            n = 0
            tries = 0
            while n < count and tries < tries_max:
                tries += 1
                x = rnd.uniform(50, W - 50)
                y = rnd.uniform(50, H - 50)
                if self.in_water(x, y, 45):
                    continue
                if (x - sx) ** 2 + (y - sy) ** 2 < 95 * 95:
                    continue
                if in_rect(zone, x, y):
                    continue
                bad = False
                for a, b, r in self.clear:
                    if (x - a) ** 2 + (y - b) ** 2 < r * r:
                        bad = True
                        break
                if bad:
                    continue
                if not self._free(x, y, spacing):
                    continue
                if self._near_path(x, y, 34):
                    continue
                self._add(x, y, kind, rnd.randint(0, nvar - 1))
                n += 1
        place(rnd.randint(850, 1100), 0, 6, 36, 16000)
        place(rnd.randint(55, 95), 1, 3, 40, 3000)
        place(rnd.randint(60, 100), 2, 3, 36, 3000)

    def _cell_ok(self, cx, cy):
        k = (cx, cy)
        v = self._pass.get(k)
        if v is None:
            v = not self.blocked(cx * 24 + 12, cy * 24 + 12, 7)
            self._pass[k] = v
        return v

    def find_path(self, sx, sy, gx, gy, avoid=None, limit=9000):
        """A* sobre una rejilla de 24 px. avoid=(x, y, radio) penaliza una zona."""
        C = 24
        cols = self.W // C
        rows = self.H // C
        start = (int(sx // C), int(sy // C))
        goal = (int(gx // C), int(gy // C))
        openl = [(0.0, 0.0, start)]
        g = {start: 0.0}
        came = {}
        n = 0
        dirs = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))
        while openl and n < limit:
            f, gc, cur = heapq.heappop(openl)
            if gc > g.get(cur, 1e9) + 1e-9:
                continue
            n += 1
            if cur == goal:
                path = []
                while cur in came:
                    path.append((cur[0] * C + 12, cur[1] * C + 12))
                    cur = came[cur]
                path.reverse()
                return path
            for dx, dy, st in dirs:
                nx = cur[0] + dx
                ny = cur[1] + dy
                if nx < 0 or ny < 0 or nx >= cols or ny >= rows:
                    continue
                nb = (nx, ny)
                if nb != goal and not self._cell_ok(nx, ny):
                    continue
                if dx and dy and not (self._cell_ok(cur[0] + dx, cur[1]) and self._cell_ok(cur[0], cur[1] + dy)):
                    continue
                pen = 0.0
                if avoid:
                    dd = math.hypot(nx * C + 12 - avoid[0], ny * C + 12 - avoid[1])
                    if dd < avoid[2]:
                        pen = (avoid[2] - dd) / avoid[2] * 4.0
                ng = gc + st + pen
                if ng < g.get(nb, 1e9):
                    g[nb] = ng
                    came[nb] = cur
                    hx = abs(nx - goal[0])
                    hy = abs(ny - goal[1])
                    h = (hx + hy) - 0.586 * min(hx, hy)
                    heapq.heappush(openl, (ng + 1.2 * h, ng, nb))
        return None

    def collides(self, x, y, pr):
        cx = int(x // self.CELL)
        cy = int(y // self.CELL)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                lst = self.grid.get((gx, gy))
                if lst:
                    for o in lst:
                        dx = x - o[0]
                        dy = y - o[1]
                        rr = o[2] + pr
                        if dx * dx + dy * dy < rr * rr:
                            return True
        return False

    def blocked(self, x, y, pr=PLAYER_R):
        if x < pr + 8 or y < pr + 8 or x > self.W - pr - 8 or y > self.H - pr - 8:
            return True
        if self.in_water(x, y, pr):
            if not in_rect(self.dock, x, y):
                return True
        return self.collides(x, y, pr)

    def slender_blocked(self, x, y):
        if x < 20 or y < 20 or x > self.W - 20 or y > self.H - 20:
            return True
        if self.in_water(x, y, 0) and not in_rect(self.dock_zone, x, y):
            return True
        return False

    def visible(self, cx, cy, vw, vh):
        out = []
        x0 = int((cx - 80) // self.CELL)
        x1 = int((cx + vw + 80) // self.CELL)
        y0 = int((cy - 10) // self.CELL)
        y1 = int((cy + vh + 140) // self.CELL)
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                lst = self.grid.get((gx, gy))
                if lst:
                    out.extend(lst)
        return out


# ----------------------------------------------------------------------------
# ENTIDADES
# ----------------------------------------------------------------------------
class Player:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.face = 0.0
        self.stamina = 100.0
        self.exhausted = False
        self.running = False
        self.moving = False
        self.battery = 100.0
        self.flash_on = True
        self.walk = 0.0
        self.step_d = 0.0


class Slender:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.state = OCULTO
        self.timer = random.uniform(14, 22)
        self.alpha = 0.0
        self.seen_t = 0.0
        self.watch = 4.0
        self.chase_t = 0.0
        self.anim = 0.0
        self.moving = False
        self.noise_t = 3.0
        self.hold = 0.0
        self.tp_cd = random.uniform(10, 15)
        self.freeze = 0.0


class Bot(Player):
    """Jugador controlado por la IA (modo Slenderman)."""

    def __init__(self, x, y):
        Player.__init__(self, x, y)
        self.path = None
        self.pi = 0
        self.replan_t = 0.0
        self.wait = 3.5
        self.stuck_t = 0.0
        self.nudge_t = 0.0
        self.nudge_a = 0.0
        self.known = False          # aun no sabe donde esta el muelle
        self.visited = set()
        self.target = None


# ----------------------------------------------------------------------------
# JUEGO
# ----------------------------------------------------------------------------
class Game:
    def __init__(self):
        try:
            pygame.mixer.pre_init(22050, -16, 1, 1024)
        except Exception:
            pass
        pygame.init()
        pygame.display.set_caption("SLENDERMAN: ESCAPE DEL BOSQUE")
        if ANDROID:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
        self.sw, self.sh = self.screen.get_size()
        self.clock = pygame.time.Clock()
        self.show_loading()
        self.audio = Audio()
        self.audio.build()
        self.art = Art()
        self.fast_scale = True
        self.mode = 'intro'
        self.ui = []
        self.t = 0.0
        self.finger_seen = False
        self.joy_id = None
        self.joy_c = (0, 0)
        self.joy_p = (0, 0)
        self.joy_v = (0.0, 0.0)
        self.run_ids = set()
        self.slider_id = None
        self.menu_glitch = 0
        self.world = None
        self.msgs = []
        self.smode = False
        self.play_mode = 'play'
        self.tp_cd = 0.0
        self.s_run = False
        self.sen = 100.0
        self.sen_ex = False
        self.goal = (0, 0)
        self.newly = False
        self.win_t = 0.0
        self.note_until = 0.0
        self.unlocked = self.load_unlock()
        self.diff_i = 1
        self.pending = 'survival'
        self.intro_t = 0.0
        self.intro_flags = set()
        self.bye_t = 0.0
        self.bye_phrase = PHRASES[0]
        self.win_phrase = PHRASES[0]
        self.layout()
        self.audio.ambient(True)

    # ------------------------------------------------------------------ pantalla
    @property
    def dk(self):
        return DIFFS[self.diff_i][1]

    def show_loading(self):
        self.screen.fill((0, 0, 0))
        draw_text(self.screen, "CARGANDO...", max(20, self.sh // 10), (170, 170, 170),
                  center=(self.sw // 2, self.sh // 2))
        pygame.display.flip()

    def layout(self):
        self.screen = pygame.display.get_surface() or self.screen
        self.sw, self.sh = self.screen.get_size()
        sw, sh = self.sw, self.sh
        u = min(sw, sh)
        self.u = u
        if sw >= sh:
            self.vh = VIEW_H
            self.vw = int(clamp(round(VIEW_H * sw / float(sh)), 360, 800))
        else:
            self.vw = VIEW_W_PORTRAIT
            self.vh = int(clamp(round(VIEW_W_PORTRAIT * sh / float(sw)), 360, 680))
        self.view = pygame.Surface((self.vw, self.vh)).convert()
        self.dark = pygame.Surface((self.vw, self.vh), pygame.SRCALPHA).convert_alpha()
        self.fade_surf = pygame.Surface((self.vw, self.vh))
        self.fade_surf.fill((0, 0, 0))
        self.flash_surf = pygame.Surface((self.vw, self.vh))
        self.flash_surf.fill((255, 255, 255))
        self.shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        self.shade.fill((0, 0, 0, 170))
        self.fs = {'s': I(u * 0.045), 'm': I(u * 0.07), 'l': I(u * 0.12), 'xl': I(u * 0.17)}
        # botones tactiles (cx, cy, radio)
        self.joy_r = u * 0.17
        self.joy_def = (u * 0.24, sh - u * 0.26)
        self.btn = {
            'run': (sw - u * 0.16, sh - u * 0.20, u * 0.125),
            'flash': (sw - u * 0.16, sh - u * 0.46, u * 0.10),
            'act': (sw - u * 0.43, sh - u * 0.22, u * 0.115),
            'pause': (sw - u * 0.075, u * 0.075, u * 0.052),
            'tpf': (sw - u * 0.16, sh - u * 0.46, u * 0.105),
            'tpb': (sw - u * 0.43, sh - u * 0.22, u * 0.115),
        }
        self.btn_img = {}
        for k, label in (('run', 'CORRER'), ('flash', 'LUZ'), ('act', 'ABORDAR')):
            r = I(self.btn[k][2])
            self.btn_img[k] = (self._circle_btn(r, label, 55), self._circle_btn(r, label, 130))
        for k, label in (('tpf', 'ADELANTE'), ('tpb', 'ATRÁS')):
            r = I(self.btn[k][2])
            self.btn_img[k] = (self._circle_btn(r, label, 55), self._circle_btn(r, label, 130))
        self.btn_img['pause'] = (self._pause_btn(I(self.btn['pause'][2]), 70), self._pause_btn(I(self.btn['pause'][2]), 130))
        jr = I(self.joy_r)
        self.joy_base = pygame.Surface((jr * 2, jr * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.joy_base, (255, 255, 255, 28), (jr, jr), jr)
        pygame.draw.circle(self.joy_base, (255, 255, 255, 90), (jr, jr), jr, 3)
        kr = I(self.joy_r * 0.42)
        self.joy_knob = pygame.Surface((kr * 2, kr * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.joy_knob, (255, 255, 255, 110), (kr, kr), kr)
        pygame.draw.circle(self.joy_knob, (255, 255, 255, 170), (kr, kr), kr, 2)
        self.menu_bg = self.make_menu_bg(sw, sh)

    def _circle_btn(self, r, label, a):
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, a), (r, r), r)
        pygame.draw.circle(s, (230, 230, 230, 170), (r, r), r, 3)
        t = text_surf(label, I(r * 0.42), (255, 255, 255))
        s.blit(t, t.get_rect(center=(r, r)))
        return s

    def _pause_btn(self, r, a):
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, a), (r, r), r)
        pygame.draw.circle(s, (230, 230, 230, 170), (r, r), r, 2)
        bw = max(3, I(r * 0.22))
        pygame.draw.rect(s, (255, 255, 255, 230), (r - bw * 2, r - r // 2, bw, r))
        pygame.draw.rect(s, (255, 255, 255, 230), (r + bw, r - r // 2, bw, r))
        return s

    def make_menu_bg(self, sw, sh):
        s = pygame.Surface((sw, sh))
        for y in range(0, sh, 3):
            t = y / float(sh)
            pygame.draw.rect(s, (I(lerp(5, 2, t)), I(lerp(9, 5, t)), I(lerp(22, 10, t))), (0, y, sw, 3))
        mx, my, mr = I(sw * 0.84), I(sh * 0.17), max(6, I(sh * 0.07))
        glow = pygame.Surface((mr * 8, mr * 8), pygame.SRCALPHA)
        for k in range(10):
            pygame.draw.circle(glow, (120, 140, 180, 6 + k * 2), (mr * 4, mr * 4), max(1, I(mr * 4 * (1 - k / 10.0))))
        s.blit(glow, (mx - mr * 4, my - mr * 4))
        pygame.draw.circle(s, (200, 208, 222), (mx, my), mr)
        rnd = random.Random(3)
        layers = [(0.58, (7, 13, 19), 26, 0.34), (0.72, (4, 9, 12), 22, 0.44), (0.88, (2, 5, 6), 14, 0.60)]
        for li, (byf, col, cnt, sz) in enumerate(layers):
            base_y = I(sh * byf)
            for _ in range(cnt):
                x = rnd.randint(-20, sw + 20)
                draw_pine(s, x, base_y + rnd.randint(-6, 10), I(sh * sz * rnd.uniform(0.8, 1.2)), col)
            pygame.draw.rect(s, col, (0, base_y, sw, sh - base_y))
            if li == 0:
                hx = I(sw * (0.2 if sw > sh else 0.24))
                hy = I(sh * 0.74)
                hh = I(min(sh * 0.52, sw * 1.0))
                g2 = pygame.Surface((hh // 2, hh // 2), pygame.SRCALPHA)
                for k in range(8):
                    pygame.draw.circle(g2, (200, 210, 230, 5 + k * 3), (hh // 4, hh // 4), max(1, I(hh / 4.0 * (1 - k / 8.0))))
                s.blit(g2, (hx - hh // 4, hy - hh + 4 - hh // 8))
                draw_slender(s, hx, hy, hh, 0)
        fog = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for fy in (0.55, 0.7, 0.85):
            pygame.draw.ellipse(fog, (70, 85, 100, 22), (-sw // 4, I(sh * fy) - sh // 10, I(sw * 1.5), sh // 5))
        s.blit(fog, (0, 0))
        return s.convert()

    # ------------------------------------------------------------------ partida
    def new_game(self):
        self.smode = False
        self.play_mode = 'play'
        self.world = World(self.art)
        w = self.world
        self.p = Player(w.start[0], w.start[1])
        self.sl = Slender()
        self.sl.timer *= self.dk['delay']
        self.sl.tp_cd *= self.dk['tp']
        self.play_t = 0.0
        self.dock_reached = False
        self.flash = 0.0
        self.shake_t = 0.0
        self.shake_amp = 0.0
        self.flick_t = 0.0
        self.flick_off = False
        self.low_bat_msg = False
        self.glitch = 0.0
        self.cam = (0, 0)
        self.msgs = []
        self.has_torch = False
        self.bats = 0
        self.hot_done = set()
        self.last_spawn = (-9999.0, -9999.0)
        self.light_hint = False
        self.add_msg("Dificultad: %s" % DIFFS[self.diff_i][0], 3.0)
        self.add_msg("Estás solo en el bosque... no recuerdas cómo llegaste.", 5.0)
        self.add_msg("Encuentra el muelle del lago y escapa en el barco.", 5.0)
        self.add_msg("Opcional: una cabaña o un campamento pueden tener algo útil.", 5.0)
        self.joy_id = None
        self.joy_v = (0.0, 0.0)
        self.run_ids = set()
        self.mode = 'play'
        self.esc_t = 0.0
        self.boat_x = w.boat_x0
        self.audio.ambient(True)

    def _save_paths(self):
        out = []
        try:
            out.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "slenderman_save.txt"))
        except Exception:
            pass
        out.append(os.path.join(os.path.expanduser("~"), "slenderman_save.txt"))
        return out

    def load_unlock(self):
        for pth in self._save_paths():
            try:
                with open(pth) as f:
                    if f.read().strip() == "1":
                        return True
            except Exception:
                pass
        return False

    def save_unlock(self):
        for pth in self._save_paths():
            try:
                with open(pth, "w") as f:
                    f.write("1")
                return
            except Exception:
                pass

    def to_menu(self):
        self.mode = 'menu'
        self.audio.ambient(True)

    def add_msg(self, text, dur):
        self.msgs.append([text, dur, dur])

    def agg(self):
        return clamp(self.play_t / 240.0, 0.0, 1.0) * 0.6 + (0.4 if self.dock_reached else 0.0)

    def near_boat(self):
        w = self.world
        return self.mode == 'play' and math.hypot(self.p.x - w.boat_x0, self.p.y - w.boat_y) < 95

    def light_off(self):
        p = self.p
        return (not p.flash_on) and p.battery > 0

    def toggle_flash(self):
        p = self.p
        if p.battery <= 0:
            p.flash_on = False
            self.add_msg("La batería se agotó...", 2.5)
            return
        p.flash_on = not p.flash_on
        if not p.flash_on and not self.light_hint:
            self.light_hint = True
            self.add_msg("Sin luz, Slenderman desaparece... pero tú tampoco verás nada.", 4.5)

    # ------------------------------------------------------------------ entrada
    def pointer_down(self, fid, x, y):
        m = self.mode
        if m == 'intro':
            self.end_intro()
            return
        if m == 'bye':
            if self.bye_t > 1.0:
                self.finish_bye()
            return
        if m == 'play':
            b = self.btn
            if self._hit(b['pause'], x, y):
                self.play_mode = 'play'
                self.mode = 'pause'
                self.joy_id = None
                self.joy_v = (0.0, 0.0)
                self.run_ids = set()
                return
            if self._hit(b['run'], x, y):
                self.run_ids.add(fid)
                return
            if self._hit(b['flash'], x, y):
                self.toggle_flash()
                return
            if self.near_boat() and self._hit(b['act'], x, y):
                self.begin_escape()
                return
            if x < self.sw * 0.55 and self.joy_id is None:
                self.joy_id = fid
                self.joy_c = (x, y)
                self.joy_p = (x, y)
                self.joy_v = (0.0, 0.0)
        elif m == 'splay':
            b = self.btn
            if self._hit(b['pause'], x, y):
                self.play_mode = 'splay'
                self.mode = 'pause'
                self.joy_id = None
                self.joy_v = (0.0, 0.0)
                self.run_ids = set()
                return
            if self._hit(b['run'], x, y):
                self.run_ids.add(fid)
                return
            if self._hit(b['tpf'], x, y):
                self.tp_player(True)
                return
            if self._hit(b['tpb'], x, y):
                self.tp_player(False)
                return
            if x < self.sw * 0.55 and self.joy_id is None:
                self.joy_id = fid
                self.joy_c = (x, y)
                self.joy_p = (x, y)
                self.joy_v = (0.0, 0.0)
        elif m in ('menu', 'options', 'diff', 'pause', 'over', 'win', 'send'):
            if m == 'options' and self._slider_hit(x, y):
                self.slider_id = fid
                self._set_slider(x)
                return
            for r, cb in reversed(self.ui):
                if r.collidepoint(x, y):
                    cb()
                    return

    def pointer_move(self, fid, x, y):
        if fid == self.joy_id:
            cx, cy = self.joy_c
            dx = x - cx
            dy = y - cy
            d = math.hypot(dx, dy)
            R = self.joy_r
            if d > R:
                self.joy_p = (cx + dx / d * R, cy + dy / d * R)
            else:
                self.joy_p = (x, y)
            mag = min(1.0, d / R)
            if mag < 0.18 or d == 0:
                self.joy_v = (0.0, 0.0)
            else:
                self.joy_v = (dx / d * mag, dy / d * mag)
        if fid == self.slider_id:
            self._set_slider(x)

    def pointer_up(self, fid):
        if fid == self.joy_id:
            self.joy_id = None
            self.joy_v = (0.0, 0.0)
        self.run_ids.discard(fid)
        if fid == self.slider_id:
            self.slider_id = None

    def _hit(self, c, x, y):
        return math.hypot(x - c[0], y - c[1]) <= c[2] * 1.15

    def _slider_rect(self):
        w = self.sw * (0.5 if self.sw > self.sh else 0.75)
        return pygame.Rect(I(self.sw / 2 - w / 2), I(self.sh * 0.46), I(w), max(6, I(self.sh * 0.03)))

    def _slider_hit(self, x, y):
        return self._slider_rect().inflate(30, I(self.sh * 0.12)).collidepoint(x, y)

    def _set_slider(self, x):
        r = self._slider_rect()
        self.audio.set_master(clamp((x - r.left) / float(r.width), 0.0, 1.0))

    def handle(self, e):
        t = e.type
        FD = getattr(pygame, 'FINGERDOWN', -1)
        FM = getattr(pygame, 'FINGERMOTION', -1)
        FU = getattr(pygame, 'FINGERUP', -1)
        if t == pygame.QUIT:
            self.quit()
        elif t == FD or t == FM or t == FU:
            self.finger_seen = True
            fid = getattr(e, 'finger_id', 0)
            x = e.x * self.sw
            y = e.y * self.sh
            if t == FD:
                self.pointer_down(fid, x, y)
            elif t == FM:
                self.pointer_move(fid, x, y)
            else:
                self.pointer_up(fid)
        elif t == pygame.MOUSEBUTTONDOWN:
            if not self.finger_seen and not getattr(e, 'touch', False) and e.button == 1:
                self.pointer_down(-1, e.pos[0], e.pos[1])
        elif t == pygame.MOUSEMOTION:
            if not self.finger_seen and not getattr(e, 'touch', False) and e.buttons[0]:
                self.pointer_move(-1, e.pos[0], e.pos[1])
        elif t == pygame.MOUSEBUTTONUP:
            if not self.finger_seen and not getattr(e, 'touch', False):
                self.pointer_up(-1)
        elif t == pygame.KEYDOWN:
            if self.mode == 'intro':
                self.end_intro()
                return
            back = getattr(pygame, 'K_AC_BACK', -999)
            if e.key == pygame.K_ESCAPE or e.key == back:
                if self.mode in ('play', 'splay'):
                    self.play_mode = self.mode
                    self.mode = 'pause'
                elif self.mode == 'pause':
                    self.mode = self.play_mode
                elif self.mode in ('options', 'diff'):
                    self.mode = 'menu'
            elif self.mode == 'play':
                if e.key == pygame.K_f:
                    self.toggle_flash()
                elif e.key == pygame.K_e and self.near_boat():
                    self.begin_escape()
            elif self.mode == 'splay':
                if e.key == pygame.K_f:
                    self.tp_player(True)
                elif e.key == pygame.K_e:
                    self.tp_player(False)
        elif t == getattr(pygame, 'VIDEORESIZE', -1):
            pass

    def move_vec(self):
        vx, vy = self.joy_v
        try:
            k = pygame.key.get_pressed()
            kx = (1 if (k[pygame.K_d] or k[pygame.K_RIGHT]) else 0) - (1 if (k[pygame.K_a] or k[pygame.K_LEFT]) else 0)
            ky = (1 if (k[pygame.K_s] or k[pygame.K_DOWN]) else 0) - (1 if (k[pygame.K_w] or k[pygame.K_UP]) else 0)
            if kx or ky:
                vx, vy = float(kx), float(ky)
        except Exception:
            pass
        return vx, vy

    def run_pressed(self):
        if self.run_ids:
            return True
        try:
            k = pygame.key.get_pressed()
            return bool(k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT])
        except Exception:
            return False

    def quit(self):
        pygame.quit()
        sys.exit()

    # ------------------------------------------------------------------ actualizacion
    def update_player(self, dt):
        p = self.p
        w = self.world
        mx, my = self.move_vec()
        mag = math.hypot(mx, my)
        p.moving = mag > 0.12
        can_run = p.stamina > 0 and not p.exhausted
        p.running = bool(self.run_pressed() and p.moving and can_run)
        if p.running:
            p.stamina -= 24.0 * self.dk['stam'] * dt
            if p.stamina <= 0:
                p.stamina = 0.0
                p.exhausted = True
        else:
            p.stamina = min(100.0, p.stamina + (12.0 if p.moving else 20.0) * dt)
            if p.exhausted and p.stamina > 25:
                p.exhausted = False
        if p.moving:
            mag = min(1.0, mag)
            speed = (RUN_SPEED if p.running else WALK_SPEED) * max(0.45, mag)
            ux = mx / math.hypot(mx, my)
            uy = my / math.hypot(mx, my)
            nx = p.x + ux * speed * dt
            if not w.blocked(nx, p.y):
                p.x = nx
            ny = p.y + uy * speed * dt
            if not w.blocked(p.x, ny):
                p.y = ny
            target = math.atan2(uy, ux)
            d = (target - p.face + math.pi) % TAU - math.pi
            p.face += d * min(1.0, dt * 10.0)
            p.walk += speed * dt * 0.12
            p.step_d += speed * dt
            if p.step_d > 46:
                p.step_d = 0.0
                self.audio.play('step', 0.5 if p.running else 0.25)
        if p.flash_on and p.battery > 0:
            p.battery = max(0.0, p.battery - self.dk['bat'] * dt)
            if p.battery <= 0:
                self.add_msg("La batería se agotó. Casi no ves nada...", 4.0)
            elif p.battery < 20 and not self.low_bat_msg:
                self.low_bat_msg = True
                self.add_msg("La batería de la linterna se está agotando...", 3.5)
        # parpadeo con poca bateria
        if p.flash_on and 0 < p.battery < 22:
            self.flick_t -= dt
            if self.flick_t <= 0:
                self.flick_off = random.random() < 0.35
                self.flick_t = random.uniform(0.05, 0.35)
        else:
            self.flick_off = False
        # llegada al muelle
        for it in w.items:
            if not it[3] and math.hypot(p.x - it[1], p.y - it[2]) < 26:
                it[3] = True
                self.audio.play('step', 0.6)
                if it[0] == 'torch':
                    self.has_torch = True
                    self.add_msg("¡Encontraste una antorcha! Ahora ves mejor a tu alrededor.", 4.5)
                else:
                    self.bats += 1
                    p.battery = min(100.0, p.battery + 40.0)
                    p.flash_on = True
                    self.low_bat_msg = False
                    self.add_msg("Pilas encontradas (%d/%d). La linterna se recarga." % (self.bats, w.n_bats), 4.0)
        if not self.dock_reached and in_rect(w.dock, p.x, p.y) and w.dir * (p.x - w.dock_in) > 40:
            self.on_dock_reached()

    def on_dock_reached(self):
        self.dock_reached = True
        self.msgs = []
        self.add_msg("\u00abHas encontrado el muelle... pero algo te ha seguido\u00bb", 5.0)
        self.add_msg("Camina hasta el barco.", 4.0)
        self.audio.play('sting', 0.8)
        self.flash = 0.4
        s = self.sl
        if s.state != OCULTO and s.state != DESAPARECIENDO:
            s.state = DESAPARECIENDO
        s.hold = 5.0
        if s.state == OCULTO:
            s.timer = 5.0

    def slender_speed(self, chase):
        p = self.p
        w = self.world
        agg = self.agg()
        near_dock = clamp(1.0 - math.hypot(p.x - w.dock_in, p.y - w.dock_y) / 800.0, 0.0, 1.0)
        ramp = clamp(self.play_t / 300.0, 0.0, 1.0)      # cada vez mas rapido con el tiempo
        if chase:
            base = 108.0 + 16.0 * agg + 22.0 * ramp + (14.0 if p.running else 0.0)
        else:
            base = 42.0 + 20.0 * agg + 12.0 * ramp + (22.0 if p.running else 0.0)
        base *= 1.0 + 0.2 * near_dock + (0.1 if self.dock_reached else 0.0)
        base *= self.dk['spd']
        return min(base, (146.0 if chase else 78.0) * self.dk['spd'])

    def slender_move(self, speed, dt):
        s = self.sl
        p = self.p
        w = self.world
        tx, ty = p.x, p.y
        if in_rect(w.dock_zone, p.x, p.y) and not in_rect(w.dock_zone, s.x, s.y):
            tx, ty = w.dock_in, w.dock_y
        dx = tx - s.x
        dy = ty - s.y
        d = math.hypot(dx, dy)
        if d < 1:
            return
        nx = s.x + dx / d * speed * dt
        ny = s.y + dy / d * speed * dt
        if w.slender_blocked(nx, ny):
            if not w.slender_blocked(nx, s.y):
                ny = s.y
            elif not w.slender_blocked(s.x, ny):
                nx = s.x
            else:
                return
        s.x, s.y = nx, ny
        s.moving = True
        s.anim += dt * 7.0

    def slender_teleport(self, agg):
        """Se teletransporta detras o delante del jugador (con un instante de pausa para reaccionar)."""
        s = self.sl
        p = self.p
        w = self.world
        ahead = random.random() < 0.45
        sign = 1.0 if ahead else -1.0
        for _ in range(16):
            dist = random.uniform(120, 150) if ahead else random.uniform(80, 110)
            a = p.face + random.uniform(-0.5, 0.5)
            x = p.x + sign * math.cos(a) * dist
            y = p.y + sign * math.sin(a) * dist
            if w.blocked(x, y, 8):
                continue
            s.x, s.y = x, y
            s.alpha = 255.0
            s.freeze = 0.7 if ahead else 0.9
            s.tp_cd = random.uniform(11, 17) * (1.0 - 0.4 * agg) * self.dk['tp']
            self.audio.play('sting', 0.8)
            self.flash = 0.4
            self.shake_t = 0.3
            return True
        s.tp_cd = 2.0
        return False

    def hot_event(self):
        """Punto de acecho: al acercarte a la cabana, el campamento u otros lugares, te sigue."""
        s = self.sl
        if s.state == OBSERVANDO:
            s.state = ACECHANDO
            s.timer = random.uniform(8, 13)
        elif s.state == OCULTO:
            if self.spawn_slender(self.agg()):
                s.state = ACECHANDO
                s.timer = random.uniform(8, 13)
                s.alpha = 255.0

    def spawn_slender(self, agg):
        s = self.sl
        p = self.p
        w = self.world
        for _ in range(50):
            m = random.random()
            if m < 0.4:
                dx = random.uniform(-self.vw * 0.5 + 40, self.vw * 0.5 - 40)
                dy = random.uniform(-self.vh * 0.5 + 25, self.vh * 0.5 - 5)
            elif m < 0.75 or not w.hotspots:
                a = random.uniform(0, TAU)
                r = random.uniform(240, 430)
                dx = math.cos(a) * r
                dy = math.sin(a) * r
            else:
                hx, hy = random.choice(w.hotspots)
                a = random.uniform(0, TAU)
                r = random.uniform(40, 130)
                dx = hx + math.cos(a) * r - p.x
                dy = hy + math.sin(a) * r - p.y
            dd = math.hypot(dx, dy)
            if dd < 170 or dd > 440:
                continue
            x = p.x + dx
            y = p.y + dy
            if math.hypot(x - self.last_spawn[0], y - self.last_spawn[1]) < 200:
                continue
            if w.blocked(x, y, 10) or in_rect(w.dock.inflate(30, 30), x, y):
                continue
            s.x, s.y = x, y
            self.last_spawn = (x, y)
            s.state = OBSERVANDO
            s.alpha = 0.0
            s.seen_t = 0.0
            s.watch = random.uniform(2.8, 4.8) * (1.0 - 0.25 * agg)
            s.noise_t = random.uniform(1.0, 3.0)
            camx, camy = self.cam
            sx = x - camx
            sy = y - camy
            if -8 < sx < self.vw + 8 and 10 < sy < self.vh + 70:
                self.audio.play('sting', 0.7)
                self.flash = 0.45
                self.shake_t = 0.35
            return True
        s.timer = 1.5
        return False

    def vanish(self):
        self.sl.state = DESAPARECIENDO

    def start_chase(self):
        s = self.sl
        s.state = PERSIGUIENDO
        s.chase_t = 0.0
        s.alpha = 255.0
        self.audio.play('sting', 0.9)
        self.flash = 0.35
        self.shake_t = 0.4

    def update_slender(self, dt):
        s = self.sl
        p = self.p
        d = math.hypot(s.x - p.x, s.y - p.y)
        agg = self.agg()
        camx, camy = self.cam
        sx = s.x - camx
        sy = s.y - camy
        on_screen = (-8 < sx < self.vw + 8) and (10 < sy < self.vh + 70)
        chase_ok = self.dock_reached or self.play_t > 20
        trig = 150 + 70 * agg + (55 if self.dock_reached else 0)
        s.moving = False
        lo = self.light_off()
        if lo and s.state in (OBSERVANDO, ACECHANDO, PERSIGUIENDO):
            s.state = DESAPARECIENDO          # al apagar la linterna desaparece
        if (not lo) and self.play_t > 12 and s.state in (OCULTO, OBSERVANDO):
            for i, (hx, hy) in enumerate(self.world.hotspots):
                if i not in self.hot_done and math.hypot(p.x - hx, p.y - hy) < 190:
                    self.hot_done.add(i)
                    self.hot_event()
                    break
        st = s.state
        if st == OCULTO:
            s.alpha = 0.0
            if not lo:
                s.timer -= dt
            if s.timer <= 0:
                self.spawn_slender(agg)
        elif st == OBSERVANDO:
            s.alpha = min(255.0, s.alpha + 1200 * dt)
            s.seen_t += dt if on_screen else dt * 0.25
            if chase_ok and d < trig:
                self.start_chase()
            elif d < 110:
                self.vanish()
            elif s.seen_t >= s.watch:
                r = random.random()
                pst = 0.45 + 0.35 * agg + (0.2 if self.dock_reached else 0.0)
                if chase_ok and r < 0.25 + 0.3 * agg:
                    self.start_chase()
                elif chase_ok and r < pst:
                    s.state = ACECHANDO
                    s.timer = random.uniform(7, 12)
                else:
                    self.vanish()
        elif st == ACECHANDO:
            s.alpha = 255.0
            s.timer -= dt
            s.tp_cd -= dt
            if s.freeze > 0:
                s.freeze -= dt
            elif d < ATTACK_R:
                s.state = ATAQUE
                self.begin_jump()
                return
            elif s.tp_cd <= 0 and d > 190:
                self.slender_teleport(agg)
            elif d < trig * 0.8:
                self.start_chase()
            elif s.timer <= 0:
                self.vanish()
            else:
                self.slender_move(self.slender_speed(False), dt)
        elif st == PERSIGUIENDO:
            s.alpha = 255.0
            s.chase_t += dt
            s.tp_cd -= dt
            if s.freeze > 0:
                s.freeze -= dt
            elif d < ATTACK_R:
                s.state = ATAQUE
                self.begin_jump()
                return
            elif s.tp_cd <= 0 and d > 170 and chase_ok:
                self.slender_teleport(agg)
            elif (s.chase_t > 13 and not self.dock_reached) or d > 470:
                self.vanish()
            else:
                self.slender_move(self.slender_speed(True), dt)
        elif st == DESAPARECIENDO:
            s.alpha -= 1600 * dt
            if s.alpha <= 0:
                s.alpha = 0.0
                s.state = OCULTO
                base = random.uniform(5, 10) * (1.0 - 0.55 * agg) * self.dk['delay']
                if self.dock_reached:
                    base = min(base, 6.5)
                s.timer = max(base, s.hold)
                s.hold = 0.0
        # sonidos y efectos segun la cercania
        if s.state in (OBSERVANDO, ACECHANDO, PERSIGUIENDO) and s.alpha > 30:
            lvl = clamp(1.0 - d / 330.0, 0.0, 1.0) ** 1.2
            self.glitch = clamp(1.0 - d / 240.0, 0.0, 1.0)
            s.noise_t -= dt
            if s.noise_t <= 0:
                self.audio.play(random.choice(('creak', 'whisper')), 0.5)
                s.noise_t = random.uniform(2.5, 6.0)
        else:
            lvl = 0.0
            self.glitch = 0.0
        self.audio.set_near(lvl)
        self.shake_amp = max(self.glitch * 2.5, 3.0 if self.shake_t > 0 else 0.0)

    def update_play(self, dt):
        self.play_t += dt
        self.update_player(dt)
        self.update_slender(dt)
        self.tick_common(dt)

    def tick_common(self, dt):
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt * 1.6)
        if self.shake_t > 0:
            self.shake_t -= dt
        if self.msgs:
            self.msgs[0][1] -= dt
            if self.msgs[0][1] <= 0:
                self.msgs.pop(0)

    # ------------------------------------------------------------------ escape
    def begin_escape(self):
        w = self.world
        self.mode = 'escape'
        self.esc_t = 0.0
        self.boat_x = w.boat_x0
        self.msgs = []
        self.joy_id = None
        self.run_ids = set()
        s = self.sl
        s.x = w.dock_out - w.dir * 30
        s.y = w.dock_y
        s.state = OBSERVANDO
        s.alpha = 255.0
        self.glitch = 0.35
        self.audio.play('sting', 0.8)
        self.audio.set_near(0.45)

    def update_escape(self, dt):
        self.esc_t += dt
        w = self.world
        p = self.p
        self.boat_x += w.dir * 14.0 * dt
        p.x = self.boat_x - 4 * w.dir
        p.y = w.boat_y + 4
        p.moving = False
        self.cam = self._camera(0, 0)
        self.shake_amp = 1.0
        self.tick_common(dt)
        if self.esc_t > 9.5:
            self.mode = 'win'
            self.win_t = 0.0
            self.win_phrase = random.choice(PHRASES)
            self.newly = not self.unlocked
            if not self.unlocked:
                self.unlocked = True
                self.save_unlock()
            self.audio.set_near(0.0)

    # ------------------------------------------------------------------ susto final
    def begin_jump(self):
        self.mode = 'jump'
        self.jt = 0.0
        self.audio.ambient(False)
        self.audio.play('scream', 1.0)
        self.flash = 1.0
        self.joy_id = None
        self.run_ids = set()

    # ------------------------------------------------------------------ bucle
    async def run(self):
        try:
            while True:
                dt = min(self.clock.tick(50) / 1000.0, 0.05)
                self.t += dt
                scr = pygame.display.get_surface()
                if scr is not None and scr.get_size() != (self.sw, self.sh):
                    self.layout()
                for e in pygame.event.get():
                    self.handle(e)
                m = self.mode
                if m == 'play':
                    self.update_play(dt)
                elif m == 'escape':
                    self.update_escape(dt)
                elif m == 'splay':
                    self.update_splay(dt)
                elif m == 'intro':
                    self.intro_t += dt
                    if self.intro_t > sum(d for _, d in INTRO) + TITLE_T:
                        self.end_intro()
                elif m == 'bye':
                    self.bye_t += dt
                    if self.bye_t > 5.0:
                        self.finish_bye()
                elif m == 'jump':
                    self.jt += dt
                    self.shake_amp = 8.0
                    if self.jt > 2.4:
                        self.mode = 'over'
                elif m == 'win':
                    self.win_t += dt
                self.draw()
                pygame.display.flip()
                await asyncio.sleep(0)
        finally:
            pygame.quit()

    # ------------------------------------------------------------------ dibujo
    def _camera(self, ox, oy):
        w = self.world
        p = self.sl if self.smode else self.p
        cx = clamp(p.x - self.vw / 2.0 + ox, 0, w.W - self.vw)
        cy = clamp(p.y - self.vh / 2.0 - 10 + oy, 0, w.H - self.vh)
        return int(cx), int(cy)

    def draw(self):
        m = self.mode
        self.ui = []
        if m == 'play' or m == 'pause' or m == 'splay':
            self.draw_game()
            self.draw_hud()
            if m == 'pause':
                self.screen.blit(self.shade, (0, 0))
                draw_text(self.screen, "PAUSA", self.fs['xl'], (220, 220, 220), center=(self.sw / 2, self.sh * 0.26))
                self.ui_button("CONTINUAR", self.sw / 2, self.sh * 0.5, lambda: self._set_mode(self.play_mode))
                self.ui_button("MENÚ PRINCIPAL", self.sw / 2, self.sh * 0.69, self.to_menu)
        elif m == 'escape':
            self.draw_game()
        elif m == 'win':
            self.screen.fill((0, 0, 0))
            draw_wrapped(self.screen, "HAS SOBREVIVIDO... POR AHORA", self.fs['l'], (200, 30, 30),
                         self.sw / 2, self.sh * 0.34, self.sw * 0.92)
            draw_wrapped(self.screen, self.win_phrase, I(self.u * 0.05), (150, 150, 150), self.sw / 2, self.sh * 0.405, self.sw * 0.88)
            extra = (1 if self.has_torch else 0) + self.bats
            draw_text(self.screen, "Objetivos opcionales: %d/%d" % (extra, 1 + self.world.n_bats), self.fs['m'],
                      (170, 170, 170), center=(self.sw / 2, self.sh * 0.47))
            if self.newly:
                draw_text(self.screen, "¡MODO SLENDERMAN DESBLOQUEADO!", self.fs['m'], (240, 200, 90),
                          center=(self.sw / 2, self.sh * 0.545))
            if self.win_t > 2.5:
                self.ui_button("JUGAR DE NUEVO", self.sw / 2, self.sh * 0.65, self.new_game)
                self.ui_button("MODO SLENDERMAN", self.sw / 2, self.sh * 0.79, self.new_slender_game)
                self.ui_button("MENÚ PRINCIPAL", self.sw / 2, self.sh * 0.93, self.to_menu)
        elif m == 'jump':
            if self.jt < 0.4:
                self.draw_game(extra_shake=6.0)
            else:
                self.draw_jump_face(self.jt - 0.4)
        elif m == 'intro':
            self.draw_intro()
        elif m == 'diff':
            self.draw_diff()
        elif m == 'bye':
            self.draw_bye()
        elif m == 'send':
            self.screen.fill((8, 0, 0) if self.send_win else (4, 6, 10))
            if self.send_win:
                draw_wrapped(self.screen, "¡ATRAPASTE AL JUGADOR!", self.fs['l'], (190, 20, 20),
                             self.sw / 2, self.sh * 0.28, self.sw * 0.92)
                draw_wrapped(self.screen, "No pudo escapar del bosque... esta vez.", self.fs['m'], (200, 200, 200),
                             self.sw / 2, self.sh * 0.44, self.sw * 0.9)
            else:
                draw_wrapped(self.screen, "EL JUGADOR ESCAPÓ", self.fs['l'], (210, 210, 210),
                             self.sw / 2, self.sh * 0.28, self.sw * 0.92)
                draw_wrapped(self.screen, "Llegó al barco antes de que lo alcanzaras.", self.fs['m'], (170, 170, 170),
                             self.sw / 2, self.sh * 0.44, self.sw * 0.9)
            self.ui_button("JUGAR DE NUEVO", self.sw / 2, self.sh * 0.62, self.new_slender_game)
            self.ui_button("MENÚ PRINCIPAL", self.sw / 2, self.sh * 0.80, self.to_menu)
        elif m == 'over':
            self.screen.fill((8, 0, 0))
            draw_text(self.screen, "GAME OVER", self.fs['xl'], (190, 20, 20), center=(self.sw / 2, self.sh * 0.28))
            self.ui_button("REINTENTAR", self.sw / 2, self.sh * 0.55, self.new_game)
            self.ui_button("MENÚ PRINCIPAL", self.sw / 2, self.sh * 0.74, self.to_menu)
        elif m == 'menu':
            self.draw_menu()
        elif m == 'options':
            self.draw_options()

    def _set_mode(self, m):
        self.mode = m

    def ui_button(self, label, cx, cy, cb, locked=False):
        bw = min(self.sw * 0.82, self.sh * 0.95)
        bh = min(self.sh * 0.13, self.sw * 0.17)
        r = pygame.Rect(0, 0, I(bw), I(bh))
        r.center = (I(cx), I(cy))
        pygame.draw.rect(self.screen, (14, 16, 20), r)
        pygame.draw.rect(self.screen, (70, 70, 74) if locked else (150, 28, 28), r, 3)
        draw_text(self.screen, label, I(bh * 0.5), (110, 110, 114) if locked else (235, 235, 235), center=r.center)
        self.ui.append((r, cb))

    def open_diff(self, kind):
        self.pending = kind
        self.mode = 'diff'

    def start_pending(self, i):
        self.diff_i = i
        if self.pending == 'slender':
            self.new_slender_game()
        else:
            self.new_game()

    def end_intro(self):
        self.menu_bg.set_alpha(None)
        self.mode = 'menu'

    def begin_bye(self):
        self.mode = 'bye'
        self.bye_t = 0.0
        self.bye_phrase = random.choice(PHRASES)
        self.audio.play('whisper', 0.5)

    def finish_bye(self):
        if sys.platform == 'emscripten':
            self.to_menu()
        else:
            self.quit()

    def draw_diff(self):
        sc = self.screen
        sc.blit(self.menu_bg, (0, 0))
        sc.blit(self.shade, (0, 0))
        land = self.sw > self.sh
        t1 = I(min(self.sh * 0.12, self.sw * 0.13))
        draw_text(sc, "DIFICULTAD", t1, (225, 225, 225), center=(self.sw / 2, self.sh * 0.11))
        sub = "Modo Slenderman" if self.pending == 'slender' else "Escapa del bosque"
        draw_text(sc, sub, self.fs['s'], (190, 120, 120), center=(self.sw / 2, self.sh * (0.195 if land else 0.18)))
        ys = (0.31, 0.45, 0.59, 0.73, 0.87) if land else (0.29, 0.38, 0.47, 0.56, 0.68)
        for i, (name, _) in enumerate(DIFFS):
            self.ui_button(name, self.sw / 2, self.sh * ys[i], (lambda k=i: self.start_pending(k)))
        self.ui_button("ATRÁS", self.sw / 2, self.sh * ys[4], lambda: self._set_mode('menu'))

    def draw_intro(self):
        sc = self.screen
        t = self.intro_t
        total = sum(d for _, d in INTRO)
        sc.fill((0, 0, 0))
        start_bg = INTRO[0][1] + INTRO[1][1]
        k = clamp((t - start_bg) / 4.0, 0.0, 1.0)
        if k > 0:
            if t < total:
                a = I(150 * k)
            else:
                a = I(150 + 105 * clamp((t - total) / 1.5, 0.0, 1.0))
            self.menu_bg.set_alpha(a)
            sc.blit(self.menu_bg, (0, 0))
            self.menu_bg.set_alpha(None)
        acc = 0.0
        for i, (txt, dur) in enumerate(INTRO):
            if acc <= t < acc + dur:
                loc = t - acc
                a = 255 * clamp(min(loc / 0.7, (dur - loc) / 0.7), 0.0, 1.0)
                draw_wrapped(sc, txt, self.fs['m'], (225, 225, 225), self.sw / 2, self.sh * 0.5, self.sw * 0.88, alpha=a)
                if i in (2, 4) and i not in self.intro_flags and loc > 0.1:
                    self.intro_flags.add(i)
                    self.audio.play('sting' if i == 4 else 'creak', 0.5)
                if i in (2, 4) and random.random() < 0.05:
                    ns = pygame.transform.scale(random.choice(self.art.noise), (self.sw, self.sh))
                    ns.set_alpha(70)
                    sc.blit(ns, (0, 0))
                break
            acc += dur
        if t >= total:
            loc = t - total
            a = 255 * clamp(loc / 1.0, 0.0, 1.0)
            t1 = I(min(self.sh * 0.15, self.sw * 0.17))
            t2 = I(min(self.sh * 0.095, self.sw * 0.105))
            draw_text(sc, "SLENDERMAN:", t1, (225, 225, 225), center=(self.sw / 2, self.sh * 0.40), alpha=a)
            draw_text(sc, "ESCAPE DEL BOSQUE", t2, (180, 25, 25), center=(self.sw / 2, self.sh * 0.40 + t1 * 0.85), alpha=a)
        draw_text(sc, "Toca para saltar", self.fs['s'], (120, 120, 120), center=(self.sw / 2, self.sh * 0.95), alpha=110)

    def draw_bye(self):
        sc = self.screen
        sc.fill((0, 0, 0))
        t = self.bye_t
        a = 255 * clamp(min(t / 1.2, (5.0 - t) / 1.0), 0.0, 1.0)
        draw_wrapped(sc, self.bye_phrase, self.fs['m'], (215, 215, 215), self.sw / 2, self.sh * 0.45, self.sw * 0.88, alpha=a)
        if t > 2.2:
            b = 255 * clamp(min((t - 2.2) / 1.0, (5.0 - t) / 0.8), 0.0, 1.0)
            draw_text(sc, "Gracias por jugar.", self.fs['s'], (150, 150, 150), center=(self.sw / 2, self.sh * 0.62), alpha=b)

    def _locked_note(self):
        self.note_until = self.t + 2.5

    def draw_menu(self):
        sc = self.screen
        sc.blit(self.menu_bg, (0, 0))
        if self.menu_glitch > 0:
            self.menu_glitch -= 1
            ns = pygame.transform.scale(random.choice(self.art.noise), (self.sw, self.sh))
            ns.set_alpha(45)
            sc.blit(ns, (0, 0))
        elif random.random() < 0.012:
            self.menu_glitch = 4
        land = self.sw > self.sh
        cx = self.sw * 0.6 if land else self.sw * 0.5
        t1 = I(min(self.sh * 0.15, self.sw * 0.17))
        t2 = I(min(self.sh * 0.095, self.sw * 0.105))
        y1 = self.sh * 0.14
        draw_text(sc, "SLENDERMAN:", t1, (225, 225, 225), center=(cx, y1))
        draw_text(sc, "ESCAPE DEL BOSQUE", t2, (180, 25, 25), center=(cx, y1 + t1 * 0.85))
        ys = (0.43, 0.58, 0.73, 0.88) if land else (0.40, 0.50, 0.60, 0.70)
        self.ui_button("JUGAR", cx, self.sh * ys[0], lambda: self.open_diff('survival'))
        self.ui_button("MODO SLENDERMAN", cx, self.sh * ys[1],
                       (lambda: self.open_diff('slender')) if self.unlocked else self._locked_note,
                       locked=not self.unlocked)
        self.ui_button("OPCIONES", cx, self.sh * ys[2], lambda: self._set_mode('options'))
        self.ui_button("SALIR", cx, self.sh * ys[3], self.begin_bye)
        if self.t < self.note_until:
            draw_text(sc, "Escapa en el barco para desbloquearlo", self.fs['s'], (210, 120, 120),
                      center=(cx, self.sh * (ys[3] + 0.08 if land else ys[3] + 0.07)))

    def draw_options(self):
        sc = self.screen
        sc.blit(self.menu_bg, (0, 0))
        sc.blit(self.shade, (0, 0))
        draw_text(sc, "OPCIONES", self.fs['l'], (225, 225, 225), center=(self.sw / 2, self.sh * 0.17))
        draw_text(sc, "VOLUMEN  %d%%" % I(self.audio.master * 100), self.fs['m'], (210, 210, 210),
                  center=(self.sw / 2, self.sh * 0.33))
        r = self._slider_rect()
        pygame.draw.rect(sc, (40, 40, 46), r)
        fill = r.copy()
        fill.width = I(r.width * self.audio.master)
        pygame.draw.rect(sc, (150, 28, 28), fill)
        pygame.draw.circle(sc, (235, 235, 235), (fill.right, r.centery), max(8, r.height))
        self.ui_button("VOLVER", self.sw / 2, self.sh * 0.78, lambda: self._set_mode('menu'))

    def draw_jump_face(self, k):
        sc = self.screen
        sw, sh = self.sw, self.sh
        ph = int(k * 30)
        if ph % 5 == 0:
            sc.fill((130, 0, 0))
        elif ph % 9 == 0:
            sc.fill((235, 235, 235))
        else:
            sc.fill((0, 0, 0))
        z = 0.8 + min(k, 0.5) * 1.7 + 0.05 * math.sin(k * 45)
        base = min(sh, sw * 1.45)
        cx = sw // 2 + random.randint(-16, 16)
        cy = I(sh * 0.44) + random.randint(-16, 16)
        hh = I(base * 0.40 * z)
        hw = I(hh * 0.66)
        pygame.draw.polygon(sc, (8, 8, 10), [(cx - hw * 3, sh), (cx - I(hw * 0.9), cy + I(hh * 0.8)),
                                             (cx + I(hw * 0.9), cy + I(hh * 0.8)), (cx + hw * 3, sh)])
        pygame.draw.polygon(sc, (205, 205, 210), [(cx - I(hw * 0.35), cy + I(hh * 0.9)),
                                                  (cx + I(hw * 0.35), cy + I(hh * 0.9)), (cx, cy + I(hh * 1.8))])
        pygame.draw.line(sc, (130, 10, 10), (cx, cy + I(hh * 1.0)), (cx, cy + I(hh * 1.9)), max(4, hw // 8))
        pygame.draw.rect(sc, (225, 225, 228), (cx - I(hw * 0.2), cy + hh - 12, I(hw * 0.4), I(hh * 0.3)))
        pygame.draw.ellipse(sc, (244, 244, 246), (cx - hw, cy - hh, hw * 2, hh * 2))
        pygame.draw.ellipse(sc, (205, 205, 210), (cx - hw, cy - hh, hw * 2, hh * 2), max(2, hw // 30))
        for _ in range(4):
            yy = random.randint(0, max(1, sh - 80))
            hs = random.randint(8, 60)
            strip = sc.subsurface((0, yy, sw, min(hs, sh - yy))).copy()
            sc.blit(strip, (random.randint(-40, 40), yy))
        ns = pygame.transform.scale(random.choice(self.art.noise), (sw, sh))
        ns.set_alpha(130)
        sc.blit(ns, (0, 0))

    def draw_game(self, extra_shake=0.0):
        v = self.view
        vw, vh = self.vw, self.vh
        w = self.world
        p = self.p
        s = self.sl
        art = self.art
        t = self.t
        amp = self.shake_amp + extra_shake
        ox = oy = 0.0
        if amp > 0.2:
            ox = random.uniform(-amp, amp)
            oy = random.uniform(-amp, amp)
        camx, camy = self._camera(ox, oy)
        self.cam = (camx, camy)

        # 1. suelo
        gx0 = -(camx % 256)
        gy0 = -(camy % 256)
        x = gx0
        while x < vw:
            y = gy0
            while y < vh:
                v.blit(art.ground, (x, y))
                y += 256
            x += 256

        # 2. caminos
        for pts in w.paths:
            sp = [(I(a - camx), I(b - camy)) for a, b in pts]
            pygame.draw.lines(v, (31, 28, 24), False, sp, 30)
            for q in sp:
                pygame.draw.circle(v, (31, 28, 24), q, 15)

        # 3. lago, muelle y barco
        self.draw_lake(v, w, camx, camy, t)

        # 4. objetos ordenados por profundidad
        items = []
        for o in w.visible(camx, camy, vw, vh):
            if o[3] >= 0:
                items.append((o[1], 0, o))
        for it in w.items:
            if not self.smode and not it[3] and -30 < it[1] - camx < vw + 30 and -30 < it[2] - camy < vh + 40:
                items.append((it[2], 1, it))
        items.append((p.y, 2, None))
        if s.alpha > 0 and s.state != OCULTO:
            items.append((s.y, 3, None))
        items.sort(key=lambda a: a[0])
        for _, kind, o in items:
            if kind == 2:
                self.draw_player(v, p.x - camx, p.y - camy)
            elif kind == 3:
                self.draw_slender_world(v, s.x - camx, s.y - camy)
            elif kind == 1:
                spr = art.torch_item if o[0] == 'torch' else art.bat_item
                v.blit(spr, (I(o[1] - camx) - spr.get_width() // 2, I(o[2] - camy) - spr.get_height()))
            else:
                spr = art.sprites[o[3]][o[4]]
                bx = I(o[0] - camx)
                by = I(o[1] - camy)
                v.blit(spr, (bx - spr.get_width() // 2, by - spr.get_height() + 5))
                if o[3] == 5:
                    fh = 8 + random.randint(0, 5)
                    pygame.draw.polygon(v, (255, 140, 30), [(bx - 5, by - 3), (bx, by - 3 - fh), (bx + 5, by - 3)])
                    pygame.draw.polygon(v, (255, 225, 110), [(bx - 2, by - 3), (bx, by - 3 - fh // 2), (bx + 2, by - 3)])

        # 5. niebla
        for fx, fy, var, spd in w.fog:
            px_ = (fx + t * spd) % (w.W + 400) - 200
            spr = art.fog[var]
            bx = I(px_ - camx)
            by = I(fy - camy)
            if bx < vw and by < vh and bx + spr.get_width() > 0 and by + spr.get_height() > 0:
                v.blit(spr, (bx, by))

        # 6. oscuridad + linterna / antorcha
        lx = I(p.x - camx)
        ly = I(p.y - camy - 6)
        dk = self.dark
        dk.fill((4, 6, 14, 190 if self.smode else 226))
        lit = p.flash_on and p.battery > 0 and not self.flick_off
        if lit:
            idx = int(round((p.face % TAU) / TAU * art.n_cones)) % art.n_cones
            cone = art.cones[idx]
            dk.blit(cone, (lx - cone.get_width() // 2, ly - cone.get_height() // 2), special_flags=pygame.BLEND_RGBA_SUB)
        if self.has_torch:
            hb = art.halo_torch
        elif lit:
            hb = art.halo_big
        else:
            hb = art.halo_small
        dk.blit(hb, (lx - hb.get_width() // 2, ly - hb.get_height() // 2), special_flags=pygame.BLEND_RGBA_SUB)
        if self.smode:
            hs = art.halo_torch
            dk.blit(hs, (I(s.x - camx) - hs.get_width() // 2, I(s.y - camy - 6) - hs.get_height() // 2),
                    special_flags=pygame.BLEND_RGBA_SUB)
        v.blit(dk, (0, 0))

        # 7. elementos que brillan en la oscuridad
        if s.alpha > 0 and s.state != OCULTO:
            fr = int(s.anim) % 3 if s.moving else 0
            dim = art.sl[fr]
            dim.set_alpha(I(s.alpha * 0.5))
            v.blit(dim, (I(s.x - camx) - 23, I(s.y - camy) - 110))
        lamp_x = w.dock_in + w.dir * 40 - camx
        lamp_y = w.dock.top - 34 - camy
        if -80 < lamp_x < vw + 80 and -80 < lamp_y < vh + 80:
            gl = art.glow
            gl.set_alpha(I(185 + 40 * math.sin(t * 7.0) * random.random()))
            v.blit(gl, (I(lamp_x) - 70, I(lamp_y) - 70))
        for fx, fy in w.fires:
            gx = fx - camx
            gy = fy - camy - 8
            if -80 < gx < vw + 80 and -80 < gy < vh + 80:
                gl = art.glow
                gl.set_alpha(I(150 + 70 * random.random()))
                v.blit(gl, (I(gx) - 70, I(gy) - 70))
        for it in w.items:
            if not it[3] and not self.smode:
                gx = it[1] - camx
                gy = it[2] - camy - 8
                if -40 < gx < vw + 40 and -40 < gy < vh + 40:
                    gl = art.glow_small
                    gl.set_alpha(I(110 + 40 * math.sin(t * 4.0 + it[1])))
                    v.blit(gl, (I(gx) - 32, I(gy) - 32))
        if self.smode:
            gl = art.glow_small
            gl.set_alpha(I(150 + 60 * random.random()))
            v.blit(gl, (lx - 32, ly - 32))
        if self.has_torch:
            gl = art.glow_big
            gl.set_alpha(I(60 + 25 * random.random()))
            v.blit(gl, (lx - 110, ly - 110))

        # 8. interferencia, susto y fundido
        g = self.glitch
        if g > 0.05 and self.mode in ('play', 'escape', 'splay'):
            ns = pygame.transform.scale(random.choice(art.noise), (vw, vh))
            ns.set_alpha(I(g * 110))
            v.blit(ns, (0, 0))
            if g > 0.3 and random.random() < 0.5 * g:
                for _ in range(2):
                    yy = random.randint(0, vh - 30)
                    hh = random.randint(6, 24)
                    strip = v.subsurface((0, yy, vw, hh)).copy()
                    v.blit(strip, (random.randint(-18, 18), yy))
        if self.flash > 0:
            self.flash_surf.set_alpha(I(255 * clamp(self.flash, 0, 1)))
            v.blit(self.flash_surf, (0, 0))
        if self.mode == 'escape':
            a = clamp((self.esc_t - 0.5) / 8.5, 0.0, 1.0)
            self.fade_surf.set_alpha(I(255 * a))
            v.blit(self.fade_surf, (0, 0))

        # 9. escalar a la pantalla
        self.blit_scaled()

    def blit_scaled(self):
        size = (self.sw, self.sh)
        if self.fast_scale:
            try:
                pygame.transform.scale(self.view, size, self.screen)
                return
            except Exception:
                self.fast_scale = False
        self.screen.blit(pygame.transform.scale(self.view, size), (0, 0))

    def draw_lake(self, v, w, camx, camy, t):
        vw, vh = self.vw, self.vh
        d = w.dir
        if not ((d > 0 and camx + vw > 2000) or (d < 0 and camx < w.W - 2000)):
            return
        y0 = int((camy - 30) // 24) * 24
        y1 = int(camy + vh + 30)
        pts = []
        y = y0
        while y <= y1 + 24:
            pts.append((I(w.shore_x(y) - camx), y - camy))
            y += 24
        top = pts[0][1]
        bot = pts[-1][1]
        far = vw + 40 if d > 0 else -40
        pygame.draw.polygon(v, (30, 32, 28), [(a - 16 * d, b) for a, b in pts] + [(far, bot), (far, top)])
        pygame.draw.polygon(v, (7, 16, 30), pts + [(far, bot), (far, top)])
        for rx, ry, ph in w.ripples:
            sx = rx - camx
            sy = ry - camy
            if 0 < sx < vw and 0 < sy < vh:
                c = 22 + I(16 * math.sin(t * 1.6 + ph))
                pygame.draw.line(v, (c // 2, c, c + 24), (I(sx), I(sy)), (I(sx) + 7, I(sy)), 1)
        # muelle
        r = w.dock
        rr = r.move(-camx, -camy)
        if rr.right > 0 and rr.left < vw:
            pygame.draw.rect(v, (52, 36, 24), rr)
            xx = r.left
            while xx < r.right:
                px = xx - camx
                if -2 < px < vw + 2:
                    pygame.draw.line(v, (34, 24, 16), (px, rr.top), (px, rr.bottom))
                xx += 14
            pygame.draw.line(v, (30, 20, 14), (rr.left, rr.top), (rr.right, rr.top), 2)
            pygame.draw.line(v, (30, 20, 14), (rr.left, rr.bottom), (rr.right, rr.bottom), 2)
            xx = r.left + 6
            while xx < r.right:
                px = xx - camx
                if -4 < px < vw + 4:
                    pygame.draw.circle(v, (24, 17, 11), (px, rr.top), 3)
                    pygame.draw.circle(v, (24, 17, 11), (px, rr.bottom), 3)
                xx += 60
            lx = w.dock_in + d * 40 - camx
            ly = r.top - 4 - camy
            pygame.draw.line(v, (30, 22, 16), (lx, ly), (lx, ly - 30), 3)
            pygame.draw.circle(v, (255, 205, 130), (lx, ly - 32), 3)
        # barco
        bx = I(self.boat_x_now() - camx)
        by = I(w.boat_y - camy + 2 * math.sin(t * 1.3))
        if -60 < bx < vw + 60:
            if self.mode != 'escape':
                pygame.draw.line(v, (80, 70, 50), (bx - 36 * d, by), (w.dock_out - camx, by), 1)
            hull = [(bx + a * d, by + b) for a, b in ((-36, -9), (30, -13), (44, 0), (30, 13), (-36, 9))]
            inner = [(bx + a * d, by + b) for a, b in ((-30, -6), (26, -9), (36, 0), (26, 9), (-30, 6))]
            pygame.draw.polygon(v, (68, 45, 28), hull)
            pygame.draw.polygon(v, (36, 24, 16), inner)
            pygame.draw.line(v, (84, 58, 36), (bx - 4 * d, by - 8), (bx - 4 * d, by + 8), 3)
            pygame.draw.polygon(v, (26, 17, 11), hull, 1)

    def boat_x_now(self):
        return self.boat_x if self.mode in ('escape', 'win') else self.world.boat_x0

    def draw_player(self, v, sx, sy):
        p = self.p
        sx = I(sx)
        sy = I(sy)
        pygame.draw.ellipse(v, (4, 6, 6), (sx - 7, sy - 3, 14, 6))
        lg = I(math.sin(p.walk) * 3) if p.moving else 0
        pygame.draw.line(v, (24, 26, 40), (sx - 2, sy - 10), (sx - 2 + lg, sy), 3)
        pygame.draw.line(v, (24, 26, 40), (sx + 2, sy - 10), (sx + 2 - lg, sy), 3)
        pygame.draw.rect(v, (150, 66, 58) if self.smode else (62, 84, 124), (sx - 4, sy - 21, 8, 12))
        pygame.draw.circle(v, (205, 172, 150), (sx, sy - 25), 4)
        pygame.draw.rect(v, (34, 24, 18), (sx - 4, sy - 29, 8, 3))
        fx = I(math.cos(p.face) * 8)
        fy = I(math.sin(p.face) * 4)
        if self.has_torch:
            pygame.draw.line(v, (96, 62, 30), (sx - 6, sy - 13), (sx - 6, sy - 19), 2)
            fl = 3 + random.randint(0, 2)
            pygame.draw.polygon(v, (255, 150, 40), [(sx - 9, sy - 19), (sx - 6, sy - 19 - fl - 2), (sx - 3, sy - 19)])
            pygame.draw.polygon(v, (255, 228, 120), [(sx - 7, sy - 19), (sx - 6, sy - 19 - fl), (sx - 5, sy - 19)])
        pygame.draw.line(v, (230, 220, 150), (sx + fx, sy - 14 + fy),
                         (sx + I(math.cos(p.face) * 14), sy - 14 + I(math.sin(p.face) * 7)), 2)

    def draw_slender_world(self, v, sx, sy):
        s = self.sl
        sx = I(sx)
        sy = I(sy)
        pygame.draw.ellipse(v, (3, 4, 5), (sx - 9, sy - 4, 18, 8))
        fr = int(s.anim) % 3 if s.moving else 0
        spr = self.art.sl[fr]
        spr.set_alpha(I(clamp(s.alpha, 0, 255)))
        v.blit(spr, (sx - 23, sy - 110))

    # ------------------------------------------------------------------ HUD
    def draw_hud(self):
        if self.smode:
            self.draw_hud_s()
            return
        sc = self.screen
        u = self.u
        p = self.p
        # barras
        bw = u * 0.50
        bh = max(8, u * 0.028)
        x0 = u * 0.04
        y0 = u * 0.04
        draw_text(sc, "RESISTENCIA", self.fs['s'], (200, 200, 200), topleft=(x0, y0))
        y1 = y0 + self.fs['s'] * 0.85
        pygame.draw.rect(sc, (18, 18, 20), (I(x0), I(y1), I(bw), I(bh)))
        c = (70, 190, 90) if p.stamina > 35 else (210, 70, 50)
        if p.exhausted:
            c = (210, 70, 50)
        pygame.draw.rect(sc, c, (I(x0), I(y1), I(bw * p.stamina / 100.0), I(bh)))
        pygame.draw.rect(sc, (120, 120, 120), (I(x0), I(y1), I(bw), I(bh)), 1)
        y2 = y1 + bh + u * 0.02
        draw_text(sc, "BATERÍA", self.fs['s'], (200, 200, 200), topleft=(x0, y2))
        y3 = y2 + self.fs['s'] * 0.85
        pygame.draw.rect(sc, (18, 18, 20), (I(x0), I(y3), I(bw), I(bh)))
        bc = (230, 200, 70) if p.battery > 20 else (220, 90, 40)
        pygame.draw.rect(sc, bc, (I(x0), I(y3), I(bw * p.battery / 100.0), I(bh)))
        pygame.draw.rect(sc, (120, 120, 120), (I(x0), I(y3), I(bw), I(bh)), 1)
        y4 = y3 + bh + u * 0.025
        w = self.world
        tc = (240, 200, 90) if self.has_torch else (190, 190, 190)
        draw_text(sc, "ANTORCHA: %s" % ("SÍ" if self.has_torch else "NO"), self.fs['s'], tc, topleft=(x0, y4))
        pc = (240, 200, 90) if self.bats >= w.n_bats else (190, 190, 190)
        draw_text(sc, "PILAS: %d/%d" % (self.bats, w.n_bats), self.fs['s'], pc, topleft=(x0, y4 + self.fs['s'] * 0.85))
        # mensajes
        if self.msgs:
            text, left, total = self.msgs[0]
            a = 255 * clamp(min(left, total - left) / 0.6, 0.0, 1.0)
            draw_wrapped(sc, text, I(u * 0.062), (235, 235, 235), self.sw / 2, self.sh * 0.20, self.sw * 0.9, alpha=a)
        # joystick
        if self.joy_id is not None:
            cx, cy = self.joy_c
            kx, ky = self.joy_p
        else:
            cx, cy = self.joy_def
            kx, ky = cx, cy
        jr = self.joy_base.get_width() // 2
        sc.blit(self.joy_base, (I(cx) - jr, I(cy) - jr))
        kr = self.joy_knob.get_width() // 2
        sc.blit(self.joy_knob, (I(kx) - kr, I(ky) - kr))
        # botones
        self._draw_btn('run', bool(self.run_ids) or p.running)
        self._draw_btn('flash', p.flash_on and p.battery > 0)
        self._draw_btn('pause', False)
        if self.near_boat():
            self._draw_btn('act', False)

    def new_slender_game(self):
        """Modo Slenderman: tu controlas a Slenderman y persigues al bot."""
        self.new_game()
        w = self.world
        self.smode = True
        self.play_mode = 'splay'
        bot = Bot(w.start[0], w.start[1])
        bot.face = math.atan2(w.dock_y - w.start[1], w.dock_in - w.start[0])
        self.p = bot
        self.goal = (w.boat_x0 - w.dir * 55, w.boat_y)
        s = Slender()
        s.state = PERSIGUIENDO
        s.alpha = 255.0
        self.sl = s
        cand = list(w.hotspots) + [(w.W / 2.0, w.H / 2.0)]
        random.shuffle(cand)
        pos = (w.W / 2.0, w.H / 2.0)
        for (x, y) in cand:
            if math.hypot(x - bot.x, y - bot.y) > 700 and not w.slender_blocked(x, y):
                pos = (x, y)
                break
        s.x, s.y = pos
        self.sen = 100.0
        self.sen_ex = False
        self.s_run = False
        self.tp_cd = 0.0
        self.msgs = []
        self.add_msg("Eres SLENDERMAN. Impide que el jugador llegue al barco.", 5.0)
        self.add_msg("ADELANTE y ATRÁS te teletransportan junto a él.", 5.0)
        self.add_msg("Con el tiempo te vuelves más rápido.", 4.0)
        bot.path = w.find_path(bot.x, bot.y, self.goal[0], self.goal[1])
        bot.pi = 0
        self.audio.set_near(0.0)
        self.mode = 'splay'

    def sl_speed(self):
        return 100.0 + 42.0 * clamp(self.play_t / 200.0, 0.0, 1.0)

    def tp_player(self, ahead):
        if self.mode != 'splay' or self.tp_cd > 0:
            return
        b = self.p
        s = self.sl
        w = self.world
        sign = 1.0 if ahead else -1.0
        for _ in range(14):
            dist = (115.0 if ahead else 70.0) + random.uniform(-25, 35)
            a = b.face + random.uniform(-0.6, 0.6)
            x = b.x + sign * math.cos(a) * dist
            y = b.y + sign * math.sin(a) * dist
            if w.slender_blocked(x, y):
                continue
            s.x, s.y = x, y
            self.tp_cd = max(4.0, 8.0 - 3.0 * clamp(self.play_t / 240.0, 0.0, 1.0))
            self.audio.play('sting', 0.5)
            self.flash = 0.3
            self.shake_t = 0.25
            return

    def end_slender(self, win):
        self.mode = 'send'
        self.send_win = win
        self.joy_id = None
        self.run_ids = set()
        self.glitch = 0.0
        if win:
            self.audio.play('scream', 0.6)

    def update_splay(self, dt):
        self.play_t += dt
        s = self.sl
        b = self.p
        w = self.world
        mx, my = self.move_vec()
        mag = math.hypot(mx, my)
        moving = mag > 0.12
        run = bool(self.run_pressed() and moving and self.sen > 0 and not self.sen_ex)
        if run:
            self.sen -= 30.0 * dt
            if self.sen <= 0:
                self.sen = 0.0
                self.sen_ex = True
        else:
            self.sen = min(100.0, self.sen + (14.0 if moving else 22.0) * dt)
            if self.sen_ex and self.sen > 30:
                self.sen_ex = False
        self.s_run = run
        s.moving = False
        if moving:
            sp = self.sl_speed() * (1.3 if run else 1.0) * max(0.45, min(1.0, mag))
            ux = mx / mag
            uy = my / mag
            nx = s.x + ux * sp * dt
            if not w.slender_blocked(nx, s.y):
                s.x = nx
            ny = s.y + uy * sp * dt
            if not w.slender_blocked(s.x, ny):
                s.y = ny
            s.moving = True
            s.anim += dt * (9.0 if run else 7.0)
        self.tp_cd = max(0.0, self.tp_cd - dt)
        self.update_bot(dt)
        self.glitch = 0.5 if self.shake_t > 0 else 0.0
        self.shake_amp = 3.0 if self.shake_t > 0 else 0.0
        ds = math.hypot(b.x - s.x, b.y - s.y)
        self.audio.set_near(0.0)
        self.tick_common(dt)
        if ds < ATTACK_R + 4:
            self.end_slender(True)
        elif math.hypot(b.x - w.boat_x0, b.y - w.boat_y) < 70:
            self.end_slender(False)

    def _bot_choose_target(self):
        """El bot elige una zona sin explorar (no conoce el camino al muelle)."""
        b = self.p
        w = self.world
        for _ in range(2):
            best = None
            bs = 1e9
            for cx in range(int(w.W // 160) + 1):
                for cy in range(int(w.H // 160) + 1):
                    if (cx, cy) in b.visited:
                        continue
                    x = cx * 160 + 80
                    y = cy * 160 + 80
                    if x > w.W - 40 or y > w.H - 40 or w.in_water(x, y, 50):
                        continue
                    sc = math.hypot(x - b.x, y - b.y) + random.uniform(0, 350)
                    if sc < bs:
                        bs = sc
                        best = (x, y)
            if best:
                b.target = (best[0] + random.uniform(-35, 35), best[1] + random.uniform(-35, 35))
                return
            b.visited = set()
        b.target = (w.W / 2.0, w.H / 2.0)

    def update_bot(self, dt):
        b = self.p
        s = self.sl
        w = self.world
        dk = self.dk
        ds = math.hypot(b.x - s.x, b.y - s.y)
        b.moving = False
        if b.wait > 0:
            b.wait -= dt
            b.running = False
            return
        b.visited.add((int(b.x // 160), int(b.y // 160)))
        if not b.known and math.hypot(b.x - w.dock_in, b.y - w.dock_y) < dk['bot_sight']:
            b.known = True
            b.path = None
            b.target = None
            self.add_msg("¡El jugador vio la luz del muelle!", 3.5)
        if b.known:
            goal = self.goal
        else:
            if b.target is None:
                self._bot_choose_target()
                b.path = None
            goal = b.target
        b.replan_t -= dt
        need = b.path is None
        if not need and b.replan_t <= 0:
            b.replan_t = 1.2
            for q in b.path[b.pi:b.pi + 6]:
                if math.hypot(q[0] - s.x, q[1] - s.y) < 120:
                    need = True
                    break
        if need:
            avoid = (s.x, s.y, 160.0) if ds < 400 else None
            path = w.find_path(b.x, b.y, goal[0], goal[1], avoid, 9000 if b.known else 5000)
            b.path = path if path else [goal]
            b.pi = 0
            b.replan_t = 1.2
        while b.pi < len(b.path) - 1 and math.hypot(b.path[b.pi][0] - b.x, b.path[b.pi][1] - b.y) < 10:
            b.pi += 1
        if not b.known:
            last = b.path[-1]
            if (b.pi >= len(b.path) - 1 and math.hypot(b.x - last[0], b.y - last[1]) < 16) \
                    or math.hypot(b.x - goal[0], b.y - goal[1]) < 45:
                b.visited.add((int(goal[0] // 160), int(goal[1] // 160)))
                b.target = None
                b.path = None
                return
        tx, ty = b.path[b.pi]
        dx = tx - b.x
        dy = ty - b.y
        d = math.hypot(dx, dy)
        if d < 3:
            return
        ux = dx / d
        uy = dy / d
        if b.nudge_t > 0:
            b.nudge_t -= dt
            ux = math.cos(b.nudge_a)
            uy = math.sin(b.nudge_a)
        can = b.stamina > 0 and not b.exhausted
        b.running = bool(ds < dk['bot_fear'] and can)
        if b.running:
            b.stamina -= 22.0 * dt
            if b.stamina <= 0:
                b.stamina = 0.0
                b.exhausted = True
        else:
            b.stamina = min(100.0, b.stamina + 10.0 * dt)
            if b.exhausted and b.stamina > 30:
                b.exhausted = False
        speed = (BOT_RUN if b.running else BOT_WALK) * dk['bot_spd']
        ox, oy = b.x, b.y
        nx = b.x + ux * speed * dt
        if not w.blocked(nx, b.y):
            b.x = nx
        ny = b.y + uy * speed * dt
        if not w.blocked(b.x, ny):
            b.y = ny
        moved = math.hypot(b.x - ox, b.y - oy)
        b.moving = moved > 0.01
        target = math.atan2(uy, ux)
        da = (target - b.face + math.pi) % TAU - math.pi
        b.face += da * min(1.0, dt * 10.0)
        b.walk += moved * 0.12
        if moved < speed * dt * 0.3:
            b.stuck_t += dt
        else:
            b.stuck_t = 0.0
        if b.stuck_t > 0.8:
            b.stuck_t = 0.0
            b.path = None
            b.nudge_t = 0.5
            b.nudge_a = random.uniform(0, TAU)
            if not b.known and b.target is not None:
                b.visited.add((int(b.target[0] // 160), int(b.target[1] // 160)))
                b.target = None
        b.step_d += moved
        if b.step_d > 46:
            b.step_d = 0.0
            vol = 0.5 * clamp(1.0 - ds / 450.0, 0.0, 1.0)
            if vol > 0.03:
                self.audio.play('step', vol)

    def draw_hud_s(self):
        sc = self.screen
        u = self.u
        b = self.p
        s = self.sl
        bw = u * 0.50
        bh = max(8, u * 0.028)
        x0 = u * 0.04
        y0 = u * 0.04
        draw_text(sc, "ENERGÍA", self.fs['s'], (200, 200, 200), topleft=(x0, y0))
        y1 = y0 + self.fs['s'] * 0.85
        pygame.draw.rect(sc, (18, 18, 20), (I(x0), I(y1), I(bw), I(bh)))
        pygame.draw.rect(sc, (150, 70, 210) if not self.sen_ex else (210, 70, 50), (I(x0), I(y1), I(bw * self.sen / 100.0), I(bh)))
        pygame.draw.rect(sc, (120, 120, 120), (I(x0), I(y1), I(bw), I(bh)), 1)
        ds = math.hypot(b.x - s.x, b.y - s.y)
        y2 = y1 + bh + u * 0.025
        draw_text(sc, "DISTANCIA: %d m" % int(ds / 10), self.fs['s'], (225, 200, 200), topleft=(x0, y2))
        draw_text(sc, "VELOCIDAD: %d" % int(self.sl_speed()), self.fs['s'], (225, 200, 200),
                  topleft=(x0, y2 + self.fs['s'] * 0.85))
        if self.msgs:
            text, left, total = self.msgs[0]
            a = 255 * clamp(min(left, total - left) / 0.6, 0.0, 1.0)
            draw_wrapped(sc, text, I(u * 0.062), (235, 235, 235), self.sw / 2, self.sh * 0.20, self.sw * 0.9, alpha=a)
        # flecha hacia el jugador cuando esta fuera de la pantalla
        camx, camy = self.cam
        bx = (b.x - camx) * self.sw / float(self.vw)
        by = (b.y - camy) * self.sh / float(self.vh)
        m = u * 0.09
        if not (m < bx < self.sw - m and m < by < self.sh - m):
            cx0 = self.sw / 2.0
            cy0 = self.sh / 2.0
            ang = math.atan2(by - cy0, bx - cx0)
            ca = abs(math.cos(ang)) + 1e-6
            sa = abs(math.sin(ang)) + 1e-6
            t = min((cx0 - m) / ca, (cy0 - m) / sa)
            ex = cx0 + math.cos(ang) * t
            ey = cy0 + math.sin(ang) * t
            r = u * 0.05
            pts = [(I(ex + math.cos(ang) * r), I(ey + math.sin(ang) * r)),
                   (I(ex + math.cos(ang + 2.5) * r), I(ey + math.sin(ang + 2.5) * r)),
                   (I(ex + math.cos(ang - 2.5) * r), I(ey + math.sin(ang - 2.5) * r))]
            pygame.draw.polygon(sc, (220, 50, 50), pts)
            pygame.draw.polygon(sc, (255, 200, 200), pts, 2)
        # joystick
        if self.joy_id is not None:
            cx, cy = self.joy_c
            kx, ky = self.joy_p
        else:
            cx, cy = self.joy_def
            kx, ky = cx, cy
        jr = self.joy_base.get_width() // 2
        sc.blit(self.joy_base, (I(cx) - jr, I(cy) - jr))
        kr = self.joy_knob.get_width() // 2
        sc.blit(self.joy_knob, (I(kx) - kr, I(ky) - kr))
        self._draw_btn('run', bool(self.run_ids) or self.s_run)
        self._draw_btn('pause', False)
        for k in ('tpf', 'tpb'):
            self._draw_btn(k, self.tp_cd > 0)
            if self.tp_cd > 0:
                c = self.btn[k]
                draw_text(sc, "%d" % math.ceil(self.tp_cd), I(c[2] * 0.7), (255, 255, 255),
                          center=(c[0], c[1] + c[2] * 0.5))

    def _draw_btn(self, name, pressed):
        c = self.btn[name]
        img = self.btn_img[name][1 if pressed else 0]
        r = img.get_width() // 2
        self.screen.blit(img, (I(c[0]) - r, I(c[1]) - r))


async def main():
    game = Game()
    await game.run()


if __name__ == "__main__" or sys.platform == "emscripten":
    asyncio.run(main())
