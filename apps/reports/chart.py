"""A small grouped bar chart as inline SVG (no scripts, works offline and in PDF).

It only draws values it is given. Bar height is the stored value over the axis maximum.
"""

from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

WIDTH, HEIGHT, LEFT, TOP, BOTTOM = 720, 260, 36, 14, 52
COLOURS = ("#4c78a8", "#f58518", "#54a24b", "#b279a2")
AXIS_MAX = Decimal(3)


def _pixels(value: Decimal, plot_height: int, axis_max: Decimal) -> int:
    return int((value / axis_max * plot_height).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def bar_chart(codes: list[str], series: list[tuple[str, list[Decimal | None]]]) -> str:
    """One group per outcome code, one bar per batch. A missing value draws no bar."""
    if not codes or not series:
        return ""
    values = [v for _, points in series for v in points if v is not None]
    axis_max = max([AXIS_MAX, *values])
    plot_h = HEIGHT - TOP - BOTTOM
    group_w = Decimal(WIDTH - LEFT - 8) / len(codes)
    bar_w = max(int(group_w / (len(series) + 1)), 2)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Three-batch comparison">',
        f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{TOP + plot_h}" stroke="#444"/>',
        f'<line x1="{LEFT}" y1="{TOP + plot_h}" x2="{WIDTH - 8}" y2="{TOP + plot_h}" '
        'stroke="#444"/>',
        f'<text x="2" y="{TOP + 8}" font-size="9">{escape(str(axis_max.normalize()))}</text>',
        f'<text x="2" y="{TOP + plot_h}" font-size="9">0</text>',
    ]
    for i, code in enumerate(codes):
        x0 = LEFT + int(group_w * i) + 4
        for j, (_, points) in enumerate(series):
            value = points[i]
            if value is None:
                continue
            h = _pixels(value, plot_h, axis_max)
            x = x0 + j * bar_w
            parts.append(
                f'<rect x="{x}" y="{TOP + plot_h - h}" width="{bar_w - 1}" height="{h}" '
                f'fill="{COLOURS[j % len(COLOURS)]}"/>'
            )
        parts.append(f'<text x="{x0}" y="{TOP + plot_h + 12}" font-size="8">{escape(code)}</text>')
    for j, (label, _) in enumerate(series):
        x = LEFT + j * 170
        y = HEIGHT - 12
        parts.append(f'<rect x="{x}" y="{y - 8}" width="9" height="9" fill="{COLOURS[j % 4]}"/>')
        parts.append(f'<text x="{x + 13}" y="{y}" font-size="9">{escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)
