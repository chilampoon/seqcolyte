"""``python -m sim run --config <yaml>`` — run the failure simulator."""

from __future__ import annotations

import argparse
import json

from sim.config import load_config
from sim.engine import run_simulation
from sim.registry import known_modes


def cmd_run(args: argparse.Namespace) -> int:
    manifest = run_simulation(load_config(args.config))
    print(json.dumps({
        "name": manifest["name"],
        "n_pairs": manifest["n_pairs"],
        "label_counts": manifest["label_counts"],
        "label_fractions": manifest["label_fractions"],
        "r1_byte_identical": manifest["r1_byte_identical"],
        "outputs": manifest["outputs"],
    }, indent=2))
    return 0


def cmd_modes(args: argparse.Namespace) -> int:
    print("\n".join(known_modes()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sim", description="Seqcolyte failure simulator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run", help="run a simulation from a YAML config")
    rp.add_argument("--config", required=True)
    rp.set_defaults(func=cmd_run)
    mp = sub.add_parser("modes", help="list registered failure modes")
    mp.set_defaults(func=cmd_modes)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
