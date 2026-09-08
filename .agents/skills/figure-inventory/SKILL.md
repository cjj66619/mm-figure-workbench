---
name: figure-inventory
description: 用确定性规则盘点项目 figures/ 目录：哪些是可优化的数据图、哪些是必须跳过的示意图/模板，并关联论文里的题注与 FIGURE_SCOPE 覆盖。
---

# figure-inventory

脚本：`scripts/inventory_figures.py <proj> [--only …] [--out figures/figure_inventory.json]`

## 分类规则（按顺序命中）

| kind | 判据 | 处理 |
| --- | --- | --- |
| template | 文件夹名以 `_` / `.` 开头 | 跳过 |
| diagram | 含 `*.drawio` 或 `REDRAW_NOTES.md` | 跳过（流程图 / 路线图 / 机理图由人工重画） |
| data | 含 `make_figure.py` + `manifest.json` | 进入优化 |
| other | 其余 | 列出不处理（半成品、手工图片） |

只看文件，不看名字、不猜语义。一张"看起来像数据图"的 drawio 也不会被处理——要优化它先把它改成 make_figure.py。

## FIGURE_SCOPE.json（放在 `<proj>/figures/`，可选）

```json
{
  "include": ["fig0*", "fig1[0-4]_*"],
  "exclude": ["fig13_*"],
  "accept": {"fig07_*": ["panel_size_uneven"], "*": ["missing_axis_label"]}
}
```

- `include` 为空 = 全部数据图；`--only` 再与之取交集。
- `accept` 是"已人工确认可接受"的 lint 代码：audit 把它们降为 INFO 并标 `accepted`，报告单列。
  写理由到 FIGURE_REPORT 无法自动做到，请在提交说明或 review.json 的 `human.notes` 里补一句。

## 题注关联

扫 `paper/sections/*.md` 与 `polish/sections/*.md`（都在则都扫）里的 `![题注](figures/<id>/…){#fig:…}`，
每处引用记 `file:line + caption`。这是 audit 做题注比对、`--apply-captions` 定点改写的依据；
同一张图在两个目录各引用一次时，两处都会被同步。
