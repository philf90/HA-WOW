/*
 * Karte "WoW Berufe" fuer die Integration WoW Charakter.
 *
 * Berufe eines Charakters: je Beruf Symbol, Name, Stufe (Erweiterung) und
 * Skill als Balken bis zum Maximum der neuesten Stufe, sortiert nach
 * Fortschritt. Ein ausgelernter Beruf (Skill = Maximum) wird gruen.
 * Unterzeile: Spielversion, Name des Charakters und Anzahl der Berufe.
 * WoW Classic: Die Classic-API liefert keine Berufe; die Karte nennt das.
 *
 * Die Karte findet die Sensoren "Beruf {Name}" ueber das Geraet des
 * Charakters und den Uebersetzungsschluessel profession, nicht ueber
 * Entity-IDs; sie funktioniert deshalb mit jeder Sprache und ohne Praefix.
 * Den Namen des Berufs nimmt sie aus dem Entitaetsnamen ("Beruf
 * Schneiderei", "Profession Tailoring").
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-professions-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-berufe-karte.yaml; ohne das Theme in beiden Modi dunkel.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  gruen: "var(--nachtblau-gruen, #a6d49e)",
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

const TEXT = {
  de: {
    title: "Berufe",
    count: (n) => (n === 1 ? "1 Beruf" : `${n} Berufe`),
    classic: "Berufe gibt es für WoW Classic nicht: Die Classic-API von Blizzard liefert keine Berufsdaten.",
    none: "Keine Berufe gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
  },
  en: {
    title: "Professions",
    count: (n) => (n === 1 ? "1 profession" : `${n} professions`),
    classic: "WoW Classic has no professions: Blizzard's Classic API returns no profession data.",
    none: "No professions found.",
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

function zahl(value) {
  const n = parseFloat(value);
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

class WowProfessionsCard extends HTMLElement {
  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === "wow_character" && e.translation_key === "level"
    );
    return { entity: entry?.entity_id || "" };
  }

  static async getConfigElement() {
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
    this._berufe = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    // Entitaeten des Geraets nur neu suchen, wenn sich Entitaeten oder
    // Geraete geaendert haben; bei Zustandsaenderungen ersetzt das Frontend
    // nur hass.states.
    if (!this._berufe || this._quelle !== hass.entities || this._geraete !== hass.devices) {
      this._finden(hass);
      this._quelle = hass.entities;
      this._geraete = hass.devices;
      this._signatur = undefined;
    }
    const signatur = [this._level, ...this._berufe].map((id) => hass.states[id]);
    signatur.push(hass.locale?.language);
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
    return 2 + (this._berufe?.length || 0);
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
    // Level-Sensor und Berufe am Geraet der konfigurierten Entitaet
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._level = undefined;
    this._berufe = [];
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id !== device || e.platform !== "wow_character") {
        continue;
      }
      if (e.translation_key === "level") {
        this._level = e.entity_id;
      } else if (e.translation_key === "profession") {
        this._berufe.push(e.entity_id);
      }
    }
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const states = this._hass.states;
    const g = this._device;
    const spiel = spielversion(g?.model);
    const lvl = states[this._level];
    const name = String(
      g?.name_by_user || g?.name || String(lvl?.attributes?.friendly_name || "").replace(/\s*Level$/, "")
    ).split(" – ")[0];
    const geraetName = g?.name_by_user || g?.name || "";
    const berufe = this._berufe
      .map((id) => states[id])
      .filter(Boolean)
      .map((e) => {
        // "Name – Realm Beruf Schneiderei" -> "Schneiderei"
        let n = String(e.attributes?.friendly_name || e.entity_id);
        if (geraetName && n.startsWith(geraetName)) {
          n = n.slice(geraetName.length).trim();
        }
        n = n.replace(/^(Beruf|Profession)\s+/, "");
        return {
          name: n,
          tier: e.attributes?.tier,
          bild: e.attributes?.entity_picture,
          skill: zahl(e.state),
          max: zahl(e.attributes?.max_skill),
        };
      })
      .sort(
        (a, b) =>
          (b.max ? (b.skill || 0) / b.max : 0) - (a.max ? (a.skill || 0) / a.max : 0) ||
          a.name.localeCompare(b.name, this._lang())
      );

    let body;
    if (!this._level) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!berufe.length) {
      body = `<div class="hinweis">${esc(this._t(spiel.key?.startsWith("classic_") ? "classic" : "none"))}</div>`;
    } else {
      body = `<div class="kachel">${berufe.map((b) => this._zeile(b)).join("")}</div>`;
    }
    const label = [spiel.name, name, this._level ? this._t("count")(berufe.length) : null]
      .filter(Boolean)
      .join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:hammer-wrench"></ha-icon></div>
          <div class="name">${esc(this._t("title"))}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _zeile(b) {
    const fertig = b.max && b.skill !== null && b.skill >= b.max;
    const breite = b.max && b.skill !== null ? Math.max(0, Math.min(100, (b.skill / b.max) * 100)) : 0;
    // Ohne Symbol beginnt die Zeile mit dem Namen
    const spalte = b.bild ? "2" : "1";
    return `
      <div class="beruf${b.bild ? " mit-bild" : ""}">
        ${b.bild ? `<img class="bild" src="${esc(b.bild)}" alt="">` : ""}
        <span class="bname">${esc(b.name)}</span>
        <span class="skill"><b${fertig ? ' class="fertig"' : ""}>${b.skill === null ? "–" : b.skill}</b>${
          b.max ? ` / ${b.max}` : ""
        }</span>
        ${b.tier ? `<span class="tier" style="grid-column:${spalte} / -1">${esc(b.tier)}</span>` : ""}
        <div class="balken" style="grid-column:${spalte} / -1"><div style="width:${breite}%;background:${
          fertig ? FARBEN.gruen : FARBEN.akzent
        }"></div></div>
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
  .label { grid-area: l; align-self: start; margin-top: 1px; font-size: 12.5px; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .body { padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; }
  .kachel { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 12px; }
  .beruf { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; align-items: baseline; }
  .beruf.mit-bild { grid-template-columns: 30px minmax(0, 1fr) auto; }
  .bild { grid-row: 1 / span 2; align-self: center; width: 30px; height: 30px; border-radius: 8px; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .bname { min-width: 0; font-size: 13px; font-weight: 700; color: ${FARBEN.text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .skill { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; }
  .skill b { font-size: 14px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; }
  .skill b.fertig { color: ${FARBEN.gruen}; }
  .tier { font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .balken { height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken > div { height: 100%; border-radius: 5px; }
`;

if (!customElements.get("wow-professions-card")) {
  customElements.define("wow-professions-card", WowProfessionsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-professions-card",
    name: "WoW Berufe",
    description: "Berufe eines Charakters: Skill, Stufe und Fortschritt.",
  });
}
