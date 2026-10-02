import base64
import pytest
from superkraken.execution.rest_client import KrakenMarketDataClient, get_kraken_signature


def test_get_kraken_signature():
    urlpath = "/0/private/Balance"
    data = {"nonce": "1234567890"}
    secret = base64.b64encode(b"test_secret_key_1234567890_32bytes").decode()
    sig = get_kraken_signature(urlpath, data, secret)
    assert isinstance(sig, str)
    assert len(sig) > 0


@pytest.mark.asyncio
async def test_get_account_balances_missing_keys():
    client = KrakenMarketDataClient()
    # When keys are explicitly empty
    res = await client.get_account_balances(api_key="", api_secret="")
    assert res["success"] is False
    assert "Missing" in res["error"]


@pytest.mark.asyncio
async def test_get_account_balances_invalid_secret():
    client = KrakenMarketDataClient()
    res = await client.get_account_balances(api_key="valid_key", api_secret="not_base64_encoded!!!")
    assert res["success"] is False
    assert "Invalid API secret" in res["error"]
