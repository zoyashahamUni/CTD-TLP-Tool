# tool/sanity_twix.py
from __future__ import annotations

from tool.generator import generate_pairwise_twix  
from tool.config_loader import load_json_config


def main():
    # Adjust the path if you want a different factors file,
    # but this should work from the repo root:
    cfg = load_json_config("examples/shopping/factors.json")
    rows = generate_pairwise_twix(cfg.factors)

    print("[sanity_twix] rows produced by TWIX:")
    for i, row in enumerate(rows, 1):
        print(f"{i:02d}. {row}")


if __name__ == "__main__":
    main()
