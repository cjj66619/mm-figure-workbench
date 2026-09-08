---
name: figure-polish
description: 逐张优化数据图的操作程序：读脚本与论文上下文 → 诊断五类问题（文字繁琐、公式渲染、要素堆叠、配色、整体风格）→ 只改 make_figure.py 的呈现层 → 重跑审计 → 题注留痕。
---

# figure-polish

对象：`inventory` 判为 data 且 in_scope 的每一张图。每张图一个循环，改完立刻重跑，不要一次改十张再看。

## 0. 先读，再动手

1. `figures/<id>/make_figure.py` 的 docstring（回答什么问题、每个图元的机理、已知缺陷）和 `README.md`。
2. 论文里引用它的段落（inventory 给了 `file:line`）：图要支撑正文的哪个结论，主面板是哪一个。
3. 现有 `review.json` 的 auto.findings 与基线 `FIGURE_REPORT.md` 里这张图的条目。
4. 打开 PNG 看一眼，按下面五类记问题清单。

## 1. 五类问题与处置

| 问题 | 判据 | 处置 |
| --- | --- | --- |
| 文字繁琐 | 图内一条文字 > 36 单位（中文 1 / 英文 0.5）或 > 2 行；lint `text_verbose` | 图内留短标签（"最优 $N_d$=…"），完整说明搬进 `save_fig(caption=)`；标题只写"是什么"，不写"怎么算" |
| 公式渲染 | `N_d`、`d/D`、`10^-3` 等假公式；PDF 出现 `¤` | 改成 mathtext 并加 `**zh_math_kw()`；对数刻度用普通数字 |
| 要素堆叠 | lint `text_overlap` / `text_crowded` / `legend_over_data` / `text_over_data` / `pdf_line_through_text` | 散点标签 `annotate_points`；注释 `place_text_clear`；图例移到图外 `bbox_to_anchor`；热力图 `annotate_heatmap`；面板标签 `label_panels(offset_pt=)` |
| 配色 | 裸 hex、`C0…C9` 默认色、彩虹图、红绿乱用 | `apply_style(palette="nature"/"nmi")`；多方法比较用 nmi + 单一强调色；连续量 viridis |
| 整体风格 | 坐标轴四边框、粗线、图例边框、面板尺寸失衡、标题长 | 依赖 `apply_style` 的默认（去上右轴、细线、无图例框）；一个主面板视觉占优；标题 ≤ 12 字 |

## 2. 可以改 / 不能改

可以：文字、标签、标题、图例位置、颜色、marker、线宽、字号、面板比例与 gridspec、坐标范围（配题注说明）、
注释位置、题注。

不能：`snapshot_data` 的来源与内容、任何 `results/` 文件、脚本里的计算（均值/排序/阈值/最优点的选择）、
在图里新增或删除数据系列、把某个数据点"移一点让它好看"。离群值处理只能用"钉在轴边 + 标真值"的方式。

## 3. 改完必须做

```bash
python .agents/skills/figure-kickoff/scripts/run_figures.py <proj> --only <id>
```

- `[check_figures]` 无 FAIL；`FIGURE_REPORT.md` 这张图的 WARN 只剩已说明的例外（写进 `FIGURE_SCOPE.accept`）。
- 看 PNG：中文/公式/下标正确，无堆叠，颜色克制，主面板突出。
- 题注：脚本里 `caption=` 与论文原题注不一致时先不写回，等全部样图确认后统一 `--apply-captions`。
- 在脚本 docstring "已知视觉缺陷" 一节更新：删掉已修的，写上有意为之的（如面板宽度不等的原因）。

## 4. 配方速查

```python
apply_style(lang="zh", base_size=8, palette="nmi")
ax.set_xlabel("滚动体数 $N_d$", **zh_math_kw())
annotate_points(ax, xs, ys, labels, fontsize=6, color=[NATURE["red"] if sel else "black" for sel in is_sel])
place_text_clear(ax, "$N_d$=20", [(0.98, 0.96, "right", "top"), (0.02, 0.96, "left", "top")])
annotate_heatmap(ax, im, fontsize=6)
cax = ax.inset_axes([1.04, 0, 0.05, 1]); fig.colorbar(im, cax=cax, label="…")
ax.legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=3, borderaxespad=0)     # 图例放到轴上方
label_panels(axes, offset_pt=(-30, 3))
save_fig(fig, HERE / FIG_ID, source=SRC, params={...}, caption="……")
```
