/*
 * Karte "WoW PvP" fuer die Integration WoW Charakter.
 *
 * PvP eines Charakters fuer alle Spielversionen:
 *   Kacheln    Ehrenstufe und Ehrenhafte Siege (nur die vorhandenen Sensoren)
 *   Wertungen  je Bracket (3v3, 2v2, gewertete Schlachtfelder) die Wertung,
 *              die Siegquote der Saison als Balken, Siege und Niederlagen der
 *              Saison und der Woche
 * Die Integration legt einen Bracket-Sensor nur an, wenn die API beim Start
 * Daten liefert; Brackets ohne Sensor fallen weg. Ohne jedes Bracket steht
 * ein Hinweis da, bei Classic Era, dass es dort keine Arenen gibt.
 * Unterzeile: Spielversion und Name des Charakters.
 *
 * Die Karte findet die Sensoren ueber das Geraet des Charakters und die
 * Uebersetzungsschluessel honor_level, honorable_kills und pvp_bracket. Die
 * Bracket-Sensoren teilen sich einen Schluessel; das Bracket steht am Ende
 * des Namens ("PvP-Wertung 3V3", "PvP rating 3V3"), hilfsweise am Ende der
 * Entity-ID.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-pvp-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-pvp-karte.yaml; ohne das Theme in beiden Modi dunkel. Siege und
 * Niederlagen stehen als Text, nicht als Gruen und Rot.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  text: "var(--nachtblau-text, #f2f5f8)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
  spur: "var(--nachtblau-neutral-kachel, rgba(255, 255, 255, 0.05))",
};

// Spielversion aus dem Geraetemodell: "World of Warcraft" (Retail),
// "World of Warcraft Classic Era" usw.; bis 0.21.x "World of Warcraft (classic_era)"
const VERSIONEN = {
  retail: "Retail",
  classic_era: "Classic Era",
  classic_progression: "Classic Progression",
  classic_anniversary: "Classic Anniversary",
  forever: "Forever",
};

// Brackets in der Reihenfolge des PvP-Fensters im Spiel
const BRACKETS = ["3v3", "2v2", "rbg"];

const TEXT = {
  de: {
    title: "PvP",
    honorLevel: "Ehrenstufe",
    honorableKills: "Ehrenhafte Siege",
    ratings: "Wertungen",
    brackets: { "3v3": "3v3-Arena", "2v2": "2v2-Arena", rbg: "Gewertete Schlachtfelder" },
    season: "Saison",
    week: "Woche",
    noGames: "keine Spiele",
    record: (s, n) => `${s} S · ${n} N`,
    classicEra: "Arena-Wertungen gibt es in Classic Era nicht: Arenen kamen erst mit The Burning Crusade.",
    noBracket:
      "Keine PvP-Wertung: Für 2v2, 3v3 und gewertete Schlachtfelder lieferte die API beim Start keine Daten. Neue Wertungen erscheinen nach dem Neuladen der Integration.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
  },
  en: {
    title: "PvP",
    honorLevel: "Honor level",
    honorableKills: "Honorable kills",
    ratings: "Ratings",
    brackets: { "3v3": "3v3 arena", "2v2": "2v2 arena", rbg: "Rated battlegrounds" },
    season: "Season",
    week: "Week",
    noGames: "no games",
    record: (s, n) => `${s} W · ${n} L`,
    classicEra: "Classic Era has no arena ratings: arenas came with The Burning Crusade.",
    noBracket:
      "No PvP rating: the API returned no data for 2v2, 3v3 and rated battlegrounds at startup. New ratings appear after reloading the integration.",
    missing: "No entities of the integration “WoW Charakter” for",
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

function zahl(stateObj) {
  if (!stateObj || ["unavailable", "unknown", ""].includes(stateObj.state)) {
    return null;
  }
  const n = parseFloat(stateObj.state);
  return Number.isNaN(n) ? null : n;
}

function anzahl(v) {
  return typeof v === "number" && !Number.isNaN(v) ? v : null;
}

// Spielversion als {key, name}; key retail, classic_era, ... oder null
function spielversion(model) {
  const m = /^World of Warcraft(?: \((.+)\)| (.+))?$/.exec(model || "");
  if (!m) {
    return { key: null, name: null };
  }
  if (m[1]) {
    return { key: m[1], name: VERSIONEN[m[1]] || m[1] };
  }
  const name = m[2] || VERSIONEN.retail;
  const key = Object.keys(VERSIONEN).find((k) => VERSIONEN[k] === name) || name.toLowerCase().replace(/ /g, "_");
  return { key, name };
}

// Bracket eines Sensors: Ende des Namens, sonst Ende der Entity-ID
function bracketVon(stateObj, entityId) {
  const name = /(?:^|\s)(2v2|3v3|rbg)$/i.exec(String(stateObj?.attributes?.friendly_name || ""));
  if (name) {
    return name[1].toLowerCase();
  }
  const id = /_(2v2|3v3|rbg)(?:_\d+)?$/.exec(entityId);
  return id ? id[1] : null;
}

class WowPvpCard extends HTMLElement {
  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === "wow_character" && e.translation_key === "level"
    );
    return { entity: entry?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere (wow-card-editor.js), mit Version im Pfad
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({ name: "entity" });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    this._config = { ...config };
    this._signatur = undefined;
    this._quelle = undefined;
    this._ids = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    // Entitaeten des Geraets nur neu suchen, wenn sich Entitaeten oder
    // Geraete geaendert haben; bei Zustandsaenderungen ersetzt das Frontend
    // nur hass.states.
    if (!this._ids || this._quelle !== hass.entities || this._geraete !== hass.devices) {
      this._finden(hass);
      this._quelle = hass.entities;
      this._geraete = hass.devices;
      this._signatur = undefined;
    }
    const ids = [...Object.values(this._ids), ...this._brackets];
    const signatur = [...ids.map((id) => hass.states[id]), hass.locale?.language];
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

  getCardSize() {
    return 3 + 2 * (this._brackets?.length || 0);
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
    // Level, Ehrenstufe, Ehrenhafte Siege und Brackets am Geraet der
    // konfigurierten Entitaet
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = {};
    this._brackets = [];
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id !== device || e.platform !== "wow_character") {
        continue;
      }
      if (["level", "honor_level", "honorable_kills"].includes(e.translation_key)) {
        this._ids[e.translation_key] = e.entity_id;
      } else if (e.translation_key === "pvp_bracket") {
        this._brackets.push(e.entity_id);
      }
    }
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const states = this._hass.states;
    const st = (key) => (this._ids[key] ? states[this._ids[key]] : undefined);
    const g = this._device;
    const spiel = spielversion(g?.model);
    const lvl = st("level");
    const name = String(
      g?.name_by_user || g?.name || String(lvl?.attributes?.friendly_name || "").replace(/\s*Level$/, "")
    ).split(" – ")[0];

    let body;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else {
      const teile = [];
      const kacheln = [
        ["honor_level", "honorLevel"],
        ["honorable_kills", "honorableKills"],
      ].filter(([key]) => st(key));
      if (kacheln.length) {
        teile.push(`<div class="kacheln" style="--kacheln:${kacheln.length}">${kacheln
          .map(
            ([key, text]) => `
          <div class="kachel">
            <div class="kwert">${esc(this._format(zahl(st(key))))}</div>
            <div class="ktitel">${esc(this._t(text))}</div>
          </div>`
          )
          .join("")}</div>`);
      }
      const brackets = this._brackets
        .map((id) => ({ e: states[id], b: bracketVon(states[id], id) }))
        .filter((x) => x.e)
        .sort((a, b) => this._rang(a.b) - this._rang(b.b));
      if (brackets.length) {
        teile.push(`<div class="wertungen">
          <div class="ueberschrift">${esc(this._t("ratings"))}</div>
          ${brackets.map((x) => this._bracket(x)).join("")}
        </div>`);
      } else {
        teile.push(`<div class="hinweis">${esc(this._t(spiel.key === "classic_era" ? "classicEra" : "noBracket"))}</div>`);
      }
      body = teile.join("");
    }
    const label = [spiel.name, name].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:sword-cross"></ha-icon></div>
          <div class="name">${esc(this._t("title"))}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _rang(b) {
    return BRACKETS.includes(b) ? BRACKETS.indexOf(b) : BRACKETS.length;
  }

  _format(v) {
    return v === null ? "–" : Math.round(v).toLocaleString(this._hass?.locale?.language || "de");
  }

  _bilanz(spiele, siege, nieder) {
    if (spiele === null) {
      return null;
    }
    if (spiele === 0) {
      return this._t("noGames");
    }
    return this._t("record")(siege ?? 0, nieder ?? 0);
  }

  _bracket({ e, b }) {
    const a = e.attributes || {};
    // Unbekanntes Bracket: Name des Sensors ohne Geraetenamen
    const geraetName = this._device?.name_by_user || this._device?.name || "";
    let titel = this._t("brackets")[b];
    if (!titel) {
      titel = String(a.friendly_name || e.entity_id);
      if (geraetName && titel.startsWith(geraetName)) {
        titel = titel.slice(geraetName.length).trim();
      }
    }
    const spiele = anzahl(a.season_played);
    const siege = anzahl(a.season_won);
    const quote = spiele ? Math.round(((siege || 0) / spiele) * 100) : null;
    const saison = this._bilanz(spiele, siege, anzahl(a.season_lost));
    const woche = this._bilanz(anzahl(a.weekly_played), anzahl(a.weekly_won), anzahl(a.weekly_lost));
    return `
      <div class="bracket">
        <div class="bkopf">
          <span class="bname">${esc(titel)}</span>
          <span class="bwert">${esc(this._format(zahl(e)))}</span>
        </div>
        <div class="balken"><div style="width:${quote === null ? 0 : Math.max(2, quote)}%"></div></div>
        <div class="bilanz">
          <span>${esc(this._t("season"))}: ${esc(saison === null ? "–" : saison)}${quote === null ? "" : ` · ${quote} %`}</span>
          <span>${esc(this._t("week"))}: ${esc(woche === null ? "–" : woche)}</span>
        </div>
      </div>`;
  }
}

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
  .label {
    grid-area: l; align-self: start; margin-top: 1px; font-size: 12.5px; color: ${FARBEN.sek};
    overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance;
  }
  .body { display: grid; gap: 8px; padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; padding: 0 2px; }
  .kacheln { display: grid; grid-template-columns: repeat(var(--kacheln), minmax(0, 1fr)); gap: 6px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 13px; padding: 8px 6px; text-align: center; }
  .kwert { font-size: 16px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ktitel { margin-top: 2px; font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; }
  .wertungen { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 12px; }
  .ueberschrift { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: ${FARBEN.sek}; }
  .bracket { display: grid; gap: 4px; }
  .bkopf { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: baseline; }
  .bname { font-size: 13px; font-weight: 700; line-height: 1.3; color: ${FARBEN.label}; }
  .bwert { font-size: 18px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .balken { height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken > div { height: 100%; border-radius: 5px; background: ${FARBEN.akzent}; }
  .bilanz { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 2px 10px; font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; font-variant-numeric: tabular-nums; }
`;

if (!customElements.get("wow-pvp-card")) {
  customElements.define("wow-pvp-card", WowPvpCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-pvp-card",
    name: "WoW PvP",
    description: "PvP eines Charakters: Ehrenstufe, ehrenhafte Siege, Wertungen je Bracket.",
  });
}
