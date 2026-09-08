# mm-figure-workbench

数模论文**数据图优化**工作流：对 mm-draft-workbench 生成的一图一文件夹项目（`figures/<id>/make_figure.py`），
逐张改善文字、公式、排布、配色与风格，全部变化来自重跑脚本，不动数据、不动结论，题注改动留痕可审。

```text
mm-draft-workbench（出图） → mm-figure-workbench（本仓库，优化数据图） → mm-layout-workbench（排版）
```

## 快速开始

```bash
python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --no-regen           # 基线报告
python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --sync-tools --no-regen   # 升级项目 tools/
# 按 .agents/skills/figure-polish/SKILL.md 改 figures/<id>/make_figure.py
python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --only fig06_*,fig07_*    # 重跑 + 审计样图
python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --apply-captions --strict # 交付
```

产物：`figures/figure_inventory.json`、`figures/figure_audit.json`、`figures/FIGURE_REPORT.md`。

## 技能

| 技能 | 作用 |
| --- | --- |
| `figure-kickoff` | 入口与一键管线 `run_figures.py` |
| `figure-inventory` | 数据图 / 示意图 / 模板的确定性分类；`FIGURE_SCOPE.json` 覆盖；论文题注关联 |
| `figure-style` | 配色（nature / nmi）、中英混排公式、字号、防堆叠 helper；`mm_plot_style` / `fig_layout_lint` 的维护点与 `sync_tools.py` |
| `figure-polish` | 逐张优化的操作程序：五类问题的判据与处置、可改/不可改边界、配方 |
| `figure-audit` | 产物 / lint / PDF 字体 / 题注比对与写回 |
| `figure-report` | `FIGURE_REPORT.md` |

## 范围

- 只处理同时含 `make_figure.py` + `manifest.json` 的文件夹；含 `.drawio` / `REDRAW_NOTES.md` 的示意图和 `_` 开头的模板跳过。
- 不修改任何具体项目的数据、计算或结论；本仓库也不包含任何具体项目的内容。

## 依赖

Python 3.10+，matplotlib、numpy、pandas；可选 `pymupdf`（PDF 级检查）。无 LaTeX、无 pandoc。

## 开发

```bash
python -m compileall -q .agents/skills scripts
python scripts/smoke_test.py
```
