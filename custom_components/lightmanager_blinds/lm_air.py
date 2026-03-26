"""Light Manager Air HTTP client."""

import logging

import aiohttp

log = logging.getLogger(__name__)


class LightManagerAir:
    """HTTP client for the jbmedia Light Manager Air."""

    def __init__(self, host: str):
        self.host = host
        self._url = f"http://{host}/control"

    async def send_command(self, lm_air_id: int) -> bool:
        """Send a command to the Light Manager Air."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._url,
                    data=f"cmd=idx,{lm_air_id}",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        log.debug("LM Air command %d sent successfully", lm_air_id)
                        return True
                    log.error("LM Air command %d failed: HTTP %d", lm_air_id, resp.status)
        except (aiohttp.ClientError, TimeoutError) as e:
            log.error("LM Air command %d failed: %s", lm_air_id, e)
        return False

    async def test_connection(self) -> bool:
        """Test if the Light Manager Air is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self.host}/",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    return resp.status == 200
        except (aiohttp.ClientError, TimeoutError):
            return False
