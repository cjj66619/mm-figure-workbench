"""sync_tools.py — 把本工作流维护的绘图基础设施（mm_plot_style / fig_layout_lint / check_figures）
同步到项目的 tools/，并更新 tools/VENDORED.json 的来源与哈希。

用法：
    python sync_tools.py <proj>            # 复制 + 更新 VENDORED.json
    python sync_tools.py <proj> --check    # 只比对哈希：项目里的版本落后/被改过则非零退出

项目里的 tools/ 是随论文交付的副本，规则是"整体替换、不在项目里 fork"；要改样式或 lint 规则，
改这里的脚本再 sync 回去。绝不覆盖 tools/fonts/ 与项目自己的其它脚本。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ("mm_plot_style.py", "fig_layout_lint.py", "check_figures.py")
REL_FROM = ".agents/skills/figure-style/scripts"


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    tools = Path(args.proj).resolve() / "tools"
    if not tools.is_dir():
        print(f"[sync_tools] {tools} 不存在（项目应有 tools/ 目录）", file=sys.stderr)
        return 2
    vend_path = tools / "VENDORED.json"
    vend = json.loads(vend_path.read_text(encoding="utf-8")) if vend_path.is_file() else {"files": {}}
    vend.setdefault("files", {})

    stale: list[str] = []
    for name in FILES:
        src, dst = HERE / name, tools / name
        same = dst.is_file() and sha16(src) == sha16(dst)
        if args.check:
            state = "ok" if same else ("missing" if not dst.is_file() else "differs")
            print(f"[sync_tools] {name}: {state}")
            if not same:
                stale.append(name)
            continue
        if not same:
            shutil.copy2(src, dst)
            print(f"[sync_tools] 已更新 tools/{name}")
        vend["files"][name] = {"from": f"{REL_FROM}/{name}", "sha256_16": sha16(dst), "workbench": "mm-figure-workbench"}
    if args.check:
        if stale:
            print(f"[sync_tools] 项目 tools/ 与工作流不一致：{', '.join(stale)}（运行 sync_tools.py <proj> 更新）")
            return 1
        return 0
    vend["generated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    vend_path.write_text(json.dumps(vend, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[sync_tools] VENDORED.json 已更新 → {vend_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
