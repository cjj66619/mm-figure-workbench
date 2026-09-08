---
name: figure-kickoff
description: 数据图优化工作流入口。给定数模项目目录，盘点数据图、逐张重生成、审计版式/字体/题注并出报告；先做 2–3 张样图确认风格再铺开。
---

# figure-kickoff

## 何时用

用户说"优化图 / 图太乱 / 配色难看 / 公式渲染错 / 文字堆叠"，且项目是 mm-draft-workbench 生成的
一图一文件夹结构（`figures/<id>/make_figure.py` + `manifest.json`）。

## 流程

1. **盘点**：`python .agents/skills/figure-inventory/scripts/inventory_figures.py <proj>`，
   确认 data / diagram / template 分类符合预期；示意图绝不进入优化。需要缩小范围或接受例外时写
   `<proj>/figures/FIGURE_SCOPE.json`（格式见 inventory 脚本 docstring）。
2. **基线**：`python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --no-regen`，
   拿到改图前的 `figures/FIGURE_REPORT.md`，知道每张图现有的 WARN。
3. **同步基础设施**：报告里 sync-tools 提示不一致时，`run_figures.py <proj> --sync-tools --no-regen`
   把工作流版本的 `mm_plot_style.py` / `fig_layout_lint.py` / `check_figures.py` 覆盖到 `<proj>/tools/`。
4. **先做样图**：挑 2–3 张有代表性问题的图（公式、堆叠、多系列配色各一），按 `figure-polish/SKILL.md`
   改 `make_figure.py`，`run_figures.py <proj> --only figA,figB` 重跑 + 审计，把 PNG 发给用户确认风格。
5. **铺开**：确认后逐张处理其余数据图，每改几张跑一次 `run_figures.py <proj>`。
6. **题注**：所有 `caption_differs` 逐条核对无误后 `run_figures.py <proj> --no-regen --apply-captions`；
   报告"题注变更记录"即审计留痕。
7. **交付**：`run_figures.py <proj> --strict` 应为 0 FAIL；剩余 WARN 要么修掉，要么写进 FIGURE_SCOPE.accept
   并说明理由。最后跑一次项目自带的 `python tools/figure_index.py` 刷新 `figures/README.md` / `FIGURE_REVIEW.md`。

## 参数

| 参数 | 作用 |
| --- | --- |
| `--only fig06_*,fig07_*` | 只处理匹配的图（与 FIGURE_SCOPE.include 取交集） |
| `--no-regen` | 不重跑 make_figure.py，只审计现有产物 |
| `--sync-tools` | 覆盖项目 tools/ 三个脚本并更新 VENDORED.json |
| `--apply-captions` | 把脚本题注写回论文 md |
| `--strict` | 未接受的 WARN 也非零退出（交付门禁） |
| `--lang en` | 英文论文：不要求 PDF 可提取中文 |

## 排错

- `regen` 抛 `RuntimeError: … 未通过图检查`：save_fig 的 check_pdf 报 FAIL（缺字 ¤ / 字体未嵌入），看上方
  `[check_figures]` 行；中英混排公式用 `zh_math_kw()`。
- `pdf_lint_skipped` / `pdf_check_skipped`：环境缺 `pymupdf`，PDF 级检查降级，不影响其它步骤。
- Windows 上中文乱码：脚本已 `reconfigure(encoding="utf-8")`，终端用 `chcp 65001` 或 PowerShell 7。
