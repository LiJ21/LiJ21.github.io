"""Draw the note's editable SVG diagrams; uses only the Python standard library."""
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'assets/posts/qleaf-inference-latency'
OUT.mkdir(parents=True, exist_ok=True)
INK, BLUE, SOFT, LINE = '#172b3e', '#003b71', '#edf3f8', '#bccbd7'


class Diagram:
    def __init__(self, title, height):
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}" role="img" aria-labelledby="title">
<title id="title">{escape(title)}</title>
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8Z" fill="{BLUE}"/></marker></defs>
<rect width="720" height="{height}" fill="white"/>
<g font-family="Arial, Helvetica, sans-serif" fill="{INK}">''']

    def text(self, x, y, text, size=15, bold=False, anchor='start', fill=INK):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{600 if bold else 400}" text-anchor="{anchor}" fill="{fill}">{escape(text)}</text>')

    def rect(self, x, y, w, h, fill=SOFT, stroke=LINE):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="{stroke}"/>')

    def box(self, x, y, w, h, lines, dark=False, size=15):
        self.rect(x, y, w, h, BLUE if dark else SOFT, BLUE if dark else LINE)
        lines = lines.split('\n')
        for i, line in enumerate(lines):
            self.text(x+w/2, y+h/2-(len(lines)-1)*10+5+i*20, line, size, anchor='middle', fill='white' if dark else INK)

    def arrow(self, x1, y1, x2, y2):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{BLUE}" stroke-width="1.6" marker-end="url(#arrow)"/>')

    def rule(self, x1, y1, x2, y2):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{LINE}" stroke-dasharray="5 5"/>')

    def save(self, name):
        (OUT/name).write_text('\n'.join(self.parts)+ '\n</g></svg>\n')


d = Diagram('QLeaf: prepare once, predict repeatedly', 390)
d.text(28, 30, 'FRAMEWORK', 13, True, fill=BLUE)
d.box(28, 54, 190, 62, 'Forest + worker JSON')
d.box(264, 54, 428, 62, 'Inferrer: node buffer + tree partitions', True)
d.arrow(219, 85, 261, 85)
d.text(28, 145, 'INITIALIZATION ABOVE · PER-REQUEST PATH BELOW', 12, True, fill=BLUE)
d.rule(28, 158, 692, 158)
d.box(28, 212, 150, 66, 'Feature row')
d.box(242, 180, 226, 58, 'CPU workers\npersistent host threads')
d.box(242, 258, 226, 58, 'CUDA worker\none-shot or persistent')
d.arrow(179, 240, 239, 209)
d.arrow(179, 250, 239, 287)
d.box(530, 212, 162, 66, 'Collect + sum\nraw margin', True)
d.arrow(469, 209, 527, 240)
d.arrow(469, 287, 527, 250)
d.text(355, 247, 'OR', 12, anchor='middle', fill=BLUE)
d.text(28, 359, 'Same prediction interface; backend and layout selected by C++ types.', 14)
d.save('framework.svg')


def lifetime(name, kind, first, last, persistent_first, persistent_last, resident):
    d = Diagram(f'{kind}: per-request launch versus persistent workers', 340)
    d.text(28, 29, f'{kind.upper()} · PER-REQUEST LAUNCH', 13, True, fill=BLUE)
    for offset, row in [(28, 'row 1'), (380, 'row 2')]:
        d.text(offset, 59, row, 13)
        for i, text in enumerate([first, 'Evaluate', last]):
            x = offset+i*102
            d.box(x, 74, 94, 47, text, dark=(i==1), size=14)
            if i < 2:
                d.arrow(x+95, 97, x+101, 97)
    d.text(28, 151, 'Setup and completion repeated for every row', 14)
    d.rule(28, 170, 692, 170)
    d.text(28, 199, f'{kind.upper()} · PERSISTENT', 13, True, fill=BLUE)
    d.rect(24, 214, 672, 90, '#f8fafc')
    d.text(40, 237, resident, 13)
    for offset in (40, 386):
        for i, text in enumerate([persistent_first, 'Evaluate', persistent_last]):
            x = offset+i*100
            d.box(x, 250, 92, 38, text, dark=(i==1), size=14)
            if i < 2:
                d.arrow(x+93, 269, x+99, 269)
    d.arrow(334, 269, 381, 269)
    d.text(28, 328, 'Schematic sequence; box widths do not represent measured time.', 12, fill='#505050')
    d.save(name)


lifetime('cpu-workers.svg', 'CPU', 'Start', 'Join', 'Publish', 'Collect',
         'Threads created once · pinned workers stay ready between requests')
lifetime('gpu-workers.svg', 'GPU', 'Launch', 'Sync', 'Signal', 'Publish',
         'Kernel launched once · resident blocks wait for successive requests')

d = Diagram('Host-to-host latency includes communication and evaluation', 340)
d.text(28, 29, 'MEASURE THE COMPLETE ROUND TRIP', 13, True, fill=BLUE)
d.rect(252, 60, 145, 222, '#f8fafc')
d.text(324, 86, 'PCIe', 15, True, anchor='middle', fill=BLUE)
d.box(28, 110, 180, 62, 'Host feature row')
d.box(445, 110, 247, 62, 'GPU: evaluate trees', True)
d.arrow(209, 141, 442, 141)
d.text(324, 127, 'input / request', 13, anchor='middle')
d.box(445, 206, 247, 62, 'Coordinate + publish')
d.arrow(568, 173, 568, 203)
d.box(28, 206, 180, 62, 'Host-visible result')
d.arrow(442, 237, 211, 237)
d.text(324, 224, 'output / completion', 13, anchor='middle')
d.text(28, 309, 'The model stays on the GPU; input and result cross for each request.', 14)
d.save('request-path.svg')

d = Diagram('Explicit copies and mapped host input both cross PCIe', 420)
d.text(28, 29, 'EXPLICIT INPUT COPY', 13, True, fill=BLUE)
d.box(28, 70, 172, 64, 'Host row\nmay be pinned')
d.box(338, 70, 160, 64, 'Device buffer')
d.box(548, 70, 144, 64, 'Evaluate', True)
d.arrow(201, 102, 335, 102)
d.text(268, 79, 'cudaMemcpy', 13, anchor='middle')
d.text(268, 123, 'over PCIe', 12, anchor='middle')
d.arrow(499, 102, 545, 102)
d.text(28, 162, 'Transfer the row, then use device-local reads during evaluation.', 14)
d.rule(28, 188, 692, 188)
d.text(28, 218, 'MAPPED PINNED INPUT', 13, True, fill=BLUE)
d.box(28, 258, 172, 64, 'Mapped host row\npinned pages')
d.box(338, 258, 160, 64, 'GPU loads\noptional staging')
d.box(548, 258, 144, 64, 'Evaluate', True)
d.arrow(201, 290, 335, 290)
d.text(268, 267, 'direct loads', 13, anchor='middle')
d.text(268, 312, 'over PCIe', 12, anchor='middle')
d.arrow(499, 290, 545, 290)
d.text(28, 355, 'Avoid the explicit input copy; stage on-device to reuse features.', 14)
d.text(28, 389, 'Pinned ≠ device-local. Mapping removes a copy call, not the interconnect.', 13, fill='#505050')
d.save('input-memory.svg')

d = Diagram('Shared GPU completion versus independent host result slots', 440)
d.text(28, 29, 'SHARED DEVICE-SIDE COMPLETION', 13, True, fill=BLUE)
for i in range(3):
    y = 55+i*49
    d.box(28, y, 155, 34, f'Block {i}: local sum', size=14)
    d.arrow(185, y+17, 271, 120)
d.box(274, 78, 225, 85, 'Atomic sum + counter\nlast block publishes', True)
d.box(555, 91, 137, 58, 'Host result')
d.arrow(500, 120, 552, 120)
d.text(28, 202, 'All blocks update shared completion state on the GPU.', 14)
d.rule(28, 221, 692, 221)
d.text(28, 250, 'INDEPENDENT HOST-VISIBLE SLOTS', 13, True, fill=BLUE)
d.text(268, 276, 'PCIe', 12, True, anchor='middle', fill=BLUE)
d.text(400, 276, 'Pinned host memory', 12, anchor='middle')
d.rule(268, 285, 268, 408)
for i in range(3):
    y = 290+i*45
    d.box(28, y, 155, 32, f'Block {i}: local sum', size=14)
    d.box(331, y, 138, 32, f'Slot {i}', size=14)
    d.arrow(185, y+16, 328, y+16)
    d.arrow(471, y+16, 552, 351)
d.box(555, 321, 137, 60, 'Host collects\nand sums', True, size=14)
d.save('completion.svg')
