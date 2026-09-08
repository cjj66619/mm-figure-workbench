# AGENTS.md — mm-figure-workbench

数模论文**数据图优化**专用下游工作流（`mm-draft-workbench` 出图 → 本仓库优化 → `mm-layout-workbench` 排版）。
输入一个项目目录 `<proj>`（含 `figures/`、`tools/`、`paper/` 或 `polish/`），输出仍在 `<proj>/figures/`。
入口技能：`.agents/skills/figure-kickoff/SKILL.md`。

本仓库是通用工具，服务于任何一届比赛的任何项目：**不得写入任何具体项目的图号、模型名、变量名、题注文本或结论。**
项目特有的东西只能出现在项目自己的 `figures/<id>/make_figure.py` 与 `figures/FIGURE_SCOPE.json` 里。

## 硬规则（违反即失败）

1. **只优化数据图**：`figures/<id>/` 同时含 `make_figure.py` + `manifest.json` 才算；含 `.drawio` / `REDRAW_NOTES.md`
   的示意图（流程图、路线图、机理图）与 `_` 开头的模板文件夹一律跳过。判定用 `inventory_figures.py` 的规则，不靠名字猜。
2. **不改科学内容**：不改数据快照、不改 `results/`、不改任何计算/阈值/取值；不手改 PNG/PDF/SVG——所有变化必须来自
   `make_figure.py` 重跑。只允许改：文字与标签、公式写法、颜色、尺寸/布局、坐标范围（配合题注说明）、题注。
3. **题注可改但必须留痕**：`save_fig(caption=)` 声明题注 → `audit_figures.py --apply-captions` 写回论文 md 的
   `![题注](figures/<id>/…)`，before/after 记入 `figure_audit.json` 与 `FIGURE_REPORT.md`。除题注外 `paper/`、`polish/`
   一个字不动。
4. **只写**：`figures/figure_inventory.json`、`figures/figure_audit.json`、`figures/FIGURE_REPORT.md`、各图文件夹
   由 `save_fig` 产出的文件、`--sync-tools` 时 `tools/` 的三个脚本。`data/`、`code/`、`results/`、`layout/` 只读。
5. **样式只从 `mm_plot_style` 取**：`apply_style(palette=…)` + `PALETTES` / `NATURE`；不在图脚本里写裸色值、不用
   jet/rainbow/hsv；文字 5 pt ≤ 字号（含 mathtext 上下标 ≈ 0.7×）；`svg.fonttype=none` 保持 SVG 文字可编辑。
6. **基础设施改在这里，再 sync 到项目**：`mm_plot_style.py` / `fig_layout_lint.py` / `check_figures.py` 的唯一维护点是
   `.agents/skills/figure-style/scripts/`；项目里的 `tools/` 副本用 `sync_tools.py` 整体替换，不要在项目里 fork。
7. 代码：Python 3.10+，`pathlib`，读写显式 `encoding="utf-8"`，跨平台（Windows/Linux），子进程用列表形式；
   依赖只有 matplotlib / numpy / pandas，`pymupdf` 可选（缺失时 PDF 级检查降级为 INFO）。
8. 不提交比赛数据、图产物、凭据到仓库。

## 管线

```text
figure-kickoff/scripts/run_figures.py <proj> [--only …] [--apply-captions] [--strict]
  → figure-inventory/scripts/inventory_figures.py   分类 + FIGURE_SCOPE + 论文题注 → figures/figure_inventory.json
  → figure-style/scripts/sync_tools.py --check      项目 tools/ 是否与工作流一致（--sync-tools 才覆盖）
  → 逐张 python figures/<id>/make_figure.py          重生成（save_fig 内已跑 lint_figure / check_pdf / lint_pdf）
  → figure-audit/scripts/audit_figures.py           产物齐全、lint、PDF 字体/缺字、题注比对 → figures/figure_audit.json
  → figure-report/scripts/report_figures.py         figures/FIGURE_REPORT.md（结论 + 题注变更 + 待办）
```

逐图改脚本的方法与配方见 `figure-polish/SKILL.md`；配色/字体/公式规范见 `figure-style/SKILL.md`。

## 改代码后必须跑

```bash
python -m compileall -q .agents/skills scripts
python scripts/smoke_test.py      # 临时最小项目：1 张数据图（中英混排公式 + 散点标签）+ 1 张示意图 + 模板 → 全管线
```

有真实项目时 `run_figures.py <proj> --only <两三张>` 看 `FIGURE_REPORT.md` 没有新增 FAIL / 误报。
