"""Kraken CLI execution wrapper.

Interfaces with the Kraken single-binary AI-native CLI (151+ commands)
supporting spot orders, paper trading, and the dead man's switch.
"""

import json
import logging
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from superkraken.config import settings

logger = logging.getLogger(__name__)


class KrakenCLIWrapper:
    """Subprocess adapter for Kraken CLI."""

    def __init__(self, cli_path: Optional[str] = None):
        self.cli_path = cli_path or settings.kraken_cli_path
        self._binary_available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if kraken binary is installed on PATH or custom path."""
        if self._binary_available is None:
            self._binary_available = shutil.which(self.cli_path) is not None
        return self._binary_available

    def run_command(self, args: List[str], timeout: int = 15) -> Dict[str, Any]:
        """Execute a kraken CLI command and parse JSON output."""
        if not self.is_available():
            raise FileNotFoundError(
                f"Kraken CLI binary '{self.cli_path}' was not found in PATH."
            )

        cmd = [self.cli_path] + args
        logger.debug(f"Running Kraken CLI: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"Kraken CLI error (code {result.returncode}): {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr.strip() or f"Exited with code {result.returncode}",
                    "raw_output": result.stdout,
                }

            stdout = result.stdout.strip()
            if not stdout:
                return {"success": True, "data": {}}

            try:
                data = json.loads(stdout)
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                return {"success": True, "raw_output": stdout}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # High-level CLI helpers
    def paper_init(self, balance: float = 10000.0) -> Dict[str, Any]:
        """Initialize paper trading environment via kraken CLI."""
        return self.run_command(["paper", "init", "--balance", str(balance)])

    def get_spot_balance(self) -> Dict[str, Any]:
        """Retrieve spot account balances."""
        return self.run_command(["spot", "balance"])

    def spot_order_add(
        self,
        symbol: str,
        side: str,
        order_type: str,
        volume: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Place a spot order using 'kraken spot order add'."""
        args = [
            "spot",
            "order",
            "add",
            "--pair",
            symbol,
            "--type",
            side.lower(),
            "--ordertype",
            order_type.lower(),
            "--volume",
            str(volume),
        ]
        if price and order_type.lower() == "limit":
            args.extend(["--price", str(price)])
        return self.run_command(args)

    def spot_cancel_after(self, timeout_seconds: int = 60) -> Dict[str, Any]:
        """Trigger dead man's switch: cancel open orders after timeout."""
        return self.run_command(["spot", "cancel-after", "--timeout", str(timeout_seconds)])

    def get_market_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get live market ticker data."""
        return self.run_command(["market", "ticker", "--pair", symbol])

    def get_market_ohlc(self, symbol: str, interval: int = 1) -> Dict[str, Any]:
        """Get OHLC candle data."""
        return self.run_command(["market", "ohlc", "--pair", symbol, "--interval", str(interval)])
