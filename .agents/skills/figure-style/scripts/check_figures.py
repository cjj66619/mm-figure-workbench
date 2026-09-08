#!/usr/bin/env python3
"""检查论文图 PDF：字体嵌入、轮廓合法性（Noto CJK OTF + fonttype=42 乱码）、
中文可提取、字号下限、图宽。

用法（在项目根目录）::

    python tools/check_figures.py --expect-cjk figures/     # 遍历 figures/*.pdf 与 figures/<fig_id>/<fig_id>.pdf
    python tools/check_figures.py --strict figures/fig02_q1_fit/   # Type3 也判 FAIL

退出码：0 全部通过；1 存在 FAIL；2 参数/文件错误。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mm_plot_style import check_pdf  # noqa: E402


def iter_pdfs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(path.glob("*.pdf")))
            for sub in sorted(x for x in path.iterdir() if x.is_dir() and not x.name.startswith(("_", "."))):
                out.extend(sorted(sub.glob(f"{sub.name}.pdf")) or sorted(sub.glob("*.pdf")))
        elif path.suffix.lower() == ".pdf" and path.exists():
            out.append(path)
        else:
            print(f"[check_figures] 跳过非 PDF 或不存在的路径: {p}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="PDF 文件或目录")
    ap.add_argument("--expect-cjk", action="store_true", help="要求能提取出中文字符（中文论文图）")
    ap.add_argument("--no-cjk", action="store_true", help="明确不检查中文（英文图）")
    ap.add_argument("--strict", action="store_true", help="Type3 字体也判 FAIL")
    ap.add_argument("--max-width-cm", type=float, default=16.0, help="版心宽度上限，默认 16 cm")
    ap.add_argument("--min-font-pt", type=float, default=5.0, help="最小字号，默认 5 pt")
    args = ap.parse_args(argv)

    pdfs = iter_pdfs(args.paths)
    if not pdfs:
        print("[check_figures] 没有可检查的 PDF", file=sys.stderr)
        return 2
    expect = True if args.expect_cjk else (False if args.no_cjk else None)

    n_fail = 0
    for pdf in pdfs:
        findings = check_pdf(pdf, expect_cjk=expect, strict=args.strict,
                             max_width_cm=args.max_width_cm, min_font_pt=args.min_font_pt)
        status = "FAIL" if any(lv == "FAIL" for lv, _ in findings) else ("WARN" if findings else "OK")
        n_fail += status == "FAIL"
        print(f"{status:4s} {pdf}")
        for lv, msg in findings:
            print(f"     - {lv}: {msg}")
    print(f"[check_figures] {len(pdfs)} 个 PDF，{n_fail} 个 FAIL")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
