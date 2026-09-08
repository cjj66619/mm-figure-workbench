"""run_figures.py — 一键跑数据图管线：inventory → (sync-tools) → regenerate → audit → report。

用法：
    python run_figures.py <proj> [--only fig06,fig07] [--no-regen] [--sync-tools] [--apply-captions] [--strict] [--lang zh]

步骤：
    inventory   figures/figure_inventory.json（数据图/示意图/模板分类 + FIGURE_SCOPE + 论文题注）
    sync-tools  校验项目 tools/ 与工作流的 mm_plot_style/fig_layout_lint/check_figures 是否一致；
                不一致只 WARN，加 --sync-tools 才覆盖（并更新 VENDORED.json）
    regenerate  逐张以当前解释器运行 figures/<id>/make_figure.py（cwd=<proj>），任一张抛错即停
    audit       figures/figure_audit.json
    report      figures/FIGURE_REPORT.md

只写：figures/figure_inventory.json、figures/figure_audit.json、figures/FIGURE_REPORT.md、
各图文件夹里 make_figure.py 自己的产物（pdf/png/svg/manifest/review/README/caption.md），
--sync-tools 时的 tools/ 三个脚本，--apply-captions 时论文 md 的 ![题注]。其它一律不动。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
STEPS = {
    "inventory": SKILLS / "figure-inventory" / "scripts" / "inventory_figures.py",
    "sync-tools": SKILLS / "figure-style" / "scripts" / "sync_tools.py",
    "audit": SKILLS / "figure-audit" / "scripts" / "audit_figures.py",
    "report": SKILLS / "figure-report" / "scripts" / "report_figures.py",
}


def run(name: str, argv: list[str], cwd: Path | None = None) -> int:
    print(f"\n=== [{name}] {' '.join(argv)}", flush=True)
    t0 = time.monotonic()
    rc = subprocess.run([sys.executable, *argv], cwd=str(cwd) if cwd else None, check=False).returncode
    print(f"=== [{name}] rc={rc}  {time.monotonic() - t0:.1f}s", flush=True)
    return rc


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj")
    ap.add_argument("--only", default=None, help="逗号分隔的图 id / fnmatch 模式")
    ap.add_argument("--no-regen", action="store_true", help="不重跑 make_figure.py，只审计现有产物")
    ap.add_argument("--sync-tools", action="store_true", help="用工作流版本覆盖项目 tools/ 三个脚本")
    ap.add_argument("--apply-captions", action="store_true", help="把脚本题注写回论文 md")
    ap.add_argument("--strict", action="store_true", help="audit 里未接受的 WARN 也视为失败")
    ap.add_argument("--lang", default="zh", choices=("zh", "en"))
    args = ap.parse_args()
    proj = Path(args.proj).resolve()
    if not (proj / "figures").is_dir():
        print(f"[error] {proj / 'figures'} 不存在", file=sys.stderr)
        return 2
    missing = [p for p in STEPS.values() if not p.is_file()]
    if missing:
        print(f"[error] 缺少脚本：{missing}", file=sys.stderr)
        return 2

    only = ["--only", args.only] if args.only else []
    inv_rel = "figures/figure_inventory.json"
    if run("inventory", [str(STEPS["inventory"]), str(proj), *only, "--out", inv_rel]):
        return 1

    if (proj / "tools").is_dir():
        rc = run("sync-tools", [str(STEPS["sync-tools"]), str(proj), *([] if args.sync_tools else ["--check"])])
        if rc == 1 and not args.sync_tools:
            print("[warn] 项目 tools/ 与工作流不一致；加 --sync-tools 覆盖后重跑，或先看两边差异", flush=True)
        elif rc:
            return 1

    if not args.no_regen:
        inv = json.loads((proj / inv_rel).read_text(encoding="utf-8"))
        todo = [it for it in inv["figures"] if it.get("in_scope")]
        print(f"\n=== [regenerate] {len(todo)} 张", flush=True)
        for it in todo:
            script = proj / it["path"] / "make_figure.py"
            if run(f"regen {it['id']}", [str(script)], cwd=proj):
                print(f"[error] {it['id']} 重生成失败，停止", file=sys.stderr)
                return 1

    audit_args = [str(STEPS["audit"]), str(proj), *only, "--lang", args.lang]
    if args.strict:
        audit_args.append("--strict")
    if args.apply_captions:
        audit_args.append("--apply-captions")
    rc_audit = run("audit", audit_args)
    if rc_audit == 2:
        return 2
    if run("report", [str(STEPS["report"]), str(proj)]):
        return 1
    print(f"\n完成：{proj / 'figures' / 'FIGURE_REPORT.md'}", flush=True)
    return rc_audit


if __name__ == "__main__":
    sys.exit(main())
