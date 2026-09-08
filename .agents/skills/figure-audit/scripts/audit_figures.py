"""audit_figures.py — 对范围内的数据图做交付审计，汇总成 figures/figure_audit.json。

用法：
    python audit_figures.py <proj> [--only fig06,fig07] [--strict] [--apply-captions]
                                   [--inventory figures/figure_inventory.json]

每张 in_scope 的数据图检查：
    outputs        pdf/png/svg 是否齐全；输出是否比 make_figure.py 旧（stale_output）
    layout_lint    上次重生成时 save_fig 写进 review.json 的 Figure 级发现（重叠/越界/字号/配色/面板…）
    pdf_lint       对 PDF 重新跑 fig_layout_lint.lint_pdf（词重叠、越界、线穿字）
    pdf_check      mm_plot_style.check_pdf（字体嵌入、中文可提取、¤/U+FFFD 缺字、字号下限）
    caption        make_figure.py 通过 save_fig(caption=) 声明的题注 vs 论文 md 里 ![题注](figures/<id>/…)
                   status: same / differs / no_script_caption / no_paper_ref
                   --apply-captions 时把 differs 的论文题注替换为脚本题注，并把 before/after 记入审计（这是本工作流
                   唯一允许写 paper/polish 的动作，只改 ![...] 中括号里的文字，其它一个字不动）

FIGURE_SCOPE.json 的 accept 里列出的 lint 代码降为 INFO 并标 accepted=true（已人工确认可接受，如
"共用 colorbar 导致 panel_size_uneven"）。

退出码：0 通过；1 有 FAIL（或 --strict 下有未接受的 WARN）；2 参数/环境错误。
只写 figures/figure_audit.json（以及 --apply-captions 时的论文 md 题注）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
sys.path.insert(0, str(SKILLS / "figure-inventory" / "scripts"))
from inventory_figures import IMG_RE, build_inventory  # noqa: E402

LEVEL_RANK = {"FAIL": 2, "WARN": 1, "INFO": 0}


def _import_tools(proj: Path):
    """优先用项目自己的 tools/（与出图时同版本），没有再退回工作流副本。"""
    for cand in (proj / "tools", SKILLS / "figure-style" / "scripts"):
        if (cand / "mm_plot_style.py").is_file() and (cand / "fig_layout_lint.py").is_file():
            sys.path.insert(0, str(cand))
            break
    import matplotlib
    matplotlib.use("Agg")
    from fig_layout_lint import lint_pdf  # noqa: WPS433
    from mm_plot_style import check_pdf  # noqa: WPS433
    return lint_pdf, check_pdf


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def audit_one(proj: Path, item: dict, lint_pdf, check_pdf, expect_cjk: bool, apply_captions: bool) -> dict:
    folder = proj / item["path"]
    fid = item["id"]
    accept = set(item.get("accept", []))
    findings: list[dict] = []

    def add(level: str, code: str, message: str, source: str) -> None:
        f = {"level": level, "code": code, "message": message, "source": source}
        if code in accept and level != "FAIL":
            f.update({"level": "INFO", "accepted": True, "original_level": level})
        findings.append(f)

    outputs = item.get("outputs") or {}
    script = folder / "make_figure.py"
    for ext in ("pdf", "png", "svg"):
        out = folder / outputs.get(ext, f"{fid}.{ext}")
        if not out.is_file():
            add("FAIL", "output_missing", f"缺 {ext}：{out.name}", "outputs")
        elif script.is_file() and out.stat().st_mtime < script.stat().st_mtime:
            add("WARN", "stale_output", f"{out.name} 比 make_figure.py 旧，需重跑", "outputs")

    review = _load(folder / "review.json")
    for f in review.get("auto", {}).get("findings", []):
        add(f.get("level", "WARN"), f.get("code", "?"), f.get("message", ""), "layout_lint")

    pdf = folder / outputs.get("pdf", f"{fid}.pdf")
    if pdf.is_file():
        try:
            for f in lint_pdf(pdf):
                add(f.level, f.code, f.message, "pdf_lint")
        except Exception as e:  # pymupdf 缺失等
            add("INFO", "pdf_lint_skipped", f"lint_pdf 不可用：{e}", "pdf_lint")
        try:
            for level, msg in check_pdf(pdf, expect_cjk=expect_cjk):
                if level in ("FAIL", "WARN"):
                    code = "pdf_missing_glyph" if ("¤" in msg or "FFFD" in msg) else \
                        "font_too_small" if "字号" in msg else "pdf_font"
                    add(level, code, msg, "pdf_check")
        except Exception as e:
            add("INFO", "pdf_check_skipped", f"check_pdf 不可用：{e}", "pdf_check")

    # 题注
    cap: dict = {"script": item.get("script_caption"), "paper": item.get("paper_captions", []), "changes": []}
    if not cap["script"]:
        cap["status"] = "no_script_caption"
        add("INFO", "caption_not_declared", "make_figure.py 未通过 save_fig(caption=) 声明题注，无法核对", "caption")
    elif not cap["paper"]:
        cap["status"] = "no_paper_ref"
        add("WARN", "caption_no_paper_ref", "论文 md 里没有引用这张图", "caption")
    else:
        differs = [c for c in cap["paper"] if _norm(c["caption"]) != _norm(cap["script"])]
        cap["status"] = "differs" if differs else "same"
        if differs and apply_captions:
            for c in differs:
                md = proj / c["file"]
                lines = md.read_text(encoding="utf-8").splitlines(keepends=True)
                line = lines[c["line"] - 1]
                new_line, n = _replace_caption(line, fid, cap["script"])
                if n:
                    lines[c["line"] - 1] = new_line
                    md.write_text("".join(lines), encoding="utf-8")
                    cap["changes"].append({"file": c["file"], "line": c["line"], "before": c["caption"], "after": cap["script"]})
            cap["status"] = "applied"
            add("INFO", "caption_applied", f"已把 {len(cap['changes'])} 处论文题注替换为脚本题注（见 caption.changes）", "caption")
        elif differs:
            add("WARN", "caption_differs", "脚本题注与论文题注不一致；确认后用 --apply-captions 同步", "caption")

    worst = max((LEVEL_RANK[f["level"]] for f in findings), default=0)
    return {"id": fid, "path": item["path"], "status": {2: "FAIL", 1: "WARN", 0: "OK"}[worst],
            "counts": {k: sum(1 for f in findings if f["level"] == k) for k in ("FAIL", "WARN", "INFO")},
            "accepted": sorted(accept), "findings": findings, "caption": cap}


def _replace_caption(line: str, fid: str, new_cap: str) -> tuple[str, int]:
    n = 0

    def sub(m: re.Match) -> str:
        nonlocal n
        if m["fig"] != fid:
            return m.group(0)
        n += 1
        return f"![{new_cap}]({m['path']}){m['attr'] or ''}"

    return IMG_RE.sub(sub, line), n


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj")
    ap.add_argument("--only", default=None)
    ap.add_argument("--strict", action="store_true", help="未接受的 WARN 也视为失败")
    ap.add_argument("--apply-captions", action="store_true", help="把脚本题注写回论文 md（记录 before/after）")
    ap.add_argument("--lang", default="zh", choices=("zh", "en"), help="zh 时要求 PDF 能提取出中文")
    ap.add_argument("--out", default="figures/figure_audit.json")
    args = ap.parse_args(argv)
    proj = Path(args.proj).resolve()
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    try:
        inv = build_inventory(proj, only)
    except FileNotFoundError as e:
        print(f"[audit] {e}", file=sys.stderr)
        return 2
    lint_pdf, check_pdf = _import_tools(proj)

    results = [audit_one(proj, it, lint_pdf, check_pdf, args.lang == "zh", args.apply_captions)
               for it in inv["figures"] if it.get("in_scope")]
    skipped = [{"id": it["id"], "kind": it["kind"], "reason": it.get("reason", "不在 FIGURE_SCOPE/--only 范围内")}
               for it in inv["figures"] if not it.get("in_scope")]
    summary = {
        "figures": len(results),
        "ok": sum(1 for r in results if r["status"] == "OK"),
        "warn": sum(1 for r in results if r["status"] == "WARN"),
        "fail": sum(1 for r in results if r["status"] == "FAIL"),
        "findings": {k: sum(r["counts"][k] for r in results) for k in ("FAIL", "WARN", "INFO")},
        "accepted": sum(1 for r in results for f in r["findings"] if f.get("accepted")),
        "caption": {s: sum(1 for r in results if r["caption"]["status"] == s)
                    for s in ("same", "differs", "applied", "no_script_caption", "no_paper_ref")},
        "caption_changes": sum(len(r["caption"]["changes"]) for r in results),
    }
    out = proj / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "project": str(proj),
                               "sections_dirs": inv["sections_dirs"], "strict": args.strict, "summary": summary,
                               "figures": results, "skipped": skipped}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in results:
        print(f"[audit] {r['status']:4s} {r['id']}  FAIL {r['counts']['FAIL']} / WARN {r['counts']['WARN']} / "
              f"INFO {r['counts']['INFO']}  题注:{r['caption']['status']}")
    print(f"[audit] {summary['figures']} 张：OK {summary['ok']} / WARN {summary['warn']} / FAIL {summary['fail']}；"
          f"跳过 {len(skipped)} → {out.relative_to(proj).as_posix()}")
    if summary["fail"] or (args.strict and summary["warn"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
