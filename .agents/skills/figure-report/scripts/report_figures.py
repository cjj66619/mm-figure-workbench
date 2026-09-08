"""report_figures.py — 把 figures/figure_audit.json 汇总成人能读的 figures/FIGURE_REPORT.md。

用法：
    python report_figures.py <proj> [--audit figures/figure_audit.json] [--out figures/FIGURE_REPORT.md]

内容：结论一句话 → 逐图状态表 → 题注变更记录（before/after，供论文侧核对）→ 未接受的 WARN/FAIL 清单与修法
→ 已接受的例外 → 跳过的示意图/模板 → 人工审图待办。只写 --out 指定的一个文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIX_HINTS = {
    "text_overlap": "缩短文字 / 改 loc / 用 place_text_clear()、annotate_points()",
    "text_crowded": "标签自动避让 annotate_points()，或减少标签、错位排布",
    "text_verbose": "图内只留短标签，长说明移到题注（save_fig(caption=)）",
    "text_clipped": "缩短或换行；label_panels(offset_pt=) 用物理点偏移；检查 constrained_layout",
    "legend_over_data": "legend(loc=…) 放到图外（bbox_to_anchor）或空白角",
    "text_over_data": "注释移到空白处（place_text_clear 候选位）",
    "font_too_small": "mathtext 上下标是基准的 0.7 倍：含公式的文字基准 ≥ 7.2 pt；对数轴刻度用普通数字代替 10^{-3}",
    "pdf_missing_glyph": "中英混排公式用 zh_math_kw() 或 fix_mixed_math_text(fig)",
    "color_off_palette": "只用 apply_style(palette=) 选定的 PALETTES / NATURE 颜色",
    "label_color_mismatch": "同一变量在各面板用同一颜色（按图例标签统一）",
    "panel_size_uneven": "共用 colorbar / 主副面板时可在 FIGURE_SCOPE.accept 里接受；否则统一 gridspec 比例",
    "panel_label_misaligned": "label_panels(axes, offset_pt=(-30, 3)) 统一用物理偏移",
    "pdf_line_through_text": "参考线画在文字下方（zorder）或给文字加白底 bbox",
    "pdf_word_overlap": "同 text_overlap；旋转刻度或减少刻度",
    "missing_axis_label": "补 set_xlabel/set_ylabel（含单位）",
    "stale_output": "重跑 make_figure.py",
    "output_missing": "重跑 make_figure.py，检查 save_fig 是否抛错",
    "caption_differs": "确认脚本题注后 audit --apply-captions 同步到论文",
    "caption_no_paper_ref": "论文里补 ![题注](figures/<id>/<id>.png){#fig:…} 或从 FIGURE_SCOPE exclude",
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def render(audit: dict) -> str:
    s = audit["summary"]
    L: list[str] = ["# 数据图审计报告（FIGURE_REPORT）", "",
                    f"> 生成时间 {audit['generated']}；由 mm-figure-workbench `audit_figures.py` → `report_figures.py` 产出。"
                    f"只审 `figures/` 下的数据图（make_figure.py + manifest.json）；示意图不在范围内。", ""]
    verdict = "全部通过" if not s["fail"] and not s["warn"] else \
        f"{s['fail']} 张 FAIL、{s['warn']} 张有未接受的 WARN"
    L += ["## 结论", "",
          f"- 范围内 {s['figures']} 张数据图：{verdict}（OK {s['ok']}）。",
          f"- 发现：FAIL {s['findings']['FAIL']} / WARN {s['findings']['WARN']} / INFO {s['findings']['INFO']}，"
          f"其中已接受例外 {s['accepted']} 条。",
          f"- 题注：一致 {s['caption']['same']}，已同步 {s['caption']['applied']}（{s['caption_changes']} 处），"
          f"待同步 {s['caption']['differs']}，脚本未声明 {s['caption']['no_script_caption']}，"
          f"论文未引用 {s['caption']['no_paper_ref']}。", ""]

    L += ["## 逐图状态", "", "| 图 | 状态 | FAIL | WARN | INFO | 题注 | 已接受例外 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in audit["figures"]:
        c = r["counts"]
        L.append(f"| `{r['id']}` | {r['status']} | {c['FAIL']} | {c['WARN']} | {c['INFO']} | {r['caption']['status']} | "
                 f"{', '.join(r['accepted']) or '—'} |")
    L.append("")

    changes = [(r["id"], ch) for r in audit["figures"] for ch in r["caption"]["changes"]]
    if changes:
        L += ["## 题注变更记录（已写入论文）", ""]
        for fid, ch in changes:
            L += [f"### `{fid}` — `{ch['file']}:{ch['line']}`", "", f"- 原：{ch['before']}", f"- 新：{ch['after']}", ""]
    pending = [r for r in audit["figures"] if r["caption"]["status"] == "differs"]
    if pending:
        L += ["## 题注待同步（脚本题注 ≠ 论文题注）", ""]
        for r in pending:
            L += [f"### `{r['id']}`", "", f"- 脚本：{r['caption']['script']}"]
            for c in r["caption"]["paper"]:
                L.append(f"- 论文 `{c['file']}:{c['line']}`：{c['caption']}")
            L.append("")

    open_items = [(r["id"], f) for r in audit["figures"] for f in r["findings"]
                  if f["level"] in ("FAIL", "WARN") and not f.get("accepted")]
    L += ["## 待处理的 FAIL / WARN", ""]
    if not open_items:
        L.append("无。")
    for fid, f in open_items:
        hint = FIX_HINTS.get(f["code"], "")
        L.append(f"- **{f['level']}** `{fid}` `{f['code']}`：{f['message']}" + (f"　→ {hint}" if hint else ""))
    L.append("")

    accepted = [(r["id"], f) for r in audit["figures"] for f in r["findings"] if f.get("accepted")]
    if accepted:
        L += ["## 已接受的例外（FIGURE_SCOPE.json accept）", ""]
        for fid, f in accepted:
            L.append(f"- `{fid}` `{f['code']}`（原 {f['original_level']}）：{f['message']}")
        L.append("")

    if audit.get("skipped"):
        L += ["## 未处理的文件夹", ""]
        for it in audit["skipped"]:
            L.append(f"- `{it['id']}`（{it['kind']}）：{it['reason']}")
        L.append("")

    L += ["## 人工审图待办", "",
          "- [ ] 逐图打开 PNG：文字是否可读、没有堆叠；公式（下标/斜体）是否正确；配色是否与全文其它图一致",
          "- [ ] 题注变更是否与正文引用语一致（`见图 X` 后面的描述）",
          "- [ ] 数值型注释（最优点、指标）与 results/ 报告一致——本工作流不改数据，但请确认",
          "- [ ] 已接受例外是否仍然成立（如共用 colorbar 的面板宽度差）",
          "- [ ] 在各图 `review.json` 的 `human` 字段记录 reviewer / date / verdict，然后重跑 `tools/figure_index.py`", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj")
    ap.add_argument("--audit", default="figures/figure_audit.json")
    ap.add_argument("--out", default="figures/FIGURE_REPORT.md")
    args = ap.parse_args(argv)
    proj = Path(args.proj).resolve()
    audit_path = proj / args.audit
    if not audit_path.is_file():
        print(f"[report] 缺 {audit_path}，先跑 audit_figures.py", file=sys.stderr)
        return 2
    out = proj / args.out
    out.write_text(render(_load(audit_path)), encoding="utf-8")
    print(f"[report] → {out.relative_to(proj).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
