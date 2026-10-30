/*
 * Karte "WoW Charaktere" fuer die Integration WoW Charakter.
 *
 * Alle Charaktere auf einen Blick, gruppiert nach Spielversion. Jede Version
 * ist eine Unterkachel mit Kopf (Version, Anzahl), darin je Charakter eine
 * Zeile: Avatar mit Symbol der Spezialisierung, Name, Itemlevel; Stufe,
 * Spezialisierung, Klasse, Realm und Mythic+-Wertung (nur Retail); letzter
 * Login und ein Level-Aufstieg der letzten 7 Tage.
 * Gruppen: Retail, Classic Era, Classic Progression, Classic Anniversary,
 * Forever, dann unbekannte Versionen, zuletzt "Spielversion unbekannt".
 * Innerhalb der Gruppe sortiert nach Stufe, dann Itemlevel.
 *
 * Die Karte findet die Charaktere ueber die Level-Sensoren der Integration
 * und deren Geraete, nicht ueber Entity-IDs; sie funktioniert deshalb mit
 * jeder Sprache und ohne Praefix.
 *
 * Konfiguration:
 *   type: custom:wow-characters-card
 *   entities:                          # optional, sonst alle Charaktere
 *     - sensor.<charakter>_level       # eine beliebige Entitaet je Charakter
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-charaktere-karte.yaml; ohne das Theme in beiden Modi dunkel.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  text: "var(--nachtblau-text, #f2f5f8)",
  titel: "var(--nachtblau-titel, #e7ecf3)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
  spur: "var(--nachtblau-neutral-kachel, rgba(255, 255, 255, 0.05))",
  // Ring um das Spec-Symbol, trennt es vom Avatar
  ring: "var(--nachtblau-huelle-oben, #1b2231)",
};

// Entitaeten je Charakter (Uebersetzungsschluessel der Integration)
const SCHLUESSEL = ["level", "item_level", "mythic_rating", "last_login", "avatar", "level_up"];

// Spielversionen in der Reihenfolge der Gruppen. Das Geraetemodell ist
// "World of Warcraft" + Name (seit 0.22.0), vorher "World of Warcraft (<schluessel>)".
const VERSIONEN = {
  retail: "Retail",
  classic_era: "Classic Era",
  classic_progression: "Classic Progression",
  classic_anniversary: "Classic Anniversary",
  forever: "Forever",
};
const REIHE = Object.values(VERSIONEN);

const TAG = 86400000;

const TEXT = {
  de: {
    title: "Charaktere",
    count: (n) => (n === 1 ? "1 Charakter" : `${n} Charaktere`),
    level: "Stufe",
    unknownVersion: "Spielversion unbekannt",
    login: (vor) => `Login ${vor}`,
    loginUnknown: "Login unbekannt",
    levelUp: (lvl, vor) => `Level ${lvl} erreicht ${vor}`,
    minutes: (n) => `vor ${n} min`,
    hours: (n) => `vor ${n} h`,
    days: (n, lang) => (n === 1 ? "vor 1 Tag" : `vor ${n.toLocaleString(lang)} Tagen`),
    none: "Keine Charaktere gefunden. Integration „WoW Charakter“ einrichten oder entities prüfen.",
    notFound: "Nicht gefunden:",
  },
  en: {
    title: "Characters",
    count: (n) => (n === 1 ? "1 character" : `${n} characters`),
    level: "Level",
    unknownVersion: "Game version unknown",
    login: (vor) => `Login ${vor}`,
    loginUnknown: "Login unknown",
    levelUp: (lvl, vor) => `Reached level ${lvl} ${vor}`,
    minutes: (n) => `${n} min ago`,
    hours: (n) => `${n} h ago`,
    days: (n, lang) => (n === 1 ? "1 day ago" : `${n.toLocaleString(lang)} days ago`),
    none: "No characters found. Set up the integration “WoW Charakter” or check entities.",
    notFound: "Not found:",
  },
};

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function leer(stateObj) {
  return !stateObj || ["unavailable", "unknown", ""].includes(stateObj.state);
}

function zahl(stateObj) {
  if (leer(stateObj)) {
    return null;
  }
  const n = parseFloat(stateObj.state);
  return Number.isNaN(n) ? null : n;
}

function version(geraet) {
  // Anzeigename der Version (Retail, Classic Era, ...) oder null
  const m = /^World of Warcraft(?: \((.+)\)| (.+))?$/.exec(geraet?.model || "");
  if (!m) {
    return null;
  }
  if (m[1]) {
    return VERSIONEN[m[1]] || m[1];
  }
  return m[2] || VERSIONEN.retail;
}

function rang(v) {
  if (v === null) {
    return 99;
  }
  return REIHE.includes(v) ? REIHE.indexOf(v) : 98;
}

class WowCharactersCard extends HTMLElement {
  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entities",
          selector: { entity: { multiple: true, domain: "sensor", integration: "wow_character" } },
        },
      ],
    };
  }

  setConfig(config) {
    if (config?.entities !== undefined && !Array.isArray(config.entities)) {
      throw new Error("entities muss eine Liste sein / entities must be a list");
    }
    this._config = { ...config };
    this._signatur = undefined;
    // Andere Auswahl: Charaktere neu suchen
    this._quelle = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    // Charaktere nur neu suchen, wenn sich Entitaeten oder Geraete geaendert
    // haben; bei Zustandsaenderungen ersetzt das Frontend nur hass.states.
    if (this._quelle !== hass.entities || this._geraete !== hass.devices) {
      this._charaktere = this._finden(hass);
      this._quelle = hass.entities;
      this._geraete = hass.devices;
      this._signatur = undefined;
    }
    // Nur neu zeichnen, wenn sich ein Zustand eines Charakters geaendert hat.
    const signatur = [
      ...this._charaktere.liste.flatMap((c) => Object.values(c.ids).map((id) => hass.states[id])),
      hass.locale?.language,
    ];
    if (
      this._signatur &&
      signatur.length === this._signatur.length &&
      signatur.every((s, i) => s === this._signatur[i])
    ) {
      return;
    }
    this._signatur = signatur;
    this._render();
  }

  connectedCallback() {
    // "vor 5 min" ohne Zustandsaenderung weiterzaehlen
    clearInterval(this._takt);
    this._takt = setInterval(() => this._render(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._takt);
  }

  getCardSize() {
    return 1 + Math.ceil((this._charaktere?.liste.length || 1) * 1.5);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _lang() {
    return (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
  }

  _t(key) {
    return (TEXT[this._lang()] || TEXT.en)[key];
  }

  _finden(hass) {
    // Geraet -> {Schluessel: Entity-ID} fuer jeden Charakter mit Level-Sensor.
    // Ein Level-Sensor ohne Geraet steht allein ("Spielversion unbekannt").
    const entities = hass.entities || {};
    const geraete = {};
    for (const e of Object.values(entities)) {
      if (e.platform !== "wow_character" || !SCHLUESSEL.includes(e.translation_key)) {
        continue;
      }
      const d = e.device_id || (e.translation_key === "level" ? e.entity_id : null);
      if (d) {
        (geraete[d] = geraete[d] || {})[e.translation_key] = e.entity_id;
      }
    }
    let auswahl = Object.keys(geraete).filter((d) => geraete[d].level);
    const fehlt = [];
    const gewuenscht = this._config.entities || [];
    if (gewuenscht.length) {
      auswahl = [];
      for (const id of gewuenscht) {
        const d = entities[id]?.device_id || id;
        if (geraete[d]?.level) {
          if (!auswahl.includes(d)) {
            auswahl.push(d);
          }
        } else {
          fehlt.push(id);
        }
      }
    }
    const liste = auswahl.map((d) => ({
      geraet: (hass.devices || {})[d],
      ids: geraete[d],
    }));
    return { liste, fehlt };
  }

  _render() {
    if (!this.shadowRoot || !this._hass || !this._charaktere) {
      return;
    }
    const { liste, fehlt } = this._charaktere;
    const st = (c, key) => (c.ids[key] ? this._hass.states[c.ids[key]] : undefined);
    const wert = (c, key) => zahl(st(c, key)) ?? -1;
    // Nach Stufe, dann Itemlevel
    const sortiert = liste
      .slice()
      .sort((a, b) => wert(b, "level") - wert(a, "level") || wert(b, "item_level") - wert(a, "item_level"));

    let body;
    if (!sortiert.length) {
      body = `<div class="hinweis">${esc(this._t("none"))}</div>`;
    } else {
      // Gruppen je Spielversion; die Liste ist schon nach Stufe sortiert
      const gruppen = new Map();
      for (const c of sortiert) {
        const v = version(c.geraet);
        if (!gruppen.has(v)) {
          gruppen.set(v, []);
        }
        gruppen.get(v).push(c);
      }
      body = [...gruppen.entries()]
        .sort((a, b) => rang(a[0]) - rang(b[0]) || String(a[0]).localeCompare(String(b[0]), this._lang()))
        .map(
          ([v, mitglieder]) => `
          <div class="gruppe">
            <div class="gkopf">
              <span class="gname">${esc(v ?? this._t("unknownVersion"))}</span>
              <span class="ganzahl">${esc(this._t("count")(mitglieder.length))}</span>
            </div>
            ${mitglieder.map((c) => this._zeile(c, v, st)).join("")}
          </div>`
        )
        .join("");
    }
    if (fehlt.length) {
      body += `<div class="hinweis">${esc(this._t("notFound"))} ${fehlt.map(esc).join(", ")}</div>`;
    }
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:account-group"></ha-icon></div>
          <div class="name">${esc(this._t("title"))}</div>
          <div class="label">${esc(this._t("count")(sortiert.length))}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _vor(iso) {
    // "vor 3 Tagen" aus einem Zeitstempel
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) {
      return null;
    }
    const min = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
    if (min < 60) {
      return this._t("minutes")(min);
    }
    const h = Math.round(min / 60);
    if (h < 24) {
      return this._t("hours")(h);
    }
    return this._t("days")(Math.round(h / 24), this._hass?.locale?.language || "de");
  }

  _zeile(c, spiel, st) {
    const lvl = st(c, "level");
    const a = lvl?.attributes || {};
    const g = c.geraet;
    const name = String(g?.name_by_user || g?.name || String(a.friendly_name || "").replace(/\s*Level$/, ""))
      .split(" – ")[0];
    const avatar = st(c, "avatar")?.attributes?.entity_picture;
    const ilvl = zahl(st(c, "item_level"));
    const mplus = st(c, "mythic_rating");
    let wertung = zahl(mplus);
    if (wertung === null) {
      wertung = mplus?.attributes?.api_rating ?? null;
    }
    // Mythic+ nur in Retail; ohne bekannte Version wie bisher anzeigen
    const mitMplus = !spiel || spiel === VERSIONEN.retail;
    const login = this._vor(st(c, "last_login")?.state);
    // Letzter Level-Aufstieg, hoechstens 7 Tage alt
    const auf = st(c, "level_up");
    const aufZeit = new Date(auf?.state);
    const aufstieg =
      auf?.attributes?.level && !Number.isNaN(aufZeit.getTime()) && Date.now() - aufZeit.getTime() < 7 * TAG
        ? this._t("levelUp")(auf.attributes.level, this._vor(auf.state))
        : null;
    const info = [leer(lvl) ? null : `${this._t("level")} ${lvl.state}`, [a.spec, a.class].filter(Boolean).join(" "), a.realm]
      .filter(Boolean)
      .map(esc)
      .join(" · ");
    const letzte = [login ? this._t("login")(login) : this._t("loginUnknown"), aufstieg]
      .filter(Boolean)
      .map(esc)
      .join(" · ");
    return `
      <div class="zeile">
        <div class="avatar">
          <div class="avatar-bild">${avatar ? `<img src="${esc(avatar)}" alt="">` : ""}</div>
          ${a.spec_icon ? `<img class="spec" src="${esc(a.spec_icon)}" alt="" title="${esc(a.spec || "")}">` : ""}
        </div>
        <div class="cname">${esc(name)}</div>
        <div class="ilvl"><b>${ilvl === null ? "–" : Math.round(ilvl)}</b> ilvl</div>
        <div class="info${mitMplus ? "" : " breit"}">${info}</div>
        ${mitMplus ? `<div class="mplus">M+ <b>${wertung === null ? "–" : Math.round(wertung)}</b></div>` : ""}
        <div class="info breit">${letzte}</div>
      </div>`;
  }
}

const ZWEIZEILIG =
  "overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance;";

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; padding: 14px 16px 16px; border-radius: 22px; cursor: default;
    border: 1px solid var(--nachtblau-huelle-rand, rgba(255, 255, 255, 0.05));
    background: linear-gradient(180deg, var(--nachtblau-huelle-oben, #1b2231) 0%, var(--nachtblau-huelle-unten, #171d29) 55%);
    box-shadow: 0 18px 44px -22px var(--nachtblau-schatten, rgba(0, 0, 0, 0.7));
    color: ${FARBEN.text};
  }
  .kopf { display: grid; grid-template-columns: min-content minmax(0, 1fr); grid-template-areas: "i n" "i l"; }
  .symbol {
    grid-area: i; display: flex; align-items: center; justify-content: center; align-self: center;
    width: 44px; height: 44px; margin-right: 14px; box-sizing: border-box; border-radius: 13px;
    background: color-mix(in srgb, ${FARBEN.akzent} 16%, transparent);
    border: 1px solid color-mix(in srgb, ${FARBEN.akzent} 24%, transparent);
    color: ${FARBEN.akzent};
  }
  .symbol ha-icon { --mdc-icon-size: 23px; --ha-icon-display: block; }
  .name { grid-area: n; align-self: end; font-size: 17px; font-weight: 700; letter-spacing: -0.02em; color: ${FARBEN.text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .label { grid-area: l; align-self: start; margin-top: 1px; font-size: 12.5px; color: ${FARBEN.sek}; }
  .body { display: grid; gap: 8px; padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; }
  .gruppe { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; overflow: hidden; }
  .gkopf { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 9px 12px 8px; border-bottom: 1px solid ${FARBEN.rand}; }
  .gname { min-width: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: ${FARBEN.titel}; ${ZWEIZEILIG} }
  .ganzahl { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; }
  .zeile { padding: 9px 12px; display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; gap: 2px 10px; align-items: center; }
  .zeile + .zeile { border-top: 1px solid ${FARBEN.rand}; }
  .avatar { grid-row: 1 / span 3; position: relative; width: 40px; height: 40px; }
  .avatar-bild { width: 40px; height: 40px; border-radius: 12px; overflow: hidden; background: ${FARBEN.spur}; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .avatar-bild img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .spec { position: absolute; right: -4px; bottom: -4px; width: 18px; height: 18px; border-radius: 50%; box-shadow: 0 0 0 2px ${FARBEN.ring}; }
  .cname { min-width: 0; font-size: 14.5px; line-height: 1.3; font-weight: 700; color: ${FARBEN.titel}; ${ZWEIZEILIG} }
  .ilvl { justify-self: end; font-size: 13px; color: ${FARBEN.sek}; white-space: nowrap; }
  .ilvl b { font-size: 14.5px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; }
  .info { min-width: 0; font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .info.breit { grid-column: 2 / -1; }
  .mplus { justify-self: end; align-self: start; font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; }
  .mplus b { color: ${FARBEN.label}; font-weight: 700; font-variant-numeric: tabular-nums; }
`;

if (!customElements.get("wow-characters-card")) {
  customElements.define("wow-characters-card", WowCharactersCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-characters-card",
    name: "WoW Charaktere",
    description: "Alle Charaktere nach Spielversion: Stufe, Itemlevel, Mythic+, letzter Login.",
  });
}
