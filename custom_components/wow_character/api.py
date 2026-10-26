"""Schlanker Client fuer die Blizzard Battle.net API."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import REGIONS, REQUEST_TIMEOUT


class BattleNetError(Exception):
    """Allgemeiner API-Fehler."""


class BattleNetAuthError(BattleNetError):
    """Client-ID oder Secret ungueltig."""


class BattleNetNotFound(BattleNetError):
    """Charakter, Realm-Liste oder Namespace nicht gefunden."""


class BattleNetRateLimited(BattleNetError):
    """Abfragelimit erreicht (HTTP 429)."""


class BattleNetClient:
    """Holt ein Client-Credentials-Token und fragt die Profil-API ab."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self._region = region
        self._urls = REGIONS[region]
        self._auth = aiohttp.BasicAuth(client_id, client_secret)
        self._token: str | None = None
        self._token_expires = 0.0

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires:
            return self._token
        try:
            async with self._session.post(
                self._urls["token"],
                data={"grant_type": "client_credentials"},
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status in (400, 401):
                    raise BattleNetAuthError("Client-ID oder Secret ungueltig")
                if resp.status != 200:
                    raise BattleNetError(f"Token-Abruf: HTTP {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BattleNetError(f"Token-Abruf fehlgeschlagen: {err}") from err
        self._token = data["access_token"]
        # 60 s Puffer, damit kein Token kurz vor Ablauf benutzt wird.
        self._token_expires = time.monotonic() + int(data.get("expires_in", 0)) - 60
        return self._token

    async def _get(
        self, path: str, namespace: str, retry: bool = True
    ) -> dict[str, Any]:
        token = await self._get_token()
        try:
            async with self._session.get(
                f"{self._urls['api']}{path}",
                params={"namespace": namespace, "locale": self._urls["locale"]},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401 and retry:
                    # Token serverseitig verfallen: einmal neu holen.
                    self._token = None
                    return await self._get(path, namespace, retry=False)
                if resp.status == 401:
                    raise BattleNetAuthError("Token abgelehnt")
                if resp.status == 404:
                    raise BattleNetNotFound(path)
                if resp.status == 429:
                    raise BattleNetRateLimited(path)
                if resp.status != 200:
                    raise BattleNetError(f"{path}: HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BattleNetError(f"{path}: {err}") from err

    def _character_path(self, realm: str, character: str) -> str:
        # realm ist der Slug aus der Realm-Liste, z. B. "die-aldor".
        return f"/profile/wow/character/{realm}/{quote(character.lower())}"

    def namespace(self, kind: str, suffix: str) -> str:
        """z. B. ("profile", "") -> "profile-eu", ("dynamic", "-forever") -> "dynamic-forever-eu"."""
        return f"{kind}{suffix}-{self._region}"

    async def get_realms(self, suffix: str) -> list[dict[str, Any]]:
        """Realm-Liste der Region; jeder Eintrag hat u. a. "name" und "slug"."""
        data = await self._get(
            "/data/wow/realm/index", self.namespace("dynamic", suffix)
        )
        realms = [
            r for r in data.get("realms") or [] if r.get("slug") and r.get("name")
        ]
        if not realms:
            raise BattleNetNotFound("leere Realm-Liste")
        return realms

    async def get_profile(
        self, realm: str, character: str, suffix: str
    ) -> dict[str, Any]:
        """Profil-Zusammenfassung: Level, Itemlevel, Klasse, Gilde usw."""
        return await self._get(
            self._character_path(realm, character), self.namespace("profile", suffix)
        )

    async def get_mythic_profile(
        self, realm: str, character: str, suffix: str
    ) -> dict[str, Any]:
        """Mythic+-Profil, nur Retail."""
        return await self._get(
            f"{self._character_path(realm, character)}/mythic-keystone-profile",
            self.namespace("profile", suffix),
        )
