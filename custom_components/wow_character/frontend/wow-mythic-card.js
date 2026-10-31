/*
 * Karte "WoW Mythic+" fuer die Integration WoW Charakter.
 *
 * Mythic+ eines Charakters in der aktuellen Season:
 *   Kacheln  Wertung, hoechster Schluessel, Laeufe in Zeit
 *   Liste    bester Lauf je Dungeon: Stufe, in Zeit oder nicht, Dauer,
 *            Wertung des Laufs und Affixe (Attribut runs)
 * Hat der Charakter in der aktuellen Season noch nicht gespielt, steht die
 * Wertung aus dem Attribut api_rating da (der Wert, den das Arsenal zeigt),
 * mit dem Hinweis "laut Arsenal". Mythic+ gibt es nur in Retail; fuer andere
 * Spielversionen nennt die Karte das.
 * Unterzeile: Spielversion, Name des Charakters und Zahl der Dungeons.
 *
 * Die Karte findet die Sensoren ueber das Geraet des Charakters und die
 * Uebersetzungsschluessel mythic_rating, mythic_best_key und
 * mythic_runs_timed, nicht ueber Entity-IDs; sie funktioniert deshalb mit
 * jeder Sprache und ohne Praefix.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-mythic-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-mythic-karte.yaml; ohne das Theme in beiden Modi dunkel. "in Zeit"
 * gruen, "ueber Zeit" Sekundaertext, beides als Wort. Die Wertungsfarbe der
 * API steht nicht in der Karte: Sie ist auf heller Huelle nicht sicher lesbar.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  gruen: "var(--nachtblau-gruen, #a6d49e)",
  text: "var(--nachtblau-text, #f2f5f8)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
};

// Entitaeten des Charakters (Uebersetzungsschluessel der Integration)
const SCHLUESSEL = ["level", "mythic_rating", "mythic_best_key", "mythic_runs_timed"];

// Spielversion aus dem Geraetemodell: "World of Warcraft" (Retail),
// "World of Warcraft Classic Era" usw.; bis 0.21.x "World of Warcraft (classic_era)"
const VERSIONEN = {
  retail: "Retail",
  classic_era: "Classic Era",
  classic_progression: "Classic Progression",
  classic_anniversary: "Classic Anniversary",
  forever: "Forever",
};

const TEXT = {
  de: {
    title: "Mythic+",
    season: "Season",
    dungeons: (n) => (n === 1 ? "1 Dungeon gelaufen" : `${n} Dungeons gelaufen`),
    noRunLabel: "noch kein Lauf in dieser Season",
    noRun: "Noch kein Lauf in dieser Season.",
    rating: "Wertung",
    viaArmory: "laut Arsenal",
    bestKey: "Höchster Schlüssel",
    timedTile: "In Zeit",
    timed: "in Zeit",
    overtime: "über Zeit",
    runRating: "Wertung",
    retailOnly: "Mythic+ gibt es nur in Retail. Für diese Spielversion legt die Integration keine Mythic+-Sensoren an.",
    none: "Keine Mythic+-Sensoren gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
  },
  en: {
    title: "Mythic+",
    season: "Season",
    dungeons: (n) => (n === 1 ? "1 dungeon run" : `${n} dungeons run`),
    noRunLabel: "no run this season yet",
    noRun: "No run this season yet.",
    rating: "Rating",
    viaArmory: "per Armory",
    bestKey: "Highest key",
    timedTile: "Timed",
    timed: "timed",
    overtime: "over time",
    runRating: "Rating",
    retailOnly: "Mythic+ exists only in Retail. The integration creates no Mythic+ sensors for this game version.",
    none: "No Mythic+ sensors found.",
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

// Dauer in Sekunden als m:ss
function dauer(s) {
  if (typeof s !== "number" || s < 0) {
    return "";
  }
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

class WowMythicCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit Mythic+ (Retail)
    const entries = Object.values(hass.entities || {});
    const mplus = entries.find((e) => e.platform === "wow_character" && e.translation_key === "mythic_rating");
    const level = entries.find(
      (e) => e.platform === "wow_character" && e.translation_key === "level" && e.device_id === mplus?.device_id
    );
    return { entity: level?.entity_id || mplus?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere mit Mythic+ (wow-card-editor.js)
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({ name: "entity", require: "mythic_rating" });
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
    const signatur = [...Object.values(this._ids).map((id) => hass.states[id]), hass.locale?.language];
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
    return 7;
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
    // Uebersetzungsschluessel -> Entity-ID am Geraet der konfigurierten Entitaet
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = {};
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id === device && e.platform === "wow_character" && SCHLUESSEL.includes(e.translation_key)) {
        this._ids[e.translation_key] = e.entity_id;
      }
    }
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const st = (key) => (this._ids[key] ? this._hass.states[this._ids[key]] : undefined);
    const g = this._device;
    const spiel = spielversion(g?.model);
    const lvl = st("level");
    const name = String(
      g?.name_by_user || g?.name || String(lvl?.attributes?.friendly_name || "").replace(/\s*Level$/, "")
    ).split(" – ")[0];
    const wertung = st("mythic_rating");
    const schluessel = st("mythic_best_key");
    const runs = (Array.isArray(schluessel?.attributes?.runs) ? schluessel.attributes.runs : [])
      .slice()
      .sort((a, b) => (b.level || 0) - (a.level || 0));
    const season = wertung?.attributes?.season;
    const titel = season ? `${this._t("title")} · ${this._t("season")} ${season}` : this._t("title");

    let body;
    let zusatz = null;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!wertung) {
      body = `<div class="hinweis">${esc(this._t(spiel.key && spiel.key !== "retail" ? "retailOnly" : "none"))}</div>`;
    } else {
      zusatz = runs.length ? this._t("dungeons")(runs.length) : this._t("noRunLabel");
      body = `${this._kacheln(wertung, schluessel, st("mythic_runs_timed"))}${
        runs.length
          ? `<div class="liste">${runs.map((r) => this._lauf(r)).join("")}</div>`
          : `<div class="hinweis kein-lauf">${esc(this._t("noRun"))}</div>`
      }`;
    }
    const label = [spiel.name, name, zusatz].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:key-variant"></ha-icon></div>
          <div class="name">${esc(titel)}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _kacheln(wertung, schluessel, inZeit) {
    let w = zahl(wertung);
    let hinweis = `${this._t("season")} ${wertung.attributes?.season ?? "–"}`;
    if (w === null && wertung.attributes?.api_rating != null) {
      w = wertung.attributes.api_rating;
      hinweis = this._t("viaArmory");
    }
    const k = zahl(schluessel);
    const z = zahl(inZeit);
    const lang = this._hass?.locale?.language || "de";
    const kachel = (titel, wert, zeile) => `
      <div class="kachel">
        <div class="kwert">${esc(wert)}</div>
        <div class="ktitel">${esc(titel)}</div>
        ${zeile ? `<div class="khinweis">${esc(zeile)}</div>` : ""}
      </div>`;
    return `<div class="kacheln">
      ${kachel(this._t("rating"), w === null ? "–" : Math.round(w).toLocaleString(lang), hinweis)}
      ${kachel(this._t("bestKey"), k === null ? "–" : `+${k}`, "")}
      ${kachel(this._t("timedTile"), z === null ? "–" : z, "")}
    </div>`;
  }

  _lauf(r) {
    const pille = r.timed
      ? `<span class="pille in-zeit">${esc(this._t("timed"))}</span>`
      : `<span class="pille">${esc(this._t("overtime"))}</span>`;
    const details = [
      dauer(r.duration),
      r.rating != null ? `${this._t("runRating")} ${Math.round(r.rating)}` : "",
      (Array.isArray(r.affixes) ? r.affixes : []).join(", "),
    ]
      .filter(Boolean)
      .map(esc)
      .join(" · ");
    return `
      <div class="lauf">
        <span class="stufe">+${esc(r.level ?? "?")}</span>
        <span class="dungeon">${esc(r.dungeon)}</span>
        <span class="status">${pille}</span>
        ${details ? `<span class="details">${details}</span>` : ""}
      </div>`;
  }
}

const ZWEIZEILIG =
  "overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance;";

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; padding: 14px 16px 14px; border-radius: 22px; cursor: default;
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
  .label { grid-area: l; align-self: start; margin-top: 1px; font-size: 12.5px; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .body { display: grid; gap: 8px; padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; }
  .hinweis.kein-lauf { padding: 0 2px; }
  .kacheln { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 13px; padding: 8px 6px; text-align: center; }
  .kwert { font-size: 17px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .ktitel { margin-top: 2px; font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .khinweis { font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; }
  .liste { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 2px 12px; }
  .lauf { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 2px 10px; align-items: center; padding: 8px 0; }
  .lauf + .lauf { border-top: 1px solid ${FARBEN.rand}; }
  .stufe { grid-row: 1 / span 2; font-size: 17px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; }
  .dungeon { min-width: 0; font-size: 13px; font-weight: 650; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .status { justify-self: end; }
  .pille { font-size: 11.5px; font-weight: 700; color: ${FARBEN.sek}; padding: 2px 0; white-space: nowrap; }
  .pille.in-zeit {
    color: ${FARBEN.gruen}; padding: 2px 7px; border-radius: 8px;
    background: color-mix(in srgb, ${FARBEN.gruen} 12%, transparent);
    border: 1px solid color-mix(in srgb, ${FARBEN.gruen} 24%, transparent);
  }
  .details { grid-column: 2 / -1; font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
`;

if (!customElements.get("wow-mythic-card")) {
  customElements.define("wow-mythic-card", WowMythicCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-mythic-card",
    name: "WoW Mythic+",
    description: "Mythic+ eines Charakters: Wertung, höchster Schlüssel, beste Läufe je Dungeon.",
  });
}
