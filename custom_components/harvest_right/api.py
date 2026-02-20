"""REST API client for Harvest Right."""

import logging
import time

import aiohttp

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)


class HarvestRightAuthError(Exception):
    """Raised when authentication fails."""


class HarvestRightApiError(Exception):
    """Raised when an API call fails."""


class HarvestRightApi:
    """Client for the Harvest Right REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._refresh_after: float = 0
        self._customer_id: int | None = None
        self._user_id: int | None = None

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def customer_id(self) -> int | None:
        return self._customer_id

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def refresh_after(self) -> float:
        return self._refresh_after

    def _store_auth(self, data: dict) -> None:
        """Store tokens and IDs from an auth response."""
        self._access_token = data["accessToken"]
        self._refresh_token = data["refreshToken"]
        self._refresh_after = data["refreshAfter"]
        self._customer_id = data["customerId"]
        self._user_id = data["userId"]

    async def login(self) -> dict:
        """Authenticate with email and password."""
        try:
            resp = await self._session.post(
                f"{API_BASE}/auth/v1",
                json={
                    "username": self._email,
                    "password": self._password,
                    "rememberme": True,
                },
            )
        except aiohttp.ClientError as err:
            raise HarvestRightApiError(f"Connection error: {err}") from err

        if resp.status == 401:
            raise HarvestRightAuthError("Invalid email or password")

        if resp.status != 200:
            text = await resp.text()
            raise HarvestRightApiError(
                f"Login failed with status {resp.status}: {text}"
            )

        data = await resp.json()
        if data.get("error"):
            raise HarvestRightAuthError(data["error"])

        self._store_auth(data)
        _LOGGER.debug("Logged in as customer %s", self._customer_id)
        return data

    async def refresh_token(self) -> dict:
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            return await self.login()

        try:
            resp = await self._session.post(
                f"{API_BASE}/auth/v1/refresh-token",
                headers={
                    "Authorization": f"Bearer {self._refresh_token}",
                    "Content-Type": "application/json",
                },
            )
        except aiohttp.ClientError:
            _LOGGER.warning("Token refresh failed, falling back to login")
            return await self.login()

        if resp.status != 200:
            _LOGGER.warning("Token refresh returned %s, falling back to login", resp.status)
            return await self.login()

        data = await resp.json()
        if data.get("error"):
            _LOGGER.warning("Token refresh error: %s, falling back to login", data["error"])
            return await self.login()

        self._store_auth(data)
        _LOGGER.debug("Token refreshed for customer %s", self._customer_id)
        return data

    async def ensure_valid_token(self) -> None:
        """Refresh token if it's close to expiry."""
        if time.time() >= self._refresh_after:
            await self.refresh_token()

    async def get_freeze_dryers(self) -> list[dict]:
        """Fetch the list of registered freeze dryers."""
        await self.ensure_valid_token()
        try:
            resp = await self._session.get(
                f"{API_BASE}/freeze-dryer/v1",
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        except aiohttp.ClientError as err:
            raise HarvestRightApiError(f"Connection error: {err}") from err

        if resp.status == 401:
            _LOGGER.warning("Dryer fetch got 401, refreshing token and retrying")
            await self.refresh_token()
            try:
                resp = await self._session.get(
                    f"{API_BASE}/freeze-dryer/v1",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            except aiohttp.ClientError as err:
                raise HarvestRightApiError(f"Connection error: {err}") from err

        if resp.status != 200:
            text = await resp.text()
            raise HarvestRightApiError(
                f"Failed to fetch dryers (status {resp.status}): {text}"
            )

        return await resp.json()
