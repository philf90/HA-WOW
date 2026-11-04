/*
 * Karte "WoW Raids" fuer die Integration WoW Charakter.
 *
 * Raid-Fortschritt eines Charakters in der neuesten Erweiterung:
 *   Kopf     Erweiterung, darunter Spielversion, Name und hoechste
 *            Schwierigkeit mit Kills
 *   Je Schwierigkeit (LFR, Normal, Heroisch, Mythisch) eine Unterkachel mit
 *            besiegten Bossen gesamt und je Raid als Balken, mit dem Bild
 *            des Raids davor; ein voll besiegter Raid wird gruen
 *   Fuss     letzter besiegter Boss seit dem Start von Home Assistant
 *            (Ereignis "Boss besiegt")
 * Schwierigkeiten ohne Bosse (0 von 0) blendet die Karte aus. WoW Classic:
 * Die Classic-API liefert keinen Raid-Fortschritt; die Karte nennt das.
 *
 * Die Karte findet die Sensoren ueber das Geraet des Charakters und die
 * Uebersetzungsschluessel raid_lfr, raid_normal, raid_heroic, raid_mythic
 * und boss_killed, nicht ueber Entity-IDs; sie funktioniert deshalb mit
 * jeder Sprache und ohne Praefix.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-raid-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *   difficulties: [lfr, normal, heroic, mythic]   # optional, Auswahl und Reihenfolge
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-raid-karte.yaml; ohne das Theme in beiden Modi dunkel.
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

// Schwierigkeiten in aufsteigender Reihenfolge (Uebersetzungsschluessel raid_<stufe>)
const STUFEN = ["lfr", "normal", "heroic", "mythic"];

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
    title: "Raids",
    stufen: { lfr: "LFR", normal: "Normal", heroic: "Heroisch", mythic: "Mythisch" },
    highest: "höchste Stufe",
    noBoss: "noch kein Boss",
    bosses: "Bosse",
    noRaids: "Die API meldet für diese Erweiterung noch keine Raids.",
    lastBoss: "Letzter Boss",
    noLastBoss: "Letzter Boss: noch keiner seit dem Start von Home Assistant",
    classic: "Raid-Fortschritt gibt es für WoW Classic nicht: Die Classic-API von Blizzard liefert keine Raid-Daten.",
    none: "Keine Raid-Sensoren gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    difficulties: "Schwierigkeitsgrade (leer: alle)",
  },
  en: {
    title: "Raids",
    stufen: { lfr: "LFR", normal: "Normal", heroic: "Heroic", mythic: "Mythic" },
    highest: "highest difficulty",
    noBoss: "no boss yet",
    bosses: "bosses",
    noRaids: "The API reports no raids for this expansion yet.",
    lastBoss: "Last boss",
    noLastBoss: "Last boss: none since Home Assistant started",
    classic: "WoW Classic has no raid progress: Blizzard's Classic API returns no raid data.",
    none: "No raid sensors found.",
    missing: "No entities of the integration “WoW Charakter” for",
    difficulties: "Difficulties (empty: all)",
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

class WowRaidCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit Raid-Fortschritt (Retail)
    const entries = Object.values(hass.entities || {});
    const raid = entries.find((e) => e.platform === "wow_character" && e.translation_key === "raid_lfr");
    const level = entries.find(
      (e) => e.platform === "wow_character" && e.translation_key === "level" && e.device_id === raid?.device_id
    );
    return { entity: level?.entity_id || raid?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere mit Raid-Fortschritt (wow-card-editor.js);
    // optional die Schwierigkeitsgrade, leer = alle
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({
      name: "entity",
      require: "raid_lfr",
      extra: (lang) => [
        {
          name: "difficulties",
          selector: {
            select: {
              multiple: true,
              mode: "list",
              options: STUFEN.map((s) => ({ value: s, label: (TEXT[lang] || TEXT.en).stufen[s] })),
            },
          },
        },
      ],
      labels: { difficulties: { de: TEXT.de.difficulties, en: TEXT.en.difficulties } },
    });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    const stufen = config.difficulties;
    if (stufen !== undefined && (!Array.isArray(stufen) || stufen.some((s) => !STUFEN.includes(s)))) {
      throw new Error(`difficulties: nur ${STUFEN.join(", ")}`);
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
    return 10;
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
    const keys = ["level", "boss_killed", ...STUFEN.map((s) => `raid_${s}`)];
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = {};
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id === device && e.platform === "wow_character" && keys.includes(e.translation_key)) {
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
    const auswahl = this._config.difficulties?.length ? this._config.difficulties : STUFEN;
    const sensoren = STUFEN.map((s) => ({ stufe: s, e: st(`raid_${s}`) })).filter((x) => x.e);
    const expansion = sensoren.find((x) => x.e.attributes?.expansion)?.e.attributes.expansion;
    const titel = expansion ? `${this._t("title")} · ${expansion}` : this._t("title");

    let body;
    let zusatz = null;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!sensoren.length) {
      body = `<div class="hinweis">${esc(this._t(spiel.key?.startsWith("classic_") ? "classic" : "none"))}</div>`;
    } else {
      // Hoechste Schwierigkeit mit mindestens einem Kill
      const hoechste = sensoren
        .slice()
        .reverse()
        .find((x) => parseFloat(x.e.state) > 0);
      zusatz = hoechste ? `${this._t("highest")}: ${this._t("stufen")[hoechste.stufe]}` : this._t("noBoss");
      const kacheln = auswahl
        .map((s) => sensoren.find((x) => x.stufe === s))
        .filter((x) => x && x.e.attributes?.total_bosses)
        .map((x) => this._kachel(x));
      body = `${kacheln.length ? kacheln.join("") : `<div class="hinweis">${esc(this._t("noRaids"))}</div>`}
        <div class="fuss">${esc(this._fuss(st("boss_killed")))}</div>`;
    }
    const label = [spiel.name, name, zusatz].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:sword-cross"></ha-icon></div>
          <div class="name">${esc(titel)}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _kachel({ stufe, e }) {
    const a = e.attributes || {};
    const besiegt = parseFloat(e.state) || 0;
    const bilder = a.images || {};
    const raids = Object.entries(a.raids || {})
      .map(([raid, text]) => {
        const [n, m] = String(text)
          .split("/")
          .map((v) => parseInt(v, 10));
        const fertig = m > 0 && n >= m;
        const breite = m ? Math.max(0, Math.min(100, (n / m) * 100)) : 0;
        // Bild des Raids (2:1) links neben Name und Balken
        const bild = bilder[raid];
        return `
        <div class="raid${bild ? " mit-bild" : ""}">
          ${bild ? `<img class="bild" src="${esc(bild)}" alt="">` : ""}
          <span class="rname">${esc(raid)}</span>
          <span class="rwert${fertig ? " fertig" : ""}">${esc(text)}</span>
          <div class="balken" style="grid-column:${bild ? "2" : "1"} / -1"><div style="width:${breite}%;background:${
            fertig ? FARBEN.gruen : FARBEN.akzent
          }"></div></div>
        </div>`;
      })
      .join("");
    return `
      <div class="kachel">
        <div class="kkopf">
          <span class="kname">${esc(this._t("stufen")[stufe])}</span>
          <span class="kwert"><b>${esc(`${besiegt}/${a.total_bosses}`)}</b> ${esc(this._t("bosses"))}</span>
        </div>
        ${raids}
      </div>`;
  }

  _fuss(ev) {
    // Letzter Boss: Ereignis-Entitaet, Zustand = Zeitpunkt des Ereignisses
    const d = new Date(ev?.state);
    if (!ev || Number.isNaN(d.getTime()) || !ev.attributes?.boss) {
      return this._t("noLastBoss");
    }
    const a = ev.attributes;
    const wann = d.toLocaleDateString(this._hass?.locale?.language || "de", { day: "2-digit", month: "2-digit" });
    return `${this._t("lastBoss")}: ${a.boss}${a.difficulty ? ` (${a.difficulty})` : ""} · ${wann}`;
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
  .kachel { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 8px; }
  .kkopf { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
  .kname { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; }
  .kwert { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; }
  .kwert b { font-size: 15px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; }
  .raid { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; align-items: baseline; }
  .raid.mit-bild { grid-template-columns: 52px minmax(0, 1fr) auto; }
  .bild { grid-row: 1 / span 2; align-self: center; width: 52px; height: 26px; object-fit: cover; border-radius: 6px; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .rname { min-width: 0; font-size: 12.5px; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .rwert { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; }
  .rwert.fertig { color: ${FARBEN.gruen}; }
  .balken { height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken > div { height: 100%; border-radius: 5px; }
  .fuss { font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; padding: 0 2px; ${ZWEIZEILIG} }
`;

if (!customElements.get("wow-raid-card")) {
  customElements.define("wow-raid-card", WowRaidCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-raid-card",
    name: "WoW Raids",
    description: "Raid-Fortschritt eines Charakters je Schwierigkeit, mit letztem besiegten Boss.",
  });
}
