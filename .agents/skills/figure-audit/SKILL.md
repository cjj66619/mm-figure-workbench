---
name: figure-audit
description: 对范围内数据图做交付审计：产物齐全与新鲜度、版式 lint、PDF 字体/缺字/字号、脚本题注与论文题注比对（可选写回并留痕），输出 figures/figure_audit.json。
---

# figure-audit

脚本：`scripts/audit_figures.py <proj> [--only …] [--strict] [--apply-captions] [--lang zh|en]`

## 检查项与来源

| source | 内容 | 等级 |
| --- | --- | --- |
| outputs | pdf/png/svg 缺失 `output_missing`；产物比 make_figure.py 旧 `stale_output` | FAIL / WARN |
| layout_lint | 上次 `save_fig` 写入 `review.json` 的 Figure 级发现（重叠、越界、字号、配色、面板） | 沿用 |
| pdf_lint | 对 PDF 重跑 `lint_pdf`：`pdf_word_overlap` / `pdf_text_outside` / `pdf_line_through_text` | 沿用 |
| pdf_check | `check_pdf`：字体嵌入、中文可提取、`¤`/U+FFFD 缺字 `pdf_missing_glyph`、字号下限 `font_too_small` | 沿用 |
| caption | 脚本 `caption` vs 论文 `![…]`：`same` / `differs` / `no_script_caption` / `no_paper_ref` / `applied` | WARN / INFO |

`FIGURE_SCOPE.accept` 命中的代码降为 INFO 并标 `accepted: true`，报告单列，不影响 `--strict`。
图状态 = 其发现里最高等级；退出码 1 = 有 FAIL 或（`--strict`）有未接受 WARN。

## 题注写回（唯一允许改论文的动作）

`--apply-captions` 对 `differs` 的每处引用，只替换该行 `![` 与 `](` 之间的文字，路径与 `{#fig:…}` 原样保留；
paper/ 与 polish/ 两处都引用时两处都改。每处变更 `{file, line, before, after}` 记入 `figure_audit.json` →
报告"题注变更记录"。写回前先在报告"题注待同步"里逐条核对。

## 依赖降级

无 `pymupdf` 时 pdf_lint / pdf_check 记 INFO `*_skipped`，其余照常。
