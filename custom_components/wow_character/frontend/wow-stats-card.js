/*
 * Karte "WoW Werte" fuer die Integration WoW Charakter.
 *
 * Werte wie im Charakterfenster des Spiels, dazu ein Blick auf die Ausruestung:
 *   Kopf        Charakterbild mit Symbol der Spezialisierung (ohne Bild die
 *               Icon-Kachel), Spezialisierung und Klasse, darunter
 *               Spielversion, Name und Heldentalente
 *   Kacheln     Leben und Primaerwert (Staerke, Beweglichkeit oder
 *               Intelligenz) als gefuellte Kacheln: Leben im Gruen des
 *               Lebensbalkens, Primaerwert in der Klassenfarbe
 *   Zweitwerte  Krit, Tempo, Meisterschaft, Vielseitigkeit in Prozent; die
 *               Balken stehen im Verhaeltnis zum hoechsten der vier Werte.
 *               Werte ohne Sensor fallen weg (Classic hat z. B. keine
 *               Vielseitigkeit).
 *   Ausruestung Set wie im Item-Tooltip des Arsenals (Teile und Boni), die
 *               Zahl der Teile als Pille: gruen, wenn alle Boni aktiv sind,
 *               Amber bei einem Teil, grau ohne aktiven Bonus; darunter die
 *               Plaetze mit leerem Sockel und die verzauberten Plaetze als
 *               Item-Symbole wie im Arsenal (Tooltip mit der Maus, Antippen
 *               oeffnet ihn).
 * Leere Sockel sind ein Hinweis (Amber); ohne leere Sockel steht "keine" in
 * Gruen. Fehlende Verzauberungen bewertet die Karte nicht: Welche Plaetze
 * verzauberbar sind, liefert die API nicht.
 *
 * Die sechs Werte-Sensoren legt die Integration deaktiviert an; sind sie aus,
 * nennt die Karte den Weg zum Einschalten. Die Karte findet alle Entitaeten
 * ueber das Geraet des Charakters und die Uebersetzungsschluessel, die
 * Klassenfarbe ueber die Klassen-ID (Attribut class_id am Level-Sensor); sie
 * stimmt deshalb in jeder Sprache.
 *
 * Konfiguration (im Editor nur den Charakter waehlen):
 *   type: custom:wow-stats-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-werte-karte.yaml. Leben und Primaerwert: WoW-Sonderfarben
 * (Lebensbalken #00ff00 und Klassenfarben, DESIGN.md "Sonderfarben") als
 * gefuellte Kachel mit fester Schrift, in beiden Modi gleich. Item-Symbole,
 * Tooltip und Fenster wie im Arsenal mit festen dunklen Farben;
 * Qualitaetsfarben nur als Rand, nie als Schrift.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  gruen: "var(--nachtblau-gruen, #a6d49e)",
  amber: "var(--nachtblau-amber, #e6b566)",
  text: "var(--nachtblau-text, #f2f5f8)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
  spur: "var(--nachtblau-neutral-kachel, rgba(255, 255, 255, 0.05))",
  // Ring um das Spec-Symbol, trennt es vom Charakterbild
  ring: "var(--nachtblau-huelle-oben, #1b2231)",
};

// Tooltip und Fenster wie im Arsenal: in beiden Modi dunkel (wow-arsenal-card.js)
const DUNKEL = {
  text: "#f2f5f8",
  titel: "#e7ecf3",
  label: "#b4c0cf",
  sek: "#8794a5",
  gruen: "#a6d49e",
  amber: "#e6b566",
  kachel: "rgba(255, 255, 255, 0.028)",
  rand: "rgba(255, 255, 255, 0.06)",
  pille: "rgba(255, 255, 255, 0.05)",
  huelle: "#1b2231",
  erhoeht: "#222b3c",
};

// Offizielle Qualitaetsfarben des Spiels (Feld quality der API)
const QUALITAET = {
  POOR: "#9d9d9d",
  COMMON: "#f2f5f8",
  UNCOMMON: "#1eff00",
  RARE: "#0070dd",
  EPIC: "#a335ee",
  LEGENDARY: "#ff8000",
  ARTIFACT: "#e6cc80",
  HEIRLOOM: "#00ccff",
  WOW_TOKEN: "#00ccff",
};

// WoW-Sonderfarben (DESIGN.md): Lebensbalken des Spiels und Klassenfarben
// nach Klassen-ID der API, Werte wie in wow-werte-karte.yaml; Priester (im
// Spiel Weiss) nimmt #f2f5f8
const WOW = {
  leben: "#00ff00",
  dunkel: "#10151d",
  hell: "#f2f5f8",
};
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
// Klassen, deren Fuellung helle Schrift braucht (Todesritter, Schamane,
// Daemonenjaeger)
const HELL_SCHRIFT = [6, 7, 12];

const ZWEITWERTE = ["stat_crit", "stat_haste", "stat_mastery", "stat_versatility"];

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
    title: "Charakterwerte",
    health: "Leben",
    primary: "Primärwert",
    stats: { strength: "Stärke", agility: "Beweglichkeit", intellect: "Intelligenz" },
    secondary: "Zweitwerte",
    names: { stat_crit: "Krit", stat_haste: "Tempo", stat_mastery: "Meisterschaft", stat_versatility: "Vielseitigkeit" },
    off: "Die Werte-Sensoren sind aus. Einschalten unter Einstellungen → Geräte & Dienste → WoW Charakter → Charakter → Entitäten.",
    equipment: "Ausrüstung",
    set: "Set",
    noSet: "kein Set angelegt",
    sockets: "Leere Sockel",
    empty: (n) => `${n} leer`,
    none: "keine",
    enchanted: "Verzauberte Plätze",
    noItem: "Kein Item angelegt",
    emptySocket: "leer",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    close: "Schließen",
    copper: "k",
  },
  en: {
    title: "Character stats",
    health: "Health",
    primary: "Primary stat",
    stats: { strength: "Strength", agility: "Agility", intellect: "Intellect" },
    secondary: "Secondary stats",
    names: { stat_crit: "Crit", stat_haste: "Haste", stat_mastery: "Mastery", stat_versatility: "Versatility" },
    off: "The stat sensors are disabled. Enable them under Settings → Devices & services → WoW Charakter → character → Entities.",
    equipment: "Equipment",
    set: "Set",
    noSet: "no set equipped",
    sockets: "Empty sockets",
    empty: (n) => `${n} empty`,
    none: "none",
    enchanted: "Enchanted slots",
    noItem: "No item equipped",
    emptySocket: "empty",
    missing: "No entities of the integration “WoW Charakter” for",
    close: "Close",
    copper: "c",
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

function spielversion(model) {
  const m = /^World of Warcraft(?: \((.+)\)| (.+))?$/.exec(model || "");
  if (!m) {
    return null;
  }
  if (m[1]) {
    return VERSIONEN[m[1]] || m[1];
  }
  return m[2] || VERSIONEN.retail;
}

function leereSockel(sockets) {
  return (Array.isArray(sockets) ? sockets : []).filter((s) => !s?.gem).length;
}

class WowStatsCard extends HTMLElement {
  static getStubConfig(hass) {
    // Level-Sensor des ersten Charakters mit eingeschalteten Werte-Sensoren
    const entries = Object.values(hass.entities || {}).filter((e) => e.platform === "wow_character");
    const werte = entries.find((e) => e.translation_key === "stat_health");
    const level = entries.find(
      (e) => e.translation_key === "level" && (!werte || e.device_id === werte.device_id)
    );
    return { entity: level?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl nur der Charaktere (wow-card-editor.js), mit Version im Pfad.
    // Alle Charaktere, weil die Karte ohne Werte-Sensoren einen Hinweis zeigt.
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({ name: "entity" });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    this._config = { ...config };
    this._signatur = undefined;
    this._offen = undefined;
    this._quelle = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    // Entitaeten des Geraets nur neu suchen, wenn sich Entitaeten oder Geraete
    // geaendert haben; bei Zustandsaenderungen ersetzt das Frontend nur
    // hass.states.
    if (this._quelle !== hass.entities || this._geraete !== hass.devices) {
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

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key];
  }

  _finden(hass) {
    // Uebersetzungsschluessel -> Entity-ID, fuer alle Entitaeten am Geraet
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = {};
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id === device && e.platform === "wow_character" && e.translation_key) {
        this._ids[e.translation_key] = e.entity_id;
      }
    }
  }

  _st(key) {
    const id = this._ids?.[key];
    return id ? this._hass.states[id] : undefined;
  }

  _format(v, stellen = 0) {
    return v.toLocaleString(this._hass?.locale?.language || "de", { maximumFractionDigits: stellen });
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const lvl = this._st("level");
    const body = lvl
      ? `${this._werte(lvl)}${this._ausruestung()}`
      : `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        ${this._kopf(lvl)}
        <div class="body">${body}</div>
        <div class="tipp" hidden></div>
      </ha-card>
      ${this._offen ? this._dialog(this._offen) : ""}`;
    this._verbinden();
  }

  _kopf(lvl) {
    const a = lvl?.attributes || {};
    const spec = this._st("specialization");
    const specName = leer(spec) ? a.spec : spec.state;
    const titel = [specName, a.class].filter(Boolean).join(" ") || this._t("title");
    const geraetName = this._device?.name_by_user || this._device?.name || "";
    const label = [spielversion(this._device?.model), geraetName.split(" – ")[0], spec?.attributes?.hero_talents]
      .filter(Boolean)
      .join(" · ");
    const avatar = this._st("avatar")?.attributes?.entity_picture;
    const bild = avatar
      ? `<div class="avatar">
          <div class="avatar-bild"><img src="${esc(avatar)}" alt=""></div>
          ${a.spec_icon ? `<img class="spec" src="${esc(a.spec_icon)}" alt="" title="${esc(a.spec || "")}">` : ""}
        </div>`
      : `<div class="icon"><ha-icon icon="mdi:account-star"></ha-icon></div>`;
    return `
      <div class="kopf">
        ${bild}
        <div class="name">${esc(titel)}</div>
        <div class="label">${esc(label)}</div>
      </div>`;
  }

  _abschnitt(titel, inhalt) {
    return `
      <div class="abschnitt">
        <div class="ueberschrift">${esc(titel)}</div>
        ${inhalt}
      </div>`;
  }

  _werte(lvl) {
    const leben = zahl(this._st("stat_health"));
    const primaer = this._st("stat_primary");
    const zweit = ZWEITWERTE.filter((k) => this._st(k)).map((k) => ({
      name: this._t("names")[k],
      wert: zahl(this._st(k)),
    }));
    if (leben === null && zahl(primaer) === null && zweit.every((z) => z.wert === null)) {
      return `<div class="hinweis">${esc(this._t("off"))}</div>`;
    }
    // Gefuellte Kachel (DESIGN.md, Bausteine): mit dunkler Schrift Verlauf von
    // aufgehellt zur vollen Farbe, mit heller Schrift von der vollen zur
    // abgedunkelten; Rand halb Fuellung, halb Theme-Text
    const gefuellt = (farbe, schrift) =>
      [
        `background:${
          schrift === WOW.dunkel
            ? `linear-gradient(180deg, color-mix(in srgb, ${farbe} 75%, ${WOW.hell}) 0%, ${farbe} 100%)`
            : `linear-gradient(180deg, color-mix(in srgb, ${farbe} 88%, ${WOW.dunkel}) 0%, color-mix(in srgb, ${farbe} 72%, ${WOW.dunkel}) 100%)`
        }`,
        `border-color:color-mix(in srgb, ${farbe} 50%, ${FARBEN.text})`,
        `box-shadow:0 0 14px -3px color-mix(in srgb, ${farbe} 50%, transparent)`,
        `--schrift:${schrift}`,
      ].join(";");
    const kachel = (wert, titel, stil) => `
      <div class="kachel${stil ? " voll" : ""}"${stil ? ` style="${stil}"` : ""}>
        <div class="kwert">${wert === null ? "–" : esc(this._format(Math.round(wert)))}</div>
        <div class="ktitel">${esc(titel)}</div>
      </div>`;
    const klasse = lvl.attributes?.class_id;
    const kf = KLASSEN[klasse];
    const teile = [
      `<div class="kacheln">
        ${kachel(leben, this._t("health"), leben === null ? "" : gefuellt(WOW.leben, WOW.dunkel))}
        ${kachel(
          zahl(primaer),
          this._t("stats")[primaer?.attributes?.stat] || this._t("primary"),
          !kf || zahl(primaer) === null ? "" : gefuellt(kf, HELL_SCHRIFT.includes(klasse) ? WOW.hell : WOW.dunkel)
        )}
      </div>`,
    ];
    if (zweit.length) {
      const max = Math.max(1, ...zweit.map((z) => z.wert || 0));
      teile.push(
        this._abschnitt(
          this._t("secondary"),
          zweit
            .map(
              (z) => `
            <div class="wert">
              <span class="wname">${esc(z.name)}</span>
              <span class="wzahl">${z.wert === null ? "–" : `${esc(this._format(z.wert, 1))}&thinsp;%`}</span>
              <div class="spur"><div class="balken" style="width:${z.wert ? Math.max(2, (z.wert / max) * 100) : 0}%"></div></div>
            </div>`
            )
            .join("")
        )
      );
    }
    return teile.join("");
  }

  // Getoente Pille (Flaeche 12 %, Rand 24 %) fuer Zahlen im Abschnitt Ausruestung
  _pille(farbe, text) {
    return `<span class="pille" style="color:${farbe};background:color-mix(in srgb, ${farbe} 12%, transparent);border-color:color-mix(in srgb, ${farbe} 24%, transparent)">${esc(text)}</span>`;
  }

  _zeile(titel, wert) {
    return `<div class="zeile"><span class="zname">${titel}</span><span class="zwert">${wert}</span></div>`;
  }

  // Plaetze einer Liste als Item-Symbole; zwei leere Sockel im selben Item
  // zaehlen als ein Platz. Ohne Entitaet (z. B. Classic-Zusatzplatz) nur der
  // Name als Text.
  _plaetze(liste) {
    const gesehen = new Set();
    const karten = [];
    const ohne = [];
    for (const s of Array.isArray(liste) ? liste : []) {
      if (!s?.slot || gesehen.has(s.slot)) {
        continue;
      }
      gesehen.add(s.slot);
      const name = s.slot_name || s.slot;
      const e = this._st(`equipment_${String(s.slot).toLowerCase()}`);
      if (e) {
        karten.push(this._platz(e, name));
      } else {
        ohne.push(name);
      }
    }
    return (
      (karten.length ? `<div class="plaetze">${karten.join("")}</div>` : "") +
      (ohne.length ? `<div class="zusatz">${esc(ohne.join(", "))}</div>` : "")
    );
  }

  _platz(e, name) {
    const a = e.attributes || {};
    const belegt = !!a.tooltip;
    const farbe = QUALITAET[a.quality] || DUNKEL.rand;
    const punkt = belegt && leereSockel(a.sockets) ? `<span class="punkt"></span>` : "";
    const bild = belegt && a.entity_picture ? `<img src="${esc(a.entity_picture)}" alt="">` : "";
    const stufe = zahl(e);
    return `
      <button class="platz" data-entity="${esc(e.entity_id)}" ${belegt ? "" : "disabled"}
          aria-label="${esc(belegt ? a.tooltip.name || a.name || name : this._t("noItem"))}">
        <span class="symbol${belegt ? "" : " leer"}" style="border-color:${belegt ? farbe : ""}">${bild}${punkt}</span>
        <span class="ptext"><span class="pname">${esc(name)}</span>${
          stufe === null ? "" : `<span class="pstufe">${esc(Math.round(stufe))}</span>`
        }</span>
      </button>`;
  }

  _ausruestung() {
    const set = this._st("item_set");
    const sockel = this._st("empty_sockets");
    const verz = this._st("enchantments");
    if (!set && !sockel && !verz) {
      return "";
    }
    const teile = [];
    const s = set?.attributes || {};
    if (set && s.name) {
      // Farbe der Pille: alle Boni aktiv gruen, einige Amber, keiner grau;
      // ohne Boni in den Daten nach der Zahl der Teile
      const n = parseFloat(set.state) || 0;
      const boni = Array.isArray(s.effects) ? s.effects : [];
      const aktiv = boni.filter((b) => b.active).length;
      const farbe = boni.length
        ? aktiv === boni.length
          ? FARBEN.gruen
          : aktiv
            ? FARBEN.amber
            : FARBEN.label
        : n >= s.total
          ? FARBEN.gruen
          : n
            ? FARBEN.amber
            : FARBEN.label;
      const liste = (eintraege, farbe) =>
        eintraege.map((e) => `<div class="eintrag" style="color:${farbe(e)}">${esc(e.name ?? e.text)}</div>`).join("");
      teile.push(`
        <div class="set">
          ${this._zeile(`<b>${esc(s.name)}</b>`, this._pille(farbe, `${set.state}/${s.total ?? "?"}`))}
          ${liste(Array.isArray(s.items) ? s.items : [], (i) => (i.equipped ? FARBEN.text : FARBEN.sek))}
          ${boni.length ? `<div class="boni">${liste(boni, (e) => (e.active ? FARBEN.gruen : FARBEN.sek))}</div>` : ""}
        </div>`);
    } else if (set) {
      teile.push(`<div>${this._zeile(esc(this._t("set")), "–")}<div class="zusatz">${esc(this._t("noSet"))}</div></div>`);
    }
    if (sockel) {
      const n = zahl(sockel) || 0;
      teile.push(`<div class="gruppe">
        ${this._zeile(
          esc(this._t("sockets")),
          n ? this._pille(FARBEN.amber, this._t("empty")(n)) : this._pille(FARBEN.gruen, this._t("none"))
        )}
        ${this._plaetze(sockel.attributes?.sockets)}
      </div>`);
    }
    if (verz) {
      const n = zahl(verz);
      teile.push(`<div class="gruppe">
        ${this._zeile(esc(this._t("enchanted")), this._pille(FARBEN.label, n === null ? "–" : String(n)))}
        ${this._plaetze(verz.attributes?.slots)}
      </div>`);
    }
    return this._abschnitt(this._t("equipment"), teile.join(""));
  }

  _tooltip(stateObj, optionen = {}) {
    // Item-Tooltip wie im Spiel, aus dem Attribut tooltip der Integration
    // (wie in wow-arsenal-card.js).
    const t = stateObj?.attributes?.tooltip;
    if (!t) {
      return `<div class="sek">${esc(this._t("noItem"))}</div>`;
    }
    const f = DUNKEL;
    const qf = QUALITAET[t.quality] || f.rand;
    const sockel = Array.isArray(stateObj.attributes.sockets) ? stateObj.attributes.sockets : [];
    // Leere Sockel nur zuordnen, wenn beide Listen gleich lang sind.
    const leerIdx = sockel.length === (t.sockets || []).length ? sockel.map((s) => !s?.gem) : [];
    const zeile = (links, rechts, farbe = f.text) => `
      <div class="tz" style="color:${farbe}"><span>${esc(links)}</span>${
        rechts ? `<span class="rechts">${esc(rechts)}</span>` : ""
      }</div>`;
    const block = (x) => (x.trim() ? `<div class="block">${x}</div>` : "");
    const bild = stateObj.attributes.entity_picture;
    const kopf = `
      <div class="tkopf">
        ${bild ? `<div class="tbild" style="border-color:${qf}"><img src="${esc(bild)}" alt=""></div>` : ""}
        <div class="tkopf-text">
          ${optionen.name ? `<div class="tname">${esc(t.name)}</div>` : ""}
          <div class="tqual"><span class="qpille" style="border-color:${qf}">${esc(
            t.quality_name || t.quality || ""
          )}</span><span>${esc(t.level || "")}</span></div>
          ${t.name_description ? `<div style="color:${f.gruen}">${esc(t.name_description)}</div>` : ""}
        </div>
      </div>`;
    const grund = [
      t.binding ? zeile(t.binding) : "",
      t.unique ? zeile(t.unique) : "",
      t.slot || t.subclass ? zeile(t.slot || "", t.subclass) : "",
      t.damage ? zeile(t.damage, t.speed) : "",
      t.dps ? zeile(t.dps) : "",
      t.armor ? zeile(t.armor) : "",
    ].join("");
    const werte = [
      ...(t.stats || []).map((s) => zeile(s.text, "", s.negated ? f.sek : s.bonus ? f.gruen : f.text)),
      ...(t.enchantments || []).map((e) => zeile(e, "", f.gruen)),
      ...(t.sockets || []).map((s, i) =>
        leerIdx[i] ? zeile(s, this._t("emptySocket"), f.amber) : zeile(s, "", f.label)
      ),
      ...(t.spells || []).map((s) => zeile(s, "", f.gruen)),
    ].join("");
    const set = t.set
      ? [
          `<div style="font-weight:650;color:${f.label}">${esc(t.set.name)}</div>`,
          ...(t.set.items || []).map((i) => zeile(i.name, "", i.equipped ? f.text : f.sek)),
          ...(t.set.effects || []).map(
            (e) => `<div style="margin-top:2px;color:${e.active ? f.gruen : f.sek}">${esc(e.text)}</div>`
          ),
        ].join("")
      : "";
    const p = t.sell_price;
    const preis = p
      ? `${p.header || ""} ${[
          [p.gold, "g"],
          [p.silver, "s"],
          [p.copper, this._t("copper")],
        ]
          .filter(([v]) => v && v !== "0")
          .map(([v, e]) => `${v} ${e}`)
          .join(" ")}`.trim()
      : "";
    const fuss = [[t.durability, ...(t.requirements || [])].filter(Boolean).join(" · "), preis]
      .filter(Boolean)
      .map((s) => `<div>${esc(s)}</div>`)
      .join("");
    return `
      <div class="tooltip">
        ${kopf}${block(grund)}${block(werte)}${block(set)}
        ${t.description ? `<div class="tbeschr">„${esc(t.description)}“</div>` : ""}
        ${fuss ? `<div class="tfuss">${fuss}</div>` : ""}
      </div>`;
  }

  _dialog(entityId) {
    const e = this._hass.states[entityId];
    const name = e?.attributes?.tooltip?.name || "";
    return `
      <div class="overlay" data-schliessen>
        <div class="dialog" role="dialog" aria-modal="true" aria-label="${esc(name)}">
          <div class="dkopf">
            <div class="dtitel">${esc(name)}</div>
            <button class="zu" data-schliessen aria-label="${esc(this._t("close"))}">✕</button>
          </div>
          ${this._tooltip(e)}
        </div>
      </div>`;
  }

  _verbinden() {
    const root = this.shadowRoot;
    const tipp = root.querySelector(".tipp");
    const card = root.querySelector("ha-card");
    root.querySelectorAll(".platz:not([disabled])").forEach((el) => {
      const id = el.getAttribute("data-entity");
      el.addEventListener("pointerenter", (ev) => {
        if (ev.pointerType !== "mouse" || !tipp) {
          return;
        }
        tipp.innerHTML = this._tooltip(this._hass.states[id], { name: true });
        tipp.hidden = false;
        // Neben den Platz, innerhalb der Karte halten.
        const k = card.getBoundingClientRect();
        const r = el.getBoundingClientRect();
        const breite = Math.min(320, k.width - 16);
        tipp.style.width = `${breite}px`;
        let left = r.left - k.left + r.width / 2 < k.width / 2 ? r.right - k.left + 6 : r.left - k.left - breite - 6;
        left = Math.max(8, Math.min(left, k.width - breite - 8));
        tipp.style.left = `${left}px`;
        // Unter den Platz; reicht der Platz in der Karte nicht, darueber.
        const hoehe = tipp.offsetHeight;
        const unten = r.bottom - k.top + 6;
        tipp.style.top = `${unten + hoehe > k.height ? Math.max(8, r.top - k.top - hoehe - 6) : unten}px`;
      });
      el.addEventListener("pointerleave", () => {
        if (tipp) {
          tipp.hidden = true;
        }
      });
      el.addEventListener("click", () => {
        if (tipp) {
          tipp.hidden = true;
        }
        this._offen = id;
        this._render();
      });
    });
    root.querySelectorAll("[data-schliessen]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        if (ev.target === el) {
          this._offen = undefined;
          this._render();
        }
      });
    });
    const dialog = root.querySelector(".dialog");
    if (dialog) {
      root.querySelector(".zu")?.focus();
      dialog.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
          this._offen = undefined;
          this._render();
        }
      });
    }
  }
}

const ZWEIZEILIG =
  "overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance;";

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; position: relative; overflow: visible; padding: 14px 16px 16px; border-radius: 22px; cursor: default;
    border: 1px solid var(--nachtblau-huelle-rand, rgba(255, 255, 255, 0.05));
    background: linear-gradient(180deg, var(--nachtblau-huelle-oben, #1b2231) 0%, var(--nachtblau-huelle-unten, #171d29) 55%);
    box-shadow: 0 18px 44px -22px var(--nachtblau-schatten, rgba(0, 0, 0, 0.7));
    color: ${FARBEN.text}; font-variant-numeric: tabular-nums;
  }
  .kopf { display: grid; grid-template-columns: min-content minmax(0, 1fr); grid-template-areas: "i n" "i l"; }
  .icon, .avatar { grid-area: i; align-self: center; margin-right: 14px; }
  .icon {
    display: flex; align-items: center; justify-content: center;
    width: 44px; height: 44px; box-sizing: border-box; border-radius: 13px;
    background: color-mix(in srgb, ${FARBEN.akzent} 16%, transparent);
    border: 1px solid color-mix(in srgb, ${FARBEN.akzent} 24%, transparent);
    color: ${FARBEN.akzent};
  }
  .icon ha-icon { --mdc-icon-size: 23px; --ha-icon-display: block; }
  .avatar { position: relative; width: 44px; height: 44px; }
  .avatar-bild { width: 44px; height: 44px; border-radius: 13px; overflow: hidden; background: ${FARBEN.spur}; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .avatar-bild img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .spec { position: absolute; right: -4px; bottom: -4px; width: 20px; height: 20px; border-radius: 50%; box-shadow: 0 0 0 2px ${FARBEN.ring}; }
  .name { grid-area: n; align-self: end; font-size: 17px; font-weight: 700; letter-spacing: -0.02em; color: ${FARBEN.text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .label { grid-area: l; align-self: start; margin-top: 1px; font-size: 12.5px; color: ${FARBEN.sek}; ${ZWEIZEILIG} }
  .body { display: grid; gap: 8px; padding-top: 12px; min-width: 0; }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; padding: 0 2px; }
  .kacheln { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 13px; padding: 8px 10px; }
  .kwert { font-size: 16px; font-weight: 750; color: ${FARBEN.text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ktitel { margin-top: 2px; font-size: 11.5px; color: ${FARBEN.sek}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kachel.voll .kwert, .kachel.voll .ktitel { color: var(--schrift); }
  .abschnitt { background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 9px; min-width: 0; }
  .ueberschrift { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: ${FARBEN.sek}; }
  .wert { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; align-items: baseline; }
  .wname { font-size: 12.5px; color: ${FARBEN.label}; }
  .wzahl { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; white-space: nowrap; }
  .spur { grid-column: 1 / -1; height: 6px; border-radius: 5px; background: ${FARBEN.spur}; overflow: hidden; }
  .balken { height: 100%; border-radius: 5px; background: ${FARBEN.akzent}; }
  .zeile { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 10px; align-items: baseline; }
  .zname { font-size: 12.5px; color: ${FARBEN.label}; }
  .zname b { font-weight: 650; }
  .zwert { font-size: 13px; font-weight: 700; color: ${FARBEN.text}; white-space: nowrap; }
  .pille { display: inline-block; padding: 1px 8px; border-radius: 9px; border: 1px solid; }
  .set, .gruppe { display: grid; gap: 2px; min-width: 0; }
  .eintrag { font-size: 12.5px; line-height: 1.35; overflow-wrap: break-word; }
  .boni { margin-top: 4px; display: grid; gap: 4px; }
  .zusatz { font-size: 12px; line-height: 1.3; color: ${FARBEN.sek}; }
  .plaetze { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 8px; margin-top: 6px; }
  .platz {
    display: flex; align-items: center; gap: 8px; min-width: 0; padding: 0; margin: 0; border: none; background: none;
    color: inherit; font: inherit; text-align: left; cursor: pointer; border-radius: 8px;
  }
  .platz[disabled] { cursor: default; }
  .platz:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
  .symbol { position: relative; flex: none; width: 34px; height: 34px; box-sizing: border-box; border-radius: 8px; border: 2px solid; background: ${DUNKEL.kachel}; overflow: hidden; }
  .symbol img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .symbol.leer { border: 1px dashed ${DUNKEL.rand}; }
  .punkt { position: absolute; top: 2px; right: 2px; width: 9px; height: 9px; border-radius: 50%; background: ${DUNKEL.amber}; box-shadow: 0 0 0 2px ${DUNKEL.huelle}; }
  .ptext { display: grid; min-width: 0; }
  .pname { font-size: 12.5px; line-height: 1.25; color: ${FARBEN.label}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pstufe { font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; }
  .tipp { position: absolute; z-index: 5; padding: 12px; border-radius: 14px; background: ${DUNKEL.erhoeht}; box-shadow: 0 12px 32px -12px rgba(0, 0, 0, 0.8); pointer-events: none; box-sizing: border-box; }
  .tipp .block { padding: 6px 0 0; border: none; border-top: 1px solid ${DUNKEL.rand}; border-radius: 0; background: none; }
  .tooltip { display: grid; gap: 6px; text-align: left; font-size: 13px; line-height: 1.35; color: ${DUNKEL.text}; overflow-wrap: break-word; }
  .tkopf { display: flex; gap: 10px; align-items: center; }
  .tbild { flex: none; width: 40px; height: 40px; box-sizing: border-box; border-radius: 9px; border: 2px solid; overflow: hidden; }
  .tbild img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .tkopf-text { min-width: 0; display: grid; gap: 4px; }
  .tname { font-size: 15px; font-weight: 700; line-height: 1.25; color: ${DUNKEL.titel}; }
  .tqual { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-weight: 600; }
  .qpille { display: inline-flex; padding: 2px 8px; border-radius: 9px; border: 1.5px solid; font-size: 12px; font-weight: 650; color: ${DUNKEL.label}; white-space: nowrap; }
  .block { padding: 8px 12px; border-radius: 14px; background: ${DUNKEL.kachel}; border: 1px solid ${DUNKEL.rand}; display: grid; gap: 2px; }
  .tz { display: flex; justify-content: space-between; gap: 12px; }
  .tz span:first-child { min-width: 0; }
  .rechts { flex: none; text-align: right; }
  .tbeschr { font-style: italic; color: ${DUNKEL.label}; }
  .tfuss { display: grid; gap: 1px; font-size: 12px; color: ${DUNKEL.sek}; padding: 0 2px; }
  .sek { color: ${DUNKEL.sek}; }
  .overlay { position: fixed; inset: 0; z-index: 999; background: rgba(0, 0, 0, 0.62); display: flex; align-items: center; justify-content: center; padding: 8px; box-sizing: border-box; }
  .dialog { width: min(440px, 100%); max-height: 90vh; overflow: auto; box-sizing: border-box; padding: 12px 14px 14px; border-radius: 22px; background: ${DUNKEL.huelle}; color: ${DUNKEL.text}; box-shadow: 0 18px 44px -12px rgba(0, 0, 0, 0.8); }
  .dkopf { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .dtitel { font-size: 16px; font-weight: 700; color: ${DUNKEL.titel}; }
  .zu { flex: none; width: 32px; height: 32px; border-radius: 50%; border: 1px solid ${DUNKEL.rand}; background: ${DUNKEL.pille}; color: ${DUNKEL.label}; font-size: 14px; cursor: pointer; }
`;

if (!customElements.get("wow-stats-card")) {
  customElements.define("wow-stats-card", WowStatsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-stats-card",
    name: "WoW Werte",
    description: "Charakterwerte wie im Spiel und Ausrüstungs-Check: Set, leere Sockel, Verzauberungen.",
  });
}
