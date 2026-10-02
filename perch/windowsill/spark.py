"""spark: a node's vitals history as a sparkline, drawn on the server as inline SVG (design plan 3.5, docs/06 6).

No chart library and no JavaScript. The line is ``currentColor`` set to ``--muted`` in the CSS: **colour means
state only** (docs/06 2), so a sparkline never turns red; a breached threshold shows as the usual badge.

- The scale is fixed, 0 to 100 %: CPU, RAM and disk are percentages, and the same height means the same load on
  every node and every day (an idle node is a flat line at the bottom, not a mountain range of noise).
- The span is cut into equal columns; a column holds the mean of the stored buckets that fall in it. A column
  with none is a **gap**: the line breaks there. Nothing is interpolated, so a stretch where Komodo was
  unreachable or perch was stopped looks like what it was.
- Every sparkline has a text alternative, ``RAM 24 h: 41-63 %, now 58 %`` (the lowest and highest column,
  and the latest figure), plus ``, with gaps`` when there are any. The SVG is ``role="img"`` with that as its
  label, so a screen reader reads it as one sentence instead of tracing a path.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from markupsafe import Markup, escape

WIDTH_UNIT = 1  # one SVG unit per column: the SVG is stretched to its box (preserveAspectRatio none)
HEIGHT = 28
PAD = 2


def columns(points: Sequence[tuple[datetime, float]], start: datetime, end: datetime, cols: int) -> list[float | None]:
    """Mean of the points in each of ``cols`` equal slices of [start, end); None where a slice has none."""
    span = (end - start).total_seconds()
    sums = [0.0] * cols
    counts = [0] * cols
    for at, value in points:
        offset = (at - start).total_seconds()
        if offset < 0 or offset >= span:
            continue
        i = min(cols - 1, int(offset / span * cols))
        sums[i] += value
        counts[i] += 1
    return [sums[i] / counts[i] if counts[i] else None for i in range(cols)]


def _y(value: float) -> float:
    clamped = max(0.0, min(100.0, value))
    return round(HEIGHT - PAD - clamped / 100 * (HEIGHT - 2 * PAD), 2)


def path(values: Sequence[float | None]) -> str:
    """SVG path data: one subpath per run of columns that have data, so a gap breaks the line. A run of one
    column is drawn as a dot (a zero-length segment with a round cap)."""
    parts: list[str] = []
    run: list[tuple[float, float]] = []

    def flush() -> None:
        if len(run) == 1:
            x, y = run[0]
            parts.append(f"M{x:g},{y:g}h0")
        elif run:
            parts.append("M" + " L".join(f"{x:g},{y:g}" for x, y in run))
        run.clear()

    for i, value in enumerate(values):
        if value is None:
            flush()
        else:
            run.append((i + 0.5, _y(value)))
    flush()
    return " ".join(parts)


def altText(label: str, span: str, values: Sequence[float | None], now: float | None) -> str:
    found = [v for v in values if v is not None]
    if not found:
        return f"{label} {span}: no history yet"
    last = now if now is not None else found[-1]
    gaps = ", with gaps" if None in values[values.index(found[0]) :] else ""
    return f"{label} {span}: {round(min(found))}-{round(max(found))} %, now {round(last)} %{gaps}"


def sparkline(
    points: Sequence[tuple[datetime, float]],
    *,
    start: datetime,
    end: datetime,
    cols: int,
    label: str,
    span: str,
    now: float | None = None,
) -> Markup:
    """One inline SVG, or a sentence when there is nothing to draw yet."""
    values = columns(points, start, end, cols)
    text = altText(label, span, values, now)
    if all(v is None for v in values):
        return Markup('<span class="spark-none faint small">{}</span>').format(text)
    return Markup(
        '<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="{t}" '
        'focusable="false"><path class="base" d="M0,{b}H{w}"/><path class="line" d="{d}"/></svg>'
    ).format(w=cols * WIDTH_UNIT, h=HEIGHT, t=escape(text), b=HEIGHT - PAD, d=path(values))
