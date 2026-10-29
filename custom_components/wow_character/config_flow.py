"""Einrichtungsdialoge.

Haupteintrag: Client-ID und Secret eines Battle.net-API-Clients, einmalig.
Danach wahlweise Battle.net-Login: Die Integration sucht die Charaktere des
Kontos in allen Regionen und Spielversionen und legt die angekreuzten als
Untereintraege an. "Neu konfigurieren" bietet denselben Abgleich fuer neue
Charaktere und das Aendern der Zugangsdaten.
Untereintrag "Charakter": Region und Spielversion, dann Realm aus der
Realm-Liste und Charaktername. Beliebig viele je Haupteintrag. Neu
konfigurieren aendert Realm und Name, z. B. nach Umbenennung oder Transfer;
Geraet, Entitaets-IDs und Verlauf bleiben.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    MY_AUTH_CALLBACK_PATH,
    LocalOAuth2Implementation,
    async_get_redirect_uri,
)
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    BattleNetAuthError,
    BattleNetClient,
    BattleNetError,
    BattleNetForbidden,
    BattleNetLoginError,
    BattleNetNotFound,
    api_language,
)
from .const import (
    AUTHORIZE_URL,
    CONF_CHARACTER,
    CONF_CHARACTER_ID,
    CONF_CHARACTERS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_GAME_VERSION,
    CONF_LANGUAGE,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    GAME_VERSIONS,
    LANGUAGE_HOME_ASSISTANT,
    LANGUAGE_REGION,
    LANGUAGES,
    LOGIN_SCOPE,
    MAIN_TITLE,
    REGIONS,
    SUBENTRY_CHARACTER,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

SECRET_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): SECRET_SELECTOR,
    }
)
CHARACTER_BASE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="eu"): SelectSelector(
            SelectSelectorConfig(
                options=list(REGIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_REGION,
            )
        ),
        vol.Required(CONF_GAME_VERSION, default="retail"): SelectSelector(
            SelectSelectorConfig(
                options=list(GAME_VERSIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_GAME_VERSION,
            )
        ),
    }
)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LANGUAGE, default=LANGUAGE_REGION): SelectSelector(
            SelectSelectorConfig(
                options=[LANGUAGE_REGION, LANGUAGE_HOME_ASSISTANT, *LANGUAGES],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_LANGUAGE,
            )
        ),
    }
)


def _entry_language(hass: Any, entry: ConfigEntry) -> str | None:
    """Sprache der API laut Optionen des Haupteintrags."""
    return api_language(entry.options.get(CONF_LANGUAGE), hass.config.language)


async def _validate_credentials(hass, client_id: str, client_secret: str) -> str | None:
    """Fehler-Schluessel zurueckgeben oder None, wenn die Zugangsdaten gelten."""
    client = BattleNetClient(async_get_clientsession(hass), client_id, client_secret)
    try:
        await client.validate()
    except BattleNetAuthError:
        return "invalid_auth"
    except BattleNetError:
        return "cannot_connect"
    return None


# Kennzeichen eines Hilfsdialogs, der fuer "Charakter hinzufuegen" den
# Ruecksprung nach dem Login annimmt (siehe CharacterSubentryFlow).
_RELAY = "relay_for"


class _LoginSteps:
    """Battle.net-Login, Charaktersuche und Auswahl.

    Gemeinsam fuer den Haupteintrag (Einrichten, "Charaktere abgleichen") und
    "Charakter hinzufuegen". Die Klassen liefern Zugangsdaten, die
    eingerichteten Charaktere und was mit der Auswahl geschieht.
    """

    hass: Any
    flow_id: str

    def _init_login(self) -> None:
        self._credentials: dict[str, str] = {}
        # Rueckgabe des Logins ueber /auth/external/callback: code oder error,
        # dazu state mit der benutzten redirect_uri.
        self._login: dict[str, Any] = {}
        # Auswahl-Schluessel -> gefundener Charakter, siehe _found_character.
        self._found: dict[str, dict[str, Any]] = {}
        self._failed = 0

    async def _login_flow_id(self) -> str:
        """Dialog, den Home Assistant nach dem Login fortsetzt."""
        return self.flow_id

    def _existing_characters(self) -> list[ConfigSubentry]:
        return []

    def _login_language(self) -> str | None:
        """Sprache fuer die Charaktersuche; beim ersten Einrichten die der Region."""
        return None

    def _finish(self, picked: list[dict[str, Any]]) -> Any:
        raise NotImplementedError

    def _add_characters(self, entry: ConfigEntry, picked: list[dict[str, Any]]) -> None:
        taken = {sub.unique_id for sub in entry.subentries.values()}
        for item in picked:
            self.hass.config_entries.async_add_subentry(
                entry, ConfigSubentry(**_subentry(item, taken))
            )

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> Any:
        """Battle.net-Login in einem eigenen Fenster."""
        if user_input is not None:
            self._login = user_input
            return self.async_external_step_done(next_step_id="discover")
        login = _LoginUrl(
            self.hass,
            DOMAIN,
            self._credentials[CONF_CLIENT_ID],
            self._credentials[CONF_CLIENT_SECRET],
            AUTHORIZE_URL,
            TOKEN_URL,
        )
        try:
            redirect_uri = login.redirect_uri
            url = await login.async_generate_authorize_url(await self._login_flow_id())
        except RuntimeError:
            # Ohne "My Home Assistant" braucht Home Assistant die Adresse aus der
            # laufenden Anfrage der Oberflaeche.
            return self.async_abort(reason="redirect_unknown")
        return self.async_external_step(
            step_id="login",
            url=url,
            description_placeholders={"redirect_uri": redirect_uri},
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Login-Code tauschen und die Charaktere aller Regionen suchen."""
        if "code" not in self._login:
            return self.async_abort(reason="login_rejected")
        client = BattleNetClient(
            async_get_clientsession(self.hass),
            self._credentials[CONF_CLIENT_ID],
            self._credentials[CONF_CLIENT_SECRET],
            self._login_language(),
        )
        state = self._login.get("state") or {}
        try:
            token = await client.exchange_code(
                self._login["code"], state.get("redirect_uri", "")
            )
            # Nutzer koennen einzelne Scopes abwaehlen (Blizzard-Doku).
            if LOGIN_SCOPE not in str(token.get("scope", "")).split():
                return self.async_abort(reason="scope_missing")
            found, self._failed = await _discover(client, token["access_token"])
        except BattleNetLoginError:
            return self.async_abort(reason="login_failed")
        except BattleNetError:
            return self.async_abort(reason="cannot_connect")
        if not found:
            return self.async_abort(reason="no_characters")

        existing = self._existing_characters()
        self._found = {
            _found_key(item): item
            for item in found
            if not any(_same_character(sub.data, item["data"]) for sub in existing)
        }
        if not self._found:
            return self.async_abort(reason="nothing_new")
        return await self.async_step_select()

    async def async_step_select(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self._finish(
                [
                    self._found[key]
                    for key in user_input.get(CONF_CHARACTERS, [])
                    if key in self._found
                ]
            )

        options = [
            SelectOptionDict(value=key, label=item["label"])
            for key, item in sorted(
                self._found.items(),
                key=lambda kv: (-kv[1]["level"], kv[1]["label"].casefold()),
            )
        ]
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CHARACTERS, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={
                "count": str(len(options)),
                "failed": str(self._failed),
            },
        )


class WowCharacterConfigFlow(_LoginSteps, ConfigFlow, domain=DOMAIN):
    # Version 2: Haupteintrag mit Untereintraegen je Charakter.
    VERSION = 2

    def __init__(self) -> None:
        self._init_login()
        # Nur im Hilfsdialog: der Dialog "Charakter hinzufuegen", an den der
        # Ruecksprung weitergeht.
        self._relay_for: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WowOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_CHARACTER: CharacterSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and _RELAY in user_input:
            # Hilfsdialog fuer "Charakter hinzufuegen": Home Assistant setzt
            # nach dem Login nur Dialoge des Haupteintrags fort. Quelle "user",
            # damit er nicht unter "Entdeckt" erscheint.
            self._relay_for = user_input[_RELAY]
            return self.async_show_form(step_id="relay")
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            await self.async_set_unique_id(client_id)
            self._abort_if_unique_id_configured()
            error = await _validate_credentials(
                self.hass, client_id, user_input[CONF_CLIENT_SECRET]
            )
            if error:
                errors["base"] = error
            else:
                self._credentials = {
                    CONF_CLIENT_ID: client_id,
                    CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                }
                return await self.async_step_method()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Charaktere per Battle.net-Login suchen oder spaeter von Hand anlegen."""
        try:
            redirect_uri = async_get_redirect_uri(self.hass)
        except RuntimeError:
            # Ohne My Home Assistant und ohne Anfrage der Oberflaeche; der
            # Anmeldeschritt bricht dann mit "redirect_unknown" ab.
            redirect_uri = MY_AUTH_CALLBACK_PATH
        return self.async_show_menu(
            step_id="method",
            menu_options=["login", "without_login"],
            description_placeholders={"redirect_uri": redirect_uri},
        )

    async def async_step_without_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Eintrag ohne Charaktere; die kommen ueber "Charakter hinzufuegen"."""
        return self.async_create_entry(title=MAIN_TITLE, data=self._credentials)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_credentials_step(
            "reauth_confirm", self._get_reauth_entry(), user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["sync", "credentials"]
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_credentials_step(
            "credentials", self._get_reconfigure_entry(), user_input
        )

    async def async_step_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Charaktere des Kontos mit den Untereintraegen abgleichen."""
        entry = self._get_reconfigure_entry()
        self._credentials = {
            CONF_CLIENT_ID: entry.data[CONF_CLIENT_ID],
            CONF_CLIENT_SECRET: entry.data[CONF_CLIENT_SECRET],
        }
        return await self.async_step_login()

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ruecksprung des Logins an "Charakter hinzufuegen" weitergeben."""
        if user_input is not None and self._relay_for:
            try:
                await self.hass.config_entries.subentries.async_configure(
                    self._relay_for, user_input
                )
            except UnknownFlow:
                _LOGGER.debug("Dialog %s ist schon geschlossen", self._relay_for)
        return self.async_abort(reason="relay_done")

    def _login_language(self) -> str | None:
        if self.source != SOURCE_RECONFIGURE:
            return None
        return _entry_language(self.hass, self._get_reconfigure_entry())

    def _existing_characters(self) -> list[ConfigSubentry]:
        if self.source != SOURCE_RECONFIGURE:
            return []
        return [
            sub
            for sub in self._get_reconfigure_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_CHARACTER
        ]

    def _finish(self, picked: list[dict[str, Any]]) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            self._add_characters(self._get_reconfigure_entry(), picked)
            return self.async_abort(
                reason="characters_added",
                description_placeholders={"count": str(len(picked))},
            )
        taken: set[str | None] = set()
        return self.async_create_entry(
            title=MAIN_TITLE,
            data=self._credentials,
            subentries=[_subentry(item, taken) for item in picked],
        )

    async def _async_credentials_step(
        self, step_id: str, entry: ConfigEntry, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Neue Zugangsdaten fuer einen bestehenden Haupteintrag."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            if client_id != entry.unique_id:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured()
            error = await _validate_credentials(
                self.hass, client_id, user_input[CONF_CLIENT_SECRET]
            )
            if error:
                errors["base"] = error
            else:
                if client_id != entry.unique_id:
                    _move_world_unique_ids(self.hass, entry, client_id)
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=client_id,
                    data_updates={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    },
                )
        suggested = user_input or {CONF_CLIENT_ID: entry.data[CONF_CLIENT_ID]}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, suggested
            ),
            errors=errors,
        )


def _move_world_unique_ids(hass: Any, entry: ConfigEntry, client_id: str) -> None:
    """Spielwelt-Entitaeten auf die neue Client-ID umschreiben.

    Ihre unique_id beginnt mit der unique_id des Eintrags, der Client-ID (siehe
    WowWorldEntity). Ohne Umschreiben legte Home Assistant sie nach dem Wechsel
    neu mit "_2" an; die alten blieben verwaist, mit Verlauf und Automationen.
    Gibt es die neue unique_id schon (Rueckwechsel auf eine Client-ID, deren
    Entitaeten vor 0.17.2 verwaist stehen blieben), uebernimmt Home Assistant
    beim Neuladen diesen Eintrag; die Entitaet bleibt dann unveraendert.
    """
    old = f"{entry.unique_id}-world-"
    new = f"{client_id}-world-"
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if not reg_entry.unique_id.startswith(old):
            continue
        unique_id = new + reg_entry.unique_id[len(old) :]
        if ent_reg.async_get_entity_id(reg_entry.domain, DOMAIN, unique_id):
            continue
        ent_reg.async_update_entity(reg_entry.entity_id, new_unique_id=unique_id)


class WowOptionsFlow(OptionsFlow):
    """Optionen des Haupteintrags: Sprache der Texte aus der API.

    Speichern laedt den Eintrag neu (Stand mit Optionen, siehe
    config_snapshot); nachgeschlagene Namen kommen dann in der neuen Sprache.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )


class _LoginUrl(LocalOAuth2Implementation):
    """Baut die Login-Adresse samt state, den /auth/external/callback prueft.

    Den Code-Tausch macht BattleNetClient.exchange_code mit HTTP Basic, wie es
    Blizzard dokumentiert; Home Assistant 2026.2.3 sendet das Secret im
    Formular (client_secret_post).
    """

    @property
    def extra_authorize_data(self) -> dict:
        return {"scope": LOGIN_SCOPE}


async def _discover(
    client: BattleNetClient, login_token: str
) -> tuple[list[dict[str, Any]], int]:
    """Charaktere des Kontos in allen Regionen und Spielversionen.

    Je Region und Spielversion eine Abfrage, bei mehreren Namespace-Kandidaten
    (Forever) der erste mit Konto. Gibt die Funde und die Zahl der
    fehlgeschlagenen Abfragen zurueck. HTTP 404 heisst "kein Konto", HTTP 403
    "Namespace unbekannt" (Forever-Kandidaten, Live-Test 29.10.2026); beides
    zaehlt nicht als Fehler.
    """

    async def one(region: str, version: str) -> tuple[list[dict[str, Any]], int]:
        failed = 0
        for suffix in GAME_VERSIONS[version]["namespaces"]:
            try:
                characters = await client.get_account_characters(
                    region, suffix, login_token
                )
            except BattleNetNotFound:
                continue
            except BattleNetForbidden:
                _LOGGER.debug("Charaktersuche %s%s: HTTP 403", region, suffix)
                continue
            except BattleNetLoginError:
                raise
            except BattleNetError as err:
                _LOGGER.warning("Charaktersuche %s%s: %s", region, suffix, err)
                failed += 1
                continue
            found = [
                item
                for character in characters
                if (item := _found_character(region, version, suffix, character))
            ]
            return found, failed
        return [], failed

    results = await asyncio.gather(
        *(one(region, version) for region in REGIONS for version in GAME_VERSIONS)
    )
    return (
        [item for found, _ in results for item in found],
        sum(failed for _, failed in results),
    )


def _text(value: Any) -> str:
    """Name aus der API; ohne locale-Parameter kaeme ein Objekt je Sprache."""
    if isinstance(value, dict):
        return str(value.get("de_DE") or next(iter(value.values()), ""))
    return str(value or "")


def _found_character(
    region: str, version: str, suffix: str, character: dict[str, Any]
) -> dict[str, Any] | None:
    """Gefundener Charakter: Daten des Untereintrags, Titel und Listentext."""
    realm = character.get("realm") or {}
    slug = realm.get("slug")
    name = _text(character.get("name"))
    if not slug or not name:
        return None
    realm_name = _text(realm.get("name")) or slug
    data: dict[str, Any] = {
        CONF_REGION: region,
        CONF_GAME_VERSION: version,
        CONF_REALM: slug,
        CONF_CHARACTER: name,
        CONF_NAMESPACE_SUFFIX: suffix,
        **_character_id(character),
    }
    level = character.get("level")
    level = level if isinstance(level, int) else 0
    details = " ".join(
        part
        for part in (
            f"Level {level}" if level else "",
            _text((character.get("playable_class") or {}).get("name")),
        )
        if part
    )
    game = GAME_VERSIONS[version]["label"].strip() or "Retail"
    label = f"{name} – {realm_name} · {region.upper()} {game}"
    if details:
        label = f"{label} · {details}"
    return {
        "data": data,
        "title": f"{name} – {realm_name}",
        "label": label,
        "level": level,
    }


def _found_key(item: dict[str, Any]) -> str:
    data = item["data"]
    return "|".join(
        (
            data[CONF_REGION],
            data[CONF_NAMESPACE_SUFFIX],
            data[CONF_REALM],
            data[CONF_CHARACTER].lower(),
        )
    )


def _same_character(existing: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    """Gleicher Charakter: gleiche Region, Spielversion und Realm, dazu gleiche
    ID. Ohne gespeicherte ID (aeltere Untereintraege) entscheidet der Name.

    Die ID geht vor: Ein umbenannter Charakter bleibt derselbe, und wer jetzt
    seinen alten Namen traegt, ist ein anderer.
    """
    if (
        existing.get(CONF_REGION),
        existing.get(CONF_NAMESPACE_SUFFIX),
        existing.get(CONF_REALM),
    ) != (new[CONF_REGION], new[CONF_NAMESPACE_SUFFIX], new[CONF_REALM]):
        return False
    old_id, new_id = existing.get(CONF_CHARACTER_ID), new.get(CONF_CHARACTER_ID)
    if old_id is not None and new_id is not None:
        return old_id == new_id
    return str(existing.get(CONF_CHARACTER, "")).lower() == new[CONF_CHARACTER].lower()


def _unique_id(
    region: str,
    suffix: str,
    realm: str,
    character: str,
    character_id: Any,
    taken: set[str | None],
) -> str:
    """unique_id wie beim Hinzufuegen von Hand.

    Ein umbenannter Charakter behaelt seine alte unique_id; ein neuer
    Charakter mit dem alten Namen bekommt dann eine eigene.
    """
    unique_id = (
        f"{region}-{BattleNetClient.namespace('profile', suffix, region)}-"
        f"{realm}-{character.lower()}"
    )
    if unique_id in taken:
        unique_id = f"{unique_id}-{character_id or len(taken)}"
    return unique_id


def _subentry(item: dict[str, Any], taken: set[str | None]) -> ConfigSubentryData:
    """Untereintrag fuer einen gefundenen Charakter; merkt die unique_id vor."""
    data = item["data"]
    unique_id = _unique_id(
        data[CONF_REGION],
        data[CONF_NAMESPACE_SUFFIX],
        data[CONF_REALM],
        data[CONF_CHARACTER],
        data.get(CONF_CHARACTER_ID),
        taken,
    )
    taken.add(unique_id)
    return ConfigSubentryData(
        data=dict(data),
        subentry_type=SUBENTRY_CHARACTER,
        title=item["title"],
        unique_id=unique_id,
    )


class CharacterSubentryFlow(_LoginSteps, ConfigSubentryFlow):
    """Charaktere zu einem Haupteintrag hinzufuegen: per Battle.net-Login oder
    von Hand mit Region, Spielversion, Realm und Name."""

    def __init__(self) -> None:
        self._init_login()
        self._base: dict[str, Any] = {}
        self._suffix = ""
        # Slug -> angezeigter Name, z. B. "die-aldor" -> "Die Aldor".
        self._realms: dict[str, str] = {}
        # Hilfsdialog im Haupteintrag, der den Ruecksprung des Logins annimmt.
        self._relay: str | None = None

    @property
    def _client(self) -> BattleNetClient:
        return self._get_entry().runtime_data.client

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        return self.async_show_menu(step_id="user", menu_options=["login", "manual"])

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is None:
            entry = self._get_entry()
            self._credentials = {
                CONF_CLIENT_ID: entry.data[CONF_CLIENT_ID],
                CONF_CLIENT_SECRET: entry.data[CONF_CLIENT_SECRET],
            }
        return await super().async_step_login(user_input)

    async def _login_flow_id(self) -> str:
        """Home Assistant setzt nach dem Login ueber /auth/external/callback
        nur Dialoge des Haupteintrags fort. Ein Hilfsdialog dort nimmt den
        Ruecksprung an und gibt ihn an diesen Dialog weiter."""
        self._abort_relay()
        result = await self.hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={_RELAY: self.flow_id}
        )
        self._relay = result["flow_id"]
        return self._relay

    def _abort_relay(self) -> None:
        if self._relay is None:
            return
        try:
            self.hass.config_entries.flow.async_abort(self._relay)
        except UnknownFlow:
            pass
        self._relay = None

    @callback
    def async_remove(self) -> None:
        """Dialog geschlossen oder fertig: Hilfsdialog mit beenden."""
        self._abort_relay()

    def _login_language(self) -> str | None:
        return _entry_language(self.hass, self._get_entry())

    def _existing_characters(self) -> list[ConfigSubentry]:
        return [
            sub
            for sub in self._get_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_CHARACTER
        ]

    def _finish(self, picked: list[dict[str, Any]]) -> SubentryFlowResult:
        self._add_characters(self._get_entry(), picked)
        return self.async_abort(
            reason="characters_added",
            description_placeholders={"count": str(len(picked))},
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                suffix, realms = await self._load_realms(
                    user_input[CONF_REGION], user_input[CONF_GAME_VERSION]
                )
            except BattleNetNotFound:
                errors["base"] = "realms_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                self._base = user_input
                self._suffix = suffix
                self._realms = {r["slug"]: r["name"] for r in realms}
                return await self.async_step_character()
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                CHARACTER_BASE_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_character(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        region = self._base[CONF_REGION]
        if user_input is not None:
            realm = user_input[CONF_REALM]
            character = user_input[CONF_CHARACTER].strip()
            if self._configured(region, self._suffix, realm, character):
                return self.async_abort(reason="already_configured")
            taken = {sub.unique_id for sub in self._get_entry().subentries.values()}
            try:
                profile = await self._client.get_profile(
                    region, realm, character, self._suffix
                )
            except BattleNetNotFound:
                errors["base"] = "character_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                unique_id = _unique_id(
                    region, self._suffix, realm, character, profile.get("id"), taken
                )
                return self.async_create_entry(
                    title=f"{profile.get('name', character)} – {self._realms[realm]}",
                    data={
                        **self._base,
                        CONF_REALM: realm,
                        CONF_CHARACTER: character,
                        CONF_NAMESPACE_SUFFIX: self._suffix,
                        **_character_id(profile),
                    },
                    unique_id=unique_id,
                )

        return self.async_show_form(
            step_id="character",
            data_schema=self.add_suggested_values_to_schema(
                self._character_schema(), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Realm und Name aendern; Region und Spielversion bleiben."""
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        region, suffix = data[CONF_REGION], data[CONF_NAMESPACE_SUFFIX]
        errors: dict[str, str] = {}
        if not self._realms:
            try:
                realms = await self._client.get_realms(region, suffix)
            except BattleNetError:
                return self.async_abort(reason="cannot_connect")
            self._realms = {r["slug"]: r["name"] for r in realms}
        if user_input is not None:
            realm = user_input[CONF_REALM]
            character = user_input[CONF_CHARACTER].strip()
            if self._configured(
                region, suffix, realm, character, skip=subentry.subentry_id
            ):
                return self.async_abort(reason="already_configured")
            try:
                profile = await self._client.get_profile(
                    region, realm, character, suffix
                )
            except BattleNetNotFound:
                errors["base"] = "character_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                # Die neue ID gilt als gespeicherter Stand, auch wenn sie sich
                # geaendert hat: So bestaetigt man einen anderen Charakter.
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=(
                        f"{profile.get('name', character)} – "
                        f"{self._realms.get(realm, realm)}"
                    ),
                    data={
                        **{k: v for k, v in data.items() if k != CONF_CHARACTER_ID},
                        CONF_REALM: realm,
                        CONF_CHARACTER: character,
                        **_character_id(profile),
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._character_schema(),
                user_input
                or {CONF_REALM: data[CONF_REALM], CONF_CHARACTER: data[CONF_CHARACTER]},
            ),
            errors=errors,
        )

    def _character_schema(self) -> vol.Schema:
        options = [
            SelectOptionDict(value=slug, label=name)
            for slug, name in sorted(
                self._realms.items(), key=lambda item: item[1].casefold()
            )
        ]
        return vol.Schema(
            {
                vol.Required(CONF_REALM): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(CONF_CHARACTER): str,
            }
        )

    def _configured(
        self,
        region: str,
        suffix: str,
        realm: str,
        character: str,
        skip: str | None = None,
    ) -> bool:
        """Gibt es den Charakter schon (nach Daten, nicht nach unique_id)?"""
        wanted = (region, suffix, realm, character.lower())
        return any(
            (
                sub.data.get(CONF_REGION),
                sub.data.get(CONF_NAMESPACE_SUFFIX),
                sub.data.get(CONF_REALM),
                str(sub.data.get(CONF_CHARACTER, "")).lower(),
            )
            == wanted
            for sub in self._get_entry().subentries.values()
            if sub.subentry_id != skip and sub.subentry_type == SUBENTRY_CHARACTER
        )

    async def _load_realms(
        self, region: str, game_version: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Namespace-Kandidaten der Reihe nach probieren; erster mit Realms gewinnt."""
        for suffix in GAME_VERSIONS[game_version]["namespaces"]:
            try:
                return suffix, await self._client.get_realms(region, suffix)
            except (BattleNetNotFound, BattleNetForbidden):
                # 403: Namespace (noch) unbekannt, wie bei der Charaktersuche.
                continue
        raise BattleNetNotFound("kein Namespace-Kandidat liefert eine Realm-Liste")


def _character_id(profile: dict[str, Any]) -> dict[str, int]:
    """ID des Charakters zum Speichern, falls die API sie nennt."""
    char_id = profile.get("id")
    return {CONF_CHARACTER_ID: char_id} if isinstance(char_id, int) else {}
