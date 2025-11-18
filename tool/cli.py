import argparse
from typing import Union
from .config_loader import load_json_config, load_inline_config_from_smv
from .model_interface import validate_model_contract
from .generator import generate_full_combinations, generate_pairwise
from .oracle import classify_row_with_nuxmv

__version__ = "0.1.0"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ctd-tlp-tool",
        description="CTD–TLP Tool: generate combinatorial factor assignments and LTL specs",
    )
    parser.add_argument("-v", "--version", action="store_true", help="Show version and exit.")
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("generate", help="Generate rows and specs")
    
    # Oracle-batch command
    ob = sub.add_parser("oracle-batch", help="Run oracle for all CTD rows")
    ob.add_argument("--model", required=True, help="Path to SMV model")
    ob.add_argument("--factors", required=True, help="Path to factors.json")
    ob.add_argument("--output-dir", default="output", help="Directory for traces and summaries")
    
    g.add_argument("--model", help="Path to SMV model (optional).")
    g.add_argument("--factors", help="Path to factors.json (optional).")
    g.add_argument("--print-rows", action="store_true", help="Print normalized factor domains.")
    g.add_argument("--print-specs", action="store_true", help="Print LTL specs per factor value.")
    g.add_argument("--full", action="store_true", help="Print full Cartesian product of factors.")
    g.add_argument("--pairwise", action="store_true", help="Print greedy pairwise covering set of rows.")
    g.add_argument("--ltl", action="store_true", help="Print LTL formula per row (used with --pairwise).")
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
        # For booleans, use 0/1; for ints, use the number as-is
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
    if args.model:
        return load_inline_config_from_smv(args.model)
    raise SystemExit("[ctd-tlp-tool] No configuration provided. Use --factors or --model.")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"ctd-tlp-tool {__version__}")
        return

    if args.cmd == "generate":
        cfg = _load_config(args)

        # Validate model contract if a model was provided
        if args.model:
            ok, msg = validate_model_contract(args.model, cfg)
            if not ok:
                raise SystemExit("[ctd-tlp-tool] Model contract check failed: " + msg)
    
        # If both --pairwise and --ltl: build LTL per pairwise row and exit    
        if args.pairwise and args.ltl:
            from .ltl_builder import build_ltl_for_row
            rows = generate_pairwise(cfg.factors)
            print("[ctd-tlp-tool] LTL formulas for pairwise rows:")
            for i, row in enumerate(rows, 1):
                formula = build_ltl_for_row(cfg, row)
                print(f"\nRow {i:02d}: {row}")
                print(f"  LTL: {formula}")
            return


        # --pairwise: greedy pairwise rows
        if args.pairwise:
            rows = generate_pairwise(cfg.factors)
            print(f"[ctd-tlp-tool] pairwise rows: {len(rows)}")
            for i, row in enumerate(rows, 1):
                kv = ", ".join(f"{k}={_render_value(v)}" for k, v in row.items())
                print(f"  {i:02d}. {kv}")
            return

        # --full: full Cartesian product
        if args.full:
            rows = generate_full_combinations(cfg.factors)
            print(f"[ctd-tlp-tool] full combinations: {len(rows)} rows")
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
            for f in cfg.factors:
                for v in (f.values or []):
                    rendered = cfg.ltl_template.format(factor=f.name, value=_render_value(v))
                    print(f"  - {rendered}")

        if not args.print_rows and not args.print_specs:
            print("[ctd-tlp-tool] generate — add --print-rows, --print-specs, --full or --pairwise")
        return

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
        
        print("[ctd-tlp-tool] oracle-batch")
        print(f"  Model  : {args.model}")
        print(f"  Factors: {args.factors}")
        print(f"  Output : {out_dir}")

        # 3. Generate pairwise rows (later these will be fed to nuXmv)
        rows = generate_pairwise(cfg.factors)
        print(f"[ctd-tlp-tool] pairwise rows to send to oracle: {len(rows)}")
        
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


    parser.print_help()

if __name__ == "__main__":
    main()
