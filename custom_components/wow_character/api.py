"""Schlanker Client fuer die Blizzard Battle.net API."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    LANGUAGE_HOME_ASSISTANT,
    LANGUAGE_REGION,
    LANGUAGES,
    REGIONS,
    REQUEST_TIMEOUT,
    TOKEN_URL,
)

# Interne Realms von Blizzard in der Realm-Liste (Stand EU, Oktober 2026),
# z. B. "EU1A Account Realm" (eu1a-account-realm), "EU4A1-INST-BFA"
# (eu4a1instbfa), "EU Arena Pass CSBG", "RDB EU" und "zzz_RDB EU".
_INTERNAL_REALM = re.compile(r"^(?:(?:eu|us|kr|tw)(?:\d|-arena-pass)|rdb-|zzz)")


def is_internal_realm(slug: str) -> bool:
    return bool(_INTERNAL_REALM.match(slug))


def api_language(choice: str | None, ha_language: str) -> str | None:
    """Sprache aus der Option; None heisst: Sprache der Region.

    ha_language wie in Home Assistant, z. B. "de", "en-GB" oder "zh-Hant".
    """
    if choice in (None, LANGUAGE_REGION):
        return None
    if choice == LANGUAGE_HOME_ASSISTANT:
        return ha_language.split("-")[0].lower()
    return choice


def region_locale(region: str, language: str | None) -> str:
    """Locale fuer die Abfragen einer Region, z. B. ("eu", "en") -> "en_GB"."""
    return LANGUAGES.get(language or "", {}).get(region) or REGIONS[region]["locale"]


class BattleNetError(Exception):
    """Allgemeiner API-Fehler."""


class BattleNetAuthError(BattleNetError):
    """Client-ID oder Secret ungueltig."""


class BattleNetLoginError(BattleNetError):
    """Login-Code oder Login-Token abgelehnt."""


class BattleNetNotFound(BattleNetError):
    """Charakter, Realm-Liste oder Namespace nicht gefunden."""


class BattleNetForbidden(BattleNetError):
    """HTTP 403, z. B. fuer einen Namespace, den Blizzard (noch) nicht kennt."""


class BattleNetRateLimited(BattleNetError):
    """Abfragelimit erreicht (HTTP 429)."""


class BattleNetClient:
    """Holt ein Client-Credentials-Token und fragt die API aller Regionen ab."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        language: str | None = None,
    ) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(client_id, client_secret)
        # Sprache der Texte; None heisst Sprache der Region (siehe api_language).
        self.language = language
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

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Login-Code gegen ein Login-Token tauschen.

        Blizzard-Doku "Authorization Code Flow": Client-ID und Secret per HTTP
        Basic, redirect_uri wie beim Login. Die Antwort enthaelt access_token,
        expires_in (86399) und scope, aber kein refresh_token.
        """
        try:
            async with self._session.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status in (400, 401):
                    raise BattleNetLoginError(
                        f"Login-Code abgelehnt: HTTP {resp.status}"
                    )
                if resp.status != 200:
                    raise BattleNetError(f"Code-Tausch: HTTP {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BattleNetError(f"Code-Tausch fehlgeschlagen: {err}") from err
        if not data.get("access_token"):
            raise BattleNetLoginError("Antwort ohne access_token")
        return data

    async def _get(
        self,
        region: str,
        path: str,
        namespace: str,
        retry: bool = True,
        wait_on_limit: bool = True,
        login_token: str | None = None,
    ) -> dict[str, Any]:
        token = login_token or await self._get_token()
        try:
            async with self._session.get(
                f"{REGIONS[region]['api']}{path}",
                params={
                    "namespace": namespace,
                    "locale": region_locale(region, self.language),
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401 and login_token:
                    # Ein Login-Token laesst sich nicht neu holen.
                    raise BattleNetLoginError("Login-Token abgelehnt")
                if resp.status == 401 and retry:
                    # Token serverseitig verfallen: einmal neu holen.
                    self._token = None
                    return await self._get(region, path, namespace, retry=False)
                if resp.status == 401:
                    raise BattleNetAuthError("Token abgelehnt")
                if resp.status == 404:
                    raise BattleNetNotFound(path)
                if resp.status == 403:
                    raise BattleNetForbidden(f"{path}: HTTP 403")
                if resp.status == 429 and wait_on_limit:
                    # Laut Blizzard-Doku ("Getting Started", Throttling): ueber
                    # 100 Abfragen je Sekunde gibt es 429 bis zum Ende der
                    # Sekunde. Einmal eine Sekunde warten und wiederholen.
                    await asyncio.sleep(1)
                    return await self._get(
                        region,
                        path,
                        namespace,
                        retry,
                        wait_on_limit=False,
                        login_token=login_token,
                    )
                if resp.status == 429:
                    raise BattleNetRateLimited(path)
                if resp.status != 200:
                    raise BattleNetError(f"{path}: HTTP {resp.status}")
                return await resp.json()
        except TimeoutError as err:
            # TimeoutError hat keinen eigenen Text; ohne diesen Zusatz endete
            # die Meldung im Log nach dem Pfad.
            raise BattleNetError(
                f"{path}: keine Antwort nach {REQUEST_TIMEOUT} s"
            ) from err
        except aiohttp.ClientError as err:
            raise BattleNetError(f"{path}: {type(err).__name__} {err}".strip()) from err

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
            r
            for r in data.get("realms") or []
            if r.get("slug") and r.get("name") and not is_internal_realm(r["slug"])
        ]
        if not realms:
            raise BattleNetNotFound("leere Realm-Liste")
        return realms

    async def get_account_characters(
        self, region: str, suffix: str, login_token: str
    ) -> list[dict[str, Any]]:
        """Charaktere des angemeldeten Kontos in Region und Spielversion.

        "Account Profile Summary" (/profile/user/wow), nur mit Login-Token und
        Scope wow.profile. Felder je Charakter laut Test vom 29.10.2026:
        character, faction, gender, id, level, name, playable_class,
        playable_race, protected_character, realm (id, key, name, slug).
        HTTP 404 heisst: kein WoW-Konto in diesem Namespace. HTTP 403 kam im
        Live-Test vom 29.10.2026 fuer die Forever-Kandidaten (-forever,
        -camelot), die Blizzard noch nicht dokumentiert.
        """
        data = await self._get(
            region,
            "/profile/user/wow",
            self.namespace("profile", suffix, region),
            login_token=login_token,
        )
        return [
            character
            for account in data.get("wow_accounts") or []
            for character in account.get("characters") or []
        ]

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

    async def get_static_data(
        self, region: str, suffix: str, path: str
    ) -> dict[str, Any]:
        """Spieldaten im static-Namespace, z. B. "profession/164"."""
        return await self._get(
            region, f"/data/wow/{path}", self.namespace("static", suffix, region)
        )

    async def get_profile_data(
        self, region: str, suffix: str, path: str
    ) -> dict[str, Any]:
        """Daten im profile-Namespace unter /data/wow, z. B. Gilden."""
        return await self._get(
            region, f"/data/wow/{path}", self.namespace("profile", suffix, region)
        )

    async def get_game_data(
        self, region: str, suffix: str, path: str
    ) -> dict[str, Any]:
        """Spieldaten im dynamic-Namespace, z. B. "token/index"."""
        return await self._get(
            region, f"/data/wow/{path}", self.namespace("dynamic", suffix, region)
        )
