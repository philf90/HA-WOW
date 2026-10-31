/*
 * Karte "WoW Garderobe" fuer die Integration WoW Charakter.
 *
 * Transmog-Vorlagen und Erbstuecke eines Charakters:
 *   Kopf        Zahl verschiedener Transmog-Vorlagen und gesammelter Sets
 *   Erbstuecke  Anzahl im Titel; aufgewertete als Balken (Stufe 1 voll,
 *               hoehere Stufen halb deckend), darunter die Zahl je Stufe
 *   Plaetze     Vorlagen je Platz, zweispaltig, die meisten zuerst
 * Abschnitte ohne Sensor fallen weg. WoW Classic: Die Classic-API liefert
 * keine Sammlungen; die Karte nennt das.
 * Unterzeile: Spielversion und Name des Charakters.
 *
 * Die Karte findet die Sensoren "Transmog-Vorlagen" und "Erbstuecke" ueber
 * das Geraet des Charakters und die Uebersetzungsschluessel transmogs und
 * heirlooms, nicht ueber Entity-IDs; sie funktioniert deshalb mit jeder
 * Sprache und ohne Praefix.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-wardrobe-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-garderobe-karte.yaml; ohne das Theme in beiden Modi dunkel. Hoehere
 * Erbstueck-Stufen mit Deckkraft 0,5.
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

// Entitaeten des Charakters (Uebersetzungsschluessel der Integration)
const SCHLUESSEL = ["level", "transmogs", "heirlooms"];

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
    title: "Garderobe",
    appearances: "Vorlagen",
    sets: "Sets",
    heirlooms: "Erbstücke",
    upgraded: "Aufgewertet",
    of: "von",
    level: "Stufe",
    without: "ohne",
    perSlot: "Vorlagen je Platz",
    sameName: "Gleichnamige Plätze stehen zusammen, z. B. „Brust“ für Brust und Robe.",
    classic: "Transmog-Vorlagen und Erbstücke gibt es für WoW Classic nicht.",
    none: "Keine Transmog-Vorlagen und Erbstücke gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
  },
  en: {
    title: "Wardrobe",
    appearances: "appearances",
    sets: "sets",
    heirlooms: "Heirlooms",
    upgraded: "Upgraded",
    of: "of",
    level: "Level",
    without: "none",
    perSlot: "Appearances per slot",
    sameName: "Slots with the same name are combined, e.g. “Chest” for chest and robe.",
    classic: "WoW Classic has no transmog appearances or heirlooms.",
    none: "No transmog appearances or heirlooms found.",
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
  if (!stateObj) {
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

class WowWardrobeCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit Transmog-Vorlagen (Retail)
    const entries = Object.values(hass.entities || {});
    const vorlagen = entries.find((e) => e.platform === "wow_character" && e.translation_key === "transmogs");
    const level = entries.find(
      (e) => e.platform === "wow_character" && e.translation_key === "level" && e.device_id === vorlagen?.device_id
    );
    return { entity: level?.entity_id || vorlagen?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere mit Transmog-Vorlagen (wow-card-editor.js)
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({ name: "entity", require: "transmogs" });
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
    return 8;
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

  _format(v) {
    return typeof v === "number" && !Number.isNaN(v)
      ? Math.round(v).toLocaleString(this._hass?.locale?.language || "de")
      : "–";
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
    const vorlagen = st("transmogs");
    const erbstuecke = st("heirlooms");

    let body;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!vorlagen && !erbstuecke) {
      body = `<div class="hinweis">${esc(this._t(spiel.key?.startsWith("classic_") ? "classic" : "none"))}</div>`;
    } else {
      body = [
        vorlagen ? this._kopfzahlen(vorlagen) : "",
        erbstuecke ? this._erbstuecke(erbstuecke) : "",
        vorlagen ? this._plaetze(vorlagen) : "",
      ].join("");
    }
    const label = [spiel.name, name].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:hanger"></ha-icon></div>
          <div class="name">${esc(this._t("title"))}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _abschnitt(ueberschrift, inhalt) {
    return `
      <div class="abschnitt">
        ${ueberschrift ? `<div class="ueberschrift">${esc(ueberschrift)}</div>` : ""}
        ${inhalt}
      </div>`;
  }

  _gross(wert, name) {
    return `<div class="gross"><span class="gwert">${esc(this._format(wert))}</span><span class="gname">${esc(name)}</span></div>`;
  }

  _kopfzahlen(vorlagen) {
    // Verschiedene Vorlagen und gesammelte Sets
    const sets = vorlagen.attributes?.sets;
    return this._abschnitt(
      "",
      `<div class="kopfzahlen">${this._gross(zahl(vorlagen), this._t("appearances"))}${
        typeof sets === "number" ? this._gross(sets, this._t("sets")) : ""
      }</div>`
    );
  }

  _erbstuecke(erbstuecke) {
    // Aufgewertete als geteilter Balken: Stufe 1 voll, hoehere Stufen halb deckend
    const gesamt = zahl(erbstuecke);
    const stufen = erbstuecke.attributes?.upgrade_levels || {};
    const auf = erbstuecke.attributes?.upgraded;
    const eins = Number(stufen["1"]) || 0;
    const hoeher = Math.max(0, (Number(auf) || 0) - eins);
    const anteil = (n) => (gesamt ? (n / gesamt) * 100 : 0);
    const liste = Object.keys(stufen)
      .map(Number)
      .filter((s) => !Number.isNaN(s))
      .sort((a, b) => a - b);
    const verteilung = [
      ...liste
        .filter((s) => s > 0)
        .map((s) => `${esc(this._t("level"))} ${s}: <b>${esc(this._format(Number(stufen[s])))}</b>`),
      ...(stufen["0"] !== undefined ? [`${esc(this._t("without"))}: <b>${esc(this._format(Number(stufen["0"])))}</b>`] : []),
    ].join(" · ");
    const balken =
      typeof auf === "number"
        ? `
      <div class="aufgewertet">
        <span class="aname">${esc(this._t("upgraded"))}</span>
        <span class="awert"><b>${esc(this._format(auf))}</b> ${esc(this._t("of"))} ${esc(this._format(gesamt))}</span>
        <div class="balken">
          ${eins ? `<div style="width:${anteil(eins)}%"></div>` : ""}
          ${hoeher ? `<div class="hoeher" style="width:${Math.max(2, anteil(hoeher))}%"></div>` : ""}
        </div>
      </div>`
        : "";
    return this._abschnitt(
      `${this._t("heirlooms")} · ${this._format(gesamt)}`,
      `${balken}${verteilung ? `<div class="verteilung">${verteilung}</div>` : ""}`
    );
  }

  _plaetze(vorlagen) {
    // Vorlagen je Platz, die meisten zuerst
    const plaetze = Object.entries(vorlagen.attributes?.slots || {})
      .filter(([, n]) => typeof n === "number")
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], this._lang()));
    if (!plaetze.length) {
      return "";
    }
    return `${this._abschnitt(
      this._t("perSlot"),
      `<div class="plaetze">${plaetze
        .map(
          ([platz, n]) => `
        <div class="platz"><span class="pname">${esc(platz)}</span><span class="pwert">${esc(this._format(n))}</span></div>`
        )
        .join("")}</div>`
    )}<div class="hinweis klein">${esc(this._t("sameName"))}</div>`;
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
  .body { display: grid; gap: 8px; padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; }
  .hinweis.klein { font-size: 12px; line-height: 1.3; padding: 0 2px; }
  .abschnitt { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 9px; }
  .ueberschrift { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: ${FARBEN.sek}; }
  .kopfzahlen { display: flex; flex-wrap: wrap; gap: 4px 16px; }
  .gross { display: flex; align-items: baseline; gap: 5px; min-width: 0; }
  .gwert { font-size: 22px; font-weight: 750; letter-spacing: -0.01em; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .gname { font-size: 12px; color: ${FARBEN.sek}; }
  .aufgewertet { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; align-items: baseline; }
  .aname { min-width: 0; font-size: 12.5px; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .awert { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .awert b { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; }
  .balken { grid-column: 1 / -1; height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; display: flex; gap: 2px; }
  .balken > div { height: 100%; border-radius: 5px; background: ${FARBEN.akzent}; }
  .balken > div.hoeher { background: color-mix(in srgb, ${FARBEN.akzent} 50%, transparent); }
  .verteilung { font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; }
  .verteilung b { color: ${FARBEN.label}; font-weight: 600; }
  .plaetze { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 14px; }
  .platz { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: baseline; }
  .pname { min-width: 0; font-size: 12px; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .pwert { font-size: 12.5px; font-weight: 700; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; }
`;

if (!customElements.get("wow-wardrobe-card")) {
  customElements.define("wow-wardrobe-card", WowWardrobeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-wardrobe-card",
    name: "WoW Garderobe",
    description: "Transmog-Vorlagen, Sets und Erbstücke eines Charakters.",
  });
}
