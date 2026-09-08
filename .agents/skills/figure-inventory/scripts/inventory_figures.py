"""inventory_figures.py — 盘点 <proj>/figures/*/，用确定性规则区分数据图与示意图，并关联论文题注。

用法：
    python inventory_figures.py <proj> [--only fig06,fig07] [--out figures/figure_inventory.json] [--quiet]

分类规则（不看图名、不猜语义）：
    template  文件夹名以 `_` 或 `.` 开头（`_template_figure` 等）
    diagram   含 *.drawio / REDRAW_NOTES.md（流程图、路线图、机理图；本工作流不碰）
    data      含 make_figure.py + manifest.json（mm_plot_style.save_fig 产出）——唯一进入优化管线的类型
    other     其余（缺 manifest 的半成品、手工放进来的图片等）——列出但不处理

范围覆盖：<proj>/figures/FIGURE_SCOPE.json（可选）
    {
      "include": ["fig0*"],                  # 只处理匹配的 data 图（fnmatch，缺省全部）
      "exclude": ["fig13_*"],                # 手工排除
      "accept": {"fig07_*": ["panel_size_uneven"]}   # 已人工确认可接受的 lint 代码（audit 降为 INFO）
    }
`--only` 与 include 取交集。

题注：扫 <proj>/paper/sections/*.md 与 <proj>/polish/sections/*.md（存在哪个扫哪个，两个都在就都扫，
保证题注同步时两处一致）里的
    ![题注](figures/<fig_id>/<任意文件>){#fig:xxx}
记录 file:line 与题注文本；同一图被多处引用时全部记录。

只读；`--out` 指定时写 JSON（相对 <proj>），否则打印到 stdout。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

SCOPE_NAME = "FIGURE_SCOPE.json"
IMG_RE = re.compile(r"!\[(?P<cap>.*?)\]\((?P<path>figures/(?P<fig>[^/)]+)/[^)]*)\)(?P<attr>\{[^}]*\})?")


def load_scope(figures_dir: Path) -> dict:
    p = figures_dir / SCOPE_NAME
    if not p.is_file():
        return {"include": [], "exclude": [], "accept": {}}
    scope = json.loads(p.read_text(encoding="utf-8"))
    return {"include": list(scope.get("include", [])), "exclude": list(scope.get("exclude", [])),
            "accept": dict(scope.get("accept", {}))}


def classify(folder: Path) -> str:
    if folder.name.startswith(("_", ".")):
        return "template"
    if any(folder.glob("*.drawio")) or (folder / "REDRAW_NOTES.md").is_file():
        return "diagram"
    if (folder / "make_figure.py").is_file() and (folder / "manifest.json").is_file():
        return "data"
    return "other"


def _match_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def accepted_codes(name: str, accept: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for pat, codes in accept.items():
        if fnmatch.fnmatch(name, pat):
            out.extend(codes)
    return sorted(set(out))


def sections_dirs(proj: Path) -> list[Path]:
    return [proj / rel for rel in ("paper/sections", "polish/sections") if (proj / rel).is_dir()]


def scan_captions(proj: Path) -> dict[str, list[dict]]:
    """fig_id -> [{file, line, caption, attr}]；file 为相对 proj 的 POSIX 路径。"""
    out: dict[str, list[dict]] = {}
    for md in sorted(md for sec in sections_dirs(proj) for md in sec.glob("*.md")):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for m in IMG_RE.finditer(line):
                out.setdefault(m["fig"], []).append({
                    "file": md.relative_to(proj).as_posix(), "line": i,
                    "caption": m["cap"], "attr": m["attr"] or "",
                })
    return out


def _manifest(folder: Path) -> dict:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_inventory(proj: Path, only: list[str] | None = None) -> dict:
    figures_dir = proj / "figures"
    if not figures_dir.is_dir():
        raise FileNotFoundError(f"{figures_dir} 不存在")
    scope = load_scope(figures_dir)
    captions = scan_captions(proj)
    items: list[dict] = []
    for folder in sorted(p for p in figures_dir.iterdir() if p.is_dir()):
        kind = classify(folder)
        item: dict = {"id": folder.name, "kind": kind, "path": folder.relative_to(proj).as_posix()}
        if kind == "data":
            m = _manifest(folder)
            in_scope = (not scope["include"] or _match_any(folder.name, scope["include"])) \
                and not _match_any(folder.name, scope["exclude"]) \
                and (not only or _match_any(folder.name, only) or folder.name in only)
            item.update({
                "in_scope": in_scope,
                "script": "make_figure.py",
                "outputs": m.get("files", {}),
                "source": m.get("source", []),
                "script_caption": m.get("caption"),
                "accept": accepted_codes(folder.name, scope["accept"]),
                "paper_captions": captions.get(folder.name, []),
            })
        else:
            item["in_scope"] = False
            item["reason"] = {"template": "模板/隐藏文件夹", "diagram": "示意图（drawio/REDRAW_NOTES），不做数据图优化",
                              "other": "缺 make_figure.py 或 manifest.json"}[kind]
        items.append(item)
    counts = {k: sum(1 for it in items if it["kind"] == k) for k in ("data", "diagram", "template", "other")}
    counts["in_scope"] = sum(1 for it in items if it.get("in_scope"))
    return {"project": str(proj), "sections_dirs": [d.relative_to(proj).as_posix() for d in sections_dirs(proj)],
            "scope": scope, "counts": counts, "figures": items}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj")
    ap.add_argument("--only", default=None, help="逗号分隔的图 id 或 fnmatch 模式，与 FIGURE_SCOPE include 取交集")
    ap.add_argument("--out", default=None, help="写 JSON 的路径（相对 proj）；缺省打印到 stdout")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    proj = Path(args.proj).resolve()
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    try:
        inv = build_inventory(proj, only)
    except FileNotFoundError as e:
        print(f"[inventory] {e}", file=sys.stderr)
        return 2
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.out:
        out = proj / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        if not args.quiet:
            c = inv["counts"]
            print(f"[inventory] data {c['data']}（在范围内 {c['in_scope']}）, diagram {c['diagram']}, "
                  f"template {c['template']}, other {c['other']} → {out.relative_to(proj).as_posix()}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
