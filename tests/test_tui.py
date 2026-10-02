"""Unit test for Textual UI mounting and layout components."""

import pytest
from superkraken.ui.app import SuperKrakenTUI


@pytest.mark.asyncio
async def test_tui_app_mount():
    app = SuperKrakenTUI(mode="PAPER")
    async with app.run_test() as pilot:
        # Check that top header is present
        assert app.top_header is not None
        assert app.top_header.mode == "PAPER"

        # Check all primary panels are mounted
        assert app.agent_status is not None
        assert app.price_feed is not None
        assert app.portfolio_widget is not None
        assert app.debate_log is not None
        assert app.risk_bar is not None
        assert app.notifications_bar is not None

        # Verify key binding handler for pause/resume
        await app.action_toggle_pause()
        assert app.paused is True
        await app.action_toggle_pause()
        assert app.paused is False

        # Verify emergency kill switch action with confirmation barrier
        await app.action_kill_switch()
        assert app._confirming_kill is True
        assert app.kill_switch_active is False
        # Second press confirms kill switch
        await app.action_kill_switch()
        assert app.kill_switch_active is True
        assert app.paused is True

        # Verify region info action
        await app.action_show_region()

        # Verify portfolio sparkline history
        assert len(app.portfolio_widget.equity_history) >= 1

        # Verify debate log scroll actions and focusability
        assert app.debate_log.can_focus is True
        for i in range(30):
            app.debate_log.add_log(f"Agent {i}", f"Test scroll message line {i}", "white")
        app.action_scroll_debate_up()
        app.action_scroll_debate_pageup()
        app.action_scroll_debate_down()
        app.action_scroll_debate_pagedown()

