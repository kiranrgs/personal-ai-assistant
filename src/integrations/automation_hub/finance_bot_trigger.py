"""Triggers specific on-demand jobs in the sibling `finance-bot` app (same
tower, separate venv/dependencies) without duplicating its scheduler. Calls
run in finance-bot's own virtualenv interpreter via subprocess so this
assistant never needs finance-bot's dependencies (pandas/yfinance/etc)
installed itself.

Only a fixed whitelist of job keys -> finance-bot functions can be run - the
LLM never gets to supply an arbitrary module/function path. Some of these
jobs can affect real trades/money, so every trigger requires Telegram
confirmation first, same as any other financial action.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register

# job_key -> (module path within finance-bot, function name, human description)
JOBS: dict[str, tuple[str, str, str]] = {
    "opportunity_discovery": ("src.core.scheduler", "run_opportunity_discovery_now", "Run opportunity discovery scan now"),
    "vc_weekend_scan": ("src.core.scheduler", "run_vc_weekend_now", "Run VC weekend scan now"),
    "market_scan": ("src.core.scheduler", "run_market_now", "Run market scan now"),
    "ai_analysis": ("src.core.scheduler", "run_ai_now", "Run AI analysis pass now"),
    "us_weekly_rebalance": ("src.trading.quant_trader", "run_us_weekly_rebalance", "Run US weekly rebalance (may place trades)"),
    "india_weekly_suggestions": ("src.trading.quant_trader", "run_india_weekly_suggestions", "Run India weekly suggestions"),
    "sector_weekend_analysis": ("src.trading.sector_rotation_trader", "run_weekend_analysis", "Run sector rotation weekend analysis"),
}


def _finance_bot_python() -> Path:
    settings = get_settings()
    root = Path(settings.finance_bot_path)
    candidates = [root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python"]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError(f"Couldn't find finance-bot's virtualenv Python under {root}\\.venv")


def _run_job(job_key: str) -> dict[str, Any]:
    if job_key not in JOBS:
        return {"error": f"Unknown job '{job_key}'. Valid jobs: {', '.join(JOBS)}"}
    module, func_name, _ = JOBS[job_key]
    settings = get_settings()
    python_exe = _finance_bot_python()
    script = (
        f"import sys, json; sys.path.insert(0, r'{settings.finance_bot_path}');"
        f"from {module} import {func_name} as f;"
        f"result = f();"
        f"print(json.dumps(result if result is not None else {{'status': 'completed'}}, default=str))"
    )
    proc = subprocess.run(
        [str(python_exe), "-c", script],
        cwd=settings.finance_bot_path,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return {"error": f"finance-bot job failed: {proc.stderr[-2000:]}"}
    try:
        return {"result": json.loads(proc.stdout.strip().splitlines()[-1])}
    except (json.JSONDecodeError, IndexError):
        return {"result": proc.stdout[-2000:]}


def request_finance_bot_job(job_key: str) -> Any:
    if job_key not in JOBS:
        return {"error": f"Unknown job '{job_key}'. Valid jobs: {', '.join(JOBS)}"}
    _, _, description = JOBS[job_key]
    return PendingConfirmation(
        action_type="run_finance_bot_job",
        summary=f"Run finance-bot job: {description}?",
        payload={"job_key": job_key},
    )


register(Tool(
    name="request_finance_bot_job",
    description=(
        "Request running a specific finance-bot scheduled job on demand (e.g. opportunity_discovery, "
        "vc_weekend_scan, market_scan, ai_analysis, us_weekly_rebalance, india_weekly_suggestions, "
        "sector_weekend_analysis). Always requires user confirmation since some jobs can place trades."
    ),
    parameters={
        "type": "object",
        "properties": {"job_key": {"type": "string", "enum": list(JOBS.keys())}},
        "required": ["job_key"],
    },
    handler=request_finance_bot_job,
    requires_confirmation=True,
    executor=lambda payload: _run_job(payload["job_key"]),
))
