"""Schlanker Client fuer die Blizzard Battle.net API."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import REGIONS, REQUEST_TIMEOUT, TOKEN_URL


class BattleNetError(Exception):
    """Allgemeiner API-Fehler."""


class BattleNetAuthError(BattleNetError):
    """Client-ID oder Secret ungueltig."""


class BattleNetNotFound(BattleNetError):
    """Charakter, Realm-Liste oder Namespace nicht gefunden."""


class BattleNetRateLimited(BattleNetError):
    """Abfragelimit erreicht (HTTP 429)."""


class BattleNetClient:
    """Holt ein Client-Credentials-Token und fragt die API aller Regionen ab."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(client_id, client_secret)
        self._token: str | None = None
        self._token_expires = 0.0

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires:
            return self._token
        try:
            async with self._session.post(
                TOKEN_URL,
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

    async def validate(self) -> None:
        """Zugangsdaten pruefen, indem ein Token geholt wird."""
        self._token = None
        await self._get_token()

    async def _get(
        self, region: str, path: str, namespace: str, retry: bool = True
    ) -> dict[str, Any]:
        token = await self._get_token()
        urls = REGIONS[region]
        try:
            async with self._session.get(
                f"{urls['api']}{path}",
                params={"namespace": namespace, "locale": urls["locale"]},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401 and retry:
                    # Token serverseitig verfallen: einmal neu holen.
                    self._token = None
                    return await self._get(region, path, namespace, retry=False)
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

    @staticmethod
    def namespace(kind: str, suffix: str, region: str) -> str:
        """z. B. ("profile", "", "eu") -> "profile-eu"."""
        return f"{kind}{suffix}-{region}"

    @staticmethod
    def _character_path(realm: str, character: str) -> str:
        # realm ist der Slug aus der Realm-Liste, z. B. "die-aldor".
        return f"/profile/wow/character/{realm}/{quote(character.lower())}"

    async def get_realms(self, region: str, suffix: str) -> list[dict[str, Any]]:
        """Realm-Liste der Region; jeder Eintrag hat u. a. "name" und "slug"."""
        data = await self._get(
            region,
            "/data/wow/realm/index",
            self.namespace("dynamic", suffix, region),
        )
        realms = [
            r for r in data.get("realms") or [] if r.get("slug") and r.get("name")
        ]
        if not realms:
            raise BattleNetNotFound("leere Realm-Liste")
        return realms

    async def get_profile(
        self, region: str, realm: str, character: str, suffix: str
    ) -> dict[str, Any]:
        """Profil-Zusammenfassung: Level, Itemlevel, Klasse, Gilde usw."""
        return await self._get(
            region,
            self._character_path(realm, character),
            self.namespace("profile", suffix, region),
        )

    async def get_mythic_profile(
        self, region: str, realm: str, character: str, suffix: str
    ) -> dict[str, Any]:
        """Mythic+-Profil, nur Retail."""
        return await self._get(
            region,
            f"{self._character_path(realm, character)}/mythic-keystone-profile",
            self.namespace("profile", suffix, region),
        )

    async def get_character_resource(
        self, region: str, realm: str, character: str, suffix: str, resource: str
    ) -> dict[str, Any]:
        """Unterseite eines Charakters, z. B. "encounters/raids" oder "statistics"."""
        return await self._get(
            region,
            f"{self._character_path(realm, character)}/{resource}",
            self.namespace("profile", suffix, region),
        )

    async def get_game_data(
        self, region: str, suffix: str, path: str
    ) -> dict[str, Any]:
        """Spieldaten im dynamic-Namespace, z. B. "token/index"."""
        return await self._get(
            region, f"/data/wow/{path}", self.namespace("dynamic", suffix, region)
        )
