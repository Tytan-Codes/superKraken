"""Headless test for SuperKrakenCopilotApp to verify fast startup and streaming callbacks."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from superkraken.ui.copilot_app import SuperKrakenCopilotApp
from superkraken.state import SignalAlert, TradeAction

@pytest.mark.asyncio
async def test_copilot_app_headless_startup():
    app = SuperKrakenCopilotApp()
    
    # Test callbacks directly
    app._handle_scan_progress("BTC/USD", "INDICATORS", "RSI: 48.2 │ MACD: +12.4")
    assert "BTC/USD" in app.signals_widget.active_symbol
    assert "RSI: 48.2" in app.signals_widget.active_agent_msg
    
    # Test pair scanned callback
    summary = {
        "symbol": "BTC/USD",
        "action": "BUY",
        "confidence": 0.74,
        "bull_thesis": "Strong momentum",
        "bear_thesis": "Resistance near 85k",
        "summary": "Consensus bullish",
        "indicators": {"rsi_14": 52.0},
    }
    alert = SignalAlert(
        signal_id="sig-test-1",
        symbol="BTC/USD",
        action=TradeAction.BUY,
        confidence=0.74,
        bull_score=0.75,
        bear_score=0.25,
        indicators={"rsi": 52.0, "macd": 10.0, "ema_trend": "BULLISH"},
        suggested_order={"action": "BUY", "quantity": 0.025, "notional_usdc": 2100.0, "entry_price": 84000.0, "stop_loss": 82000.0, "take_profit": 88000.0},
        risk_metrics={"portfolio_usdc": 10000.0, "max_loss_usd": 50.0, "max_loss_pct": 0.5, "target_gain_usd": 100.0, "target_gain_pct": 1.0, "risk_reward_ratio": 2.0},
        bull_thesis="Strong momentum",
        bear_thesis="Resistance near 85k",
        summary="Consensus bullish",
        advisor_speech="🟢 I think you should BUY BTC right now.",
    )
    app._handle_pair_scanned(summary, alert)
    
    assert app.signals_widget.signals["BTC/USD"]["action"] == "BUY"
    assert app.signals_widget.signals["BTC/USD"]["confidence"] == 0.74
    assert app.active_alert is not None
    assert app.active_alert.signal_id == "sig-test-1"
    print("All headless assertions passed successfully!")


@pytest.mark.asyncio
async def test_copilot_app_pilot_mount():
    app = SuperKrakenCopilotApp()
    with patch.object(app.scanner, "get_live_portfolio_usdc", AsyncMock(return_value=12500.0)), \
         patch.object(app.market_client, "get_ticker", AsyncMock(return_value={"symbol": "BTC/USD", "price": 84500.0, "change_pct": 2.5})), \
         patch.object(app.scanner, "scan_all_pairs", AsyncMock(return_value=([], None))):
        async with app.run_test() as pilot:
            # Check widgets mounted
            assert app.header_widget is not None
            assert app.header_widget.usdc_balance == 12500.0
            assert app.price_feed is not None
            assert app.signals_widget is not None
            assert app.portfolio_widget is not None
            assert app.alert_widget is not None
            assert app.history_widget is not None
            assert app.notifications_bar is not None

            # Test hotkey [S] (Scan Now)
            await pilot.press("s")
            assert app._seconds_until_scan == 300

            # Test simulated alert + [N] Skip
            alert = SignalAlert(
                signal_id="sig-test-skip",
                symbol="BTC/USD",
                action=TradeAction.BUY,
                confidence=0.70,
                bull_score=0.7,
                bear_score=0.3,
                suggested_order={"action": "BUY", "quantity": 0.01, "notional_usdc": 800.0, "entry_price": 84500.0},
                risk_metrics={"portfolio_usdc": 10000.0, "max_loss_usd": 20.0, "max_loss_pct": 0.2, "target_gain_usd": 40.0, "target_gain_pct": 0.4},
                advisor_speech="🟢 BUY BTC",
            )
            app.active_alert = alert
            app.alert_widget.set_alert(alert)
            assert app.active_alert is not None

            await pilot.press("n")
            # Should clear active alert on skip
            assert app.active_alert is None


if __name__ == "__main__":
    asyncio.run(test_copilot_app_headless_startup())
    asyncio.run(test_copilot_app_pilot_mount())
