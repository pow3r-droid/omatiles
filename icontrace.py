"""An app icon's own shape as a one-color SVG path, for apps no logo set covers.

The icon (a PNG from the icon theme) is read with the standard library only. Its
shape is what stands out from its background: from transparency when it sits on
nothing, or from the tile's color when it sits on a tile (a black knot on white,
a light face on dark). That field is traced with marching squares at sub-pixel
precision, so outlines come out smooth, and written as a path on a 24 x 24 box,
filled even-odd, the way the dock draws logos.
"""
import struct
import zlib
from pathlib import Path

GRID = 96  # the field is sampled on a GRID x GRID raster


# ── PNG ────────────────────────────────────────────────────────────────────────
def read_png(path):
    """(width, height, rows of (r, g, b, a) tuples) for an 8-bit, non-interlaced PNG."""
    data = Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    pos, idat, palette, trns = 8, [], None, None
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b'tRNS':
            trns = body
        elif kind == b'IDAT':
            idat.append(body)
        elif kind == b'IEND':
            break
    if depth != 8 or interlace:
        raise ValueError('only 8-bit, non-interlaced PNGs')
    if w * h > 1024 * 1024:
        raise ValueError('too big for an icon')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b''.join(idat))
    stride, prev, rows, i = w * channels, bytearray(w * channels), [], 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b, c = prev[x], prev[x - channels] if x >= channels else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        px = []
        for x in range(w):
            s = line[x * channels:(x + 1) * channels]
            if ctype == 6: px.append(tuple(s))
            elif ctype == 2: px.append((s[0], s[1], s[2], 255))
            elif ctype == 0: px.append((s[0], s[0], s[0], 255))
            elif ctype == 4: px.append((s[0], s[0], s[0], s[1]))
            else:
                r, g, bl = palette[s[0]]
                px.append((r, g, bl, trns[s[0]] if trns and s[0] < len(trns) else 255))
        rows.append(px)
    return w, h, rows


# ── The shape ──────────────────────────────────────────────────────────────────
def sample(w, h, rows, n=GRID):
    """The icon box-averaged onto an n x n grid, premultiplied: [(r, g, b, a)] floats 0-1."""
    out = []
    for gy in range(n):
        y0, y1 = gy * h // n, max(gy * h // n + 1, (gy + 1) * h // n)
        line = []
        for gx in range(n):
            x0, x1 = gx * w // n, max(gx * w // n + 1, (gx + 1) * w // n)
            r = g = b = a = 0.0
            cnt = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    pr, pg, pb, pa = rows[y][x]
                    k = pa / 255.0
                    r += pr / 255.0 * k; g += pg / 255.0 * k; b += pb / 255.0 * k; a += k
                    cnt += 1
            line.append((r / cnt, g / cnt, b / cnt, a / cnt))
        out.append(line)
    return out


def tile_color(px):
    """The color of the tile the icon is drawn on, or None when it has no tile: the
    icon's opaque part must be a near-full (rounded) square, and its outer ring
    mostly one color."""
    n = len(px)
    opaque = [[p[3] > 0.9 for p in line] for line in px]
    cells = [(y, x) for y in range(n) for x in range(n) if opaque[y][x]]
    if len(cells) < 0.55 * n * n:
        return None
    ys, xs = [c[0] for c in cells], [c[1] for c in cells]
    if max(ys) - min(ys) < 0.85 * n or max(xs) - min(xs) < 0.85 * n:
        return None
    ring = []
    for y, x in cells:
        if any(not (0 <= yy < n and 0 <= xx < n) or not opaque[yy][xx]
               for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1))):
            r, g, b, a = px[y][x]
            ring.append((r / a, g / a, b / a))
    counts = {}
    for c in ring:
        q = tuple(int(v * 7.99) for v in c)
        counts[q] = counts.get(q, 0) + 1
    mode, share = max(counts.items(), key=lambda kv: kv[1])
    if share < 0.5 * len(ring):
        return None
    near = [c for c in ring if tuple(int(v * 7.99) for v in c) == mode]
    return [sum(c[i] for c in near) / len(near) for i in range(3)]


def field(px):
    """How much each cell is the icon's shape, 0-1: what differs from the tile, or
    what's opaque when there is no tile. Lightly blurred, so outlines trace smooth."""
    tile = tile_color(px)
    if tile is None:
        f = [[p[3] for p in line] for line in px]
    else:
        f = []
        for line in px:
            row = []
            for r, g, b, a in line:
                if a < 0.5:
                    row.append(0.0)
                    continue
                d = max(abs(r / a - tile[0]), abs(g / a - tile[1]), abs(b / a - tile[2]))
                row.append(min(1.0, d / 0.35) * a)
            f.append(row)
    return blur(f)


def blur(f):
    """A 3 x 3 [1 2 1] blur."""
    n = len(f)
    get = lambda y, x: f[min(n - 1, max(0, y))][min(n - 1, max(0, x))]
    w = ((1, 2, 1), (2, 4, 2), (1, 2, 1))
    return [[sum(w[j][i] * get(y + j - 1, x + i - 1) for j in range(3) for i in range(3)) / 16.0
             for x in range(n)] for y in range(n)]


# ── Tracing ────────────────────────────────────────────────────────────────────
def contours(f, iso=0.5):
    """Closed outlines of the field at `iso`, as lists of (x, y) points in cells."""
    n = len(f)
    g = [[0.0] * (n + 2)] + [[0.0] + row + [0.0] for row in f] + [[0.0] * (n + 2)]
    m = n + 2
    def at(y, x, y2, x2):
        a, b = g[y][x], g[y2][x2]
        t = (iso - a) / (b - a) if b != a else 0.5
        return (x + (x2 - x) * t - 1, y + (y2 - y) * t - 1)
    segs = {}
    for y in range(m - 1):
        for x in range(m - 1):
            tl, tr, br, bl = g[y][x] > iso, g[y][x + 1] > iso, g[y + 1][x + 1] > iso, g[y + 1][x] > iso
            code = tl * 8 + tr * 4 + br * 2 + bl
            if code in (0, 15):
                continue
            pts = {'T': at(y, x, y, x + 1), 'R': at(y, x + 1, y + 1, x + 1),
                   'B': at(y + 1, x, y + 1, x + 1), 'L': at(y, x, y + 1, x)}
            keys = {'T': (y, x, 'h'), 'R': (y, x + 1, 'v'), 'B': (y + 1, x, 'h'), 'L': (y, x, 'v')}
            # Edges walked with the shape on the right, so outer outlines and holes turn opposite ways.
            table = {1: ['LB'], 2: ['BR'], 3: ['LR'], 4: ['RT'], 5: ['LT', 'RB'], 6: ['BT'], 7: ['LT'],
                     8: ['TL'], 9: ['TB'], 10: ['TR', 'BL'], 11: ['TR'], 12: ['RL'], 13: ['RB'], 14: ['BL']}
            for a, b in table[code]:
                segs[keys[a]] = (keys[b], pts[a])
    loops = []
    while segs:
        start, (nxt, p) = segs.popitem()
        loop, key = [p], nxt
        while key in segs and key != start:
            key2, p2 = segs.pop(key)
            loop.append(p2)
            key = key2
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def simplify(pts, tol):
    """Douglas-Peucker on a closed outline."""
    if len(pts) < 4:
        return pts
    def dp(seq):
        a, b = seq[0], seq[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-9
        best, idx = -1, 0
        for i in range(1, len(seq) - 1):
            d = abs(dy * (seq[i][0] - a[0]) - dx * (seq[i][1] - a[1])) / norm
            if d > best:
                best, idx = d, i
        if best <= tol:
            return [a, b]
        return dp(seq[:idx + 1])[:-1] + dp(seq[idx:])
    half = len(pts) // 2
    return dp(pts[:half + 1])[:-1] + dp(pts[half:] + [pts[0]])[:-1]


def area(pts):
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2


def to_path(loops, n=GRID):
    """The outlines on a 24 x 24 box, the shape centered and filling it like a logo does."""
    if not loops:
        return ''
    xs = [p[0] for l in loops for p in l]; ys = [p[1] for l in loops for p in l]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    scale = 24.0 / max(x1 - x0, y1 - y0, 1e-6)
    ox = (24 - (x1 - x0) * scale) / 2 - x0 * scale
    oy = (24 - (y1 - y0) * scale) / 2 - y0 * scale
    out = []
    for l in loops:
        pts = ['%.2f %.2f' % (x * scale + ox, y * scale + oy) for x, y in l]
        out.append('M' + 'L'.join(pts) + 'Z')
    return ''.join(out).replace('.00', '')


def trace(path):
    """The icon's shape as a path on a 24 x 24 box, or '' when it has no clear shape
    (a photo, an empty icon, a shape that fills its whole tile)."""
    w, h, rows = read_png(path)
    f = field(sample(w, h, rows))
    cover = sum(v > 0.5 for row in f for v in row) / float(GRID * GRID)
    if not 0.02 < cover < 0.8:
        return ''
    loops = [simplify(l, 0.35) for l in contours(f)]
    big = max((area(l) for l in loops), default=0)
    loops = [l for l in loops if len(l) >= 3 and area(l) >= max(2.0, big * 0.004)]
    if not loops or len(loops) > 400:
        return ''
    return to_path(loops)
