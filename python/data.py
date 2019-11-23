import aiohttp
import asyncio
import logging
from typing import (
    Dict,
    Optional,
)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
class Genv():
    COIN_CAP_BASE_URL = "https://api.coincap.io/v2"
    _shared_client=None
    async def _http_client(self) -> aiohttp.ClientSession:
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client

    async def fetch_prices(self):
        try:
            client = await self._http_client()
            async with client.request("GET", "https://baidu.com") as resp:
                rates_dict = await resp.json()
                print(rates_dict)
                for rate_obj in rates_dict["data"]:
                    symbol = rate_obj["symbol"].upper()
                    print(symbol)
        except Exception:
            raise
async def main():
    a=Genv()
    await a.fetch_prices()
if __name__ == "__main__":
    ev_loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    ev_loop.run_until_complete(main())