"""mm-figure-workbench 冒烟测试：临时目录里造一个最小项目并跑完整管线。

项目含：1 张数据图（中英混排公式 + 散点标签 + 题注）、1 张 drawio 示意图、1 个模板文件夹、
paper/sections/01.md 里一处旧题注。断言：分类计数、无 FAIL、产物齐全、题注被写回、报告生成。
无中文字体的环境自动退化为英文（lang=en）。用法：python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
STYLE = SKILLS / "figure-style" / "scripts"
KICKOFF = SKILLS / "figure-kickoff" / "scripts" / "run_figures.py"

FIGURE_SCRIPT = '''"""smoke — 冒烟测试用最小数据图。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from mm_plot_style import NATURE, annotate_points, apply_style, figsize, label_panels, save_fig, zh_math_kw  # noqa: E402

LANG = "__LANG__"
XL = "滚动体数 $N_d$" if LANG == "zh" else "count $N_d$"
YL = "得分" if LANG == "zh" else "score"
CAP = "冒烟图题注（新）：$N_d$ 与得分" if LANG == "zh" else "smoke caption (new): $N_d$ vs score"


def main() -> None:
    apply_style(lang=LANG, base_size=8, palette="nmi")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize("full", aspect=0.45))
    xs = np.arange(1, 7)
    ys = np.array([0.91, 0.92, 0.915, 0.93, 0.905, 0.925])
    ax1.scatter(xs, ys, s=18, color=NATURE["blue"], zorder=3)
    annotate_points(ax1, xs, ys, [f"M{i}" for i in xs], fontsize=6)
    ax1.set_xlabel(XL, **zh_math_kw())
    ax1.set_ylabel(YL)
    ax2.bar(["A", "B", "C"], [1, 2, 3])
    ax2.set_xlabel("x")
    ax2.set_ylabel(YL)
    label_panels((ax1, ax2), offset_pt=(-30, 3))
    save_fig(fig, HERE / HERE.name, source=None, params={"seed": 0}, caption=CAP)


if __name__ == "__main__":
    main()
'''


def _has_cjk() -> bool:
    sys.path.insert(0, str(STYLE))
    import warnings

    from mm_plot_style import resolve_fonts  # noqa: E402

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return resolve_fonts(lang="zh")["cjk"] is not None


def build_project(proj: Path, lang: str) -> None:
    tools = proj / "tools"
    tools.mkdir(parents=True)
    for name in ("mm_plot_style.py", "fig_layout_lint.py", "check_figures.py"):
        shutil.copy2(STYLE / name, tools / name)
    fig = proj / "figures" / "fig01_smoke"
    fig.mkdir(parents=True)
    (fig / "make_figure.py").write_text(FIGURE_SCRIPT.replace("__LANG__", lang), encoding="utf-8")
    (fig / "manifest.json").write_text("{}", encoding="utf-8")
    dia = proj / "figures" / "fig02_diagram"
    dia.mkdir()
    (dia / "fig02_diagram.drawio").write_text("<mxfile/>", encoding="utf-8")
    (proj / "figures" / "_template_figure").mkdir()
    sec = proj / "paper" / "sections"
    sec.mkdir(parents=True)
    (sec / "01.md").write_text(
        "# 一\n\n如图所示。\n\n![旧题注](figures/fig01_smoke/fig01_smoke.pdf){#fig:smoke}\n", encoding="utf-8")


def run(proj: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(KICKOFF), str(proj), "--lang", *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    lang = "zh" if _has_cjk() else "en"
    tmp = Path(tempfile.mkdtemp(prefix="mmfig_smoke_"))
    try:
        proj = tmp / "proj"
        build_project(proj, lang)
        r = run(proj, lang, "--apply-captions", "--strict")
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            print(f"FAIL: run_figures 退出码 {r.returncode}")
            return 1
        inv = json.loads((proj / "figures" / "figure_inventory.json").read_text(encoding="utf-8"))
        c = inv["counts"]
        assert (c["data"], c["diagram"], c["template"]) == (1, 1, 1), c
        aud = json.loads((proj / "figures" / "figure_audit.json").read_text(encoding="utf-8"))
        assert aud["summary"]["fail"] == 0, aud["summary"]
        fig = proj / "figures" / "fig01_smoke"
        for ext in ("pdf", "png", "svg"):
            assert (fig / f"fig01_smoke.{ext}").is_file(), ext
        assert (fig / "caption.md").is_file()
        md = (proj / "paper" / "sections" / "01.md").read_text(encoding="utf-8")
        assert "![旧题注]" not in md and "(figures/fig01_smoke/fig01_smoke.pdf){#fig:smoke}" in md, md
        assert any(f["caption"]["status"] == "applied" for f in aud["figures"]), "题注未写回"
        assert (proj / "figures" / "FIGURE_REPORT.md").is_file()
        print(f"PASS (lang={lang})")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
