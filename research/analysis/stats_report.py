#!/usr/bin/env python
"""Pairwise non-parametric significance analysis for KYRO scheduler experiments.

Usage:
    python -m research.analysis.stats_report --results research/results --out-dir research/results

For each supported input file present in --results, and for each metric in
[makespan_s, mean_flow_s, p95_flow_s, imbalance_cv] (plus dispatch_cpu_s when
that column exists), every unordered algorithm pair is compared on its
per-seed values (one independent observation per seed) using a two-sided
Mann-Whitney U (Wilcoxon rank-sum) test from scipy.stats.  Effect size is
Cliff's delta, computed directly as (#(a>b) - #(a<b)) / (n_a * n_b), with the
standard Romano et al. thresholds (|delta| < 0.147 negligible, < 0.33 small,
< 0.474 medium, else large).  Raw and Holm-Bonferroni adjusted p-values are
reported; the Holm correction is applied within each input file across all of
that file's tests.

Grouped tables: fleet_runs.csv is tested within each fleet_size;
load_sweep.csv within each compression_factor; the other files form one table
each.  Absent files are skipped with a console note.

Degenerate handling (never crash, never fabricate): if all values in both
groups of a comparison are identical, the test is reported with p=1.0,
p_holm=1.0, cliff_delta=0.0 and effect_label "degenerate-identical"; the note
column explains the zero-variance situation.  Groups with fewer than three
seeds are marked "low-n" in the note column.

Outputs:
  * stats_significance.csv -- one row per (table, group, metric, pair)
  * stats_report.md        -- methods + significant + full tables per file
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CSV_NAME = "stats_significance.csv"
MD_NAME = "stats_report.md"

BASE_METRICS = ["makespan_s", "mean_flow_s", "p95_flow_s", "imbalance_cv"]
OPTIONAL_METRICS = ["dispatch_cpu_s"]

# (file stem, grouping column or None for a single table)
INPUT_SPECS = [
    ("algo_comparison", None),
    ("baselines_comparison", None),
    ("fleet_runs", "fleet_size"),
    ("load_sweep", "compression_factor"),
]

OUTPUT_COLUMNS = [
    "table",
    "group",
    "metric",
    "algorithm_a",
    "algorithm_b",
    "n_a",
    "n_b",
    "u_statistic",
    "p_value",
    "p_holm",
    "cliff_delta",
    "effect_label",
    "note",
]

DEGENERATE_LABEL = "degenerate-identical"
DEGENERATE_NOTE = (
    "all values identical across both groups (zero variance, "
    "deterministic scheduler under this trace; significance undecidable)"
)

# Romano et al. (2008) thresholds for |Cliff's delta|
_ROMANO = [(0.147, "negligible"), (0.33, "small"), (0.474, "medium")]


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Cliff's delta = (#(a>b) - #(a<b)) / (n_a * n_b), computed directly."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        return float("nan")
    wins = int(np.sum(a[:, None] > b[None, :]))
    losses = int(np.sum(a[:, None] < b[None, :]))
    return float(wins - losses) / float(a.size * b.size)


def effect_label(delta: float) -> str:
    """Romano et al. label for |Cliff's delta|."""
    ad = abs(delta)
    for threshold, label in _ROMANO:
        if ad < threshold:
            return label
    return "large"


def holm_bonferroni(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values (capped at 1.0).

    Order statistics are adjusted by (m - rank) * p with a running maximum,
    which guarantees adjusted >= raw and monotonicity in rank order.
    """
    p = np.asarray(pvals, dtype=float)
    m = p.size
    if m == 0:
        return []
    order = np.argsort(p, kind="stable")
    adj = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(running, 1.0)
    return [float(x) for x in adj]


def _per_seed_values(df: pd.DataFrame, metric: str) -> np.ndarray:
    """One value per seed: duplicates for a (algorithm, seed) are averaged."""
    sub = df[["seed", metric]].dropna()
    return sub.groupby("seed", sort=True)[metric].mean().to_numpy(dtype=float)


def _format_group(value) -> str:
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return repr(f)
    except (TypeError, ValueError):
        return str(value)


def _test_pair(
    table: str,
    group: str,
    metric: str,
    algo_a: str,
    algo_b: str,
    va: np.ndarray,
    vb: np.ndarray,
) -> dict:
    """One Mann-Whitney comparison, with degenerate / low-n handling."""
    n_a, n_b = int(va.size), int(vb.size)
    low_n = n_a < 3 or n_b < 3
    if np.unique(np.concatenate([va, vb])).size == 1:
        note = DEGENERATE_NOTE
        if low_n:
            note += "; low-n"
        return {
            "table": table,
            "group": group,
            "metric": metric,
            "algorithm_a": algo_a,
            "algorithm_b": algo_b,
            "n_a": n_a,
            "n_b": n_b,
            "u_statistic": float("nan"),
            "p_value": 1.0,
            "cliff_delta": 0.0,
            "effect_label": DEGENERATE_LABEL,
            "note": note,
        }
    u_stat, p_value = stats.mannwhitneyu(va, vb, alternative="two-sided")
    delta = cliffs_delta(va, vb)
    return {
        "table": table,
        "group": group,
        "metric": metric,
        "algorithm_a": algo_a,
        "algorithm_b": algo_b,
        "n_a": n_a,
        "n_b": n_b,
        "u_statistic": float(u_stat),
        "p_value": float(p_value),
        "cliff_delta": float(delta),
        "effect_label": effect_label(delta),
        "note": "low-n" if low_n else "",
    }


def _analyse_file(
    stem: str, group_col: str | None, df: pd.DataFrame, console: list[str]
) -> list[dict]:
    """All pairwise tests for one input file (Holm applied across them)."""
    metrics = [m for m in BASE_METRICS if m in df.columns]
    metrics += [m for m in OPTIONAL_METRICS if m in df.columns]
    missing = [m for m in BASE_METRICS if m not in df.columns]
    if missing:
        console.append(f"{stem}: metrics absent, skipped: {', '.join(missing)}")
    if "algorithm" not in df.columns or "seed" not in df.columns:
        console.append(f"{stem}: missing 'algorithm'/'seed' column - skipped")
        return []

    if group_col is not None:
        if group_col not in df.columns:
            console.append(f"{stem}: grouping column '{group_col}' absent - skipped")
            return []
        df = df.dropna(subset=[group_col])
        groups = [
            (_format_group(val), sub) for val, sub in df.groupby(group_col, sort=True)
        ]
    else:
        groups = [("-", df)]

    rows: list[dict] = []
    for group_label, sub in groups:
        algos = sorted(str(a) for a in sub["algorithm"].dropna().unique())
        for metric in metrics:
            for algo_a, algo_b in itertools.combinations(algos, 2):
                va = _per_seed_values(sub[sub["algorithm"] == algo_a], metric)
                vb = _per_seed_values(sub[sub["algorithm"] == algo_b], metric)
                if va.size == 0 or vb.size == 0:
                    console.append(
                        f"{stem}: {metric} {algo_a}-vs-{algo_b} (group {group_label}) "
                        "has an empty group - skipped"
                    )
                    continue
                rows.append(
                    _test_pair(stem, group_label, metric, algo_a, algo_b, va, vb)
                )

    p_holm = holm_bonferroni([r["p_value"] for r in rows])
    for row, adj in zip(rows, p_holm):
        row["p_holm"] = adj
    return rows


def _fmt_u(v: float) -> str:
    return "-" if np.isnan(v) else f"{v:g}"


def _md_table(rows: list[dict]) -> str:
    """Render result rows as a GitHub-flavored markdown pipe table."""
    header = [
        "group",
        "metric",
        "algorithm_a",
        "algorithm_b",
        "n_a",
        "n_b",
        "U",
        "p_value",
        "p_holm",
        "cliff_delta",
        "effect_label",
        "note",
    ]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for r in rows:
        cells = [
            str(r["group"]),
            str(r["metric"]),
            str(r["algorithm_a"]),
            str(r["algorithm_b"]),
            str(r["n_a"]),
            str(r["n_b"]),
            _fmt_u(r["u_statistic"]),
            f"{r['p_value']:.4g}",
            f"{r['p_holm']:.4g}",
            f"{r['cliff_delta']:.3f}",
            str(r["effect_label"]),
            str(r["note"]) if r["note"] else "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _build_markdown(
    per_file_rows: dict[str, list[dict]],
    counts: dict[str, int],
    skipped: list[str],
    grouped_by: dict[str, str],
) -> str:
    out: list[str] = []
    out.append("# Statistical Significance Report (KYRO scheduler comparison)")
    out.append("")
    out.append(
        "## Methods\n"
        "Per-seed metric values (one independent observation per seed) from each "
        "results file were compared for every unordered algorithm pair using a "
        "**two-sided Mann-Whitney U test (Wilcoxon rank-sum)** "
        '(`scipy.stats.mannwhitneyu`, `alternative="two-sided"`).  Because '
        "multiple pairwise tests are performed per file, raw p-values were "
        "corrected with the **Holm-Bonferroni step-down procedure applied within "
        "each input file across all of that file's tests** (both the raw p-value "
        "and the adjusted `p_holm` are reported).  Effect size is **Cliff's "
        "delta**, computed directly as `(#(a>b) - #(a<b)) / (n_a * n_b)`, with "
        "the standard **Romano et al. thresholds**: |delta| < 0.147 negligible, "
        "< 0.33 small, < 0.474 medium, otherwise large.  Comparisons are called "
        "significant at `p_holm < 0.05`."
    )
    out.append("")
    for stem, rows in per_file_rows.items():
        out.append(f"## {stem}")
        out.append("")
        if grouped_by.get(stem):
            out.append(f"Tested within each `{grouped_by[stem]}` group.")
            out.append("")
        if not rows:
            out.append("_No pairwise tests could be computed for this file._")
            out.append("")
            continue
        out.append(f"Total pairwise tests: {counts[stem]}.")
        out.append("")
        sig = [r for r in rows if r["p_holm"] < 0.05]
        out.append("### Significant results (p_holm < 0.05)")
        out.append("")
        if sig:
            out.append(_md_table(sig))
        else:
            out.append("_No pairwise comparison reached p_holm < 0.05._")
        out.append("")
        out.append("### Full results")
        out.append("")
        out.append(_md_table(rows))
        out.append("")
    out.append("## Notes")
    out.append("")
    out.append(
        "- Algorithms that are fully deterministic under this trace produce "
        "zero-variance per-seed samples (e.g. identical values across every "
        "seed).  For such pairs the Mann-Whitney significance is *undecidable*: "
        "a degenerate-identical comparison is reported with p = 1.0, "
        "p_holm = 1.0, cliff_delta = 0.0 and effect_label "
        "`degenerate-identical` rather than a fabricated p-value.  These cases "
        "must be discussed explicitly in the paper -- a deterministic "
        "scheduler's zero variance is a property of the trace, not evidence of "
        "no effect, and non-degenerate comparisons against a degenerate "
        "algorithm inherit heavily tied ranks."
    )
    out.append(
        "- Groups with fewer than three seeds are flagged `low-n` in the note "
        "column; such p-values are indicative only."
    )
    if skipped:
        out.append(
            "- Input files absent or skipped: "
            + ", ".join(f"`{name}`" for name in skipped)
            + "."
        )
    else:
        out.append("- All four supported input files were present; none skipped.")
    out.append("")
    return "\n".join(out)


def run(results_dir: Path, out_dir: Path):
    """Analyse every supported file in results_dir; write CSV + markdown.

    Returns (dataframe, per-file test counts, skipped file names,
    csv path, markdown path, console log lines).
    """
    results_dir = Path(results_dir)
    out_dir = Path(out_dir)
    console: list[str] = []
    per_file_rows: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    skipped: list[str] = []
    grouped_by: dict[str, str] = {}

    for stem, group_col in INPUT_SPECS:
        path = results_dir / f"{stem}.csv"
        if not path.exists():
            skipped.append(path.name)
            console.append(f"{path.name} not found - skipped")
            continue
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # pragma: no cover - defensive
            skipped.append(path.name)
            console.append(f"{path.name} unreadable ({exc}) - skipped")
            continue
        if df.empty:
            skipped.append(path.name)
            console.append(f"{path.name} has no rows - skipped")
            continue
        rows = _analyse_file(stem, group_col, df, console)
        per_file_rows[stem] = rows
        counts[stem] = len(rows)
        if group_col is not None and rows:
            grouped_by[stem] = group_col

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / CSV_NAME
    md_path = out_dir / MD_NAME

    result_df = pd.DataFrame(
        [
            {col: row[col] for col in OUTPUT_COLUMNS}
            for rows in per_file_rows.values()
            for row in rows
        ],
        columns=OUTPUT_COLUMNS,
    )
    result_df.to_csv(csv_path, index=False)

    md = _build_markdown(per_file_rows, counts, skipped, grouped_by)
    md_path.write_text(md, encoding="utf-8")

    return result_df, counts, skipped, csv_path, md_path, console


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pairwise Mann-Whitney / Cliff's delta significance report."
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("research/results"),
        help="Directory containing the experiment result CSVs.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("research/results"),
        help="Directory for stats_significance.csv and stats_report.md.",
    )
    args = parser.parse_args(argv)

    df, counts, skipped, csv_path, md_path, console = run(args.results, args.out_dir)

    for line in console:
        print(line)
    for stem in counts:
        print(f"{stem}: {counts[stem]} pairwise tests")
    print(f"Wrote {csv_path} ({len(df)} rows)")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
