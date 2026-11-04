/*
 * Karte "WoW Sammlungen" fuer die Integration WoW Charakter.
 *
 * Sammlungen und Erfolge eines Charakters:
 *   Kacheln     Reittiere, Haustiere, Spielzeuge, Titel; darunter
 *               Erfolgspunkte, Erfolge, Quests (aktiver Titel darunter)
 *   Kategorien  Erfolgspunkte je Kategorie als Balken, die punktstaerksten
 *               zuerst (hoechstens categories, Vorgabe 5, 0 blendet aus)
 *   Statistik   Werte aus dem Statistik-Fenster des Spiels (IDs in
 *               statistics, Vorgabe 107, 60, 349); nur wenn der Sensor
 *               Spielstatistik eingeschaltet ist
 *   Fuss        neuester Erfolg (mit Symbol) und zuletzt gesammeltes
 *               Reittier, Haustier, Spielzeug oder Titel, je seit dem Start
 *               von Home Assistant
 * Kacheln und Abschnitte ohne Sensor fallen weg. WoW Classic: keine
 * Sammlungen; die Karte heisst dann "Erfolge" und zeigt, was die API
 * liefert, sonst einen Hinweis.
 * Unterzeile: Spielversion und Name des Charakters.
 *
 * Die Karte findet die Entitaeten ueber das Geraet des Charakters und die
 * Uebersetzungsschluessel (mounts, pets, toys, titles, achievement_points,
 * achievements, quests_completed, game_statistics, new_achievement,
 * new_collectible), nicht ueber Entity-IDs; sie funktioniert deshalb mit
 * jeder Sprache und ohne Praefix.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-collections-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *   categories: 5                      # optional, 0 blendet aus
 *   statistics: [107, 60, 349]         # optional, Statistik-IDs
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-sammlung-karte.yaml; ohne das Theme in beiden Modi dunkel.
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

const KATEGORIEN = 5;
// 98 (Quests abgeschlossen) fehlt bewusst: Die Kachel Quests zeigt den Sensor
// Abgeschlossene Quests, die Statistik zaehlt anders (live 2.505 statt 2.479).
const STATISTIKEN = [107, 60, 349];

// Entitaeten des Charakters (Uebersetzungsschluessel der Integration)
const SCHLUESSEL = [
  "level",
  "mounts",
  "pets",
  "toys",
  "titles",
  "achievement_points",
  "achievements",
  "quests_completed",
  "game_statistics",
  "new_achievement",
  "new_collectible",
];

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
    title: "Sammlungen & Erfolge",
    classicTitle: "Erfolge",
    mounts: "Reittiere",
    pets: "Haustiere",
    toys: "Spiel&shy;zeuge",
    titles: "Titel",
    achievement_points: "Erfolgs&shy;punkte",
    achievements: "Erfolge",
    quests_completed: "Quests",
    activeTitle: "Aktiver Titel",
    perCategory: "Punkte je Kategorie",
    achievementsCount: "Erfolge",
    statistics: "Statistik",
    newestAchievement: "Neuester Erfolg",
    noAchievement: "Neuester Erfolg: noch keiner seit dem Start von Home Assistant",
    collected: "Zuletzt gesammelt",
    noCollected: "Zuletzt gesammelt: nichts Neues seit dem Start von Home Assistant",
    kinds: { mount: "Reittier", pet: "Haustier", toy: "Spielzeug", title: "Titel" },
    quote: (s) => `„${s}“`,
    classic: "Sammlungen gibt es für WoW Classic nicht, und für diesen Charakter liefert die Classic-API keine Erfolge.",
    none: "Keine Sammlungen und Erfolge gefunden.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    categoriesLabel: "Kategorien (leer: 5, 0 blendet aus)",
    statisticsLabel: "Statistiken (leer: Kreaturen getötet, Tode, Flugrouten)",
  },
  en: {
    title: "Collections & Achievements",
    classicTitle: "Achievements",
    mounts: "Mounts",
    pets: "Pets",
    toys: "Toys",
    titles: "Titles",
    achievement_points: "Achievement points",
    achievements: "Achievements",
    quests_completed: "Quests",
    activeTitle: "Active title",
    perCategory: "Points per category",
    achievementsCount: "achievements",
    statistics: "Statistics",
    newestAchievement: "Newest achievement",
    noAchievement: "Newest achievement: none since Home Assistant started",
    collected: "Last collected",
    noCollected: "Last collected: nothing new since Home Assistant started",
    kinds: { mount: "Mount", pet: "Pet", toy: "Toy", title: "Title" },
    quote: (s) => `“${s}”`,
    classic: "WoW Classic has no collections, and the Classic API returns no achievements for this character.",
    none: "No collections or achievements found.",
    missing: "No entities of the integration “WoW Charakter” for",
    categoriesLabel: "Categories (empty: 5, 0 hides)",
    statisticsLabel: "Statistics (empty: creatures killed, deaths, flight paths)",
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

// Entitaet mit Uebersetzungsschluessel am Geraet einer Entitaet
function amGeraet(hass, entityId, key) {
  const entities = hass?.entities || {};
  const device = entities[entityId]?.device_id;
  if (!device) {
    return undefined;
  }
  return Object.values(entities).find(
    (e) => e.device_id === device && e.platform === "wow_character" && e.translation_key === key
  )?.entity_id;
}

class WowCollectionsCard extends HTMLElement {
  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === "wow_character" && e.translation_key === "level"
    );
    return { entity: entry?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere (wow-card-editor.js); optional die Zahl der
    // Kategorien und die Statistiken des gewaehlten Charakters
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({
      name: "entity",
      extra: (lang, { hass, entity }) => {
        const statistik = hass?.states[amGeraet(hass, entity, "game_statistics")]?.attributes?.statistics || [];
        const optionen = statistik
          .filter((s) => s.id != null)
          .slice()
          .sort((a, b) => String(a.name).localeCompare(String(b.name), lang))
          .map((s) => ({ value: String(s.id), label: `${s.name} (${s.category || s.id})` }));
        return [
          { name: "categories", selector: { number: { min: 0, max: 20, mode: "box" } } },
          { name: "statistics", selector: { select: { multiple: true, mode: "dropdown", options: optionen } } },
        ];
      },
      labels: {
        categories: { de: TEXT.de.categoriesLabel, en: TEXT.en.categoriesLabel },
        statistics: { de: TEXT.de.statisticsLabel, en: TEXT.en.statisticsLabel },
      },
    });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    if (config.statistics !== undefined && !Array.isArray(config.statistics)) {
      throw new Error("statistics muss eine Liste sein / statistics must be a list");
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
    return 9;
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
    return v === null || v === undefined || Number.isNaN(Number(v))
      ? "–"
      : Math.round(Number(v)).toLocaleString(this._hass?.locale?.language || "de");
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
    const classic = spiel.key?.startsWith("classic_");
    const lvl = st("level");
    const name = String(
      g?.name_by_user || g?.name || String(lvl?.attributes?.friendly_name || "").replace(/\s*Level$/, "")
    ).split(" – ")[0];

    let body;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!st("mounts") && !st("achievement_points")) {
      body = `<div class="hinweis">${esc(this._t(classic ? "classic" : "none"))}</div>`;
    } else {
      body = this._inhalt(st);
    }
    const label = [spiel.name, name].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:trophy-variant"></ha-icon></div>
          <div class="name">${esc(this._t(classic ? "classicTitle" : "title"))}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _reihe(st, keys) {
    // Eine Reihe teilt ihre Breite auf die vorhandenen Kacheln auf
    const da = keys.filter((k) => st(k));
    if (!da.length) {
      return "";
    }
    // Die Namen enthalten &shy; fuer die Silbentrennung; sie stehen fest im
    // Code, nicht aus Daten
    return `<div class="reihe" style="--kacheln:${da.length}">${da
      .map(
        (k) => `
      <div class="kachel">
        <div class="kwert">${esc(this._format(zahl(st(k))))}</div>
        <div class="ktitel">${this._t(k)}</div>
      </div>`
      )
      .join("")}</div>`;
  }

  _abschnitt(ueberschrift, inhalt) {
    return `
      <div class="abschnitt">
        <div class="ueberschrift">${esc(ueberschrift)}</div>
        ${inhalt}
      </div>`;
  }

  _inhalt(st) {
    const teile = [
      this._reihe(st, ["mounts", "pets", "toys", "titles"]),
      this._reihe(st, ["achievement_points", "achievements", "quests_completed"]),
    ].filter(Boolean);
    const aktiv = st("titles")?.attributes?.active;
    if (aktiv) {
      teile.push(`<div class="zeile">${esc(this._t("activeTitle"))}: <span class="hell">${esc(aktiv)}</span></div>`);
    }

    // Erfolgspunkte je Kategorie, Balken relativ zur staerksten
    const anzahl = this._config.categories === undefined ? KATEGORIEN : Number(this._config.categories) || 0;
    const kat = (Array.isArray(st("achievements")?.attributes?.categories) ? st("achievements").attributes.categories : [])
      .filter((k) => k.points > 0)
      .sort((a, b) => b.points - a.points)
      .slice(0, Math.max(0, anzahl));
    if (kat.length) {
      const max = kat[0].points;
      teile.push(
        this._abschnitt(
          this._t("perCategory"),
          kat
            .map(
              (k) => `
          <div class="kat">
            <span class="kname">${esc(k.category)}</span>
            <span class="kzahl"><b>${esc(this._format(k.points))}</b> · ${esc(this._format(k.quantity))} ${esc(
              this._t("achievementsCount")
            )}</span>
            <div class="balken"><div style="width:${Math.max(2, (k.points / max) * 100)}%"></div></div>
          </div>`
            )
            .join("")
        )
      );
    }

    // Ausgewaehlte Werte des Statistik-Fensters
    const ids = (this._config.statistics?.length ? this._config.statistics : STATISTIKEN).map(Number);
    const statistik = st("game_statistics")?.attributes?.statistics || [];
    const werte = ids.map((id) => statistik.find((s) => s.id === id)).filter(Boolean);
    if (werte.length) {
      teile.push(
        this._abschnitt(
          this._t("statistics"),
          werte
            .map(
              (s) => `
          <div class="stat"><span class="sname">${esc(s.name)}</span><span class="swert">${esc(
            this._format(s.quantity)
          )}</span></div>`
            )
            .join("")
        )
      );
    }

    // Fusszeilen aus Ereignis-Entitaeten (Zustand = Zeitpunkt)
    const erfolg = st("new_achievement");
    if (erfolg) {
      const tag = this._tag(erfolg);
      teile.push(
        tag && erfolg.attributes?.achievement
          ? this._fuss(`${this._t("newestAchievement")}: ${erfolg.attributes.achievement} · ${tag}`, erfolg.attributes.icon)
          : this._fuss(this._t("noAchievement"))
      );
    }
    const neu = st("new_collectible");
    if (neu) {
      const tag = this._tag(neu);
      const art = this._t("kinds")[neu.attributes?.event_type];
      teile.push(
        tag && art && neu.attributes?.name
          ? this._fuss(`${this._t("collected")}: ${art} ${this._t("quote")(neu.attributes.name)} · ${tag}`)
          : this._fuss(this._t("noCollected"))
      );
    }
    return teile.join("");
  }

  _tag(ev) {
    const d = new Date(ev?.state);
    return Number.isNaN(d.getTime())
      ? null
      : d.toLocaleDateString(this._hass?.locale?.language || "de", { day: "2-digit", month: "2-digit" });
  }

  _fuss(text, bild) {
    return `
      <div class="fuss">
        ${bild ? `<img src="${esc(bild)}" alt="">` : ""}
        <span>${esc(text)}</span>
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
  .reihe { display: grid; grid-template-columns: repeat(var(--kacheln), minmax(0, 1fr)); gap: 6px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 13px; padding: 8px 4px; text-align: center; }
  .kwert { font-size: 16px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ktitel { margin-top: 2px; font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .zeile { font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; padding: 0 2px; ${ZWEIZEILIG} }
  .hell { color: ${FARBEN.label}; }
  .abschnitt { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 9px; }
  .ueberschrift { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: ${FARBEN.sek}; }
  .kat { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; align-items: baseline; }
  .kname, .sname { min-width: 0; font-size: 12.5px; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .kzahl { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .kzahl b { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; }
  .balken { grid-column: 1 / -1; height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken > div { height: 100%; border-radius: 5px; background: ${FARBEN.akzent}; }
  .stat { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: baseline; }
  .swert { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .fuss { display: flex; align-items: center; gap: 8px; padding: 0 2px; }
  .fuss img { flex: none; width: 20px; height: 20px; border-radius: 5px; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .fuss span { min-width: 0; font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
`;

if (!customElements.get("wow-collections-card")) {
  customElements.define("wow-collections-card", WowCollectionsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-collections-card",
    name: "WoW Sammlungen",
    description: "Sammlungen und Erfolge eines Charakters: Reittiere, Haustiere, Kategorien, Statistik.",
  });
}
