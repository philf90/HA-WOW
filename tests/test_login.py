"""Tests fuer den Battle.net-Login: Charaktere des Kontos finden und anlegen."""

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.config_entry_oauth2_flow import (
    MY_AUTH_CALLBACK_PATH,
    OAuth2AuthorizeCallbackView,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.wow_character.const import DOMAIN, GAME_VERSIONS, REGIONS

from .conftest import (
    API,
    API2,
    BASE_INPUT,
    CREDENTIALS,
    MYTHIC,
    PROFILE,
    PROFILE2,
    TOKEN_URL,
    UID1,
    character_subentry,
    main_entry,
)

LOCALES = {"eu": "de_DE", "us": "en_US", "kr": "ko_KR", "tw": "zh_TW"}
# Felder je Charakter wie in der echten Antwort vom 29.10.2026; Werte erfunden.
TESTCHAR = {
    "character": {"href": "https://eu.api.blizzard.com/profile/wow/character/x"},
    "protected_character": {"href": "https://eu.api.blizzard.com/profile/user/x"},
    "name": "Testchar",
    "id": 11,
    "realm": {"key": {}, "name": "Die Aldor", "id": 1, "slug": "die-aldor"},
    "playable_class": {"key": {}, "name": "Magier", "id": 8},
    "playable_race": {"key": {}, "name": "Mensch", "id": 1},
    "gender": {"type": "FEMALE", "name": "Weiblich"},
    "faction": {"type": "ALLIANCE", "name": "Allianz"},
    "level": 90,
}
ZWEITCHAR = {
    **TESTCHAR,
    "name": "Zweitchar",
    "id": 12,
    "realm": {"key": {}, "name": "Aegwynn", "id": 3, "slug": "aegwynn"},
    "playable_class": {"key": {}, "name": "Krieger", "id": 1},
    "level": 80,
}
ERACHAR = {
    **TESTCHAR,
    "name": "Erachar",
    "id": 21,
    "realm": {"key": {}, "name": "Everlook", "id": 5, "slug": "everlook"},
    "playable_class": {"key": {}, "name": "Jäger", "id": 3},
    "level": 60,
}
ERA_API = "https://eu.api.blizzard.com/profile/wow/character/everlook/erachar"
SUFFIXES = [s for v in GAME_VERSIONS.values() for s in v["namespaces"]]


def _account(*characters: dict) -> dict:
    return {"id": 1, "wow_accounts": [{"id": 7, "characters": list(characters)}]}


def mock_login(
    aioclient_mock,
    accounts: dict[tuple[str, str], dict | int],
    scope: str = "wow.profile",
    code_status: int = 200,
    locales: dict[str, str] = LOCALES,
) -> None:
    """Token-Endpunkt fuer beide Flows und /profile/user/wow aller Namespaces.

    accounts: (Region, Namespace-Suffix) -> Antwort oder HTTP-Status; alle
    anderen Namespaces antworten mit 404 (kein Konto). locales: erwartete
    Sprache je Region; Abfragen mit anderer Sprache haben keine Antwort.
    """

    async def token(method, url, data):
        if data["grant_type"] == "authorization_code":
            body = {
                "access_token": "login-tok",
                "token_type": "bearer",
                "expires_in": 86399,
                "scope": scope,
                "sub": "1",
            }
            return AiohttpClientMockResponse(method, url, code_status, json=body)
        body = {"access_token": "tok", "token_type": "bearer", "expires_in": 86399}
        return AiohttpClientMockResponse(method, url, 200, json=body)

    aioclient_mock.post(TOKEN_URL, side_effect=token)
    for region in REGIONS:
        for suffix in SUFFIXES:
            answer = accounts.get((region, suffix), 404)
            aioclient_mock.get(
                f"https://{region}.api.blizzard.com/profile/user/wow",
                params={
                    "namespace": f"profile{suffix}-{region}",
                    "locale": locales[region],
                },
                status=answer if isinstance(answer, int) else 200,
                json=None if isinstance(answer, int) else answer,
            )


def mock_characters(aioclient_mock) -> None:
    """Profile fuer das Laden nach dem Anlegen; Era-Charakter ohne Daten."""
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    aioclient_mock.get(f"{API}/status", json={"id": 11, "is_valid": True})
    aioclient_mock.get(API2, json=PROFILE2)
    aioclient_mock.get(f"{API2}/mythic-keystone-profile", json=MYTHIC)
    aioclient_mock.get(f"{API2}/status", json={"id": 12, "is_valid": True})
    aioclient_mock.get(ERA_API, status=404)


@pytest.fixture
async def callback_view(hass: HomeAssistant) -> None:
    """Ruecksprung-Adresse wie in Home Assistant (registriert von "auth")."""
    assert await async_setup_component(hass, "http", {})
    hass.http.register_view(OAuth2AuthorizeCallbackView())
    hass.config.components.add("my")
    # Die Integration registriert in async_setup die Dateien ihrer Karten.
    # Das muss vor dem Start des Test-Clients geschehen: Je nach Umgebung
    # friert der Test-Server den Router beim Start ein (so in der CI).
    assert await async_setup_component(hass, DOMAIN, {})


async def _start_login(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.MENU
    # Die Redirect-URL steht als Platzhalter im Text (hassfest verbietet URLs).
    assert result["description_placeholders"] == {"redirect_uri": MY_AUTH_CALLBACK_PATH}
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "login"}
    )


async def _return(hass: HomeAssistant, client_factory, result, query: str) -> dict:
    """Battle.net leitet zurueck; danach laeuft der Dialog weiter."""
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    state = parse_qs(urlparse(result["url"]).query)["state"][0]
    client = await client_factory()
    resp = await client.get(f"/auth/external/callback?{query}&state={state}")
    assert resp.status == 200
    return await hass.config_entries.flow.async_configure(result["flow_id"])


def _options(result) -> list[dict]:
    (selector,) = result["data_schema"].schema.values()
    return selector.config["options"]


def _account_calls(aioclient_mock) -> list:
    return [c for c in aioclient_mock.mock_calls if "/profile/user/wow" in str(c[1])]


# Neuer Eintrag mit Login


async def test_login_creates_selected_characters(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    mock_login(
        aioclient_mock,
        {
            ("eu", ""): _account(TESTCHAR, ZWEITCHAR),
            ("eu", "-classic1x"): _account(ERACHAR),
        },
    )
    mock_characters(aioclient_mock)
    result = await _start_login(hass)

    # Login-Adresse: Scope wow.profile, Ruecksprung ueber My Home Assistant.
    query = parse_qs(urlparse(result["url"]).query)
    assert result["url"].startswith("https://oauth.battle.net/authorize?")
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["id"]
    assert query["scope"] == ["wow.profile"]
    assert query["redirect_uri"] == [MY_AUTH_CALLBACK_PATH]
    assert result["description_placeholders"] == {"redirect_uri": MY_AUTH_CALLBACK_PATH}

    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"
    assert result["description_placeholders"] == {"count": "3", "failed": "0"}
    # Nach Level absteigend.
    assert [o["label"] for o in _options(result)] == [
        "Testchar – Die Aldor · EU Retail · Level 90 Magier",
        "Zweitchar – Aegwynn · EU Retail · Level 80 Krieger",
        "Erachar – Everlook · EU Classic Era · Level 60 Jäger",
    ]

    # Code-Tausch mit derselben redirect_uri wie beim Login.
    (exchange,) = [
        c
        for c in aioclient_mock.mock_calls
        if str(c[1]) == TOKEN_URL and c[2]["grant_type"] == "authorization_code"
    ]
    assert exchange[2] == {
        "grant_type": "authorization_code",
        "code": "abcd",
        "redirect_uri": MY_AUTH_CALLBACK_PATH,
    }
    # 4 Regionen, 5 Spielversionen, Forever mit zwei Namespace-Kandidaten.
    calls = _account_calls(aioclient_mock)
    assert len(calls) == 4 * len(SUFFIXES)
    assert {c[3]["Authorization"] for c in calls} == {"Bearer login-tok"}

    keys = [o["value"] for o in _options(result)]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": [keys[0], keys[2]]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS
    entry = result["result"]
    subentries = sorted(entry.subentries.values(), key=lambda s: s.title)
    assert [(s.title, s.unique_id, dict(s.data)) for s in subentries] == [
        (
            "Erachar – Everlook",
            "eu-profile-classic1x-eu-everlook-erachar",
            {
                "region": "eu",
                "game_version": "classic_era",
                "realm": "everlook",
                "character": "Erachar",
                "namespace_suffix": "-classic1x",
                "character_id": 21,
            },
        ),
        (
            "Testchar – Die Aldor",
            UID1,
            {
                **BASE_INPUT,
                "realm": "die-aldor",
                "character": "Testchar",
                "namespace_suffix": "",
                "character_id": 11,
            },
        ),
    ]
    await hass.async_block_till_done()
    # Gleiche Entitaets-IDs wie beim Anlegen von Hand.
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"


async def test_login_without_selection(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    mock_login(aioclient_mock, {("eu", ""): _account(TESTCHAR)})
    result = await _start_login(hass)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].subentries == {}


async def test_login_forever_takes_namespace_with_account(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Wie beim Hinzufuegen von Hand gewinnt der Kandidat, der antwortet."""
    mock_login(aioclient_mock, {("eu", "-camelot"): _account(TESTCHAR)})
    result = await _start_login(hass)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    (option,) = _options(result)
    assert option["label"] == "Testchar – Die Aldor · EU Forever · Level 90 Magier"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": [option["value"]]}
    )
    (subentry,) = result["result"].subentries.values()
    assert subentry.data["game_version"] == "forever"
    assert subentry.data["namespace_suffix"] == "-camelot"
    assert subentry.unique_id == "eu-profile-camelot-eu-die-aldor-testchar"


async def test_login_counts_failed_queries(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Ein Aussetzer in einer Region verhindert die Auswahl nicht, steht aber da."""
    mock_login(aioclient_mock, {("eu", ""): _account(TESTCHAR), ("us", ""): 503})
    result = await _start_login(hass)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    assert result["step_id"] == "select"
    assert result["description_placeholders"] == {"count": "1", "failed": "1"}


async def test_login_unknown_namespace_is_no_failure(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Live-Test 29.10.2026: Fuer die Forever-Kandidaten, die Blizzard noch
    nicht kennt, antwortet /profile/user/wow mit 403. Das ist kein Aussetzer."""
    forever = {
        (region, suffix): 403
        for region in REGIONS
        for suffix in GAME_VERSIONS["forever"]["namespaces"]
    }
    mock_login(aioclient_mock, {**forever, ("eu", ""): _account(TESTCHAR)})
    result = await _start_login(hass)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    assert result["step_id"] == "select"
    assert result["description_placeholders"] == {"count": "1", "failed": "0"}


@pytest.mark.parametrize(
    ("query", "kwargs", "accounts", "reason"),
    [
        ("error=access_denied", {}, {}, "login_rejected"),
        ("code=abcd", {"code_status": 400}, {}, "login_failed"),
        ("code=abcd", {"scope": "openid"}, {}, "scope_missing"),
        ("code=abcd", {}, {}, "no_characters"),
        ("code=abcd", {}, {("eu", ""): 401}, "login_failed"),
        ("code=abcd", {"code_status": 503}, {}, "cannot_connect"),
    ],
)
async def test_login_errors(
    hass: HomeAssistant,
    aioclient_mock,
    hass_client_no_auth,
    callback_view,
    query,
    kwargs,
    accounts,
    reason,
) -> None:
    mock_login(aioclient_mock, accounts, **kwargs)
    result = await _start_login(hass)
    result = await _return(hass, hass_client_no_auth, result, query)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_login_needs_redirect_address(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne My Home Assistant und ohne Anfrage der Oberflaeche keine Adresse."""
    mock_login(aioclient_mock, {})
    result = await _start_login(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "redirect_unknown"


# Abgleich an einem bestehenden Eintrag


def _renamed_subentry() -> ConfigSubentryData:
    """Zweitchar (ID 12), eingerichtet unter seinem alten Namen."""
    return ConfigSubentryData(
        data={
            **BASE_INPUT,
            "realm": "aegwynn",
            "character": "Altname",
            "namespace_suffix": "",
            "character_id": 12,
        },
        subentry_type="character",
        title="Altname – Aegwynn",
        unique_id="eu-profile-eu-aegwynn-altname",
    )


async def _start_sync(
    hass: HomeAssistant, *subentries, options: dict | None = None
) -> tuple:
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "sync"}
    )
    return entry, result


async def test_sync_offers_only_new_characters(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    mock_login(
        aioclient_mock,
        {
            ("eu", ""): _account(TESTCHAR, ZWEITCHAR),
            ("eu", "-classic1x"): _account(ERACHAR),
        },
    )
    mock_characters(aioclient_mock)
    # Testchar per Name erkannt (ohne gespeicherte ID), Zweitchar per ID.
    entry, result = await _start_sync(hass, character_subentry(), _renamed_subentry())
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    (option,) = _options(result)
    assert option["label"].startswith("Erachar – Everlook")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": [option["value"]]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "characters_added"
    assert result["description_placeholders"] == {"count": "1"}
    await hass.async_block_till_done()
    assert sorted(s.title for s in entry.subentries.values()) == [
        "Altname – Aegwynn",
        "Erachar – Everlook",
        "Testchar – Die Aldor",
    ]
    # Zugangsdaten unveraendert, der Eintrag laeuft weiter.
    assert entry.data == CREDENTIALS
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_sync_nothing_new(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    mock_login(aioclient_mock, {("eu", ""): _account(TESTCHAR, ZWEITCHAR)})
    mock_characters(aioclient_mock)
    entry, result = await _start_sync(hass, character_subentry(), _renamed_subentry())
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "nothing_new"
    assert len(entry.subentries) == 2


async def test_sync_same_name_new_character_gets_own_unique_id(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Der alte Untereintrag "Zweitchar" heisst jetzt anders (andere ID), ein
    neuer Charakter traegt den Namen: eigene unique_id wie beim Anlegen von Hand."""
    old = character_subentry(
        uid="eu-profile-eu-aegwynn-zweitchar",
        title="Zweitchar – Aegwynn",
        realm="aegwynn",
        character="Zweitchar",
    )
    old["data"] = {**old["data"], "character_id": 99}
    renamed = {**ZWEITCHAR, "name": "Neuname", "id": 99}
    mock_login(aioclient_mock, {("eu", ""): _account(renamed, ZWEITCHAR)})
    mock_characters(aioclient_mock)
    entry, result = await _start_sync(hass, old)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    # Neuname ist der alte Charakter (gleiche ID), Zweitchar ein neuer.
    (option,) = _options(result)
    assert option["label"].startswith("Zweitchar – Aegwynn")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": [option["value"]]}
    )
    assert result["reason"] == "characters_added"
    new = next(s for s in entry.subentries.values() if s.data["character_id"] == 12)
    assert new.unique_id == "eu-profile-eu-aegwynn-zweitchar-12"


async def test_sync_reloads_once_for_several_characters(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Jeder neue Untereintrag loest den Update-Listener aus; geladen wird
    trotzdem nur einmal (Live-Test 29.10.2026: vier Charaktere, vier
    vollstaendige Neustarts des Eintrags)."""
    mock_login(
        aioclient_mock,
        {
            ("eu", ""): _account(TESTCHAR, ZWEITCHAR),
            ("eu", "-classic1x"): _account(ERACHAR),
        },
    )

    async def slow_profile(method, url, data):
        # Wie echte Netzwerkzeit: Das Laden gibt die Kontrolle ab, waehrend
        # die uebrigen Listener pruefen, ob sie neu laden muessen.
        await asyncio.sleep(0.01)
        return AiohttpClientMockResponse(method, url, 200, json=PROFILE)

    aioclient_mock.get(API, side_effect=slow_profile)
    mock_characters(aioclient_mock)
    entry, result = await _start_sync(hass)
    result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    keys = [o["value"] for o in _options(result)]
    calls = len(aioclient_mock.mock_calls)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"characters": keys}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "characters_added"
    assert len(entry.subentries) == 3
    # Jeder neue Charakter ist eingerichtet (Live-Test 29.10.2026: nur der
    # erste bekam Geraet und Entitaeten).
    assert set(entry.runtime_data.coordinators) == set(entry.subentries)
    assert hass.states.get("sensor.zweitchar_aegwynn_level").state == "80"
    # Das Profil eines Charakters wird je Laden einmal abgefragt.
    profile_calls = [
        c for c in aioclient_mock.mock_calls[calls:] if str(c[1]).split("?")[0] == API
    ]
    assert len(profile_calls) == 1
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"


async def test_reload_for_each_distinct_change(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Der Merker fuer ein laufendes Neuladen wird danach geloescht: Kehrt der
    Eintrag spaeter zu einem frueheren Stand zurueck, laedt er wieder neu."""
    mock_login(aioclient_mock, {})
    mock_characters(aioclient_mock)
    entry, _result = await _start_sync(hass, character_subentry())
    (subentry,) = entry.subentries.values()

    def profile_calls() -> int:
        return sum(
            1 for c in aioclient_mock.mock_calls if str(c[1]).split("?")[0] == API
        )

    for title in ("Neu", "Testchar – Die Aldor", "Neu"):
        before = profile_calls()
        hass.config_entries.async_update_subentry(entry, subentry, title=title)
        await hass.async_block_till_done()
        assert profile_calls() == before + 1, title


async def test_subentry_added_during_reload_gets_set_up(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Waehrend eines Neustarts fehlt der Update-Listener. Was in dieser Zeit
    dazukommt, laedt der Eintrag am Ende seines Starts nach."""

    async def slow_profile(method, url, data):
        await asyncio.sleep(0.01)
        return AiohttpClientMockResponse(method, url, 200, json=PROFILE)

    mock_login(aioclient_mock, {})
    aioclient_mock.get(API, side_effect=slow_profile)
    mock_characters(aioclient_mock)
    entry, _result = await _start_sync(hass, character_subentry())
    (subentry,) = entry.subentries.values()

    hass.config_entries.async_update_subentry(entry, subentry, title="Neu")
    await asyncio.sleep(0.005)  # der Neustart wartet auf das Profil
    assert entry.state is config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    hass.config_entries.async_add_subentry(
        entry,
        config_entries.ConfigSubentry(
            **character_subentry(
                uid="eu-profile-eu-aegwynn-zweitchar",
                title="Zweitchar – Aegwynn",
                realm="aegwynn",
                character="Zweitchar",
            )
        ),
    )
    await hass.async_block_till_done()
    assert set(entry.runtime_data.coordinators) == set(entry.subentries)
    assert hass.states.get("sensor.zweitchar_aegwynn_level").state == "80"


# Anmeldung aus "Charakter hinzufuegen"


async def _start_add(
    hass: HomeAssistant, *subentries, options: dict | None = None
) -> tuple:
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["login", "manual"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "login"}
    )
    return entry, result


def _relay_flows(hass: HomeAssistant) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]


async def test_add_character_with_login(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    """Der Ruecksprung erreicht nur Dialoge des Haupteintrags; ein Hilfsdialog
    dort gibt ihn an "Charakter hinzufuegen" weiter."""
    mock_login(
        aioclient_mock,
        {
            ("eu", ""): _account(TESTCHAR, ZWEITCHAR),
            ("eu", "-classic1x"): _account(ERACHAR),
        },
    )
    mock_characters(aioclient_mock)
    entry, result = await _start_add(hass, character_subentry())
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["description_placeholders"] == {"redirect_uri": MY_AUTH_CALLBACK_PATH}

    # Der state verweist auf den Hilfsdialog. Quelle "user": Home Assistant
    # zeigt ihn nicht unter "Entdeckt".
    (relay,) = _relay_flows(hass)
    assert relay["context"]["source"] == config_entries.SOURCE_USER
    assert relay["step_id"] == "relay"

    state = parse_qs(urlparse(result["url"]).query)["state"][0]
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert not _relay_flows(hass)

    result = await hass.config_entries.subentries.async_configure(result["flow_id"])
    assert result["step_id"] == "select"
    keys = [o["value"] for o in _options(result)]
    assert len(keys) == 2  # Testchar ist eingerichtet
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"characters": keys}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "characters_added"
    assert result["description_placeholders"] == {"count": "2"}
    await hass.async_block_till_done()
    assert sorted(s.title for s in entry.subentries.values()) == [
        "Erachar – Everlook",
        "Testchar – Die Aldor",
        "Zweitchar – Aegwynn",
    ]
    assert set(entry.runtime_data.coordinators) == set(entry.subentries)


async def test_add_character_login_rejected(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view
) -> None:
    mock_login(aioclient_mock, {})
    mock_characters(aioclient_mock)
    _entry, result = await _start_add(hass, character_subentry())
    state = parse_qs(urlparse(result["url"]).query)["state"][0]
    client = await hass_client_no_auth()
    await client.get(f"/auth/external/callback?error=access_denied&state={state}")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "login_rejected"


async def test_closing_add_character_ends_relay(
    hass: HomeAssistant, aioclient_mock, callback_view
) -> None:
    """Schliesst der Nutzer den Dialog vor der Anmeldung, endet auch der
    Hilfsdialog; es bleibt kein Dialog im Hintergrund liegen."""
    mock_login(aioclient_mock, {})
    mock_characters(aioclient_mock)
    _entry, result = await _start_add(hass, character_subentry())
    assert len(_relay_flows(hass)) == 1
    hass.config_entries.subentries.async_abort(result["flow_id"])
    assert not _relay_flows(hass)


async def test_setup_skips_character_deleted_meanwhile(
    hass: HomeAssistant,
    aioclient_mock,
    hass_client_no_auth,
    callback_view,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Live-Test 29.10.2026: Ein waehrend des Starts geloeschter Charakter
    fuehrte zu "Can't add entities to unknown subentry"."""

    async def slow_profile(method, url, data):
        await asyncio.sleep(0.01)
        return AiohttpClientMockResponse(method, url, 200, json=PROFILE)

    mock_login(aioclient_mock, {})
    aioclient_mock.get(API, side_effect=slow_profile)
    mock_characters(aioclient_mock)
    second = character_subentry(
        uid="eu-profile-eu-aegwynn-zweitchar",
        title="Zweitchar – Aegwynn",
        realm="aegwynn",
        character="Zweitchar",
    )
    entry, _result = await _start_sync(hass, character_subentry(), second)
    first = next(s for s in entry.subentries.values() if s.unique_id == UID1)
    other = next(s for s in entry.subentries.values() if s.unique_id != UID1)

    hass.config_entries.async_update_subentry(entry, first, title="Neu")
    await asyncio.sleep(0.005)  # der Neustart wartet auf das Profil
    assert entry.state is config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    hass.config_entries.async_remove_subentry(entry, other.subentry_id)
    await hass.async_block_till_done()
    assert "unknown subentry" not in caplog.text
    assert set(entry.runtime_data.coordinators) == {first.subentry_id}


# Sprache der API (seit 0.19.0)

ENGLISH = {"eu": "en_GB", "us": "en_US", "kr": "en_US", "tw": "en_US"}


@pytest.mark.parametrize("flow", ["sync", "add"])
async def test_login_search_uses_language(
    hass: HomeAssistant, aioclient_mock, hass_client_no_auth, callback_view, flow
) -> None:
    """Charaktersuche aus "Abgleichen" und "Hinzufuegen" in der gewaehlten Sprache.

    Die Abfragen der Charaktere selbst laufen mit dem Eintrag, ihre Mocks
    pruefen die Sprache nicht.
    """
    mock_login(
        aioclient_mock, {("eu", ""): _account(TESTCHAR, ZWEITCHAR)}, locales=ENGLISH
    )
    mock_characters(aioclient_mock)
    start = _start_sync if flow == "sync" else _start_add
    _entry, result = await start(hass, character_subentry(), options={"language": "en"})
    if flow == "sync":
        result = await _return(hass, hass_client_no_auth, result, "code=abcd")
    else:
        state = parse_qs(urlparse(result["url"]).query)["state"][0]
        client = await hass_client_no_auth()
        resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
        assert resp.status == 200
        result = await hass.config_entries.subentries.async_configure(result["flow_id"])
    assert result["step_id"] == "select"
    (option,) = _options(result)
    assert option["label"].startswith("Zweitchar – Aegwynn")
    calls = _account_calls(aioclient_mock)
    assert {c[1].query["locale"] for c in calls} == set(ENGLISH.values())
