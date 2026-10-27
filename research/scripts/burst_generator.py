"""Real commit burst generator: produces REAL git commits and REAL pushes to
KYRO-ingestion-test so KYRO's actual webhook -> n8n -> Kafka -> worker pipeline
processes them. This is the load generator for the Dragonfly research trace.

Honesty (see docs/research/DRAGONFLY_PLAN.md §3):
  * Git objects, pushes, webhook deliveries, processing durations, and
    resource samples are 100% real.
  * File CONTENTS are programmatically generated (disclosed; organic commits
    are kept separately as the organic subset).

Modes:
  python burst_generator.py --validate        # 5 pushes, proof of e2e, exits
  python burst_generator.py --burst 40        # one burst of 40 pushes
  python burst_generator.py --campaign 150    # scattered multi-burst pattern

Safety rails:
  * --max-commits per invocation (default 150)
  * --commits-per-hour budget (default 300) -> enforces pacing, keeps the
    worker's GitHub App API usage (~9 calls/commit) well under 5000/h
  * STOP_BURST file aborts between commits
  * 3 push retries with backoff; abort after 5 consecutive failures
  * never force-pushes; never touches any repo but the clone below
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(r"D:\projects\professional\KYRO\research-bursts\KYRO-ingestion-test")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
MANIFEST = OUT_DIR / "burst_manifest.jsonl"
STOP_FILE = Path(__file__).resolve().parent / "STOP_BURST"

# ---------------------------------------------------------------- content gen

PY_TEMPLATES = [
    '"""{title}."""\n\nfrom __future__ import annotations\n\nimport {mod}\n\n\ndef {fn}(data: {mod}.Mapping) -> bool:\n    """{doc}"""\n    if not data:\n        return False\n    result = {{}}\n    for key, value in data.items():\n        result[key] = value if value is not None else {default}\n    return bool(result)\n',
    'class {cls}:\n    """{doc}"""\n\n    def __init__(self, {arg}: int = {n}) -> None:\n        self.{arg} = {arg}\n        self._cache: dict[str, float] = {{}}\n\n    def compute(self, factor: float) -> float:\n        base = self.{arg} * factor\n        self._cache[str(factor)] = base\n        return base * 1.5 + {n}\n',
    "\n# {doc}\nSIGNAL = {n}\nTHRESHOLD = {n2}\n\n\ndef analyze(samples: list[float]) -> float:\n    if not samples:\n        return 0.0\n    mean = sum(samples) / len(samples)\n    return mean * SIGNAL / max(THRESHOLD, 1)\n",
]
MD_TEMPLATE = "# {title}\n\n{doc}\n\n## Notes\n\n{bullets}\n"
JSON_TEMPLATE = '{{\n  "name": "{title}",\n  "version": "{ver}",\n  "enabled": {flag},\n  "retries": {n},\n  "window_s": {n2}\n}}\n'
JS_TEMPLATE = "export function {fn}(items) {{\n  // {doc}\n  return items.filter((it) => it && it.score > {n}).map((it) => ({{\n    ...it,\n    weighted: it.score * {n2},\n  }}));\n}}\n"

TITLES = [
    "ingest pipeline",
    "chunk splitter",
    "retry policy",
    "index warmer",
    "query cache",
    "token budget",
    "webhook guard",
    "repo watcher",
    "diff parser",
    "embed worker",
    "trace writer",
    "lag monitor",
    "schema guard",
    "merge queue",
    "batch flush",
    "edge router",
    "auth gate",
    "rate limiter",
    "state machine",
    "snapshotter",
]
DOCS = [
    "Keeps counters aligned across restarts.",
    "Collapses duplicate events before the queue write.",
    "Applies the backoff schedule from config.",
    "Validates the payload shape before dispatch.",
    "Drops stale entries past the retention window.",
    "Recovers the last committed offset on boot.",
    "Normalizes branch names for the diff key.",
    "Guards against unbounded buffer growth.",
    "Emits a structured record for each stage.",
    "Fails closed when the signature mismatches.",
]
FN_NAMES = [
    "resolve",
    "hydrate",
    "collapse",
    "sweep",
    "reconcile",
    "flush",
    "advance",
    "clamp",
    "merge",
    "dispatch",
]
CLS_NAMES = [
    "Reducer",
    "Buffer",
    "Guard",
    "Tracker",
    "Planner",
    "Ledger",
    "Dispatcher",
    "Meter",
]
PATH_POOL = [
    "src/core/{m}.py",
    "src/pipeline/{m}.py",
    "src/utils/{m}.py",
    "tests/test_{m}.py",
    "docs/{m}.md",
    "config/{m}.json",
    "frontend/lib/{m}.js",
    "scripts/{m}.py",
    "research/notes_{m}.md",
    "src/handlers/{m}.py",
]


def _rng_commit(rng: random.Random) -> tuple[list[tuple[str, str]], str]:
    """Returns ([(path, content)], commit_message)."""
    r = rng.random()
    if r < 0.55:
        shape = "small"
        n_files = 1
    elif r < 0.85:
        shape = "medium"
        n_files = rng.randint(2, 6)
    else:
        shape = "large"
        n_files = rng.randint(7, 25)

    target_bytes = {
        "small": rng.randint(400, 8000),
        "medium": rng.randint(2000, 30000),
        "large": rng.randint(30000, 180000),
    }[shape]

    title = rng.choice(TITLES)
    mod = re.sub(r"[^a-z_]+", "_", rng.choice(FN_NAMES) + "_" + rng.choice(TITLES))[:24]
    files: list[tuple[str, str]] = []
    for i in range(n_files):
        path = rng.choice(PATH_POOL).format(m=mod if i == 0 else f"{mod}_{i}")
        ext = path.rsplit(".", 1)[-1]
        body_budget = max(200, target_bytes // n_files)
        if ext == "py":
            tpl = rng.choice(PY_TEMPLATES)
            body = tpl.format(
                title=title,
                mod="collections",
                fn=rng.choice(FN_NAMES),
                doc=rng.choice(DOCS),
                default="0",
                cls=rng.choice(CLS_NAMES),
                arg="size",
                n=rng.randint(2, 900),
                n2=rng.randint(901, 5000),
            )
        elif ext == "md":
            body = MD_TEMPLATE.format(
                title=title,
                doc=rng.choice(DOCS),
                bullets="\n".join(
                    f"- {rng.choice(DOCS)}" for _ in range(rng.randint(3, 12))
                ),
            )
        elif ext == "json":
            body = JSON_TEMPLATE.format(
                title=title,
                ver=f"{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 40)}",
                flag="true" if rng.random() < 0.5 else "false",
                n=rng.randint(1, 9),
                n2=rng.randint(10, 600),
            )
        else:
            body = JS_TEMPLATE.format(
                fn=rng.choice(FN_NAMES),
                doc=rng.choice(DOCS),
                n=rng.randint(1, 90),
                n2=rng.randint(1, 30),
            )
        # pad to budget with generated filler lines (keeps sizes heavy-tailed)
        while len(body.encode()) < body_budget:
            body += (
                f"# {rng.choice(DOCS)} step {len(body)}\n"
                if ext == "py"
                else f"\n{rng.choice(DOCS)} ({len(body)})\n"
            )
        files.append((path, body))

    kind = rng.choice(["feat", "fix", "chore", "docs", "refactor", "test"])
    msg = f"{kind}({title.replace(' ', '-')}): {rng.choice(DOCS).rstrip('.').lower()} #{rng.randint(100, 9999)}"
    return files, msg


def _git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout
    )


def _git_ok(*args: str, timeout: int = 120) -> bool:
    p = _git(*args, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed rc={p.returncode}: {(p.stderr or p.stdout)[:400]}"
        )
    return True


def _push_with_retry(tries: int = 3) -> tuple[bool, str]:
    last = ""
    for attempt in range(tries):
        p = _git("push", "origin", "HEAD:main", timeout=90)
        if p.returncode == 0:
            return True, (p.stdout or "").strip()[-200:]
        last = (p.stderr or p.stdout or "").strip()[-300:]
        if "Authentication failed" in last or "could not read Username" in last:
            return False, f"AUTH:{last}"
        time.sleep([5, 20, 60][attempt])
    return False, last


def _manifest(rec: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true", help="5 pushes, e2e proof")
    mode.add_argument("--burst", type=int, metavar="N", help="one burst of N pushes")
    mode.add_argument(
        "--campaign",
        type=int,
        metavar="N",
        help="scattered multi-burst pattern totaling ~N pushes",
    )
    ap.add_argument(
        "--max-commits", type=int, default=150, help="hard cap this invocation"
    )
    ap.add_argument(
        "--commits-per-hour", type=int, default=300, help="pacing budget (API safety)"
    )
    ap.add_argument(
        "--seed", type=int, default=None, help="RNG seed (default: time-based)"
    )
    ap.add_argument("--label", type=str, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed if args.seed is not None else int(time.time()))
    budget_gap_s = 3600.0 / max(args.commits_per_hour, 1)

    if not REPO_DIR.exists():
        print(f"ERROR: clone missing at {REPO_DIR}", file=sys.stderr)
        return 2

    # always start from a clean, current main
    _git_ok("checkout", "main")
    _git_ok("pull", "--rebase", "origin", "main", timeout=120)

    if args.validate:
        plan = [(label, 5, 3.0) for label in [args.label or "validate"]]
        cap = 5
    elif args.burst:
        plan = [
            (
                args.label or f"burst{int(time.time()) % 100000}",
                args.burst,
                budget_gap_s,
            )
        ]
        cap = min(args.burst, args.max_commits)
    else:
        total = min(args.campaign, args.max_commits)
        # scattered pattern: alternating spiky/steady clusters with quiet gaps
        plan = []
        remaining = total
        i = 0
        while remaining > 0:
            if i % 2 == 0:
                n, gap = (
                    min(rng.randint(8, 18), remaining),
                    0.5,
                )  # spike (sub-budget: compensated by quiet gaps)
                quiet = rng.uniform(30, 120)
            else:
                n, gap = min(rng.randint(5, 10), remaining), budget_gap_s  # steady
                quiet = rng.uniform(60, 300)
            if n <= 0:
                break
            plan.append((f"camp{i:02d}", n, gap, quiet))
            remaining -= n
            i += 1

    total_pushes = 0
    total_failures = 0
    started = time.monotonic()
    for entry in plan:
        label, n_pushes, gap = entry[0], entry[1], entry[2]
        quiet = entry[3] if len(entry) > 3 else 0.0
        print(f"[burst] label={label} pushes={n_pushes} gap~{gap:.1f}s", flush=True)
        for k in range(n_pushes):
            if STOP_FILE.exists():
                print("[burst] STOP file seen - aborting cleanly", flush=True)
                _manifest(
                    {
                        "ts": _now(),
                        "event": "stop",
                        "label": label,
                        "pushes": total_pushes,
                    }
                )
                return 0
            # 1) make 1..4 real commits locally (multi-commit pushes = bigger tasks)
            n_commits = rng.choices([1, 2, 3, 4], weights=[70, 20, 7, 3])[0]
            shas = []
            for _ in range(n_commits):
                files, msg = _rng_commit(rng)
                for path, body in files:
                    fp = REPO_DIR / path
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(body, encoding="utf-8")
                _git_ok("add", "-A")
                _git_ok("commit", "-m", msg, timeout=60)
                shas.append(_git("rev-parse", "HEAD").stdout.strip())
            # 2) push -> real webhook -> real pipeline
            t_push = _now()
            ok, info = _push_with_retry()
            rec = {
                "ts": t_push,
                "event": "push",
                "label": args.label or label,
                "ok": ok,
                "k_commits": n_commits,
                "shas": shas,
                "push_index": total_pushes,
                "elapsed_s": round(time.monotonic() - started, 1),
                "info": info if not ok else "",
            }
            _manifest(rec)
            if ok:
                total_pushes += n_commits
                total_failures = 0
                print(
                    f"[burst] push #{total_pushes} ok ({n_commits} commits)", flush=True
                )
            else:
                total_failures += 1
                print(
                    f"[burst] push FAILED ({total_failures}/5): {info[:200]}",
                    flush=True,
                    file=sys.stderr,
                )
                if total_failures >= 5 or info.startswith("AUTH"):
                    _manifest(
                        {
                            "ts": _now(),
                            "event": "abort",
                            "reason": info[:300],
                            "pushes": total_pushes,
                        }
                    )
                    return 1
            if total_pushes >= args.max_commits:
                print(f"[burst] hit --max-commits {args.max_commits}", flush=True)
                _manifest({"ts": _now(), "event": "cap", "pushes": total_pushes})
                return 0
            # 3) pace: never faster than budget gap (spikes still bounded >= 0.5s)
            time.sleep(max(gap, budget_gap_s / 2, 0.5) if gap < budget_gap_s else gap)
        if quiet:
            print(f"[burst] quiet gap {quiet:.0f}s", flush=True)
            slept = 0.0
            while slept < quiet and not STOP_FILE.exists():
                step = min(10.0, quiet - slept)
                time.sleep(step)
                slept += step
    _manifest(
        {
            "ts": _now(),
            "event": "done",
            "pushes": total_pushes,
            "label": args.label or "campaign",
        }
    )
    print(f"[burst] DONE total_commits={total_pushes}", flush=True)
    return 0


def _now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
