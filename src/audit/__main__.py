"""``python -m src.audit <experiment_id>`` — print one decision chain.

What ``make audit EXPERIMENT=<id>`` runs. Reads only; there is no write path
here and no way to reach one.
"""

from __future__ import annotations

import argparse
import sys

from src.audit.log import DEFAULT_DB_PATH, AuditLog, render_chain


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.audit")
    parser.add_argument("experiment_id", nargs="?", help="experiment to print")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--list", action="store_true", help="list experiments in the log")
    args = parser.parse_args()

    log = AuditLog(args.db)
    if args.list or not args.experiment_id:
        ids = log.experiments()
        if not ids:
            print(f"No audit entries in {args.db}.")
            return 1
        print(f"{len(ids)} experiments in {args.db}:")
        for experiment_id in ids:
            print(f"  {experiment_id}  ({len(log.chain(experiment_id))} entries)")
        print(f"\nchain intact: {'yes' if log.verify() else 'NO — TAMPERED'}")
        return 0

    print(render_chain(log, args.experiment_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
