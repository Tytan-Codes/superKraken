"""Structured JSON audit logger for agent decision chains."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from superkraken.config import settings


class AuditLogger:
    """Logs full agent debates, indicators, and execution outcomes to JSONL."""

    def __init__(self, log_path: Path = None):
        self.log_path = log_path or (settings.data_dir / "audit_decisions.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_decision_cycle(self, state: Dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": state.get("symbol"),
            "current_price": state.get("current_price"),
            "technical_report": state.get("technical_report"),
            "sentiment_report": state.get("sentiment_report"),
            "fundamental_report": state.get("fundamental_report"),
            "bull_argument": state.get("bull_argument"),
            "bear_argument": state.get("bear_argument"),
            "consensus": state.get("consensus"),
            "proposal": state.get("proposal"),
            "risk_evaluation": state.get("risk_evaluation"),
            "execution_result": state.get("execution_result"),
        }

        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            pass


audit_logger = AuditLogger()
