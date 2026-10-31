/*
 * Karte "WoW Gilde" fuer die Integration WoW Charakter.
 *
 * Gilde eines Charakters fuer alle Spielversionen:
 *   Kopf       Gildenname, darunter Spielversion, Realm, Fraktion und
 *              Gruendungsjahr
 *   Kacheln    Mitglieder, Anzahl auf der hoechsten Stufe der Liste,
 *              Erfolgspunkte der Gilde (nur, wenn die API sie liefert)
 *   Klassen    Anzahl je Klasse, mit Klassenpunkt
 *   Mitglieder die ersten members (Vorgabe 5) nach Rang, mit "dein Charakter"
 *              bei Charakteren, die in Home Assistant eingerichtet sind
 *   Aktivitaet die neuesten activities (Vorgabe 3) Bosskills und Erfolge
 * Abschnitte ohne Daten fallen weg; 0 blendet Mitglieder bzw. Aktivitaet aus.
 * Rangnamen liefert die API nicht: Rang 0 ist im Spiel immer die
 * Gildenleitung und heisst hier "Gildenmeister", sonst "Rang N".
 * Ohne Gilde legt die Integration keinen Sensor an; die Karte nennt das.
 *
 * Die Karte findet den Sensor "Gilde" ueber das Geraet des Charakters und den
 * Uebersetzungsschluessel guild. Die Klassenfarben haengen an der Klassen-ID
 * (class_id), nicht am Namen; sie stimmen deshalb in jeder Sprache.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-guild-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *   members: 5                         # optional, 0 blendet aus
 *   activities: 3                      # optional, 0 blendet aus
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-gilde-karte.yaml; ohne das Theme in beiden Modi dunkel. Klassenpunkte
 * in den WoW-Klassenfarben (DESIGN.md, Sonderfarben), immer neben dem
 * Klassennamen als Text; Rand halb Farbe, halb Text, damit auch der
 * Priester-Punkt auf heller Huelle sichtbar bleibt.
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

// WoW-Klassenfarben nach Klassen-ID der API (playable-class); Werte wie in
// wow-gilde-karte.yaml, Priester (im Spiel Weiss) nimmt #f2f5f8. IDs live
// belegt: 1, 2, 5, 7, 8, 9, 11; 3 aus den Testdaten; uebrige laut
// warcraft.wiki.gg/wiki/ClassId.
const KLASSEN = {
  1: "#c69b6d", // Krieger
  2: "#f48cba", // Paladin
  3: "#aad372", // Jaeger
  4: "#fff468", // Schurke
  5: "#f2f5f8", // Priester
  6: "#c41e3a", // Todesritter
  7: "#0070dd", // Schamane
  8: "#3fc7eb", // Magier
  9: "#8788ee", // Hexenmeister
  10: "#00ff98", // Moench
  11: "#ff7c0a", // Druide
  12: "#a330c9", // Daemonenjaeger
  13: "#33937f", // Rufer
};

const MITGLIEDER = 5;
const AKTIVITAETEN = 3;

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
    title: "Gilde",
    since: (j) => `seit ${j}`,
    members: "Mitglieder",
    onLevel: (n) => `auf Stufe ${n}`,
    achievementPoints: "Erfolgs&shy;punkte",
    classes: "Klassen",
    unknownClass: "Unbekannt",
    byRank: "Mitglieder nach Rang",
    guildMaster: "Gildenmeister",
    rank: (n) => `Rang ${n}`,
    level: "Stufe",
    yours: "dein Charakter",
    more: (n, lang) => `und ${n.toLocaleString(lang)} weitere`,
    activity: "Aktivität",
    boss: "Boss besiegt",
    achievement: (s) => `Erfolg „${s}“`,
    noGuild: "Dieser Charakter ist in keiner Gilde. Tritt er einer bei, erscheint sie nach dem Neuladen der Integration.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    membersLabel: "Mitglieder in der Liste (leer: 5, 0 blendet aus)",
    activitiesLabel: "Aktivitäten (leer: 3, 0 blendet aus)",
  },
  en: {
    title: "Guild",
    since: (j) => `since ${j}`,
    members: "Members",
    onLevel: (n) => `at level ${n}`,
    achievementPoints: "Achievement points",
    classes: "Classes",
    unknownClass: "Unknown",
    byRank: "Members by rank",
    guildMaster: "Guild master",
    rank: (n) => `Rank ${n}`,
    level: "Level",
    yours: "your character",
    more: (n, lang) => `and ${n.toLocaleString(lang)} more`,
    activity: "Activity",
    boss: "Boss defeated",
    achievement: (s) => `achievement “${s}”`,
    noGuild: "This character is not in a guild. After joining one, it appears once the integration is reloaded.",
    missing: "No entities of the integration “WoW Charakter” for",
    membersLabel: "Members in the list (empty: 5, 0 hides)",
    activitiesLabel: "Activities (empty: 3, 0 hides)",
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

function anzahl(wert, vorgabe) {
  if (wert === undefined || wert === null || wert === "") {
    return vorgabe;
  }
  const n = Number(wert);
  return Number.isNaN(n) ? vorgabe : Math.max(0, n);
}

class WowGuildCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit Gilde
    const entries = Object.values(hass.entities || {});
    const gilde = entries.find((e) => e.platform === "wow_character" && e.translation_key === "guild");
    const level = entries.find(
      (e) =>
        e.platform === "wow_character" &&
        e.translation_key === "level" &&
        (!gilde || e.device_id === gilde.device_id)
    );
    return { entity: level?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl der Charaktere (wow-card-editor.js); optional die Zahl der
    // Mitglieder und Aktivitaeten. Alle Charaktere, weil die Karte ohne Gilde
    // einen Hinweis zeigt.
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({
      name: "entity",
      extra: [
        { name: "members", selector: { number: { min: 0, max: 50, mode: "box" } } },
        { name: "activities", selector: { number: { min: 0, max: 20, mode: "box" } } },
      ],
      labels: {
        members: { de: TEXT.de.membersLabel, en: TEXT.en.membersLabel },
        activities: { de: TEXT.de.activitiesLabel, en: TEXT.en.activitiesLabel },
      },
    });
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
    // Entitaeten des Geraets und eigene Charaktere nur neu suchen, wenn sich
    // Entitaeten oder Geraete geaendert haben; bei Zustandsaenderungen ersetzt
    // das Frontend nur hass.states.
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
    return typeof v === "number" && !Number.isNaN(v)
      ? Math.round(v).toLocaleString(this._hass?.locale?.language || "de")
      : "–";
  }

  _finden(hass) {
    const entities = hass.entities || {};
    const devices = hass.devices || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? devices[device] : undefined;
    this._ids = {};
    // Eigene Charaktere: Geraete mit Level-Sensor, Name "Name – Realm"
    this._eigene = new Set();
    for (const e of Object.values(entities)) {
      if (e.platform !== "wow_character") {
        continue;
      }
      if (e.translation_key === "level" && e.device_id) {
        const g = devices[e.device_id];
        const titel = g?.name || "";
        if (titel.includes(" – ")) {
          this._eigene.add(titel.replace(" – ", "|"));
        }
      }
      if (device && e.device_id === device && ["level", "guild"].includes(e.translation_key)) {
        this._ids[e.translation_key] = e.entity_id;
      }
    }
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const st = (key) => (this._ids[key] ? this._hass.states[this._ids[key]] : undefined);
    const spiel = spielversion(this._device?.model);
    const lvl = st("level");
    const gilde = st("guild");
    const g = gilde?.attributes || {};
    const d = new Date(g.created);
    const seit = g.created && !Number.isNaN(d.getTime()) ? this._t("since")(d.getFullYear()) : null;

    let body;
    if (!lvl) {
      body = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else if (!gilde) {
      body = `<div class="hinweis">${esc(this._t("noGuild"))}</div>`;
    } else {
      body = this._inhalt(gilde, g);
    }
    const titel = g.name || this._t("title");
    const label = [spiel.name, g.realm, g.faction, seit].filter(Boolean).join(" · ");
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:shield-sword"></ha-icon></div>
          <div class="name">${esc(titel)}</div>
          <div class="label">${esc(label)}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
  }

  _punkt(klassenId) {
    // Klassenpunkt: Rand halb Farbe, halb Theme-Text (DESIGN.md)
    const farbe = KLASSEN[klassenId] || FARBEN.sek;
    return `<span class="punkt" style="background:${farbe};border-color:color-mix(in srgb, ${farbe} 50%, ${FARBEN.text})"></span>`;
  }

  _abschnitt(titel, inhalt) {
    return `
      <div class="abschnitt">
        <div class="ueberschrift">${esc(titel)}</div>
        ${inhalt}
      </div>`;
  }

  _inhalt(gilde, g) {
    const lang = this._hass?.locale?.language || "de";
    const mitglieder = Array.isArray(g.members) ? g.members : [];
    const teile = [];

    // Kacheln: Mitglieder, hoechste Stufe der Liste, Erfolgspunkte
    const stufen = mitglieder.map((m) => m.level).filter((l) => typeof l === "number");
    const hoechste = stufen.length ? Math.max(...stufen) : null;
    const kacheln = [[parseFloat(gilde.state), esc(this._t("members"))]];
    if (hoechste !== null) {
      kacheln.push([stufen.filter((l) => l === hoechste).length, esc(this._t("onLevel")(hoechste))]);
    }
    if (typeof g.achievement_points === "number") {
      // Enthaelt &shy; fuer die Silbentrennung; fest im Code
      kacheln.push([g.achievement_points, this._t("achievementPoints")]);
    }
    teile.push(`<div class="kacheln" style="--kacheln:${kacheln.length}">${kacheln
      .map(
        ([wert, name]) => `
      <div class="kachel"><div class="kwert">${esc(this._format(wert))}</div><div class="ktitel">${name}</div></div>`
      )
      .join("")}</div>`);

    // Klassen, die haeufigsten zuerst
    const zaehler = new Map();
    for (const m of mitglieder) {
      const name = m.class || this._t("unknownClass");
      const eintrag = zaehler.get(name) || { name, id: m.class_id, n: 0 };
      eintrag.n += 1;
      zaehler.set(name, eintrag);
    }
    const klassen = [...zaehler.values()].sort((a, b) => b.n - a.n || a.name.localeCompare(b.name, lang));
    if (klassen.length) {
      teile.push(
        this._abschnitt(
          this._t("classes"),
          `<div class="pillen">${klassen
            .map((k) => `<span class="pille">${this._punkt(k.id)}${esc(k.name)} <span class="zahl">${k.n}</span></span>`)
            .join("")}</div>`
        )
      );
    }

    // Mitglieder nach Rang (die Integration sortiert nach Rang und Name)
    const liste = mitglieder.slice(0, anzahl(this._config.members, MITGLIEDER));
    if (liste.length) {
      const zeilen = liste.map((m) => {
        const rang = m.rank === 0 ? this._t("guildMaster") : typeof m.rank === "number" ? this._t("rank")(m.rank) : "";
        const du = this._eigene.has(`${m.name}|${g.realm}`) ? ` <span class="du">${esc(this._t("yours"))}</span>` : "";
        const info = [typeof m.level === "number" ? `${this._t("level")} ${m.level}` : null, m.class]
          .filter(Boolean)
          .map(esc)
          .join(" · ");
        return `
          <div class="mitglied">
            ${this._punkt(m.class_id)}
            <span class="mname">${esc(m.name)}${du}</span>
            <span class="rang">${esc(rang)}</span>
            <span></span>
            <span class="minfo">${info}</span>
          </div>`;
      });
      const rest = mitglieder.length - liste.length;
      if (rest > 0) {
        zeilen.push(`<div class="rest">${esc(this._t("more")(rest, lang))}</div>`);
      }
      teile.push(this._abschnitt(this._t("byRank"), zeilen.join("")));
    }

    // Aktivitaet: Bosskills und Erfolge (neueste zuerst, von der Integration)
    const tag = (iso) => {
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(lang, { day: "2-digit", month: "2-digit" });
    };
    const aktiv = (Array.isArray(g.activities) ? g.activities : [])
      .map((a) => ({
        text: a.boss
          ? `${this._t("boss")}: ${a.boss}${a.difficulty ? ` · ${a.difficulty}` : ""}`
          : a.achievement
            ? `${a.character ? `${a.character}: ` : ""}${this._t("achievement")(a.achievement)}`
            : null,
        tag: tag(a.timestamp),
      }))
      .filter((a) => a.text)
      .slice(0, anzahl(this._config.activities, AKTIVITAETEN));
    if (aktiv.length) {
      teile.push(
        this._abschnitt(
          this._t("activity"),
          aktiv
            .map((a) => `<div class="aktiv"><span class="atext">${esc(a.text)}</span><span class="atag">${esc(a.tag)}</span></div>`)
            .join("")
        )
      );
    }
    return teile.join("");
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
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; padding: 0 2px; }
  .kacheln { display: grid; grid-template-columns: repeat(var(--kacheln), minmax(0, 1fr)); gap: 6px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 13px; padding: 8px 4px; text-align: center; }
  .kwert { font-size: 16px; font-weight: 750; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ktitel { margin-top: 2px; font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .abschnitt { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 9px; }
  .ueberschrift { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: ${FARBEN.sek}; }
  .punkt { flex: none; display: inline-block; width: 8px; height: 8px; box-sizing: border-box; border-radius: 50%; border: 1px solid; }
  .pillen { display: flex; flex-wrap: wrap; gap: 6px; }
  .pille { display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; border-radius: 9px; background: ${FARBEN.spur}; border: 1px solid ${FARBEN.rand}; font-size: 12px; color: ${FARBEN.label}; white-space: nowrap; }
  .zahl { font-variant-numeric: tabular-nums; }
  .mitglied { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 1px 8px; align-items: center; }
  .mname { min-width: 0; font-size: 13px; font-weight: 700; line-height: 1.3; color: ${FARBEN.text}; ${ZWEIZEILIG} }
  .du {
    margin-left: 4px; padding: 1px 6px; border-radius: 7px; font-size: 11px; font-weight: 600; color: ${FARBEN.akzent}; white-space: nowrap;
    background: color-mix(in srgb, ${FARBEN.akzent} 12%, transparent);
    border: 1px solid color-mix(in srgb, ${FARBEN.akzent} 24%, transparent);
  }
  .rang { font-size: 12px; color: ${FARBEN.sek}; white-space: nowrap; }
  .minfo { grid-column: 2 / -1; font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; }
  .rest { font-size: 12px; color: ${FARBEN.sek}; }
  .aktiv { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: baseline; }
  .atext { min-width: 0; font-size: 12.5px; line-height: 1.3; color: ${FARBEN.label}; ${ZWEIZEILIG} }
  .atag { font-size: 12px; color: ${FARBEN.sek}; font-variant-numeric: tabular-nums; white-space: nowrap; }
`;

if (!customElements.get("wow-guild-card")) {
  customElements.define("wow-guild-card", WowGuildCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-guild-card",
    name: "WoW Gilde",
    description: "Gilde eines Charakters: Mitglieder, Klassen, Ränge und Aktivität.",
  });
}
