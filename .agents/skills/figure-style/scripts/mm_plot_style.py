"""mm-draft-workbench 统一绘图风格（Matplotlib）。

规范来源：nature-skills/nature-figure 的 Python 后端约定（sans-serif、7–9 pt、
细坐标轴、无图例边框、svg.fonttype=none、pdf.fonttype=42）+ 华为杯中文论文与
DOCX 交稿链路的字体约束。详细说明见 `_references/figure_style.md`。

用法（项目里本文件位于 `tools/`，每张图的 `figures/<fig_id>/make_figure.py` 这样写）::

    import sys
    from pathlib import Path
    HERE = Path(__file__).resolve().parent            # figures/fig02_q1_fit/
    ROOT = HERE.parents[1]                             # 项目根目录
    sys.path.insert(0, str(ROOT / "tools"))
    from mm_plot_style import apply_style, COLORS, figsize, save_fig, snapshot_data

    apply_style(lang="zh")                             # 中文论文；英文论文用 lang="en"
    data = snapshot_data(ROOT / "results" / "q1_fit.csv", HERE)   # 快照进图文件夹
    fig, ax = plt.subplots(figsize=figsize("full"))
    ax.plot(x, y, color=COLORS[0], label="预测值")
    save_fig(fig, HERE / HERE.name, source=data, params={"seed": 0})

中文乱码根因：Linux 上常见的 Noto CJK 是 CFF(OTF) 轮廓，Matplotlib 在
``pdf.fonttype=42`` 下会把它当 TrueType 嵌入，生成非法字体流，PDF→PNG 转换后
乱码；而 ``pdf.fonttype=3`` 虽能显示，但文字不可提取/检索。因此本模块只挑选
TrueType(glyf) 轮廓的中文字体（如 WenQuanYi Micro Hei / Zen Hei、AR PL UMing），
配合 ``pdf.fonttype=42``；``save_fig`` 默认调用 ``check_pdf`` 做字体与文本自检。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib as mpl
from cycler import cycler
from matplotlib import font_manager as fm

__all__ = [
    "register_bundled_fonts",
    "COLORS",
    "PALETTES",
    "NATURE",
    "SEQUENTIAL_CMAP",
    "DIVERGING_CMAP",
    "TEXT_WIDTH_CM",
    "FIG_WIDTHS_CM",
    "apply_style",
    "figsize",
    "save_fig",
    "check_pdf",
    "resolve_fonts",
    "active_fonts",
    "label_panels",
    "zh_math_kw",
    "fix_mixed_math_text",
    "place_text_clear",
    "annotate_points",
    "annotate_heatmap",
    "figure_folder",
    "snapshot_data",
    "FIGURE_SCRIPT_NAME",
]

# --------------------------------------------------------------------------- #
# 调色板（nature-skills DEFAULT_COLORS 语义色 + 同方法族 pastel + 灰度）
# --------------------------------------------------------------------------- #
# nature-skills/nature-figure `PALETTE` 语义色：主方法深蓝、对照砖红、第二组绿、青、紫、中性灰
NATURE: dict[str, str] = {
    "blue": "#0F4D92", "blue2": "#3775BA", "red": "#B64342", "red2": "#E9A6A1",
    "green": "#8BCF8B", "green2": "#AADCA9", "teal": "#42949E", "violet": "#9A4D8E",
    "gold": "#E0B400", "gray": "#767676", "gray_light": "#CFCECE", "gray_dark": "#4D4D4D", "black": "#272727",
}
PALETTES: dict[str, list[str]] = {
    # 语义清晰、灰度下明暗有序：主方法蓝、对照红、第二组绿、青、紫、中性灰
    "default": ["#1F77B4", "#D62728", "#2CA02C", "#17BECF", "#9467BD", "#7F7F7F"],
    # nature-skills DEFAULT_COLORS：低饱和、印刷友好（推荐）
    "nature": [NATURE["blue"], NATURE["red"], NATURE["green"], NATURE["teal"], NATURE["violet"], NATURE["gray"]],
    # nature-skills NMI pastel：同一方法族多模型对比（蓝紫系由深到浅 + 一个强调色 red）
    "nmi": ["#484878", "#7884B4", "#B4C0E4", "#9A4D8E", "#42949E", "#8BCF8B", "#B64342", "#A8A8A8"],
    # 同一方法族多面板对比（旧 pastel，保留兼容）
    "pastel": ["#8EC1DA", "#F4A582", "#A6D96A", "#B2ABD2", "#FDB863", "#BABABA"],
    # 黑白打印/灰度审稿
    "gray": ["#000000", "#4D4D4D", "#7F7F7F", "#A6A6A6", "#CCCCCC", "#E5E5E5"],
}
# apply_style(palette=...) 会就地替换 COLORS 的内容，`from mm_plot_style import COLORS` 后取到的即当前调色板
COLORS: list[str] = list(PALETTES["default"])
SEQUENTIAL_CMAP = "viridis"   # 单向数值：热力图、密度
DIVERGING_CMAP = "RdBu_r"     # 有中心值：相关系数、残差
# 禁止：jet / rainbow / hsv 等彩虹色

# --------------------------------------------------------------------------- #
# 尺寸：A4 210 mm − 2×25 mm 边距 = 160 mm 版心
# --------------------------------------------------------------------------- #
TEXT_WIDTH_CM = 16.0
FIG_WIDTHS_CM: dict[str, float] = {
    "full": 14.0,        # 单栏整宽图，插入论文时按 ≈85–90% 版心
    "two-thirds": 10.5,
    "half": 7.5,         # 两图并排
    "third": 5.0,
}
_CM = 1 / 2.54

# --------------------------------------------------------------------------- #
# 字体候选（按优先级；只保留 Matplotlib 能识别、且轮廓为 TrueType 的）
# --------------------------------------------------------------------------- #
LATIN_SANS = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"]
LATIN_SERIF = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
CJK_SANS = [
    "SimHei", "Microsoft YaHei", "PingFang SC", "Heiti SC",
    "Source Han Sans SC", "Noto Sans CJK SC",
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Noto Sans CJK JP",
    "Droid Sans Fallback",
]
CJK_SERIF = [
    "SimSun", "Songti SC", "STSong",
    "Source Han Serif SC", "Noto Serif CJK SC",
    "AR PL UMing CN", "AR PL SungtiL GB", "Noto Serif CJK JP",
]
_CJK_PROBE = "中文图例测试"
_ACTIVE: dict[str, object] = {}


def _outline_kind(path: str) -> str:
    """返回字体轮廓类型：'truetype' | 'cff' | 'unknown'。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
            if head == b"ttcf":
                fh.seek(12)
                off = int.from_bytes(fh.read(4), "big")
                fh.seek(off)
                head = fh.read(4)
    except OSError:
        return "unknown"
    if head in (b"\x00\x01\x00\x00", b"true"):
        return "truetype"
    if head == b"OTTO":
        return "cff"
    return "unknown"


_FONTS_REGISTERED = False
_BUNDLED_FAMILIES: list[str] = []   # 随项目交付的字体族名，优先于系统字体，保证跨平台出图一致


def register_bundled_fonts(folder: str | os.PathLike | None = None) -> list[str]:
    """把 tools/fonts/ 下随项目交付的 TrueType 字体注册进 Matplotlib（Windows/Linux 出图一致）。

    默认目录为本模块同级的 fonts/；只认 .ttf/.ttc/.otf。重复调用无副作用。
    """
    global _FONTS_REGISTERED
    folder = Path(folder) if folder else Path(__file__).resolve().parent / "fonts"
    if _FONTS_REGISTERED and folder == Path(__file__).resolve().parent / "fonts":
        return []
    added: list[str] = []
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in (".ttf", ".ttc", ".otf"):
                try:
                    fm.fontManager.addfont(str(f))
                    name = fm.FontProperties(fname=str(f)).get_name()
                    if name not in _BUNDLED_FAMILIES:
                        _BUNDLED_FAMILIES.append(name)
                    added.append(f.name)
                except Exception:  # noqa: BLE001 - 坏字体文件跳过
                    continue
    _FONTS_REGISTERED = True
    return added


def _find_font(name: str) -> str | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return fm.findfont(fm.FontProperties(family=name), fallback_to_default=False)
    except ValueError:
        return None


def _font_has_glyphs(path: str, text: str) -> bool:
    try:
        from matplotlib.ft2font import FT2Font
        face = FT2Font(path)
        return all(face.get_char_index(ord(ch)) != 0 for ch in text)
    except Exception:  # noqa: BLE001 - 探测失败视为不可用
        return False


def resolve_fonts(font: str = "sans", lang: str = "zh", require_truetype: bool = True) -> dict[str, object]:
    """挑选 Latin 与中文字体，返回 {'latin','cjk','cjk_kind','pdf_fonttype','family'}。"""
    register_bundled_fonts()
    latin_cands = LATIN_SANS if font == "sans" else LATIN_SERIF
    cjk_cands = (CJK_SANS if font == "sans" else CJK_SERIF + CJK_SANS)
    bundled_cjk = [n for n in _BUNDLED_FAMILIES if _font_has_glyphs(_find_font(n) or "", _CJK_PROBE)]
    bundled_latin = [n for n in _BUNDLED_FAMILIES if n not in bundled_cjk]
    latin_cands = bundled_latin + latin_cands
    cjk_cands = bundled_cjk + cjk_cands

    latin = next((n for n in latin_cands if _find_font(n)), "DejaVu Sans")

    cjk: str | None = None
    cjk_kind = "none"
    fallback: tuple[str, str] | None = None
    if lang == "zh":
        for name in cjk_cands:
            path = _find_font(name)
            if not path or not _font_has_glyphs(path, _CJK_PROBE):
                continue
            kind = _outline_kind(path)
            if kind == "truetype":
                cjk, cjk_kind = name, kind
                break
            fallback = fallback or (name, kind)
        if cjk is None and fallback is not None:
            cjk, cjk_kind = fallback
    pdf_fonttype = 42
    if lang == "zh" and cjk is None:
        warnings.warn(
            "未找到任何中文字体，中文将显示为方块；请安装 fonts-wqy-microhei / fonts-wqy-zenhei。",
            stacklevel=2,
        )
    elif cjk_kind == "cff":
        if require_truetype:
            pdf_fonttype = 3
        warnings.warn(
            f"中文字体 {cjk} 为 CFF/OTF 轮廓，pdf.fonttype=42 会导出非法 PDF；"
            "已降级为 fonttype=3（文字不可检索）。建议安装 fonts-wqy-microhei 以获得 TrueType 中文字体。",
            stacklevel=2,
        )
    family = [latin] + ([cjk] if cjk else []) + ["DejaVu Sans"]
    return {"latin": latin, "cjk": cjk, "cjk_kind": cjk_kind, "pdf_fonttype": pdf_fonttype, "family": family}


def apply_style(
    *,
    font: str = "sans",
    lang: str = "zh",
    base_size: float = 9.0,
    palette: str = "default",
    spines: str = "open",
    extra: dict | None = None,
) -> dict[str, object]:
    """应用统一 rcParams。

    font: 'sans'（默认，正文图）| 'serif'
    lang: 'zh' 启用中文字体 fallback；'en' 仅 Latin
    base_size: 图内基准字号（pt），期刊 7–9，论文正文图 9
    spines: 'open' 关闭上/右脊线（默认）| 'box' 四边框
    """
    if font not in ("sans", "serif"):
        raise ValueError("font 必须是 'sans' 或 'serif'")
    if palette not in PALETTES:
        raise ValueError(f"palette 必须是 {sorted(PALETTES)} 之一")
    info = resolve_fonts(font=font, lang=lang)
    family = info["family"]
    latin = str(info["latin"])
    rc = {
        "font.family": family,
        "font.sans-serif": family if font == "sans" else LATIN_SANS,
        "font.serif": family if font == "serif" else LATIN_SERIF,
        "font.size": base_size,
        "axes.titlesize": base_size,
        "axes.labelsize": base_size,
        "xtick.labelsize": base_size - 1,
        "ytick.labelsize": base_size - 1,
        "legend.fontsize": base_size - 1,
        "legend.title_fontsize": base_size - 1,
        "figure.titlesize": base_size,
        # mathtext 不做字体回退：rm/it/bf 直接映射到正文 Latin 字体，公式与正文字形一致；
        # 含 `$` 的字符串里的中文由 fix_mixed_math_text / zh_math_kw 把中文字体放到 fontfamily 首位解决
        "mathtext.fontset": "custom",
        "mathtext.rm": latin,
        "mathtext.it": f"{latin}:italic",
        "mathtext.bf": f"{latin}:bold",
        "mathtext.sf": latin,
        "mathtext.cal": f"{latin}:italic",
        "mathtext.tt": "DejaVu Sans Mono",
        "mathtext.fallback": "stixsans" if font == "sans" else "stix",   # 希腊字母、∈ ≤ 等符号
        "mathtext.default": "it",
        "axes.unicode_minus": False,        # 负号用 ASCII '-'，避免中文字体缺 U+2212
        "pdf.fonttype": info["pdf_fonttype"],
        "ps.fonttype": 42,
        "svg.fonttype": "none",             # SVG 保留可编辑文字
        "axes.linewidth": 0.8,
        "axes.spines.top": spines == "box",
        "axes.spines.right": spines == "box",
        "axes.grid": False,
        "axes.axisbelow": True,
        "axes.prop_cycle": cycler(color=PALETTES[palette]),
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "patch.linewidth": 0.6,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.minor.width": 0.6,
        "ytick.minor.width": 0.6,
        "legend.frameon": False,
        "legend.handlelength": 1.5,
        "legend.borderaxespad": 0.3,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "figure.constrained_layout.use": True,   # 自动避免轴标签/图题被裁、面板间距不均
        "figure.dpi": 100,
        "image.cmap": SEQUENTIAL_CMAP,
        "errorbar.capsize": 2,
    }
    if extra:
        rc.update(extra)
    mpl.rcParams.update(rc)
    COLORS[:] = PALETTES[palette]
    _ACTIVE.clear()
    _ACTIVE.update({**info, "font": font, "lang": lang, "base_size": base_size, "palette": palette})
    return dict(_ACTIVE)


def active_fonts() -> dict[str, object]:
    """最近一次 apply_style 选定的字体信息。"""
    return dict(_ACTIVE)


def figsize(width: str | float = "full", aspect: float = 0.62, height_cm: float | None = None) -> tuple[float, float]:
    """按版心宽度给出 figsize（英寸）。width 可为 FIG_WIDTHS_CM 的键或 cm 数值。"""
    w_cm = FIG_WIDTHS_CM[width] if isinstance(width, str) else float(width)
    h_cm = height_cm if height_cm is not None else w_cm * aspect
    return (w_cm * _CM, h_cm * _CM)


def label_panels(axes: Iterable, labels: Sequence[str] | None = None, *, x: float = -0.12, y: float = 1.05,
                 fontsize: float | None = None, weight: str = "bold",
                 offset_pt: tuple[float, float] | None = None) -> None:
    """为多面板图加 (a)(b)(c) 标签，位置以每个 axes 的左上角为基准。

    默认按 axes 比例坐标 (x, y) 放置（老脚本兼容）；给 ``offset_pt=(dx, dy)`` 时改为
    以 axes 左上角 (0, 1) 为锚、按**物理点数**偏移（nature-figure add_panel_label 约定），
    面板大小不同时标签与各自坐标轴的距离仍一致。
    """
    axes = list(axes)
    labels = labels or [f"({chr(ord('a') + i)})" for i in range(len(axes))]
    size = fontsize or mpl.rcParams["font.size"]
    for ax, lab in zip(axes, labels):
        if offset_pt is None:
            ax.text(x, y, lab, transform=ax.transAxes, fontsize=size, fontweight=weight, va="bottom", ha="left")
            continue
        from matplotlib.transforms import ScaledTranslation
        trans = ax.transAxes + ScaledTranslation(offset_pt[0] / 72, offset_pt[1] / 72, ax.figure.dpi_scale_trans)
        ax.text(0, 1, lab, transform=trans, fontsize=size, fontweight=weight, va="bottom", ha="left")


# --------------------------------------------------------------------------- #
# 中文 + mathtext 混排、防堆叠标注（mm-figure-workbench figure-style）
# --------------------------------------------------------------------------- #
def zh_math_kw() -> dict[str, object]:
    """含 ``$公式$`` 的中文字符串要用的 kwargs：``ax.set_xlabel("滚动体数 $N_d$", **zh_math_kw())``。

    Matplotlib 只要字符串含 ``$`` 就整串走 mathtext，非公式部分用 fontfamily 的**第一个**字体，
    不做回退，所以中文要放到首位；公式部分仍按 mathtext.rm/it（Latin 字体）渲染。
    """
    cjk = _ACTIVE.get("cjk")
    fam = ([cjk] if cjk else []) + [_ACTIVE.get("latin", "DejaVu Sans"), "DejaVu Sans"]
    return {"fontfamily": fam}


def fix_mixed_math_text(fig) -> int:
    """遍历图中所有文字，凡是同时含 ``$`` 与中文的，套用 zh_math_kw()。save_fig 自动调用；返回修正个数。"""
    import matplotlib.text as mtext
    fam = zh_math_kw()["fontfamily"]
    if not _ACTIVE.get("cjk"):
        return 0
    n = 0
    for t in fig.findobj(mtext.Text):
        s = t.get_text()
        if "$" in s and _has_cjk(s) and list(t.get_fontfamily()) != list(fam):
            t.set_fontfamily(fam)
            n += 1
    return n


def _renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except AttributeError:
        return fig._get_renderer()


def _bbox_hits(bb, others, pad: float = 1.0) -> bool:
    for o in others:
        if bb.x0 - pad < o.x1 and bb.x1 + pad > o.x0 and bb.y0 - pad < o.y1 and bb.y1 + pad > o.y0:
            return True
    return False


def _points_in(bb, pts, pad: float = 1.0) -> bool:
    if pts is None or len(pts) == 0:
        return False
    return bool(((pts[:, 0] > bb.x0 - pad) & (pts[:, 0] < bb.x1 + pad)
                 & (pts[:, 1] > bb.y0 - pad) & (pts[:, 1] < bb.y1 + pad)).any())


def _axes_obstacles(ax, renderer, exclude=()):
    """收集 ax 内已绘制的数据点（像素）与文字包围盒，供防堆叠放置使用。"""
    import numpy as np
    from matplotlib.patches import Rectangle
    pts = []
    for ln in ax.get_lines():
        if not ln.get_visible() or len(ln.get_xdata()) == 0:
            continue
        xy = ln.get_transform().transform(ln.get_xydata())
        if len(xy) > 1:   # 折线：按像素插值加密，保证线段中段也算障碍
            seg = np.diff(xy, axis=0)
            n = np.maximum(1, (np.hypot(seg[:, 0], seg[:, 1]) / 3).astype(int))
            dense = [np.linspace(xy[i], xy[i + 1], k, endpoint=False) for i, k in enumerate(n)]
            xy = np.concatenate(dense + [xy[-1:]])
        pts.append(xy)
    for coll in ax.collections:   # scatter 等
        try:
            off = coll.get_offsets()
            if len(off):
                pts.append(coll.get_offset_transform().transform(off))
        except Exception:  # noqa: BLE001
            pass
    all_pts = np.concatenate(pts) if pts else np.empty((0, 2))
    all_pts = all_pts[np.isfinite(all_pts).all(axis=1)] if len(all_pts) else all_pts
    boxes = []
    for p in ax.patches:
        if isinstance(p, Rectangle) and p.get_visible():
            try:
                boxes.append(p.get_window_extent(renderer))
            except Exception:  # noqa: BLE001
                pass
    ex = {id(e) for e in exclude}
    for t in list(ax.texts) + ax.get_xticklabels() + ax.get_yticklabels():
        if id(t) in ex or not t.get_visible() or not t.get_text().strip():
            continue
        try:
            boxes.append(t.get_window_extent(renderer))
        except Exception:  # noqa: BLE001
            pass
    leg = ax.get_legend()
    if leg is not None and leg.get_visible():
        boxes.append(leg.get_window_extent(renderer))
    return all_pts, boxes


_CORNERS = ((0.02, 0.96, "left", "top"), (0.98, 0.96, "right", "top"),
            (0.02, 0.04, "left", "bottom"), (0.98, 0.04, "right", "bottom"),
            (0.50, 0.96, "center", "top"), (0.50, 0.04, "center", "bottom"))


def place_text_clear(ax, text: str, candidates: Sequence[tuple] | None = None, *, pad: float = 2.0, **kw):
    """在候选位置中挑第一个不与数据线/柱/已有文字相交的位置放文字（axes 比例坐标）。

    candidates: [(x, y, ha, va), ...]，默认四角 + 上/下中；都不行就退回第一个候选并打印 WARN。
    含中文+公式的文字自动套用 zh_math_kw()。返回 Text 对象。
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = _renderer(fig)
    if "$" in text and _has_cjk(text):
        kw = {**zh_math_kw(), **kw}
    pts, boxes = _axes_obstacles(ax, renderer)
    ax_bb = ax.get_window_extent(renderer)
    cands = list(candidates or _CORNERS)
    t = ax.text(*cands[0][:2], text, transform=ax.transAxes, ha=cands[0][2], va=cands[0][3], **kw)
    for x, y, ha, va in cands:
        t.set_position((x, y))
        t.set_ha(ha)
        t.set_va(va)
        bb = t.get_window_extent(renderer)
        inside = bb.x0 >= ax_bb.x0 - 1 and bb.x1 <= ax_bb.x1 + 1 and bb.y0 >= ax_bb.y0 - 1 and bb.y1 <= ax_bb.y1 + 1
        if inside and not _points_in(bb, pts, pad) and not _bbox_hits(bb, boxes, pad):
            return t
    t.set_position(cands[0][:2])
    t.set_ha(cands[0][2])
    t.set_va(cands[0][3])
    print(f"[mm_plot_style] WARN place_text_clear: 『{text[:18]}』所有候选位置都与图元相交", file=sys.stderr)
    return t


_OFFSETS_PT = ((0, 6), (7, 3), (-7, 3), (7, -7), (-7, -7), (0, -9), (10, 0), (-10, 0),
               (12, 8), (-12, 8), (12, -10), (-12, -10), (0, 14), (0, -16), (18, 0), (-18, 0),
               (22, 12), (-22, 12), (22, -14), (-22, -14), (0, 22), (0, -24), (28, 0), (-28, 0))


def annotate_points(ax, xs: Sequence[float], ys: Sequence[float], labels: Sequence[str], *,
                    fontsize: float | None = None, color: str | Sequence[str] | None = None,
                    offsets_pt: Sequence[tuple[float, float]] = _OFFSETS_PT, pad: float = 3.0,
                    connector: bool = True, connector_color: str = "#7F7F7F", **kw) -> list:
    """给散点逐个贴标签，贪心挑不与数据点/其他标签/坐标轴边界相交的偏移；偏移远时画细引线。

    先画完所有数据再调用；返回 Annotation 列表（顺序与输入一致）。最拥挤的点先安排；
    pad 默认 3 pt 与 fig_layout_lint 的最小文字间隙一致。所有候选都冲突时取重叠最少的偏移并打印 WARN。
    """
    import numpy as np
    fig = ax.figure
    fig.canvas.draw()
    renderer = _renderer(fig)
    pts, boxes = _axes_obstacles(ax, renderer)
    ax_bb = ax.get_window_extent(renderer)
    size = fontsize or mpl.rcParams["font.size"] - 1
    colors = [color] * len(labels) if (color is None or isinstance(color, str)) else list(color)
    placed: list = [None] * len(labels)
    anchors = ax.transData.transform(np.column_stack([np.asarray(xs, float), np.asarray(ys, float)]))
    px_pt = fig.dpi / 72
    pad = pad * px_pt   # pt → px，与像素包围盒同单位
    crowd = [int((np.hypot(*(anchors - a).T) < 30 * px_pt).sum()) for a in anchors]
    order = sorted(range(len(labels)), key=lambda i: -crowd[i])
    for i in order:
        (x, y), lab, c, anc = (xs[i], ys[i]), labels[i], colors[i], anchors[i]
        others = np.asarray([a for a in pts if not (abs(a[0] - anc[0]) < 1e-6 and abs(a[1] - anc[1]) < 1e-6)])
        peers = np.delete(anchors, i, axis=0)   # 其它待标注的点：标签不能离它们比离自己更近
        best, best_score = None, None
        ann = ax.annotate(lab, (x, y), xytext=offsets_pt[0], textcoords="offset points", fontsize=size,
                          color=c or "black", ha="center", va="center", **kw)
        for dx, dy in offsets_pt:
            ann.set_position((dx, dy))
            ann.set_ha("left" if dx > 0 else "right" if dx < 0 else "center")
            ann.set_va("bottom" if dy > 0 else "top" if dy < 0 else "center")
            bb = ann.get_window_extent(renderer)
            out_of_axes = (bb.x0 < ax_bb.x0 or bb.x1 > ax_bb.x1 or bb.y0 < ax_bb.y0 or bb.y1 > ax_bb.y1)
            hard = (4 if out_of_axes else 0) + (2 if _points_in(bb, others, pad) else 0) \
                + (2 if _bbox_hits(bb, boxes, pad) else 0) \
                + (2 if _label_ambiguous(bb, anc, peers, pad) else 0) \
                + (1 if _segment_blocked(anc, bb, peers, boxes, pad) else 0)
            score = hard + 1e-3 * (abs(dx) + abs(dy))   # 同为无冲突时取离点最近的偏移
            if best_score is None or score < best_score:
                best, best_score = (dx, dy), score
            if hard == 0:
                break
        dx, dy = best
        ann.set_position((dx, dy))
        ann.set_ha("left" if dx > 0 else "right" if dx < 0 else "center")
        ann.set_va("bottom" if dy > 0 else "top" if dy < 0 else "center")
        if best_score >= 1:
            print(f"[mm_plot_style] WARN annotate_points: 『{lab}』无完全无冲突位置", file=sys.stderr)
        if connector and (abs(dx) + abs(dy)) >= 12:
            ax.annotate("", (x, y), xytext=(dx * 0.75, dy * 0.75), textcoords="offset points",
                        arrowprops={"arrowstyle": "-", "lw": 0.5, "color": connector_color, "shrinkA": 0, "shrinkB": 1})
        boxes.append(ann.get_window_extent(renderer))
        placed[i] = ann
    return placed


def _label_ambiguous(bb, anchor, others, pad: float) -> bool:
    """标签离别的数据点比离自己的点更近（会被读成别人的标签）。"""
    import numpy as np
    if others is None or len(others) == 0:
        return False
    cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
    d_own = np.hypot(cx - anchor[0], cy - anchor[1])
    d_other = np.hypot(others[:, 0] - cx, others[:, 1] - cy).min()
    return bool(d_other < d_own + pad)


def _segment_blocked(anchor, bb, others, boxes, pad: float) -> bool:
    """点到标签中心的连线穿过别的数据点或已有文字（引线会把读者引向别处）。"""
    import numpy as np
    cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
    ax0, ay0 = float(anchor[0]), float(anchor[1])
    seg = np.array([cx - ax0, cy - ay0])
    length = float(np.hypot(*seg))
    if length < 1e-6:
        return False
    if others is not None and len(others) > 0:
        rel = others - np.array([ax0, ay0])
        t = np.clip(rel @ seg / length**2, 0.0, 1.0)
        dist = np.hypot(*(rel - t[:, None] * seg).T)
        if bool((dist < pad).any()):
            return True
    n = max(2, int(length / 2))
    for k in np.linspace(0.0, 1.0, n):
        px, py = ax0 + k * seg[0], ay0 + k * seg[1]
        if bb.x0 <= px <= bb.x1 and bb.y0 <= py <= bb.y1:
            break
        for o in boxes:
            if o.x0 - pad < px < o.x1 + pad and o.y0 - pad < py < o.y1 + pad:
                return True
    return False


def annotate_heatmap(ax, im, fmt: str = "{:.2f}", *, fontsize: float | None = None, threshold: float = 0.55,
                     skip_nan: bool = True) -> list:
    """在 imshow 热力图每格写数值，字色按格底亮度自动黑/白（nature-figure is_dark 约定）。"""
    import numpy as np
    data = np.asarray(im.get_array(), dtype=float)
    size = fontsize or mpl.rcParams["font.size"] - 2
    out = []
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if skip_nan and not np.isfinite(v):
                continue
            r, g, b, _ = im.cmap(im.norm(v))
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            out.append(ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=size,
                               color="white" if lum < threshold else "black"))
    return out


# --------------------------------------------------------------------------- #
# PDF 自检（供 save_fig 与 check_figures.py 共用）
# --------------------------------------------------------------------------- #
_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3000, 0x303F), (0xFF00, 0xFFEF))


def _has_cjk(text: str) -> bool:
    return any(any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES) for ch in text)


def check_pdf(pdf: str | os.PathLike, *, expect_cjk: bool | None = None, strict: bool = False,
              max_width_cm: float = TEXT_WIDTH_CM, min_font_pt: float = 5.0) -> list[tuple[str, str]]:
    """用 PyMuPDF 检查图 PDF：字体嵌入/轮廓合法性、文本可提取、字号下限、页数与宽度。

    返回 [(level, message)]，level ∈ {'FAIL','WARN'}；空列表表示通过。
    expect_cjk=None 时按 apply_style 的 lang 自动判断（zh → 期望能提取出中文）。
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        return [("WARN", "未安装 pymupdf，跳过 PDF 自检")]

    pdf = Path(pdf)
    out: list[tuple[str, str]] = []
    doc = pymupdf.open(pdf)
    if doc.page_count != 1:
        out.append(("WARN", f"图 PDF 应为单页，实际 {doc.page_count} 页"))
    page = doc[0]
    w_cm = page.rect.width / 72 * 2.54
    if w_cm > max_width_cm + 0.05:
        out.append(("WARN", f"图宽 {w_cm:.1f} cm 超过版心 {max_width_cm:.1f} cm，插入论文时会被缩放导致字号失真"))

    fonts = page.get_fonts(full=True)
    has_text = False
    for xref, ext, ftype, basefont, *_ in fonts:
        has_text = True
        if ftype == "Type3":
            level = "FAIL" if strict else "WARN"
            out.append((level, f"字体 {basefont} 为 Type3（pdf.fonttype=3），文字不可提取/检索"))
            continue
        try:
            _, ext2, _, buf = doc.extract_font(xref)
        except Exception:  # noqa: BLE001
            buf, ext2 = b"", ext
        if not buf:
            out.append(("FAIL", f"字体 {basefont} 未嵌入，异机渲染会替换字体"))
            continue
        if ext2 in ("ttf", "ttc") and buf[:4] == b"OTTO":
            out.append(("FAIL", f"字体 {basefont} 为 CFF 轮廓却按 TrueType 嵌入（Noto CJK OTF + fonttype=42），PDF→PNG 会乱码"))

    # 实际渲染一次（与 docx-export 的 PDF→PNG 同一路径），捕获 MuPDF 的字形加载失败
    try:
        pymupdf.TOOLS.mupdf_warnings(reset=True)
        page.get_pixmap(dpi=72)
        render_warn = pymupdf.TOOLS.mupdf_warnings()
    except Exception:  # noqa: BLE001
        render_warn = ""
    if "cannot render glyph" in render_warn or "FT_Load_Glyph" in render_warn:
        out.append(("FAIL", "渲染时无法加载字形（嵌入字体损坏），PDF→PNG/Word 内会显示乱码或空白"))
    elif render_warn.strip():
        out.append(("WARN", f"渲染警告: {render_warn.strip().splitlines()[0]}"))

    text = page.get_text()
    if "\ufffd" in text:
        out.append(("FAIL", "提取文本含 U+FFFD 替换符，存在缺字"))
    if "\u00a4" in text:
        out.append(("FAIL", "提取文本含 ¤：含 $公式$ 的字符串里中文没有字体（用 zh_math_kw()/fix_mixed_math_text）"))
    if expect_cjk is None:
        expect_cjk = _ACTIVE.get("lang") == "zh" and any(ftype != "Type3" for _, _, ftype, *_ in fonts)
    if expect_cjk and has_text and not _has_cjk(text):
        out.append(("FAIL", "期望包含中文但提取不到任何中文字符（字体回退失败或字体损坏）"))

    try:
        sizes = [
            span["size"]
            for block in page.get_text("rawdict")["blocks"] if block.get("type") == 0
            for line in block["lines"] for span in line["spans"]
            if any(ch["c"].strip() for ch in span["chars"])
        ]
    except Exception:  # noqa: BLE001
        sizes = []
    if sizes and min(sizes) < min_font_pt:
        out.append(("WARN", f"最小字号 {min(sizes):.1f} pt < {min_font_pt} pt，打印/缩放后不可读"))
    doc.close()
    return out


# --------------------------------------------------------------------------- #
# 一图一文件夹：数据快照、README、review.json
# --------------------------------------------------------------------------- #
FIGURE_SCRIPT_NAME = "make_figure.py"
_SNAPSHOTS: dict[str, str] = {}   # 快照绝对路径 → 上游来源（相对路径）
_SNAPSHOT_OF: dict[str, str] = {}  # 上游来源绝对路径 → 快照绝对路径（save_fig 复用已有快照，不重复拷贝）


def _relpath(path: str | os.PathLike, start: str | os.PathLike | None = None) -> str:
    """跨平台相对路径；Windows 上跨盘符时退回绝对路径，始终用正斜杠。"""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(start or os.getcwd()))
    except ValueError:
        rel = os.path.abspath(path)
    return rel.replace(os.sep, "/")


def _script_path() -> Path | None:
    if sys.argv and sys.argv[0]:
        p = Path(sys.argv[0])
        if p.suffix == ".py" and p.exists():
            return p.resolve()
    return None


def _script_docstring(script: Path | None) -> str:
    """读取绘图脚本的模块 docstring（要求写明机理细节），供 README 引用。"""
    if script is None:
        return ""
    try:
        import ast
        tree = ast.parse(script.read_text(encoding="utf-8"))
        return (ast.get_docstring(tree) or "").strip()
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ""


def figure_folder(script_file: str | os.PathLike) -> Path:
    """在 figures/<fig_id>/make_figure.py 内调用：返回本图所在文件夹。"""
    return Path(script_file).resolve().parent


def snapshot_data(source: str | os.PathLike, folder: str | os.PathLike, *, name: str | None = None) -> Path:
    """把绘图所需数据快照到图文件夹（一图一文件夹自包含）。

    - source 存在且不在 folder 内：复制为 folder/<name or 原文件名>，返回快照路径。
    - source 不存在但快照已在：返回快照并打印提示（模型代码未重跑时仍可复现图）。
    - 两者都没有：抛 FileNotFoundError。
    绘图脚本应始终从返回的快照路径读数据，而不是直接读 results/。
    """
    source = Path(source)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (name or source.name)
    try:
        same_dir = source.resolve().parent == folder.resolve()
    except OSError:
        same_dir = False
    if source.exists():
        if same_dir:
            return source
        import shutil
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
            shutil.copyfile(source, target)
        _SNAPSHOTS[str(target.resolve())] = _relpath(source)
        _SNAPSHOT_OF[str(source.resolve())] = str(target.resolve())
        return target
    if target.exists():
        print(f"[mm_plot_style] 上游 {source} 不存在，使用图文件夹内快照 {target.name}", file=sys.stderr)
        _SNAPSHOTS[str(target.resolve())] = _relpath(source) + "（本次未找到，用快照）"
        _SNAPSHOT_OF[str(source.resolve())] = str(target.resolve())
        return target
    raise FileNotFoundError(f"绘图数据不存在：{source}（且图文件夹内无快照 {target.name}）")


def _existing_snapshot(source: Path, folder: Path) -> Path | None:
    """若本次运行已用 snapshot_data 把 source 快照到 folder（可能用了别名，如 data.csv），返回那个快照。"""
    try:
        snap = _SNAPSHOT_OF.get(str(source.resolve()))
    except OSError:
        return None
    if not snap:
        return None
    p = Path(snap)
    if p.exists() and p.parent == folder.resolve():
        return p
    return None


def _data_columns(path: Path, limit: int = 40) -> list[str]:
    if path.suffix.lower() not in (".csv", ".tsv"):
        return []
    try:
        with open(path, encoding="utf-8-sig") as fh:
            header = fh.readline().strip()
    except (OSError, UnicodeDecodeError):
        return []
    sep = "\t" if path.suffix.lower() == ".tsv" else ","
    return [c.strip() for c in header.split(sep)][:limit]


_README_MANUAL_MARK = "## 人工备注"


def _manual_section(text: str) -> str:
    """取 README 中人工备注二级标题（顶格独占一行）之后的内容；口水里提到的同名字串不算。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == _README_MANUAL_MARK:
            return "\n".join(lines[i + 1:]).strip()
    return ""


def _write_figure_readme(folder: Path, stem: str, info: dict, docstring: str, review: dict) -> None:
    readme = folder / "README.md"
    manual = ""
    if readme.exists():
        old = readme.read_text(encoding="utf-8")
        manual = _manual_section(old)
    lines = [f"# {stem}", ""]
    lines += ["> 本文件由 `mm_plot_style.save_fig` 自动生成，最后一节“人工备注”之后的内容会被保留。", ""]
    lines += ["## 图的作用与机理（摘自 make_figure.py 头部 docstring）", ""]
    lines += [docstring or "（绘图脚本缺少模块 docstring——请在脚本顶部写明：回答什么问题、每个元素对应的模型机理、数据列含义、参数与种子。）", ""]
    lines += ["## 文件", "", "| 文件 | 说明 |", "| --- | --- |"]
    lines.append(f"| `{FIGURE_SCRIPT_NAME}` | 绘图脚本，在项目根目录运行 `python figures/{folder.name}/{FIGURE_SCRIPT_NAME}` 重新生成 |")
    for ext, f in info["files"].items():
        lines.append(f"| `{Path(f).name}` | {ext.upper()} 输出{'（论文/Word 用）' if ext == 'pdf' else '（预览）' if ext == 'png' else '（可编辑矢量）' if ext == 'svg' else ''} |")
    for s in info["data"]:
        cols = ", ".join(s.get("columns", []))
        lines.append(f"| `{s['snapshot']}` | 数据快照，来源 `{s['source']}`{'；列：' + cols if cols else ''} |")
    lines += ["| `manifest.json` | 生成记录（脚本、数据、参数、字体、检查结果） |",
              "| `review.json` | 版式自检结果 + 人工审图记录 |", ""]
    if info["params"]:
        lines += ["## 参数", "", "```json", json.dumps(info["params"], ensure_ascii=False, indent=2), "```", ""]
    lines += ["## 自动检查", ""]
    findings = review.get("auto", {}).get("findings", [])
    if findings:
        lines += [f"- {f['level']} `{f['code']}`: {f['message']}" for f in findings]
    else:
        lines.append("- 无发现")
    lines += ["", f"字体：Latin `{info['fonts'].get('latin')}` / 中文 `{info['fonts'].get('cjk')}`；生成时间 {info['generated_at']}", ""]
    lines += [_README_MANUAL_MARK, "", manual or "（人工审图后在此记录：改动、待办、与论文正文的对应位置。）", ""]
    readme.write_text("\n".join(lines), encoding="utf-8")


def _update_review(folder: Path, stem: str, findings: list[dict]) -> dict:
    rpath = folder / "review.json"
    review: dict = {}
    if rpath.exists():
        try:
            review = json.loads(rpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            review = {}
    review.setdefault("figure", stem)
    review.setdefault("human", {"status": "pending", "reviewer": None, "date": None, "verdict": None, "notes": []})
    review["auto"] = {
        "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "findings": findings,
    }
    rpath.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review


def _layout_findings(fig, pdf: str | None) -> list[dict]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fig_layout_lint import lint_figure, lint_pdf  # noqa: WPS433
    except ImportError:
        return [{"level": "WARN", "code": "lint_missing", "message": "未找到 fig_layout_lint.py，跳过版式自检"}]
    out = [f.as_dict() for f in lint_figure(fig, palette=_ACTIVE.get("palette", "default"),
                                             base_size=float(_ACTIVE.get("base_size", 9.0)))]
    if pdf:
        seen = {(f["code"], f["message"]) for f in out}
        for f in lint_pdf(pdf):
            d = f.as_dict()
            if (d["code"], d["message"]) not in seen:
                out.append(d)
    return out


# --------------------------------------------------------------------------- #
# 统一保存
# --------------------------------------------------------------------------- #
def save_fig(
    fig,
    path: str | os.PathLike,
    *,
    formats: Sequence[str] | None = None,
    dpi: int = 300,
    source: str | os.PathLike | Sequence[str | os.PathLike] | None = None,
    params: dict | None = None,
    check: bool = True,
    layout_lint: bool = True,
    strict: bool = False,
    manifest: bool = True,
    layout: str = "auto",
    close: bool = True,
    caption: str | None = None,
) -> dict[str, str]:
    """统一导出。两种布局：

    - ``flat``：``figures/fig_q1_fit`` → 同目录写 fig_q1_fit.pdf/.png，记录进 ``_manifest.json``（mm-workbench 旧习惯）。
    - ``folder``（mm-draft-workbench 默认）：``figures/fig02_q1_fit/fig02_q1_fit`` → 该文件夹内写
      PDF/PNG/SVG + ``manifest.json`` + ``review.json`` + ``README.md``，并把 ``source`` 数据快照进文件夹。
      ``layout="auto"`` 时，父目录名与文件名相同或父目录含 ``make_figure.py`` 即视为 folder。

    check=True 运行 check_pdf（字体/中文/字号），layout_lint=True 运行 fig_layout_lint（重叠/越界/尺寸/配色）；
    FAIL 抛 RuntimeError，WARN 只记录到 review.json/manifest 供人工审图。
    caption：论文题注（含图内省略掉的细节说明）；folder 布局下写入 caption.md 并记入 manifest，供正文同步。
    """
    path = Path(path)
    stem = path.with_suffix("") if path.suffix.lower() in (".pdf", ".png", ".svg") else path
    folder = stem.parent
    if layout == "auto":
        layout = "folder" if (folder.name == stem.name or (folder / FIGURE_SCRIPT_NAME).exists()) else "flat"
    if layout not in ("flat", "folder"):
        raise ValueError("layout 必须是 'auto' | 'flat' | 'folder'")
    if formats is None:
        formats = ("pdf", "png", "svg") if layout == "folder" else ("pdf", "png")
    folder.mkdir(parents=True, exist_ok=True)

    fix_mixed_math_text(fig)
    # 版式自检需要在 savefig 之前完成一次 draw（savefig 内部也会 draw，顺序无影响）
    lint: list[dict] = []
    if layout_lint:
        try:
            fig.canvas.draw()
            lint = _layout_findings(fig, None)
        except Exception as exc:  # noqa: BLE001 - 自检不应阻断出图
            lint = [{"level": "WARN", "code": "lint_error", "message": f"版式自检异常: {exc}"}]

    written: dict[str, str] = {}
    for ext in formats:
        ext = ext.lower().lstrip(".")
        target = stem.with_suffix(f".{ext}")
        kw = {"dpi": dpi} if ext == "png" else {}
        fig.savefig(target, **kw)
        written[ext] = str(target)

    findings: list[tuple[str, str]] = []
    if check and "pdf" in written:
        findings = check_pdf(written["pdf"], strict=strict)
        for level, msg in findings:
            print(f"[check_figures] {level}: {stem.name}.pdf: {msg}", file=sys.stderr)
    if layout_lint and "pdf" in written:
        try:
            from fig_layout_lint import lint_pdf  # noqa: WPS433
            seen = {(f["code"], f["message"]) for f in lint}
            lint += [f.as_dict() for f in lint_pdf(written["pdf"]) if (f.code, f.message) not in seen]
        except ImportError:
            pass
    for f in lint:
        print(f"[fig_layout_lint] {f['level']} {f['code']}: {stem.name}: {f['message']}", file=sys.stderr)

    sources = [source] if isinstance(source, (str, os.PathLike)) else (list(source) if source else [])
    script = _script_path()
    data_records: list[dict] = []
    if layout == "folder":
        for s in sources:
            s = Path(s)
            snap = _existing_snapshot(s, folder)
            if snap is None and (s.exists() or (folder / s.name).exists()):
                snap = snapshot_data(s, folder)
            data_records.append({
                "source": _SNAPSHOTS.get(str(snap.resolve()), _relpath(s)) if snap else _relpath(s),
                "snapshot": snap.name if snap else None,
                "columns": _data_columns(snap) if snap else [],
            })
    info = {
        "figure": stem.name,
        "layout": layout,
        "files": {k: (Path(v).name if layout == "folder" else _relpath(v)) for k, v in written.items()},
        "script": (_relpath(script, folder if layout == "folder" else None) if script else None),
        "source": [_relpath(s) for s in sources],
        "data": data_records,
        "params": params or {},
        "caption": caption,
        "fonts": {k: _ACTIVE.get(k) for k in ("latin", "cjk", "pdf_fonttype")},
        "checks": [f"{lv}: {m}" for lv, m in findings],
        "layout_lint": lint,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    if manifest:
        if layout == "folder":
            (folder / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if caption is not None:
                (folder / "caption.md").write_text(caption.strip() + "\n", encoding="utf-8")
            review = _update_review(folder, stem.name, lint)
            _write_figure_readme(folder, stem.name, info, _script_docstring(script), review)
        else:
            mpath = folder / "_manifest.json"
            try:
                data = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
            except json.JSONDecodeError:
                data = {}
            data[stem.name] = info
            mpath.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if close:
        import matplotlib.pyplot as plt
        plt.close(fig)
    if any(lv == "FAIL" for lv, _ in findings) or (strict and any(f["level"] == "FAIL" for f in lint)):
        raise RuntimeError(f"{stem.name}.pdf 未通过图检查，见上方 [check_figures]/[fig_layout_lint] 输出")
    return written
