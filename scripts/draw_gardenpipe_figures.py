"""Draw the GardenPipe note's figures from data/gardenpipe-note.json; standard library only."""
from html import escape
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets/posts/gardenpipe-bounded-memory'
DATA = json.loads((ROOT / 'data/gardenpipe-note.json').read_text())
OUT.mkdir(parents=True, exist_ok=True)

INK, MUTED, SOFT, LINE, GRID = '#111111', '#505050', '#f5f5f5', '#d2d2d2', '#e6e6e6'
STREAM, CONTROL = '#0550ae', '#d95926'   # Validated pair: site link blue and an opposing orange.
COLD, WARM, MID = (5, 80, 174), (201, 53, 47), (240, 239, 236)
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"


class Figure:
    def __init__(self, title, width, height):
        self.width, self.height = width, height
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">
<title id="title">{escape(title)}</title>
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8Z" fill="{INK}"/></marker></defs>
<rect width="{width}" height="{height}" fill="white"/>
<g font-family="{SANS}" fill="{INK}">''']

    def text(self, x, y, text, size=14, bold=False, anchor='start', fill=INK, mono=False):
        family = f' font-family="{MONO}"' if mono else ''
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{600 if bold else 400}" text-anchor="{anchor}" fill="{fill}"{family}>{escape(text)}</text>')

    def heading(self, text):
        self.text(24, 32, text, 13, bold=True)

    def rect(self, x, y, w, h, fill=SOFT, stroke=LINE, radius=4):
        line = f' stroke="{stroke}"' if stroke else ''
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" fill="{fill}"{line}/>')

    def box(self, x, y, w, h, lines, dark=False, size=14):
        self.rect(x, y, w, h, INK if dark else SOFT, INK if dark else LINE)
        for i, line in enumerate(lines):
            self.text(x + w / 2, y + h / 2 - (len(lines) - 1) * 9 + 5 + i * 18, line, size, anchor='middle', fill='white' if dark else INK)

    def rule(self, x1, y1, x2, y2, stroke=GRID, width=1):
        self.parts.append(f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" fill="none" stroke="{stroke}" stroke-width="{width}"/>')

    def arrow(self, x1, y1, x2, y2):
        self.parts.append(f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" fill="none" stroke="{INK}" stroke-width="1.6" marker-end="url(#arrow)"/>')

    def line(self, points, stroke, width=2, dash=None):
        path = ' '.join(f'{"M" if i == 0 else "L"}{x:.1f} {y:.1f}' for i, (x, y) in enumerate(points))
        dashes = f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{dashes}/>')

    def dot(self, x, y, fill, radius=4):
        # The white ring keeps markers legible where they meet a line.
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 2}" fill="white"/><circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}"/>')

    def cross(self, x, y, stroke, size=6):
        self.parts.append(f'<path d="M{x - size:.1f} {y - size:.1f} L{x + size:.1f} {y + size:.1f} M{x - size:.1f} {y + size:.1f} L{x + size:.1f} {y - size:.1f}" stroke="{stroke}" stroke-width="2.5" stroke-linecap="round"/>')

    def legend(self, x, y, entries):
        for label, color, *dash in entries:
            self.line([(x, y - 7.5), (x + 16, y - 7.5)], color, 3 if not dash else 2, *dash)
            self.text(x + 22, y - 3, label, 13, fill=MUTED)
            x += 34 + 7.4 * len(label)

    def save(self, name):
        (OUT / name).write_text('\n'.join(self.parts) + '\n</g></svg>\n')


class Axes:
    """A linear or logarithmic plot area; ticks are hairlines and labels stay muted."""

    def __init__(self, figure, x, y, w, h, xr, yr, log_x=False):
        self.f, self.x0, self.y0, self.w, self.h, self.xr, self.yr, self.log_x = figure, x, y, w, h, xr, yr, log_x

    def px(self, v):
        lo, hi = self.xr
        t = (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) if self.log_x else (v - lo) / (hi - lo)
        return self.x0 + t * self.w

    def py(self, v):
        lo, hi = self.yr
        return self.y0 + self.h - (v - lo) / (hi - lo) * self.h

    def y_ticks(self, ticks, fmt=str):
        for t in ticks:
            self.f.rule(self.x0, self.py(t), self.x0 + self.w, self.py(t))
            self.f.text(self.x0 - 10, self.py(t) + 4, fmt(t), 12, anchor='end', fill=MUTED, mono=True)

    def x_ticks(self, ticks, fmt=str):
        self.f.rule(self.x0, self.y0 + self.h, self.x0 + self.w, self.y0 + self.h, LINE)
        for t in ticks:
            self.f.text(self.px(t), self.y0 + self.h + 20, fmt(t), 12, anchor='middle', fill=MUTED, mono=True)

    def x_label(self, text):
        self.f.text(self.x0 + self.w / 2, self.y0 + self.h + 42, text, 13, anchor='middle', fill=MUTED)

    def y_label(self, text):
        self.f.text(self.x0, self.y0 - 12, text, 13, fill=MUTED)


def budget():
    f = Figure('What GardenPipe holds in memory, and what grows with the data', 720, 332)
    f.heading('WHAT GROWS, AND WHAT DOES NOT')
    f.text(24, 66, 'On disk', 14, bold=True)
    f.text(24, 86, 'Grows with the data', 13, fill=MUTED)
    for i in range(4):
        f.rect(36 - i * 4, 150 - i * 12, 136, 46, 'white' if i < 3 else SOFT)
    f.text(96, 134, 'One file per date', 14, anchor='middle')
    f.text(96, 214, 'Any number of dates', 13, anchor='middle', fill=MUTED)
    f.rule(216, 50, 216, 306, LINE)
    f.text(240, 66, 'In memory', 14, bold=True)
    f.text(240, 86, 'Fixed by settings you choose', 13, fill=MUTED)
    f.box(240, 104, 138, 72, ['One window', 'plus look-ahead'])
    f.box(408, 104, 118, 72, ['One batch', 'rows × columns'])
    f.box(556, 104, 140, 72, ['Model state', 'depends on model'], dark=True)
    f.arrow(180, 140, 238, 140)
    f.arrow(378, 140, 406, 140)
    f.arrow(526, 140, 554, 140)
    f.box(240, 194, 286, 46, ['Prefetch budget, counted in bytes'])
    f.box(240, 256, 456, 40, ['Interpreter, libraries, reader buffers'])
    f.save('budget.svg')


def scale():
    rows = DATA['scale']
    f = Figure('Peak memory against dataset size, streaming and materialized', 720, 356)
    f.heading('PEAK MEMORY AS THE DATA GROW')
    f.legend(24, 62, [('Materialized in memory', CONTROL), ('Streamed', STREAM)])
    top = max(r['peak_gib'] for r in rows if r['mode'] == 'materialize')
    ax = Axes(f, 72, 100, 590, 190, (0, 380), (0, math.ceil(top / 5) * 5))
    ax.y_label('Peak RSS, GiB')
    ax.y_ticks(range(0, math.ceil(top / 5) * 5 + 1, 5))
    ax.x_ticks([0, 90, 180, 270, 360])
    ax.x_label('Rows in the dataset, millions')
    for mode, color in (('materialize', CONTROL), ('stream', STREAM)):
        points = [(ax.px(r['rows_m']), ax.py(r['peak_gib'])) for r in rows if r['mode'] == mode]
        f.line(points, color)
        for x, y in points:
            f.dot(x, y, color)
    last = {m: [r for r in rows if r['mode'] == m][-1] for m in ('materialize', 'stream')}
    f.text(ax.px(last['materialize']['rows_m']) - 10, ax.py(last['materialize']['peak_gib']) - 12, f"{last['materialize']['peak_gib']:.1f} GiB", 13, bold=True, anchor='end')
    f.text(ax.px(last['stream']['rows_m']) - 2, ax.py(last['stream']['peak_gib']) - 14, f"{last['stream']['peak_gib']:.1f} GiB", 13, bold=True, anchor='end')
    f.save('scale.svg')


def density():
    d = DATA['density']
    f = Figure('Peak memory against rows per date, before and after the two fixes', 720, 356)
    f.heading('PEAK MEMORY AS EACH DATE GROWS')
    f.legend(24, 62, [('First version', CONTROL), ('Both fixes', STREAM), ('Both fixes, same look-ahead in rows', STREAM, '2 5')])
    ax = Axes(f, 72, 100, 590, 190, (0.8, 110), (0, 1.25), log_x=True)
    ax.y_label('Peak RSS, GiB')
    ax.y_ticks([0, 0.5, 1.0], lambda v: f'{v:.1f}')
    ax.x_ticks([1, 4, 10, 20, 40, 80], lambda v: f'{v}M')
    ax.x_label('Rows per date, five dates (logarithmic)')
    f.rule(ax.x0, ax.py(1), ax.x0 + ax.w, ax.py(1), INK)
    f.text(ax.x0 + 6, ax.py(1) - 7, '1 GiB', 13)
    for name, color, dash in (('first', CONTROL, None), ('fixed', STREAM, None), ('same_lookahead', STREAM, '2 5')):
        points = [(ax.px(x), ax.py(y / 1024)) for x, y in d[name]]
        f.line(points, color, 2, dash)
        if not dash:
            for x, y in points:
                f.dot(x, y, color)
    for name in ('first', 'fixed'):
        x, y = d[name][-1]
        f.text(ax.px(x) + 10, ax.py(y / 1024) + 5, f'{y / 1024:.1f} GiB' if y >= 1024 else f'{y} MiB', 13, bold=True)
    x, y = d['same_lookahead'][-1]
    f.text(ax.px(x) + 10, ax.py(y / 1024) + 11, f'{y} MiB', 13, bold=True)
    f.save('density.svg')


def cap():
    d = DATA['cap']
    f = Figure('Memory over time for the same job under a one gibibyte limit', 720, 320)
    f.heading('THE SAME JOB UNDER A 1 GiB LIMIT')
    f.legend(24, 62, [('Materialized', CONTROL), ('Streamed', STREAM)])
    span = max(p[0] for p in d['stream'])
    ax = Axes(f, 72, 100, 590, 160, (0, span), (0, 1.2))
    ax.y_label('RSS, GiB')
    ax.y_ticks([0, 0.5, 1.0], lambda v: f'{v:.1f}')
    step = 30 if span < 240 else 60
    ax.x_ticks(range(0, int(span) + 1, step))
    ax.x_label('Seconds since the process started')
    f.rule(ax.x0, ax.py(1), ax.x0 + ax.w, ax.py(1), INK, 1)
    f.text(ax.x0 + ax.w, ax.py(1) - 7, '1 GiB limit', 13, anchor='end')
    f.line([(ax.px(t), ax.py(v)) for t, v in d['stream']], STREAM)
    f.line([(ax.px(t), ax.py(v)) for t, v in d['materialize']], CONTROL)
    x, y = d['materialize'][-1]
    f.cross(ax.px(x), ax.py(y), CONTROL)
    f.text(ax.px(x) + 15, ax.py(1) + 19, f'Killed at {d["killed_after"]:.0f} s', 13, bold=True)
    f.text(ax.px(d['stream'][-1][0]), ax.py(d['stream'][-1][1]) + 24, 'Finished', 13, bold=True, anchor='end')
    f.save('cap.svg')


def weeks():
    f = Figure('Observed temperature and six-hour forecasts for two weeks of 2015', 720, 444)
    f.heading('SIX-HOUR FORECASTS, TWO FIXED WEEKS OF 2015')
    f.legend(24, 62, [('Observed', INK), ('Ridge', STREAM), ('Persistence', CONTROL)])
    for i, (name, label, days) in enumerate((('winter', 'Winter', '12–18 January'), ('summer', 'Summer', '13–19 July'))):
        rows = DATA['weeks'][name]
        low = math.floor(min(min(r[1:]) for r in rows) / 5) * 5
        high = math.ceil(max(max(r[1:]) for r in rows) / 5) * 5
        ax = Axes(f, 72, 92 + i * 172, 590, 128, (0, 7), (low, high))
        step = 5 if high - low <= 25 else 10
        ax.y_ticks(range(low, high + 1, step), lambda v: f'{v}°')
        f.text(ax.x0 + ax.w, ax.y0 - 8, f'{label}, {days}', 13, anchor='end', fill=MUTED)
        ax.x_ticks(range(0, 8), lambda v: f'{v}')
        for col, color, width in ((3, CONTROL, 2), (2, STREAM, 2), (1, INK, 2)):
            f.line([(ax.px(r[0]), ax.py(r[col])) for r in rows], color, width)
    f.text(72 + 295, 434, 'Days since Monday', 13, anchor='middle', fill=MUTED)
    f.save('weeks.svg')


def colour(v, limit=2.0):
    t = max(-1.0, min(1.0, v / limit))
    pole = WARM if t > 0 else COLD
    t = abs(t)
    return '#%02x%02x%02x' % tuple(round(MID[i] + (pole[i] - MID[i]) * t) for i in range(3))


def bias_map():
    f = Figure('Mean forecast bias by month and issue hour for two models', 720, 396)
    f.heading('MEAN FORECAST ERROR BY MONTH AND ISSUE HOUR')
    months = 'JFMAMJJASOND'
    panels = (('ridge', 'Ridge', 44), ('boosting', 'Gradient boosting', 392))
    cell_w, cell_h = 12.4, 19
    for key, label, x0 in panels:
        f.text(x0, 66, label, 14, bold=True)
        for m, h, b in DATA['bias'][key]:
            f.rect(x0 + h * cell_w, 80 + (m - 1) * cell_h, cell_w - 1, cell_h - 1, colour(b), None, 1)
        for m in range(12):
            f.text(x0 - 8, 80 + m * cell_h + 14, months[m], 12, anchor='end', fill=MUTED, mono=True)
        for h in (0, 6, 12, 18):
            f.text(x0 + h * cell_w + cell_w / 2, 80 + 12 * cell_h + 18, f'{h:02d}', 12, anchor='middle', fill=MUTED, mono=True)
    f.text(44 + 149, 80 + 12 * cell_h + 38, 'Hour the forecast is issued', 13, anchor='middle', fill=MUTED)
    f.text(392 + 149, 80 + 12 * cell_h + 38, 'Hour the forecast is issued', 13, anchor='middle', fill=MUTED)
    x, y, w = 240, 352, 240
    for i in range(41):
        f.rect(x + i * w / 41, y, w / 41 + 0.5, 12, colour(-2 + i * 0.1), None, 0)
    f.text(x - 10, y + 11, '−2 °C, too cold', 12, anchor='end', fill=MUTED)
    f.text(x + w + 10, y + 11, '+2 °C, too warm', 12, fill=MUTED)
    f.save('bias-map.svg')


def width():
    d = DATA['width']
    f = Figure('Test error against the number of model features', 720, 340)
    f.heading('SPENDING MEMORY ON WIDTH')
    ax = Axes(f, 72, 74, 590, 196, (12, 6000), (1.3, 1.75), log_x=True)
    ax.y_label('Test MAE, °C')
    ax.y_ticks([1.3, 1.4, 1.5, 1.6, 1.7], lambda v: f'{v:.1f}')
    ax.x_ticks([18, 518, 2018, 4018], lambda v: f'{v:,}')
    ax.x_label('Features in the linear model (logarithmic)')
    y = ax.py(d['boosting'])
    f.rule(ax.x0, y, ax.x0 + ax.w, y, INK)
    f.text(ax.x0 + 6, y - 8, f"Gradient boosting, {d['boosting']:.2f} °C, holds rows in memory", 13)
    f.line([(ax.px(p['d']), ax.py(p['mae'])) for p in d['points']], STREAM)
    for p in d['points']:
        f.dot(ax.px(p['d']), ax.py(p['mae']), STREAM)
    for p, anchor, dx in zip(d['points'], ('start', 'start', 'end', 'start'), (10, 10, -6, -6)):
        f.text(ax.px(p['d']) + dx, ax.py(p['mae']) - 14, p['label'], 13, bold=True, anchor=anchor)
    f.save('width.svg')


budget()
scale()
density()
cap()
weeks()
bias_map()
width()
