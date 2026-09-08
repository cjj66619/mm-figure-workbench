#!/usr/bin/env python3
"""fig_layout_lint.py — 数据图版式自检：字图重合、越界、尺寸不均、字号异常、配色越界。

初稿的图往往"看起来正确"，仔细看却有文字压线、图例盖住曲线、面板大小不一、
同一变量在两张图里颜色不同等问题。本模块提供两层检查：

1. ``lint_figure(fig)``：在 Matplotlib Figure 对象上做**精确**检查（save_fig 内自动调用）：
   - text_overlap          文字与文字的包围盒重叠（含刻度标签拥挤）
   - text_clipped          文字超出画布
   - legend_over_data      图例包围盒覆盖了数据线/柱
   - text_over_data        注释文字覆盖了数据线
   - font_too_small / font_size_spread   字号 < 5 pt；字号种类过多或极差过大
   - color_off_palette     线/柱颜色不在允许调色板中（渐变色图不检查）
   - label_color_mismatch  同一图例标签在不同面板颜色不一致
   - panel_size_uneven     多面板尺寸差异 > 15%
   - panel_label_misaligned 面板标签 (a)(b) 相对位置不一致
   - legend_too_long       图例条目 > 8
   - fig_too_wide          图宽 > 16 cm 版心
   - missing_axis_label    有数据但缺坐标轴标签（INFO）
2. ``lint_pdf(pdf)``：对已导出的 PDF 做**近似**检查（可离线复查任意图，含 drawio 导出）：
   - pdf_word_overlap      提取到的词包围盒互相重叠
   - pdf_text_outside      文字超出页面
   - pdf_line_through_text 线段穿过文字

结果等级：FAIL（必须修）/ WARN（人工审图确认）/ INFO（提示）。默认只有 lint 自身
异常和明显越界才 FAIL；`--strict` 把 WARN 也当失败，可作交付门禁。

命令行::

    python tools/fig_layout_lint.py figures/                # 遍历 figures/*/ 的 PDF，更新各 review.json 的 auto.pdf
    python tools/fig_layout_lint.py figures/fig02_q1_fit/fig02_q1_fit.pdf --strict
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Finding", "lint_figure", "lint_pdf", "ALLOWED_EXTRA_COLORS"]

_CM = 1 / 2.54
TEXT_WIDTH_CM = 16.0
MIN_FONT_PT = 5.0
MIN_TEXT_GAP_PT = 3.0    # 非刻度文字之间的最小间隙，小于此值计为拥挤
# 允许出现但不计入"配色越界"的中性色（坐标轴、网格、误差线、参考线）
ALLOWED_EXTRA_COLORS = {"#000000", "#ffffff", "#7f7f7f", "#808080", "#4d4d4d", "#a6a6a6", "#cccccc", "#e5e5e5",
                        "#bababa", "#333333", "#666666", "#999999", "#d9d9d9", "#f0f0f0"}
_PANEL_LABEL = re.compile(r"^\(?[a-zA-Z]\)?$")


@dataclass
class Finding:
    level: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


def _short(text: str, n: int = 18) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


MAX_TEXT_UNITS = 36      # 单行最大“字宽”：中文 1 字 = 1，Latin 1 字符 = 0.5
MAX_TEXT_LINES = 2


def _text_units(text: str) -> float:
    """估算最长一行的字宽（中文 1，其它 0.5；忽略 mathtext 的 $ 与 \\ 控制符）。"""
    best = 0.0
    for line in text.split("\n"):
        line = re.sub(r"\\[a-zA-Z]+|[$^_{}]", "", line)
        best = max(best, sum(1.0 if ord(ch) > 0x2E7F else 0.5 for ch in line))
    return best


def _too_verbose(text: str) -> bool:
    return _text_units(text) > MAX_TEXT_UNITS or text.count("\n") + 1 > MAX_TEXT_LINES


def _bbox_overlap(a, b) -> float:
    """两个 Bbox 的交叠面积占较小者面积的比例。"""
    x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
    x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    small = min(a.width * a.height, b.width * b.height)
    return inter / small if small > 0 else 0.0


def _to_hex(color) -> str | None:
    try:
        from matplotlib.colors import to_hex, to_rgba
        rgba = to_rgba(color)
    except (ValueError, TypeError):
        return None
    if rgba[3] == 0:
        return None
    return to_hex(rgba[:3]).lower()


def _palette_set(palette: str | None) -> set[str]:
    try:
        from mm_plot_style import PALETTES
    except ImportError:
        return set()
    if palette is None:
        return {c.lower() for cols in PALETTES.values() for c in cols}
    return {c.lower() for c in PALETTES.get(palette, [])}


def _visible_ticklabels(axis) -> list:
    """只取落在视图区间内的刻度标签（Matplotlib 会为越界刻度也建 Text 对象，但不绘制）。"""
    lo, hi = sorted(axis.get_view_interval())
    eps = (hi - lo) * 1e-9
    out = []
    for which in ("major", "minor"):
        locs = axis.get_majorticklocs() if which == "major" else axis.get_minorticklocs()
        labels = axis.get_majorticklabels() if which == "major" else axis.get_minorticklabels()
        for loc, lab in zip(locs, labels):
            if lo - eps <= loc <= hi + eps:
                out.append(lab)
    return out


def _is_colorbar(ax) -> bool:
    return ax.get_label() == "<colorbar>" or getattr(ax, "_colorbar", None) is not None


# --------------------------------------------------------------------------- #
# 1. Figure 对象精确检查
# --------------------------------------------------------------------------- #
def lint_figure(fig, *, palette: str | None = "default", base_size: float = 9.0,
                max_width_cm: float = TEXT_WIDTH_CM, min_font_pt: float = MIN_FONT_PT) -> list[Finding]:
    import matplotlib.text as mtext
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    from matplotlib.transforms import Bbox

    out: list[Finding] = []
    try:
        renderer = fig.canvas.get_renderer()
    except AttributeError:  # 非 Agg 后端
        renderer = fig._get_renderer()
    fig_bbox = Bbox([[0, 0], [fig.bbox.width, fig.bbox.height]])
    w_cm, h_cm = fig.get_size_inches() * 2.54

    if w_cm > max_width_cm + 0.05:
        out.append(Finding("WARN", "fig_too_wide", f"图宽 {w_cm:.1f} cm 超过版心 {max_width_cm:.0f} cm，插入后会被缩放"))
    if h_cm / w_cm > 1.6 or h_cm / w_cm < 0.25:
        out.append(Finding("INFO", "fig_aspect_unusual", f"图高宽比 {h_cm / w_cm:.2f} 偏离常规区间 [0.25, 1.6]"))

    axes = [ax for ax in fig.get_axes() if ax.get_visible()]
    data_axes = [ax for ax in axes if not _is_colorbar(ax)]

    # ---- 收集文字：白名单方式，只取当前真正绘制的文字对象 ----
    tick_ids: set[int] = set()
    candidates: list = list(fig.texts)
    for ax in axes:
        ticks = _visible_ticklabels(ax.xaxis) + _visible_ticklabels(ax.yaxis)
        tick_ids.update(id(t) for t in ticks)
        candidates += ticks
        candidates += list(ax.texts) + [ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label,
                                        ax.xaxis.get_offset_text(), ax.yaxis.get_offset_text()]
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            candidates += list(leg.get_texts())
            if leg.get_title().get_text():
                candidates.append(leg.get_title())
    texts = []
    seen: set[int] = set()
    for t in candidates:
        if id(t) in seen or not isinstance(t, mtext.Text):
            continue
        seen.add(id(t))
        if not t.get_visible() or not t.get_text().strip():
            continue
        try:
            bb = t.get_window_extent(renderer)
        except Exception:  # noqa: BLE001
            continue
        if bb.width <= 0 or bb.height <= 0:
            continue
        texts.append((t, bb))

    # 图内文字冗长：标题/注释应是短语，细节放题注
    verbose = [t for t, _ in texts if id(t) not in tick_ids and _too_verbose(t.get_text())]
    for t in verbose[:3]:
        out.append(Finding("WARN", "text_verbose", f"图内文字过长『{_short(t.get_text(), 24)}』（{_text_units(t.get_text())} 字宽），精简或移到题注"))
    if len(verbose) > 3:
        out.append(Finding("WARN", "text_verbose", f"另有 {len(verbose) - 3} 处图内文字过长"))

    # 字号
    sizes = sorted({round(float(t.get_fontsize()), 1) for t, _ in texts})
    small = [t for t, _ in texts if float(t.get_fontsize()) < min_font_pt]
    if small:
        out.append(Finding("WARN", "font_too_small", f"{len(small)} 处文字字号 < {min_font_pt} pt，例如『{_short(small[0].get_text())}』"))
    if sizes and (len(sizes) > 4 or sizes[-1] > 1.6 * base_size):
        out.append(Finding("WARN", "font_size_spread", f"字号种类 {sizes}，超过 4 种或最大值 > 1.6×基准 {base_size} pt，观感大小不均"))

    # 越界
    clipped = [t for t, bb in texts if not fig_bbox.contains(bb.x0 + 1, bb.y0 + 1) or not fig_bbox.contains(bb.x1 - 1, bb.y1 - 1)]
    if clipped:
        out.append(Finding("WARN", "text_clipped", f"{len(clipped)} 处文字超出画布（bbox_inches='tight' 会扩边但版式失衡），例如『{_short(clipped[0].get_text())}』"))

    # 文字-文字重叠（同一坐标轴的刻度标签互相重叠单独归为 tick_crowded）
    overlaps, crowded, tight = [], set(), []
    gap_px = MIN_TEXT_GAP_PT * fig.dpi / 72
    for (ta, ba), (tb, bb) in itertools.combinations(texts, 2):
        r = _bbox_overlap(ba, bb)
        if r < 0.10:
            # 非刻度文字之间间隙 < MIN_TEXT_GAP_PT 视为拥挤（盒子不交但胉眼看连在一起）
            if id(ta) not in tick_ids and id(tb) not in tick_ids and ta.axes is tb.axes \
                    and _bbox_overlap(ba.expanded(1 + 2 * gap_px / max(ba.width, 1), 1 + 2 * gap_px / max(ba.height, 1)), bb) > 0:
                tight.append((ta, tb))
            continue
        if id(ta) in tick_ids and id(tb) in tick_ids:
            crowded.add(id(ta.axes))
        else:
            overlaps.append((ta, tb, r))
    if crowded:
        out.append(Finding("WARN", "tick_crowded", f"{len(crowded)} 个坐标轴的刻度标签互相重叠，考虑减少刻度、旋转或改用科学计数"))
    for ta, tb, r in overlaps[:5]:
        out.append(Finding("WARN", "text_overlap", f"『{_short(ta.get_text())}』与『{_short(tb.get_text())}』重叠 {r:.0%}"))
    if len(overlaps) > 5:
        out.append(Finding("WARN", "text_overlap", f"另有 {len(overlaps) - 5} 处文字重叠未列出"))
    for ta, tb in tight[:3]:
        out.append(Finding("WARN", "text_crowded", f"『{_short(ta.get_text())}』与『{_short(tb.get_text())}』间隙 < {MIN_TEXT_GAP_PT} pt，考虑 annotate_points()/错位排布"))
    if len(tight) > 3:
        out.append(Finding("WARN", "text_crowded", f"另有 {len(tight) - 3} 对文字拥挤未列出"))

    # ---- 逐坐标轴：图例/注释压数据、配色、标签 ----
    pal = _palette_set(palette)
    off_palette: dict[str, int] = {}
    label_colors: dict[str, set[str]] = {}
    for ax in data_axes:
        lines = [ln for ln in ax.get_lines() if ln.get_visible() and len(ln.get_xdata()) > 0]
        rects = [p for p in ax.patches if isinstance(p, Rectangle) and p.get_visible()]
        pts = []
        for ln in lines:
            try:
                xy = ln.get_transform().transform(ln.get_xydata())
                pts.append(xy)
            except Exception:  # noqa: BLE001
                pass
        for coll in ax.collections:   # scatter 散点也是数据
            try:
                off = coll.get_offsets()
                if coll.get_visible() and len(off):
                    pts.append(coll.get_offset_transform().transform(off))
            except Exception:  # noqa: BLE001
                pass
        import numpy as np
        all_pts = np.concatenate(pts) if pts else np.empty((0, 2))
        all_pts = all_pts[np.isfinite(all_pts).all(axis=1)] if len(all_pts) else all_pts

        def _covers_data(bb) -> bool:
            if len(all_pts):
                inside = (all_pts[:, 0] > bb.x0) & (all_pts[:, 0] < bb.x1) & (all_pts[:, 1] > bb.y0) & (all_pts[:, 1] < bb.y1)
                if inside.any():
                    return True
            for p in rects:
                try:
                    if _bbox_overlap(p.get_window_extent(renderer), bb) > 0.05:
                        return True
                except Exception:  # noqa: BLE001
                    continue
            return False

        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            try:
                lbb = leg.get_window_extent(renderer)
                if _covers_data(lbb):
                    out.append(Finding("WARN", "legend_over_data", f"坐标轴『{_short(ax.get_title() or ax.get_ylabel() or str(data_axes.index(ax)))}』的图例盖住了数据，改 loc 或放到图外"))
                if len(leg.get_texts()) > 8:
                    out.append(Finding("WARN", "legend_too_long", f"图例 {len(leg.get_texts())} 项，过多；考虑分面板或直接标注"))
            except Exception:  # noqa: BLE001
                pass
            for txt, h in zip(leg.get_texts(), leg.legend_handles):
                c = None
                if isinstance(h, Line2D):
                    c = _to_hex(h.get_color())
                elif hasattr(h, "get_facecolor"):
                    try:
                        c = _to_hex(h.get_facecolor())
                    except Exception:  # noqa: BLE001
                        c = None
                if c:
                    label_colors.setdefault(txt.get_text(), set()).add(c)
        # 注释文字压线（只看位于绘图区内、且不是刻度/轴标签/图例的文字）
        ax_bb = ax.get_window_extent(renderer)
        for t in ax.texts:
            if not t.get_visible() or not t.get_text().strip():
                continue
            try:
                tb = t.get_window_extent(renderer)
            except Exception:  # noqa: BLE001
                continue
            if _bbox_overlap(tb, ax_bb) > 0.5 and len(all_pts) and not _PANEL_LABEL.match(t.get_text().strip()):
                inside = (all_pts[:, 0] > tb.x0) & (all_pts[:, 0] < tb.x1) & (all_pts[:, 1] > tb.y0) & (all_pts[:, 1] < tb.y1)
                if inside.any():
                    out.append(Finding("WARN", "text_over_data", f"注释『{_short(t.get_text())}』压在数据线上"))
        # 配色
        if pal:
            for ln in lines:
                c = _to_hex(ln.get_color())
                if c and c not in pal and c not in ALLOWED_EXTRA_COLORS:
                    off_palette[c] = off_palette.get(c, 0) + 1
            for p in rects:
                c = _to_hex(p.get_facecolor())
                if c and c not in pal and c not in ALLOWED_EXTRA_COLORS:
                    off_palette[c] = off_palette.get(c, 0) + 1
        # 坐标轴标签
        if (lines or rects) and not ax.get_xlabel() and not ax.get_ylabel() and not ax.get_xticklabels()[:1]:
            out.append(Finding("INFO", "missing_axis_label", "有数据但坐标轴无标签"))
        elif (lines or rects) and not ax.get_ylabel():
            out.append(Finding("INFO", "missing_axis_label", f"坐标轴缺 ylabel（{_short(ax.get_xlabel() or '无 xlabel')}）"))

    if off_palette:
        items = ", ".join(f"{c}×{n}" for c, n in sorted(off_palette.items(), key=lambda kv: -kv[1])[:6])
        out.append(Finding("WARN", "color_off_palette", f"线/柱颜色不在调色板『{palette}』内：{items}；用 COLORS/PALETTES 取色"))
    for lab, cs in label_colors.items():
        if len(cs) > 1:
            out.append(Finding("WARN", "label_color_mismatch", f"图例『{_short(lab)}』在不同面板用了不同颜色 {sorted(cs)}"))

    # ---- 多面板一致性 ----
    if len(data_axes) > 1:
        ws = [ax.get_window_extent(renderer).width for ax in data_axes]
        hs = [ax.get_window_extent(renderer).height for ax in data_axes]
        if max(ws) > 1.15 * min(ws) or max(hs) > 1.15 * min(hs):
            out.append(Finding("WARN", "panel_size_uneven", f"面板宽 {min(ws):.0f}–{max(ws):.0f} px、高 {min(hs):.0f}–{max(hs):.0f} px，差异 > 15%（共用 colorbar 时可忽略）"))
        rel, abs_pt = [], []
        pt = fig.dpi / 72
        for ax in data_axes:
            abb = ax.get_window_extent(renderer)
            for t in ax.texts:
                if _PANEL_LABEL.match(t.get_text().strip()):
                    tb = t.get_window_extent(renderer)
                    rel.append(((tb.x0 - abb.x0) / abb.width, (tb.y0 - abb.y0) / abb.height))
                    abs_pt.append(((tb.x0 - abb.x0) / pt, (tb.y0 - abb.y1) / pt))
        if len(rel) > 1:
            xs = [r[0] for r in rel]
            ys = [r[1] for r in rel]
            axs_ = [a[0] for a in abs_pt]
            ays_ = [a[1] for a in abs_pt]
            rel_ok = max(xs) - min(xs) <= 0.05 and max(ys) - min(ys) <= 0.05
            abs_ok = max(axs_) - min(axs_) <= 1.5 and max(ays_) - min(ays_) <= 1.5   # nature-figure 容差 1.5 pt
            if not rel_ok and not abs_ok:
                out.append(Finding("WARN", "panel_label_misaligned", "面板标签 (a)(b)… 相对各自坐标轴的位置不一致，用 label_panels(axes) 统一"))
    return out


# --------------------------------------------------------------------------- #
# 2. PDF 近似检查
# --------------------------------------------------------------------------- #
def _rect_overlap(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / small if small > 0 else 0.0


def _seg_hits_rect(p0, p1, r, pad: float = 0.5) -> bool:
    """线段 (p0,p1) 是否穿过矩形 r=(x0,y0,x1,y1) 的内部（缩进 pad 以忽略擦边）。"""
    x0, y0, x1, y1 = r[0] + pad, r[1] + pad, r[2] - pad, r[3] - pad
    if x1 <= x0 or y1 <= y0:
        return False
    (ax, ay), (bx, by) = p0, p1
    # 两端点都在矩形一侧 → 不相交
    if max(ax, bx) < x0 or min(ax, bx) > x1 or max(ay, by) < y0 or min(ay, by) > y1:
        return False
    if x0 <= ax <= x1 and y0 <= ay <= y1 or x0 <= bx <= x1 and y0 <= by <= y1:
        return True
    dx, dy = bx - ax, by - ay
    for t_edge in ((x0 - ax) / dx if dx else None, (x1 - ax) / dx if dx else None):
        if t_edge is not None and 0 <= t_edge <= 1 and y0 <= ay + t_edge * dy <= y1:
            return True
    for t_edge in ((y0 - ay) / dy if dy else None, (y1 - ay) / dy if dy else None):
        if t_edge is not None and 0 <= t_edge <= 1 and x0 <= ax + t_edge * dx <= x1:
            return True
    return False


def lint_pdf(pdf: str | Path, *, max_report: int = 5) -> list[Finding]:
    try:
        import pymupdf
    except ImportError:
        return [Finding("WARN", "pdf_lint_skipped", "未安装 pymupdf，跳过 PDF 版式检查")]
    out: list[Finding] = []
    doc = pymupdf.open(pdf)
    page = doc[0]
    W, H = page.rect.width, page.rect.height
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words") if w[4].strip()]

    outside = [w for w in words if w[0] < -0.5 or w[1] < -0.5 or w[2] > W + 0.5 or w[3] > H + 0.5]
    if outside:
        out.append(Finding("WARN", "pdf_text_outside", f"{len(outside)} 个词超出页面，例如『{_short(outside[0][4])}』"))

    n_ov = 0
    for a, b in itertools.combinations(words, 2):
        r = _rect_overlap(a[:4], b[:4])
        if r > 0.15:
            # 同一行相邻词的包围盒常轻微相交，要求纵向也有明显重叠
            vy = min(a[3], b[3]) - max(a[1], b[1])
            if vy > 0.4 * min(a[3] - a[1], b[3] - b[1]) and min(a[2], b[2]) - max(a[0], b[0]) > 1.0:
                n_ov += 1
                if n_ov <= max_report:
                    out.append(Finding("WARN", "pdf_word_overlap", f"『{_short(a[4])}』与『{_short(b[4])}』重叠 {r:.0%}"))
    if n_ov > max_report:
        out.append(Finding("WARN", "pdf_word_overlap", f"另有 {n_ov - max_report} 处词重叠未列出"))

    hit_words: list[str] = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        drawings = []
    segs = [((it[1].x, it[1].y), (it[2].x, it[2].y))
            for d in drawings if d.get("color") is not None
            for it in d.get("items", []) if it[0] == "l"]
    for w in words:
        if any(_seg_hits_rect(p0, p1, w[:4]) for p0, p1 in segs):
            hit_words.append(w[4])
    for t in hit_words[:max_report]:
        out.append(Finding("WARN", "pdf_line_through_text", f"线段穿过文字『{_short(t)}』"))
    if len(hit_words) > max_report:
        out.append(Finding("WARN", "pdf_line_through_text", f"另有 {len(hit_words) - max_report} 处文字被线段穿过未列出"))
    doc.close()
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _iter_pdfs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(path.glob("*.pdf")))
            for sub in sorted(x for x in path.iterdir() if x.is_dir()):
                out.extend(sorted(sub.glob(f"{sub.name}.pdf")) or sorted(sub.glob("*.pdf"))[:1])
        elif path.suffix.lower() == ".pdf" and path.exists():
            out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="PDF 文件、图文件夹或 figures/ 根目录")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    ap.add_argument("--no-update", action="store_true", help="不写回 review.json")
    args = ap.parse_args(argv)
    pdfs = _iter_pdfs(args.paths)
    if not pdfs:
        print("[fig_layout_lint] 没有可检查的 PDF", file=sys.stderr)
        return 2
    bad = 0
    for pdf in pdfs:
        findings = lint_pdf(pdf)
        worst = "FAIL" if any(f.level == "FAIL" for f in findings) else ("WARN" if any(f.level == "WARN" for f in findings) else "OK")
        bad += worst == "FAIL" or (args.strict and worst == "WARN")
        print(f"{worst:4s} {pdf}")
        for f in findings:
            print(f"     - {f.level} {f.code}: {f.message}")
        review = pdf.parent / "review.json"
        if not args.no_update and pdf.parent.name == pdf.stem:
            data = {}
            if review.exists():
                try:
                    data = json.loads(review.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
            data.setdefault("figure", pdf.stem)
            data.setdefault("human", {"status": "pending", "reviewer": None, "date": None, "verdict": None, "notes": []})
            import datetime as dt
            data["auto_pdf"] = {"checked_at": dt.datetime.now().isoformat(timespec="seconds"),
                                "findings": [f.as_dict() for f in findings]}
            review.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[fig_layout_lint] {len(pdfs)} 个 PDF，{bad} 个未通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
