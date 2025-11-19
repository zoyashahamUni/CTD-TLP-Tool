import argparse
from typing import Union
from .config_loader import load_json_config
from .model_interface import validate_model_contract
from .generator import generate_pairwise_twix
from .oracle import classify_row_with_nuxmv
from .ipo_runner import run_ipo_with_oracle

__version__ = "0.1.0"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ctd-tlp-tool",
        description="CTD–TLP Tool: generate combinatorial factor assignments and LTL specs",
    )
    parser.add_argument("-v", "--version", action="store_true", help="Show version and exit.")
    sub = parser.add_subparsers(dest="cmd")

    # -------- generate --------
    g = sub.add_parser("generate", help="Generate rows and specs")
    g.add_argument("--model", help="Path to SMV model (optional).")
    g.add_argument("--factors", help="Path to factors.json (optional).")
    g.add_argument("--print-rows", action="store_true", help="Print normalized factor domains.")
    g.add_argument("--print-specs", action="store_true", help="Print LTL specs per factor value.")
    g.add_argument(
        "--pairwise",
        action="store_true",
        help="Print IPO–Twix pairwise covering set of rows (Twix is the only pairwise generator).",
    )
    g.add_argument(
        "--ltl",
        action="store_true",
        help="Print LTL formula per row (used with --pairwise, Twix-based).",
    )

    # -------- oracle-batch --------
    ob = sub.add_parser("oracle-batch", help="Run oracle for all CTD rows (Twix pairwise)")
    ob.add_argument("--model", required=True, help="Path to SMV model")
    ob.add_argument("--factors", required=True, help="Path to factors.json")
    ob.add_argument(
        "--output-dir",
        default="output",
        help="Directory for traces and summaries",
    )

    # -------- oracle-ipo --------
    oi = sub.add_parser("oracle-ipo", help="Run oracle with IPO-style dynamic pairwise")
    oi.add_argument("--model", required=True, help="Path to SMV model")
    oi.add_argument("--factors", required=True, help="Path to factors.json")
    oi.add_argument(
        "--output-dir",
        default="output",
        help="Directory for traces and summaries",
    )

    return parser


def _render_value(v: Union[bool, int]) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)


def _profile_name_from_row(row: dict) -> str:
    """
    Build a short profile name from a row, e.g.
    {'a_no_logout_after_add': False, 'b_max_items': 3, 'c_no_remove': True}
    -> 'A0_B3_C1'
    """
    parts = []
    for name in sorted(row.keys()):
        v = row[name]
        if isinstance(v, bool):
            num = 1 if v else 0
        else:
            num = v
        abbrev = name[0].upper()  # A,B,C from the first letter
        parts.append(f"{abbrev}{num}")
    return "_".join(parts)


def _load_config(args):
    if args.factors:
        return load_json_config(args.factors)
    raise SystemExit("Use --factors to provide configuration.")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"ctd-tlp-tool {__version__}")
        return

    # =========================
    # cmd: generate
    # =========================
    if args.cmd == "generate":
        cfg = _load_config(args)

        # Validate model contract if a model was provided
        if args.model:
            ok, msg = validate_model_contract(args.model, cfg)
            if not ok:
                raise SystemExit("[ctd-tlp-tool] Model contract check failed: " + msg)

        # If both --pairwise and --ltl: build LTL per Twix row and exit
        if args.pairwise and args.ltl:
            from .ltl_builder import build_ltl_for_row
            rows = generate_pairwise_twix(cfg.factors)
            print("[ctd-tlp-tool] LTL formulas for Twix pairwise rows:")
            for i, row in enumerate(rows, 1):
                formula = build_ltl_for_row(cfg, row)
                print(f"\nRow {i:02d}: {row}")
                print(f"  LTL: {formula}")
            return

        # --pairwise: Twix pairwise rows
        if args.pairwise:
            rows = generate_pairwise_twix(cfg.factors)
            print(f"[ctd-tlp-tool] Twix pairwise rows: {len(rows)}")
            for i, row in enumerate(rows, 1):
                kv = ", ".join(f"{k}={_render_value(v)}" for k, v in row.items())
                print(f"  {i:02d}. {kv}")
            return

        # Print factor domains
        if args.print_rows:
            print("[ctd-tlp-tool] factors (normalized domains):")
            for f in cfg.factors:
                vals = ", ".join(_render_value(v) for v in (f.values or []))
                print(f"  - {f.name} ({f.kind}): [{vals}]")

        # Print per-value specs
        if args.print_specs:
            print("[ctd-tlp-tool] specs (per factor value using ltl_template):")
            template = cfg.ltl_template
            for f in cfg.factors:
                for v in (f.values or []):
                    val_str = _render_value(v)
                    cond = f"{f.name}={val_str}"

                    # Support both templates: {conditions} or {factor}/{value}
                    if "{conditions}" in template:
                        rendered = template.format(conditions=cond)
                    else:
                        rendered = template.format(factor=f.name, value=val_str)

                    print(f"  - {rendered}")

        if not args.print_rows and not args.print_specs and not args.pairwise:
            print("[ctd-tlp-tool] generate — add --print-rows, --print-specs, or --pairwise")
        return

    # =========================
    # cmd: oracle-batch
    # =========================
    if args.cmd == "oracle-batch":
        # 1. Load config from JSON
        cfg = load_json_config(args.factors)

        # 2. Validate model contract
        ok, msg = validate_model_contract(args.model, cfg)
        if not ok:
            raise SystemExit("[ctd-tlp-tool] Model contract check failed: " + msg)

        from pathlib import Path
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        print("[ctd-tlp-tool] oracle-batch (Twix pairwise)")
        print(f"  Model  : {args.model}")
        print(f"  Factors: {args.factors}")
        print(f"  Output : {out_dir}")

        # 3. Generate Twix pairwise rows (then feed to nuXmv)
        rows = generate_pairwise_twix(cfg.factors)
        print(f"[ctd-tlp-tool] Twix pairwise rows to send to oracle: {len(rows)}")

        results = []

        for i, row in enumerate(rows, 1):
            profile = _profile_name_from_row(row)
            kv = ", ".join(f"{k}={_render_value(v)}" for k, v in row.items())
            run_file = out_dir / f"run_{profile}.txt"

            print(f"  {i:02d}. {profile}: {kv}")
            print(f"       -> {run_file}")

            # Call nuXmv for this row
            result = classify_row_with_nuxmv(
                model_path=args.model,
                cfg=cfg,
                row=row,
                row_index=i,
                out_dir=args.output_dir,
                trace_path_override=str(run_file),
            )

            results.append((profile, result["feasible"], result["trace_path"]))

            status = "FEASIBLE" if result["feasible"] else "INFEASIBLE"
            print(f"       => {status}, trace: {result['trace_path']}")

        # After the loop: build summary files
        feasible_profiles = [p for (p, ok, _) in results if ok]
        infeasible_profiles = [p for (p, ok, _) in results if not ok]

        # 1) feasible.txt
        (out_dir / "feasible.txt").write_text(
            "\n".join(feasible_profiles) + "\n",
            encoding="utf-8",
        )

        # 2) infeasible.txt
        (out_dir / "infeasible.txt").write_text(
            "\n".join(infeasible_profiles) + "\n",
            encoding="utf-8",
        )

        # 3) summary.csv
        lines = ["profile,feasible"]
        for (p, ok, trace_path) in results:
            lines.append(f"{p},{int(ok)}")
        (out_dir / "summary.csv").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        print(f"[ctd-tlp-tool] wrote {len(feasible_profiles)} feasible profiles to {out_dir/'feasible.txt'}")
        print(f"[ctd-tlp-tool] wrote {len(infeasible_profiles)} infeasible profiles to {out_dir/'infeasible.txt'}")
        print(f"[ctd-tlp-tool] wrote summary CSV to {out_dir/'summary.csv'}")
        return

    # =========================
    # cmd: oracle-ipo
    # =========================
    if args.cmd == "oracle-ipo":
        # 1. Load config from JSON
        cfg = load_json_config(args.factors)

        # 2. Validate model contract
        ok, msg = validate_model_contract(args.model, cfg)
        if not ok:
            raise SystemExit("[ctd-tlp-tool] Model contract check failed: " + msg)

        from pathlib import Path
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        print("[ctd-tlp-tool] oracle-ipo (IPO-style dynamic pairwise)")
        print(f"  Model  : {args.model}")
        print(f"  Factors: {args.factors}")
        print(f"  Output : {out_dir}")

        # 3. Run IPO + oracle loop
        result = run_ipo_with_oracle(
            model_path=args.model,
            cfg=cfg,
            out_dir=args.output_dir,
        )

        print(f"[ctd-tlp-tool] IPO completed.")
        print(f"  Feasible profiles : {len(result['feasible'])}")
        print(f"  Infeasible profiles: {len(result['infeasible'])}")

        # Optional: print the profiles themselves
        if result["feasible"]:
            print("  Feasible list:")
            for p in result["feasible"]:
                print(f"    - {p}")
        if result["infeasible"]:
            print("  Infeasible list:")
            for p in result["infeasible"]:
                print(f"    - {p}")

        return

    # Fallback: no command
    parser.print_help()


if __name__ == "__main__":
    main()
