---
name: figure-style
description: 数据图的配色、字体、公式与文字排布规范，以及实现它们的 mm_plot_style / fig_layout_lint 基础设施（本仓库唯一维护点，sync_tools.py 同步到项目 tools/）。
---

# figure-style

## 文件

| 文件 | 作用 |
| --- | --- |
| `scripts/mm_plot_style.py` | `apply_style` / `figsize` / `save_fig` / `snapshot_data` / 调色板 / 中英混排公式 / 防堆叠 helper / `check_pdf` |
| `scripts/fig_layout_lint.py` | Figure 级与 PDF 级版式检查（`save_fig` 自动调用；也可命令行复查） |
| `scripts/check_figures.py` | PDF 字体审计命令行（`--expect-cjk`、`--strict`） |
| `scripts/sync_tools.py` | 把以上三个文件同步到 `<proj>/tools/` 并更新 `VENDORED.json`；`--check` 只比对 |

规则：改这里 → `sync_tools.py <proj>` → 重跑项目图。不要在项目 `tools/` 里直接改。

## 配色（参考 Nature 系列图的克制用色）

`apply_style(lang="zh", base_size=8, palette=…)`：

| palette | 用途 |
| --- | --- |
| `nature` | 默认主色：深蓝 / 砖红 / 浅绿 / 青 / 紫 / 灰。少量类别、需要"一个主角"的图 |
| `nmi` | 低饱和同族色（蓝紫系为主）：多模型 / 多方法并列比较，谁都不抢眼，再用 `NATURE["red"]` 单独点亮选定方案 |
| `pastel` / `gray` | 背景层、置信带、"其它"类 |
| `default` | 旧图兼容 |

- 语义色保留：绿=好/通过/上升，红=差/失败/选中强调；不要把红绿用在无方向意义的类别上。
- 同一变量在全文各图颜色一致（lint `label_color_mismatch`）。
- 连续量用 `SEQUENTIAL_CMAP`（viridis），有正负用 `DIVERGING_CMAP`；禁 jet / rainbow / hsv。
- 单个颜色用 `NATURE["blue"]` 这样的具名色，不写裸 hex（lint `color_off_palette`）。

## 中英混排公式

Matplotlib mathtext 不做字体回退：`"滚动体数 $N_d$"` 在默认设置下中文会变成 `¤`。`apply_style` 已把
`mathtext.fontset=custom` 并把中文字体放进 fontfamily 首位，写法：

```python
ax.set_xlabel("滚动体数 $N_d$", **zh_math_kw())        # 单条文字
fix_mixed_math_text(fig)                                # 或者出图前对整张图兜底
```

不要再用 `N_d` 这种纯文本假下标。`check_pdf` 会把 PDF 里出现的 `¤` / U+FFFD 判 FAIL。

## 字号

- 基准 8 pt（`base_size=8`），全部文字 ≥ 5 pt：mathtext 上下标是 0.7×，所以含公式的文字基准 ≥ 7.2 pt。
- 对数轴刻度 `10^{-3}` 的上标会 < 5 pt：用普通数字 `0.001` 做刻度标签。
- 面板标签 `label_panels(axes, offset_pt=(-30, 3))` 用物理点偏移，多面板对齐误差 ≤ 1.5 pt。

## 防堆叠 helper

| helper | 场景 |
| --- | --- |
| `annotate_points(ax, xs, ys, labels)` | 散点逐点标签：贪心挑不压点、不压别的标签、不出界的偏移；最拥挤的点先放；偏移大时画细引线 |
| `place_text_clear(ax, text, candidates)` | 单条注释在几个候选角落里挑一个不与图元相交的位置 |
| `annotate_heatmap(ax, im)` | 热力图格内数值，按底色亮度自动黑/白字 |
| `save_fig(..., caption=…)` | 把长说明搬到题注：图内只留短标签，题注写进 manifest + `caption.md`，供 audit 与论文同步 |

## 布局

- `constrained_layout` 下 `fig.colorbar(ax=)` 会让同一行不同列的 axes 被拉成等宽、在图与色条间留大空隙；
  用 `cax = ax.inset_axes([1.04, 0, 0.05, 1]); fig.colorbar(im, cax=cax)`。
- 主面板占两列、副面板各一列这类**有意的**尺寸差异会触发 `panel_size_uneven`，在脚本 docstring 说明并写进
  `FIGURE_SCOPE.accept`。
- 一个远离主体的离群值（如"无训练的基线"）把纵轴拉得很长时：缩小坐标范围只看主体，离群值用 `marker="v"`
  钉在轴底并把真值写在标签里，题注注明"纵轴只显示 a–b"。这是布局不是数据改动，但必须在题注说明。
