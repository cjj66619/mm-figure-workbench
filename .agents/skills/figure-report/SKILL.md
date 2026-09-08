---
name: figure-report
description: 把 figure_audit.json 渲染成 figures/FIGURE_REPORT.md：一句结论、逐图状态表、题注变更留痕、待处理 WARN/FAIL 及修法、已接受例外、跳过的示意图、人工审图待办。
---

# figure-report

脚本：`scripts/report_figures.py <proj> [--audit figures/figure_audit.json] [--out figures/FIGURE_REPORT.md]`

## 章节

1. 结论：范围内几张、FAIL/WARN/OK 各几张、题注一致/已同步/待同步计数。
2. 逐图状态表。
3. 题注变更记录（`--apply-captions` 后）：`file:line` + 原/新——这是给论文侧核对"见图 X"引用语的依据。
4. 题注待同步：脚本题注 vs 论文题注并列。
5. 待处理 FAIL / WARN：每条附修法提示（`FIX_HINTS`，按 lint 代码查表）。
6. 已接受例外（FIGURE_SCOPE.accept）。
7. 未处理的文件夹：示意图 / 模板 / 范围外的数据图及原因。
8. 人工审图待办（固定清单）。

## 约定

- 只写一个文件；不改 audit JSON。
- 新增 lint 代码时同步补 `FIX_HINTS`，否则报告里该条没有修法提示。
- 报告面向人：不出现绝对路径、不贴 JSON。
