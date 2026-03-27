"""Code metrics collection for benchmark report."""

import os
from pathlib import Path


def count_loc(directory: str, extensions: tuple = (".py", ".sql", ".json")) -> dict:
    """Count lines of code by file type. Returns {ext: {files: N, loc: N, sloc: N}}."""
    results = {}
    for ext in extensions:
        results[ext] = {"files": 0, "loc": 0, "sloc": 0}

    for root, _dirs, files in os.walk(directory):
        for f in files:
            ext = Path(f).suffix
            if ext in extensions:
                path = os.path.join(root, f)
                with open(path) as fh:
                    lines = fh.readlines()
                results[ext]["files"] += 1
                results[ext]["loc"] += len(lines)
                results[ext]["sloc"] += sum(1 for line in lines if line.strip())

    return results


def count_total(directory: str) -> dict:
    """Count total files and SLOC in a directory."""
    metrics = count_loc(directory)
    total_files = sum(m["files"] for m in metrics.values())
    total_sloc = sum(m["sloc"] for m in metrics.values())
    return {"files": total_files, "sloc": total_sloc, "by_type": metrics}


def marginal_cost_comparison(rest_dir: str, mesh_dir: str) -> dict:
    """Compare UC-04 marginal cost between approaches."""
    rest = count_total(rest_dir)
    mesh = count_total(mesh_dir)
    return {
        "rest": rest,
        "cognimesh": mesh,
        "ratio": mesh["sloc"] / rest["sloc"] if rest["sloc"] > 0 else 0,
    }
