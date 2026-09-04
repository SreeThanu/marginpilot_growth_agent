"""Print the Day-2 sanity report for an already-generated dev split.

Cycle 2 needs the Cycle 1 report to compare against, and `python -m src.world`
only prints one as a side effect of generating. Dev worlds only.
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.world.__main__ import _print_report, _world_summary
from src.world.persistence import load_world

root = Path(sys.argv[1])
summaries, ids = [], []
for path in sorted(root.glob("*.world.json")):
    world = load_world(path)
    summaries.append(_world_summary(world))
    if not ids:
        ids = [i.intervention_id for i in world.interventions]
    del world
_print_report(summaries, ids)
