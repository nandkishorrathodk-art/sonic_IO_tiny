"""
SONIC v2 — Self-Evolution Engine CLI Runner
===========================================
Dedicated command-line interface for running automated codebase upgrades,
bug fixes, and logical enhancements.

Usage Examples:
    # 1. Apply a patch with automated tests, auto-commit, and git push:
    python -m sonic.evolution.cli patch --target sonic-core/sonic/tools/sample.py --code-file new_code.py --desc "Upgrade parser logic" --auto-promote --push

    # 2. Apply a unified diff file with auto-promotion:
    python -m sonic.evolution.cli patch --target sonic-core/sonic/research/fast_graph.py --diff-file fix.patch --desc "Fix boundary index bug" --auto-promote

    # 3. Dry-run / test without committing or pushing:
    python -m sonic.evolution.cli patch --target sonic-core/sonic/tools/sample.py --diff-file fix.patch --no-auto-promote
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sonic.evolution.codebase_evolver import CodebaseEvolver, EvolutionSummaryReport
from sonic.evolution.pipeline import EvolutionStage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sonic.evolution.cli",
        description="🧬 SONIC Self-Evolution Engine — Automated Codebase Patcher & Upgrade Runner",
    )
    subparsers = parser.add_subparsers(dest="command", help="Evolution command")

    # Command: patch
    patch_parser = subparsers.add_parser("patch", help="Apply a code patch, verify via automated tests, commit, and push")
    patch_parser.add_argument("--target", required=True, help="Target component file relative to repository root")
    patch_parser.add_argument("--desc", required=True, help="Description of the bug fix, upgrade, or logical enhancement")
    patch_parser.add_argument("--diff-file", help="Path to a unified diff (.patch) or code replacement file")
    patch_parser.add_argument("--diff", help="Raw diff or code string passed directly")
    patch_parser.add_argument("--auto-promote", action="store_true", default=True, help="Auto-commit on 100%% test pass without human approval (default: True)")
    patch_parser.add_argument("--no-auto-promote", dest="auto_promote", action="store_false", help="Do not auto-commit, await manual approval")
    patch_parser.add_argument("--push", action="store_true", default=False, help="Git push to origin after successful promotion")
    patch_parser.add_argument("--tests", nargs="*", help="Specific pytest files/paths to verify against")
    patch_parser.add_argument("--summary-out", help="Optional output path to save the generated markdown summary")

    # Command: status
    subparsers.add_parser("status", help="Show self-evolution engine safety status and protected components")

    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    evolver = CodebaseEvolver()

    if args.command == "status":
        print("=" * 70)
        print("🧬 SONIC CONTINUOUS CODEBASE EVOLUTION ENGINE")
        print("=" * 70)
        print(f"Repository Root: {evolver.repo_root}")
        print("\nProtected Safety Components (AI Self-Modification FORBIDDEN):")
        from sonic.evolution.codebase_evolver import _PROTECTED_COMPONENTS
        for c in sorted(_PROTECTED_COMPONENTS):
            print(f"  ⛔ {c}")
        print("\nAll other components (tools, agents, research, mission_engine) are EVOLVABLE.")
        return 0

    if args.command == "patch":
        diff_content = ""
        if args.diff_file:
            p = Path(args.diff_file)
            if not p.exists():
                print(f"Error: Diff file not found: {args.diff_file}", file=sys.stderr)
                return 1
            diff_content = p.read_text(encoding="utf-8", errors="replace")
        elif args.diff:
            diff_content = args.diff
        else:
            print("Error: Must provide either --diff-file or --diff", file=sys.stderr)
            return 1

        print("🧬 Starting Codebase Evolution Cycle...")
        print(f"   Target:      {args.target}")
        print(f"   Description: {args.desc}")
        print(f"   Auto-Promote:{args.auto_promote}")
        print(f"   Git Push:    {args.push}")
        print("-" * 70)

        report: EvolutionSummaryReport = evolver.evolve(
            target_component=args.target,
            description=args.desc,
            code_diff=diff_content,
            auto_promote=args.auto_promote,
            push=args.push,
            test_paths=args.tests,
        )

        md = report.to_markdown()
        print("\n" + md + "\n")

        if args.summary_out:
            out_p = Path(args.summary_out)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(md, encoding="utf-8")
            print(f"📝 Summary saved to: {args.summary_out}")

        if report.stage in (EvolutionStage.PROMOTED, EvolutionStage.AWAITING_APPROVAL):
            return 0
        else:
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
