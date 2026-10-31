/*
 * Karte "WoW Ruf" fuer die Integration WoW Charakter.
 *
 * Ruf eines Charakters: je Fraktion Name, Stufe ("Ruhmstufe 15",
 * "Freundlich") und Fortschritt innerhalb der Stufe als Balken, bei Paragon
 * zusaetzlich dessen Fortschritt.
 *
 * Auswahl:
 *   factions leer   die Fraktionen mit Ruhmstufe, die neuesten zuerst,
 *                   hoechstens count (Vorgabe 6)
 *   factions        feste Liste von Fraktions-IDs in dieser Reihenfolge
 * Die API ordnet Fraktionen keiner Erweiterung zu. "Neueste zuerst" heisst
 * hier: hoechste Fraktions-ID zuerst; neue Fraktionen haben bisher hoehere
 * IDs bekommen, belegt ist das nicht. Namen sind nicht eindeutig, deshalb
 * die ID. Im Editor stehen die Fraktionen des Charakters mit Namen zur
 * Auswahl.
 * WoW Classic: Die Classic-API liefert keinen Ruf; die Karte nennt das.
 * Unterzeile: Spielversion, Name und "x von y Fraktionen".
 *
 * Die Karte findet den Sensor "Ruf" ueber das Geraet des Charakters und den
 * Uebersetzungsschluessel reputation, nicht ueber Entity-IDs; sie
 * funktioniert deshalb mit jeder Sprache und ohne Praefix.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-reputation-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *   factions: [2710, 2696]             # optional, Fraktions-IDs
 *   count: 6                           # optional, ohne factions
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-ruf-karte.yaml; ohne das Theme in beiden Modi dunkel. Paragon in
 * Violett, mit "Paragon" als Text.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  violett: "var(--nachtblau-violett, #b399d4)",
  text: "var(--nachtblau-text, #f2f5f8)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
  spur: "var(--nachtblau-neutral-kachel, rgba(255, 255, 255, 0.05))",
};

const ANZAHL = 6;

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
    renownTitle: "Ruhmstufen",
    title: "Ruf",
    of: (n, m) => `${n} von ${m} Fraktionen`,
    renown: "Ruhmstufe",
    paragon: "Paragon",
    noMatch: "Keine passenden Fraktionen. Ohne Ruhmstufe die Fraktionen im Editor auswählen.",
    classic: "Ruf gibt es für WoW Classic nicht: Die Classic-API von Blizzard liefert keine Ruf-Daten.",
    none: "Kein Ruf-Sensor gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    factions: "Fraktionen (leer: neueste mit Ruhmstufe)",
    count: "Anzahl neueste Ruhmstufen (leer: 6; nur ohne Fraktionsauswahl)",
  },
  en: {
    renownTitle: "Renown",
    title: "Reputation",
    of: (n, m) => `${n} of ${m} factions`,
    renown: "Renown",
    paragon: "Paragon",
    noMatch: "No matching factions. Without renown, select the factions in the editor.",
    classic: "WoW Classic has no reputation: Blizzard's Classic API returns no reputation data.",
    none: "No reputation sensor found.",
    missing: "No entities of the integration “WoW Charakter” for",
    factions: "Factions (empty: newest with renown)",
    count: "Number of newest renown factions (empty: 6; only without faction selection)",
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

// Sensor "Ruf" am Geraet einer Entitaet
function rufSensor(hass, entityId) {
  const entities = hass?.entities || {};
  const device = entities[entityId]?.device_id;
  if (!device) {
    return undefined;
  }
  return Object.values(entities).find(
    (e) => e.device_id === device && e.platform === "wow_character" && e.translation_key === "reputation"
  )?.entity_id;
}

class WowReputationCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit Ruf (Retail)
    const entries = Object.values(hass.entities || {});
    const ruf = entries.find((e) => e.platform === "wow_character" && e.translation_key === "reputation");
    const level = entries.find(
      (e) => e.platform === "wow_character" && e.translation_key === "level" && e.device_id === ruf?.device_id
    );
    return { entity: level?.entity_id || ruf?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere mit Ruf (wow-card-editor.js); optional die
    // Fraktionen des gewaehlten Charakters und die Anzahl
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({
      name: "entity",
      require: "reputation",
      extra: (lang, { hass, entity }) => {
        const factions = hass?.states[rufSensor(hass, entity)]?.attributes?.factions || [];
        const optionen = factions
          .filter((r) => r.faction_id != null)
          .slice()
          .sort((a, b) => String(a.faction).localeCompare(String(b.faction), lang))
          .map((r) => ({ value: String(r.faction_id), label: `${r.faction} (${r.faction_id})` }));
        return [
          { name: "factions", selector: { select: { multiple: true, mode: "dropdown", options: optionen } } },
          { name: "count", selector: { number: { min: 1, max: 30, mode: "box" } } },
        ];
      },
      labels: {
        factions: { de: TEXT.de.factions, en: TEXT.en.factions },
        count: { de: TEXT.de.count, en: TEXT.en.count },
      },
    });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    if (config.factions !== undefined && !Array.isArray(config.factions)) {
      throw new Error("factions muss eine Liste sein / factions must be a list");
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
    return 2 + (this._config?.factions?.length || this._config?.count || ANZAHL);
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

  _zahl(v) {
    return Number(v || 0).toLocaleString(this._hass?.locale?.language || "de");
  }

  _finden(hass) {
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = {};
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id === device && e.platform === "wow_character" && ["level", "reputation"].includes(e.translation_key)) {
        this._ids[e.translation_key] = e.entity_id;
      }
    }
  }

  _auswahl(alle) {
    // Feste Liste in dieser Reihenfolge, sonst die neuesten mit Ruhmstufe
    const ids = this._config.factions || [];
    if (ids.length) {
      return ids.map((id) => alle.find((r) => r.faction_id === Number(id))).filter(Boolean);
    }
    const anzahl = Number(this._config.count) > 0 ? Number(this._config.count) : ANZAHL;
    return alle
      .filter((r) => r.renown != null)
      .sort((a, b) => (b.faction_id || 0) - (a.faction_id || 0))
      .slice(0, anzahl);
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
    const ruf = st("reputation");
    const alle = Array.isArray(ruf?.attributes?.factions) ? ruf.attributes.factions : [];
    const auswahl = this._auswahl(alle);
    const titel = this._config.factions?.length ? this._t("title") : this._t("renownTitle");

    let body;
    let zusatz = null;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!ruf) {
      body = `<div class="hinweis">${esc(this._t(spiel.key?.startsWith("classic_") ? "classic" : "none"))}</div>`;
    } else {
      zusatz = this._t("of")(auswahl.length, alle.length);
      body = auswahl.length
        ? `<div class="kachel">${auswahl.map((r) => this._zeile(r)).join("")}</div>`
        : `<div class="hinweis">${esc(this._t("noMatch"))}</div>`;
    }
    const label = [spiel.name, name, zusatz].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:handshake"></ha-icon></div>
          <div class="name">${esc(titel)}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _balken(wert, max, farbe) {
    const breite = max ? Math.max(0, Math.min(100, (wert / max) * 100)) : 0;
    return `<div class="balken"><div style="width:${breite}%;background:${farbe}"></div></div>`;
  }

  _zeile(r) {
    // Stufe ohne Fortschritt (z. B. Ehrfuerchtig 0/0): voller Balken
    const max = r.max || 0;
    const stufe = r.renown != null ? `${this._t("renown")} ${r.renown}` : r.standing;
    const fortschritt = max ? `${this._zahl(r.value)} / ${this._zahl(max)}` : "";
    const paragon =
      r.paragon && r.paragon.max
        ? `<div class="paragon"><span>${esc(this._t("paragon"))}</span><span>${esc(
            `${this._zahl(r.paragon.value)} / ${this._zahl(r.paragon.max)}`
          )}</span></div>${this._balken(r.paragon.value, r.paragon.max, FARBEN.violett)}`
        : "";
    return `
      <div class="fraktion">
        <div class="fkopf">
          <span class="fname">${esc(r.faction)}</span>
          <span class="stufe">${esc(stufe)}</span>
        </div>
        ${this._balken(max ? r.value : 1, max || 1, FARBEN.akzent)}
        ${fortschritt ? `<div class="fortschritt">${esc(fortschritt)}</div>` : ""}
        ${paragon}
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
  .fraktion { display: grid; gap: 4px; }
  .fkopf { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 10px; align-items: baseline; }
  .fname { min-width: 0; font-size: 13px; font-weight: 700; line-height: 1.3; color: ${FARBEN.text}; ${ZWEIZEILIG} }
  .stufe { font-size: 12.5px; font-weight: 650; color: ${FARBEN.label}; white-space: nowrap; }
  .balken { height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken > div { height: 100%; border-radius: 5px; }
  .fortschritt { font-size: 12px; color: ${FARBEN.sek}; font-variant-numeric: tabular-nums; text-align: right; }
  .paragon { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; color: ${FARBEN.sek}; }
  .paragon span:last-child { font-variant-numeric: tabular-nums; }
`;

if (!customElements.get("wow-reputation-card")) {
  customElements.define("wow-reputation-card", WowReputationCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-reputation-card",
    name: "WoW Ruf",
    description: "Ruf und Ruhmstufen eines Charakters mit Fortschritt und Paragon.",
  });
}
