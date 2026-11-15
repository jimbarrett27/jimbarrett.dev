"""Redraw sketched flowcharts and plots found in a transcript.

The transcription pass marks each drawing it sees: ``[figure:flowchart: ...]``,
``[figure:plot: ...]``, or ``[sketch: ...]`` for doodles, which are left alone. Each
figure marker gets a second vision call on its page: flowcharts come back as Mermaid,
which Obsidian renders natively; plots come back as a :class:`PlotSpec` that we draw
with matplotlib, so the model never writes code and every plot looks the same.

A redraw is a bonus on top of the page photo the note already embeds, so any failure
just leaves the marker in place. Each redraw also yields a PNG preview for the chat,
which is never saved.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib
import numpy as np
from matplotlib.figure import Figure as MplFigure
from pydantic import BaseModel

from handwritten_notes import mermaid
from handwritten_notes.transcribe import MODEL, _strip_fences, prepare
from llm.llm_util import get_vision_response
from notes_routing import context
from util.logging_util import setup_logger

logger = setup_logger(__name__)

FIGURE_MODEL = MODEL
PROMPTS = Path(__file__).parent / "prompts"
FLOWCHART_PROMPT = PROMPTS / "flowchart.jinja2"
PLOT_PROMPT = PROMPTS / "plot.jinja2"

MARKER = re.compile(r"^\[figure:(flowchart|plot): (.+)\]$", re.MULTILINE)
PAGE_BREAK = re.compile(r"^---$", re.MULTILINE)
# Mermaid sources start with their diagram type.
MERMAID_TYPES = ("flowchart", "graph", "mindmap", "sequenceDiagram", "stateDiagram",
                 "classDiagram", "erDiagram", "timeline", "quadrantChart", "block")

# A plot's file name depends on the note's name, which only the vault knows, so
# the transcript carries a placeholder that vault.save_note fills in.
PLACEHOLDER = re.compile(r"\{\{figure-(\d+)\}\}")
# A redrawn figure as it sits in the transcript: the plot embed or Mermaid block,
# then its caption line.
CHAT_FIGURE = re.compile(
    r"^(?:!\[\[\{\{figure-\d+\}\}\]\]|```mermaid\n.*?^```)\n\*[^\n]*\*$\n?",
    re.MULTILINE | re.DOTALL)
BLANK_RUN = re.compile(r"\n{3,}")
PREVIEW_DPI = 200


def placeholder(n: int) -> str:
    return f"{{{{figure-{n}}}}}"


@dataclass(frozen=True)
class Marker:
    kind: str
    description: str
    page: int  # 0-based
    start: int
    end: int


@dataclass(frozen=True)
class Preview:
    description: str
    png: bytes


@dataclass(frozen=True)
class Redrawn:
    transcript: str
    svgs: list[bytes]  # plot SVGs; svgs[0] stands in for {{figure-1}}
    previews: list[Preview]  # one per figure that could be rendered, in order


def find_figures(transcript: str, pages: int = 1) -> list[Marker]:
    """Figure markers in order, each with the page it sits on."""
    found = []
    for m in MARKER.finditer(transcript):
        page = len(PAGE_BREAK.findall(transcript, 0, m.start()))
        found.append(Marker(m.group(1), m.group(2).strip(), min(page, pages - 1),
                            m.start(), m.end()))
    return found


class Curve(BaseModel):
    label: str | None = None
    kind: Literal["line", "scatter"] = "line"
    style: Literal["solid", "dashed", "dotted"] = "solid"
    points: list[tuple[float, float]]


class Annotation(BaseModel):
    x: float
    y: float
    text: str


class PlotSpec(BaseModel):
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    x_range: tuple[float, float] | None = None
    y_range: tuple[float, float] | None = None
    show_ticks: bool = False
    x_log: bool = False
    y_log: bool = False
    curves: list[Curve]
    annotations: list[Annotation] = []


def smooth(points: list[tuple[float, float]], steps: int = 12) -> np.ndarray:
    """A Catmull-Rom spline through the points: sketched curves are drawn smooth, but
    the model can only give us a few points, which a plain line would join with corners."""
    p = np.asarray(points, dtype=float)
    if len(p) < 3:
        return p
    p = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])  # mirror the ends
    t = np.linspace(0, 1, steps, endpoint=False)[:, None]
    segments = [
        0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
               + (3 * p1 - p0 - 3 * p2 + p3) * t**3)
        for p0, p1, p2, p3 in zip(p, p[1:], p[2:], p[3:])
    ]
    return np.vstack(segments + [p[-2]])


def render_plot(spec: PlotSpec, fmt: Literal["svg", "png"] = "svg") -> bytes:
    """Draw a plot spec; SVGs keep their text as text so Obsidian can search it."""
    with matplotlib.rc_context({"svg.fonttype": "none", "font.size": 11}):
        fig = MplFigure(figsize=(6, 4))
        ax = fig.subplots()
        for curve in spec.curves:
            # Colours only need to differ when a legend tells curves apart; an
            # unlabelled guide line in a second colour just looks like noise.
            color = None if curve.label else "C0"
            if curve.kind == "scatter":
                ax.scatter(*zip(*curve.points), label=curve.label, color=color)
            else:
                ax.plot(*smooth(curve.points).T, linestyle=curve.style, label=curve.label,
                        color=color)

        if spec.x_log:
            ax.set_xscale("log")
        if spec.y_log:
            ax.set_yscale("log")
        if spec.x_range:
            ax.set_xlim(*spec.x_range)
        if spec.y_range:
            ax.set_ylim(*spec.y_range)
        if not spec.show_ticks:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.minorticks_off()
        ax.set_title(spec.title or "")
        # Axis labels at the ends of the axes, as they're sketched; this also keeps
        # the middle of the x-axis free for notes written under it.
        ax.set_xlabel(spec.x_label or "", loc="right")
        ax.set_ylabel(spec.y_label or "", loc="top")
        ax.spines[["top", "right"]].set_visible(False)
        if any(c.label for c in spec.curves):
            ax.legend(frameon=False)
        bottom = ax.get_ylim()[0]
        for note in spec.annotations:
            # Notes are often written under the x-axis, e.g. naming a point on it; how far
            # under is noise from the sketch, so tuck them just beneath the axis line.
            if note.y < bottom:
                ax.annotate(note.text, (note.x, bottom), xytext=(0, -6), textcoords="offset points",
                            annotation_clip=False, ha="center", va="top")
            else:
                ax.annotate(note.text, (note.x, note.y), ha="center", va="bottom")

        out = io.BytesIO()
        fig.savefig(out, format=fmt, bbox_inches="tight", dpi=PREVIEW_DPI)
    return out.getvalue()


def redraw_flowchart(page: tuple[bytes, str], description: str, model: str = FIGURE_MODEL) -> str:
    source = _strip_fences(get_vision_response(
        str(FLOWCHART_PROMPT), {"description": description, "context": context.about()},
        [prepare(*page)], model_name=model))
    if not source.startswith(MERMAID_TYPES):
        raise ValueError(f"not a Mermaid diagram: {source[:80]!r}")
    return source


def redraw_plot(page: tuple[bytes, str], description: str, model: str = FIGURE_MODEL) -> PlotSpec:
    raw = _strip_fences(get_vision_response(
        str(PLOT_PROMPT), {"description": description, "context": context.about()},
        [prepare(*page)], model_name=model))
    return PlotSpec.model_validate_json(raw)


def _flowchart_preview(source: str) -> bytes | None:
    # The note's Mermaid is rendered by Obsidian either way; only the chat misses out.
    try:
        return mermaid.render_png(source)
    except Exception:
        logger.exception("Couldn't render a flowchart preview")
        return None


def redraw_all(transcript: str, pages: list[tuple[bytes, str]],
               model: str = FIGURE_MODEL) -> Redrawn:
    """Replace each figure marker with its redraw."""
    svgs: list[bytes] = []
    previews: list[Preview] = []
    parts, last = [], 0
    for marker in find_figures(transcript, len(pages)):
        page = pages[marker.page]
        try:
            if marker.kind == "flowchart":
                source = redraw_flowchart(page, marker.description, model)
                drawn = f"```mermaid\n{source}\n```"
                png = _flowchart_preview(source)
            else:
                spec = redraw_plot(page, marker.description, model)
                svgs.append(render_plot(spec))
                drawn = f"![[{placeholder(len(svgs))}]]"
                png = render_plot(spec, "png")
        except Exception:
            logger.exception(f"Couldn't redraw {marker.kind} {marker.description!r}")
            continue
        if png:
            previews.append(Preview(marker.description, png))
        parts += [transcript[last:marker.start], f"{drawn}\n*{marker.description}*"]
        last = marker.end
    parts.append(transcript[last:])
    return Redrawn("".join(parts), svgs, previews)


def for_chat(transcript: str) -> str:
    """Drop redrawn figures from the chat text: Telegram shows neither plot embeds nor
    Mermaid, and each one follows as a captioned preview image anyway."""
    return BLANK_RUN.sub("\n\n", CHAT_FIGURE.sub("", transcript)).strip()
