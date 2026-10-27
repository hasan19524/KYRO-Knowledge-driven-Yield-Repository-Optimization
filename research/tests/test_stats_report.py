"""Tests for research/analysis/stats_report.py using small synthetic fixtures.

Every CSV fixture written here is clearly SYNTHETIC TEST DATA written to
pytest's tmp_path (same column schema as the real result files).  Nothing
here touches the real research/results/ directory, the database, or docker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis import stats_report  # noqa: E402


# ---------------------------------------------------------------------------
# helpers

ALGO_COLUMNS = [
    "algorithm",
    "seed",
    "n_requests",
    "makespan_s",
    "mean_flow_s",
    "p95_flow_s",
    "sla_violations",
    "imbalance_cv",
    "util_mean",
]


def synth_rows(alg_values: dict) -> list[dict]:
    """Synthetic per-seed rows: one metric value copied into every metric
    column so the fixture matches the real schema without hiding any numbers.
    """
    rows = []
    for algo, values in alg_values.items():
        for seed, value in enumerate(values):
            rows.append(
                {
                    "algorithm": algo,
                    "seed": seed,
                    "n_requests": 100,
                    "makespan_s": float(value),
                    "mean_flow_s": float(value),
                    "p95_flow_s": float(value),
                    "sla_violations": 0,
                    "imbalance_cv": float(value),
                    "util_mean": 0.5,
                }
            )
    return rows


def write_algo_csv(results_dir: Path, alg_values: dict) -> Path:
    path = results_dir / "algo_comparison.csv"
    pd.DataFrame(synth_rows(alg_values), columns=ALGO_COLUMNS).to_csv(path, index=False)
    return path


def run_report(results_dir: Path):
    out_dir = results_dir / "out"
    df, counts, skipped, csv_path, md_path, console = stats_report.run(
        results_dir, out_dir
    )
    return df, counts, skipped, csv_path, md_path


def pick(df: pd.DataFrame, metric: str, a: str, b: str) -> pd.Series:
    rows = df[
        (df["metric"] == metric) & (df["algorithm_a"] == a) & (df["algorithm_b"] == b)
    ]
    assert len(rows) == 1, f"expected exactly one {a}-vs-{b} row for {metric}"
    return rows.iloc[0]


# ---------------------------------------------------------------------------
# known case: two normal distributions far apart


def test_far_apart_distributions_significant_large(tmp_path):
    rng = np.random.default_rng(0)
    fast = rng.normal(10.0, 1.0, 12)
    slow = rng.normal(20.0, 1.0, 12)
    write_algo_csv(tmp_path, {"fast": fast.tolist(), "slow": slow.tolist()})

    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    assert counts == {"algo_comparison": 4}  # 4 metrics x 1 pair
    for metric in ["makespan_s", "mean_flow_s", "p95_flow_s", "imbalance_cv"]:
        row = pick(df, metric, "fast", "slow")
        assert row["p_holm"] < 0.05
        assert abs(row["cliff_delta"]) > 0.474
        assert row["effect_label"] == "large"
    # fast is the smaller group in the pair ordering: a > b never happens here
    assert pick(df, "mean_flow_s", "fast", "slow")["cliff_delta"] == -1.0
    assert csv_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "Mann-Whitney" in md and "Holm-Bonferroni" in md
    assert "Cliff" in md and "Romano" in md


# ---------------------------------------------------------------------------
# identical groups -> degenerate label


def test_identical_groups_degenerate(tmp_path):
    write_algo_csv(tmp_path, {"algo_x": [2.5] * 5, "algo_y": [2.5] * 5})

    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    row = pick(df, "mean_flow_s", "algo_x", "algo_y")
    assert row["effect_label"] == "degenerate-identical"
    assert row["p_value"] == 1.0
    assert row["p_holm"] == 1.0
    assert row["cliff_delta"] == 0.0
    assert np.isnan(row["u_statistic"])
    assert "zero variance" in row["note"]
    md = md_path.read_text(encoding="utf-8")
    assert "undecidable" in md


# ---------------------------------------------------------------------------
# Holm correction ordering sanity


def test_holm_adjusted_not_below_raw_and_monotone(tmp_path):
    rng = np.random.default_rng(1)
    alg_values = {
        "a": rng.normal(10.0, 1.0, 10).tolist(),
        "b": rng.normal(10.05, 1.0, 10).tolist(),  # nearly identical to a
        "c": rng.normal(13.0, 1.0, 10).tolist(),  # moderate separation
        "d": rng.normal(30.0, 1.0, 10).tolist(),  # far from everything
    }
    write_algo_csv(tmp_path, alg_values)

    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    assert counts == {"algo_comparison": 24}  # 4 metrics x 6 pairs
    assert (df["p_holm"] >= df["p_value"]).all()
    assert (df["p_holm"] <= 1.0).all()
    ordered = df.sort_values("p_value", kind="stable")["p_holm"].to_numpy()
    assert np.all(np.diff(ordered) >= -1e-12), "p_holm must be monotone in rank"
    # sanity: the closest pair (a vs b) must NOT be significant
    assert pick(df, "mean_flow_s", "a", "b")["p_holm"] >= 0.05
    # sanity: the far pair (a vs d) must be significant
    assert pick(df, "mean_flow_s", "a", "d")["p_holm"] < 0.05


# ---------------------------------------------------------------------------
# missing input files are skipped without crashing


def test_missing_input_files_skipped(tmp_path):
    (tmp_path / "unrelated.txt").write_text("not a result csv")
    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    assert counts == {}
    assert df.empty
    for name in [
        "algo_comparison.csv",
        "baselines_comparison.csv",
        "fleet_runs.csv",
        "load_sweep.csv",
    ]:
        assert name in skipped
    assert csv_path.exists()  # outputs still produced (header-only CSV)
    md = md_path.read_text(encoding="utf-8")
    assert "algo_comparison.csv" in md  # absent files listed in Notes


def test_only_one_file_present(tmp_path):
    write_algo_csv(tmp_path, {"algo_x": [1.0, 2.0, 3.0], "algo_y": [4.0, 5.0, 6.0]})
    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    assert set(counts) == {"algo_comparison"}
    assert set(df["table"].unique()) == {"algo_comparison"}
    assert "load_sweep.csv" in skipped
    assert "fleet_runs.csv" in skipped


# ---------------------------------------------------------------------------
# Cliff's delta exactness on a hand-computable example


def test_cliffs_delta_exact_by_hand():
    # a=[2,3], b=[1,1]: pairs 2>1, 2>1, 3>1, 3>1 -> 4 wins, 0 losses,
    # n_a*n_b = 4 -> delta = (4 - 0) / 4 = 1.0
    assert stats_report.cliffs_delta([2.0, 3.0], [1.0, 1.0]) == 1.0
    # reversed sign
    assert stats_report.cliffs_delta([1.0, 1.0], [2.0, 3.0]) == -1.0
    # a=[1,3], b=[2,4]: only 3>2 wins; 1<2, 1<4, 3<4 losses -> (1-3)/4 = -0.5
    assert stats_report.cliffs_delta([1.0, 3.0], [2.0, 4.0]) == -0.5
    # all ties -> 0 wins, 0 losses
    assert stats_report.cliffs_delta([2.0, 2.0], [2.0, 2.0]) == 0.0


def test_effect_label_thresholds():
    assert stats_report.effect_label(0.10) == "negligible"
    assert stats_report.effect_label(0.20) == "small"
    assert stats_report.effect_label(0.40) == "medium"
    assert stats_report.effect_label(0.60) == "large"
    assert stats_report.effect_label(-0.90) == "large"


# ---------------------------------------------------------------------------
# grouped tables: fleet_size / compression_factor


def test_fleet_runs_grouped_by_fleet_size(tmp_path):
    rng = np.random.default_rng(2)
    rows = []
    for fleet_size in [5, 10]:
        for algo, shift in [("algo_x", 0.0), ("algo_y", 2.0)]:
            for seed, value in enumerate(rng.normal(10.0 + shift, 0.3, 6)):
                row = {col: 0 for col in ALGO_COLUMNS}
                row.update(
                    {
                        "fleet_size": fleet_size,
                        "algorithm": algo,
                        "seed": seed,
                        "n_requests": 100,
                        "makespan_s": float(value),
                        "mean_flow_s": float(value),
                        "p95_flow_s": float(value),
                        "imbalance_cv": float(value),
                        "util_mean": 0.5,
                    }
                )
                rows.append(row)
    pd.DataFrame(rows).to_csv(tmp_path / "fleet_runs.csv", index=False)

    df, counts, skipped, csv_path, md_path = run_report(tmp_path)

    assert counts == {"fleet_runs": 8}  # 2 sizes x 4 metrics x 1 pair
    assert set(df["group"].unique()) == {"5", "10"}
    assert (df["table"] == "fleet_runs").all()
    row = df[(df["metric"] == "mean_flow_s") & (df["group"] == "10")].iloc[0]
    assert row["p_holm"] < 0.05
    assert row["cliff_delta"] == -1.0
    assert row["effect_label"] == "large"


def test_low_n_flagged(tmp_path):
    write_algo_csv(tmp_path, {"algo_x": [1.0, 9.0], "algo_y": [2.0, 10.0]})
    df, counts, skipped, csv_path, md_path = run_report(tmp_path)
    row = pick(df, "mean_flow_s", "algo_x", "algo_y")
    assert row["note"] == "low-n"
