/*
 * Karte "WoW Arsenal" fuer die Integration WoW Charakter.
 *
 * Charakterseite wie im Arsenal des Spiels: Kopf mit Avatar, Name, Titel,
 * Spielversion, Stufe, Volk, Spezialisierung und Klasse; Ganzkoerperbild mit
 * den Ausruestungsplaetzen links, rechts und darunter; Kennzahlen unten.
 * Mit der Maus zeigt ein Platz den Item-Tooltip, Antippen oeffnet ihn.
 *
 * Die Karte findet die Entitaeten des Charakters ueber das Geraet und die
 * Uebersetzungsschluessel der Integration, nicht ueber Entity-IDs; sie
 * funktioniert deshalb mit jeder Sprache und ohne Praefix.
 *
 * Konfiguration:
 *   type: custom:wow-arsenal-card
 *   entity: sensor.<charakter>_level   # eine beliebige Entitaet des Charakters
 *
 * Farben: Nachtblau-Stil, in beiden Modi dunkel; Qualitaetsfarben des Spiels
 * nur als Rand, nie als Schrift.
 */

const FARBEN = {
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

// Plaetze in der Reihenfolge des Arsenals (Uebersetzungsschluessel)
const LINKS = ["head", "neck", "shoulder", "back", "chest", "shirt", "tabard", "wrist"];
const RECHTS = ["hands", "waist", "legs", "feet", "finger_1", "finger_2", "trinket_1", "trinket_2"];

const VERSIONEN = {
  retail: "Retail",
  classic_era: "Classic Era",
  classic_progression: "Classic Progression",
  classic_anniversary: "Classic Anniversary",
  forever: "Forever",
};

const TEXT = {
  de: {
    level: "Stufe",
    itemLevel: "Itemlevel",
    achievements: "Erfolge",
    mounts: "Reittiere",
    honorLevel: "Ehren&shy;stufe",
    honorableKills: "Ehrenhafte Siege",
    raid: "Raid",
    raids: { raid_mythic: "Mythisch", raid_heroic: "Heroisch", raid_normal: "Normal", raid_lfr: "LFR" },
    noItem: "Kein Item angelegt",
    empty: "leer",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
    close: "Schließen",
    copper: "k",
  },
  en: {
    level: "Level",
    itemLevel: "Item level",
    achievements: "Achievements",
    mounts: "Mounts",
    honorLevel: "Honor level",
    honorableKills: "Honorable kills",
    raid: "Raid",
    raids: { raid_mythic: "Mythic", raid_heroic: "Heroic", raid_normal: "Normal", raid_lfr: "LFR" },
    noItem: "No item equipped",
    empty: "empty",
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

function leereSockel(sockets) {
  return (Array.isArray(sockets) ? sockets : []).filter((s) => !s?.gem).length;
}

class WowArsenalCard extends HTMLElement {
  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === "wow_character" && e.translation_key === "level"
    );
    return { entity: entry?.entity_id || "" };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { domain: "sensor", integration: "wow_character" } },
        },
      ],
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    this._config = { ...config };
    this._signatur = undefined;
    this._offen = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._entitaeten = this._finden(hass);
    // Nur neu zeichnen, wenn sich ein Zustand des Charakters geaendert hat.
    const signatur = [
      ...Object.values(this._entitaeten).map((id) => hass.states[id]),
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

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 6, min_columns: 6, rows: "auto" };
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key];
  }

  _finden(hass) {
    // Uebersetzungsschluessel -> Entity-ID, fuer alle Entitaeten am Geraet
    const eintrag = (hass.entities || {})[this._config.entity];
    const result = {};
    if (!eintrag?.device_id) {
      return result;
    }
    for (const e of Object.values(hass.entities || {})) {
      if (e.device_id === eintrag.device_id && e.platform === "wow_character" && e.translation_key) {
        result[e.translation_key] = e.entity_id;
      }
    }
    return result;
  }

  _st(key) {
    const id = this._entitaeten?.[key];
    return id ? this._hass.states[id] : undefined;
  }

  _render() {
    if (!this.shadowRoot || !this._hass) {
      return;
    }
    const lvl = this._st("level");
    let inhalt;
    if (!lvl) {
      inhalt = `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`;
    } else {
      inhalt = `
        ${this._kopf(lvl)}
        <div class="mitte">
          ${LINKS.map((s, i) => this._platz(s, "links", `l${i + 1}`)).join("")}
          ${RECHTS.map((s, i) => this._platz(s, "rechts", `r${i + 1}`)).join("")}
          ${this._platz("main_hand", "rechts", "w1")}
          ${this._platz("off_hand", "links", "w2")}
          <div class="bild" style="grid-area:bild">${this._bild()}</div>
        </div>
        ${this._leiste()}`;
    }
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>${inhalt}<div class="tipp" hidden></div></ha-card>
      ${this._offen ? this._dialog(this._offen) : ""}`;
    this._verbinden();
  }

  _kopf(lvl) {
    const a = lvl.attributes || {};
    const geraet = (this._hass.devices || {})[(this._hass.entities || {})[lvl.entity_id]?.device_id];
    const geraetName = geraet?.name_by_user || geraet?.name || String(a.friendly_name || "");
    const name = geraetName.split(" – ")[0];
    let titel = a.title || "";
    if (titel && name && titel.includes(name)) {
      titel = titel.replace(name, "").replace(/^[\s,]+|[\s,]+$/g, "");
    }
    const m = /^World of Warcraft \((.+)\)$/.exec(geraet?.model || "");
    const spiel = m ? VERSIONEN[m[1]] || m[1] : null;
    const zeile = [
      spiel,
      leer(lvl) ? null : `${this._t("level")} ${lvl.state}`,
      a.race,
      [a.spec, a.class].filter(Boolean).join(" "),
    ]
      .filter(Boolean)
      .map(esc)
      .join(" · ");
    const avatar = this._st("avatar")?.attributes?.entity_picture;
    const ilvl = zahl(this._st("item_level"));
    const mplus = this._st("mythic_rating");
    let wertung = zahl(mplus);
    if (wertung === null) {
      wertung = mplus?.attributes?.api_rating ?? null;
    }
    const pille = (x) => `<span class="pille">${x}</span>`;
    const wert = (v) => `<b>${esc(v)}</b>`;
    const pillen = [
      ilvl === null ? "" : pille(`${wert(Math.round(ilvl))} ${esc(this._t("itemLevel"))}`),
      wertung === null ? "" : pille(`M+ ${wert(Math.round(wertung))}`),
      a.faction ? pille(esc(a.faction)) : "",
      a.realm ? pille(esc(a.realm)) : "",
      a.guild ? pille(esc(a.guild)) : "",
    ].join("");
    return `
      <div class="kopf">
        <div class="avatar">
          <div class="avatar-bild">${avatar ? `<img src="${esc(avatar)}" alt="">` : ""}</div>
          ${a.spec_icon ? `<img class="spec" src="${esc(a.spec_icon)}" alt="" title="${esc(a.spec || "")}">` : ""}
        </div>
        <div class="namen">
          <div class="name">${esc(name)}</div>
          ${titel ? `<div class="titel">${esc(titel)}</div>` : ""}
        </div>
        <div class="zeile">${zeile}</div>
        ${pillen ? `<div class="pillen">${pillen}</div>` : ""}
      </div>`;
  }

  _bild() {
    // Ganzkoerperbild (1600 x 1200, transparent): Die Figur fuellt nur gut die
    // Haelfte der Hoehe, deshalb auf 140 % vergroessert und mittig.
    const bild = this._st("full_body")?.attributes?.entity_picture;
    return bild ? `<img src="${esc(bild)}" alt="">` : "";
  }

  _platz(slot, seite, area) {
    const e = this._st(`equipment_${slot}`);
    const a = e?.attributes || {};
    const belegt = !!a.tooltip;
    const farbe = QUALITAET[a.quality] || FARBEN.rand;
    const punkt = belegt && leereSockel(a.sockets) ? `<span class="punkt"></span>` : "";
    const symbol =
      belegt && a.entity_picture
        ? `<div class="symbol" style="border-color:${farbe}"><img src="${esc(a.entity_picture)}" alt="">${punkt}</div>`
        : belegt
          ? `<div class="symbol" style="border-color:${farbe}">${punkt}</div>`
          : `<div class="symbol leer"></div>`;
    // Zustand ist das Itemlevel; ausserhalb von Retail ohne Itemlevel der Name.
    const stufe = zahl(e);
    const text = `<span class="stufe">${stufe === null ? "" : Math.round(stufe)}</span>`;
    const label = belegt ? a.tooltip.name || a.name || "" : this._t("noItem");
    const waffe = area.startsWith("w") ? ` ${area}` : "";
    return `<button class="platz ${seite}${waffe}" style="grid-area:${area}" data-entity="${esc(e?.entity_id || "")}"
        data-seite="${seite}" ${belegt ? "" : "disabled"} aria-label="${esc(label)}">
      ${seite === "links" ? symbol + text : text + symbol}
    </button>`;
  }

  _leiste() {
    const format = (v) =>
      v === null ? "–" : Math.round(v).toLocaleString(this._hass?.locale?.language || "de");
    const kacheln = [];
    // Raid in der hoechsten Schwierigkeit mit Kills
    const stufen = ["raid_mythic", "raid_heroic", "raid_normal", "raid_lfr"];
    if (stufen.some((k) => this._st(k))) {
      let raid = { wert: "–", name: this._t("raid") };
      for (const k of stufen) {
        const e = this._st(k);
        const n = zahl(e);
        if (n !== null && (n > 0 || k === "raid_lfr")) {
          const gesamt = e.attributes?.total_bosses;
          raid = {
            wert: gesamt ? `${n}/${gesamt}` : `${n}`,
            name: `${this._t("raid")} ${this._t("raids")[k]}`,
          };
          break;
        }
      }
      kacheln.push(raid);
    }
    // Nur Kennzahlen, die der Charakter hat (Classic: keine Raids, Erfolge
    // oder Sammlungen); ohne Ehrenstufe die ehrenhaften Siege.
    const liste = [
      ["achievement_points", "achievements"],
      ["mounts", "mounts"],
      this._st("honor_level") ? ["honor_level", "honorLevel"] : ["honorable_kills", "honorableKills"],
    ];
    for (const [key, text] of liste) {
      const e = this._st(key);
      if (e) {
        kacheln.push({ wert: format(zahl(e)), name: this._t(text) });
      }
    }
    if (!kacheln.length) {
      return "";
    }
    return `<div class="leiste" style="grid-template-columns:repeat(${kacheln.length}, minmax(0,1fr))">
      ${kacheln
        .map(
          (k) => `<div class="kachel"><div class="kachel-wert">${esc(k.wert)}</div>
            <div class="kachel-name">${k.name}</div></div>`
        )
        .join("")}
    </div>`;
  }

  _tooltip(stateObj, optionen = {}) {
    // Item-Tooltip wie im Spiel, aus dem Attribut tooltip der Integration.
    const t = stateObj?.attributes?.tooltip;
    if (!t) {
      return `<div class="sek">${esc(this._t("noItem"))}</div>`;
    }
    const f = FARBEN;
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
        leerIdx[i] ? zeile(s, this._t("empty"), f.amber) : zeile(s, "", f.label)
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
        // Neben den Platz, zur Bildmitte hin; innerhalb der Karte halten.
        const k = card.getBoundingClientRect();
        const r = el.getBoundingClientRect();
        const breite = Math.min(320, k.width - 16);
        tipp.style.width = `${breite}px`;
        let left = el.getAttribute("data-seite") === "links" ? r.right - k.left + 6 : r.left - k.left - breite - 6;
        left = Math.max(8, Math.min(left, k.width - breite - 8));
        tipp.style.left = `${left}px`;
        tipp.style.top = `${Math.max(8, r.top - k.top)}px`;
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

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; position: relative; overflow: visible; padding: 18px; border-radius: 22px;
    border: 1px solid rgba(255, 255, 255, 0.05);
    background: linear-gradient(180deg, #1b2231 0%, #171d29 55%);
    box-shadow: 0 18px 44px -22px rgba(0, 0, 0, 0.7);
    color: ${FARBEN.text}; font-variant-numeric: tabular-nums;
  }
  .hinweis { font-size: 12.5px; line-height: 1.4; color: ${FARBEN.sek}; }
  .kopf { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 0 12px; align-items: center; margin-bottom: 9px; }
  .avatar { position: relative; width: 44px; height: 44px; }
  .avatar-bild { width: 44px; height: 44px; border-radius: 13px; overflow: hidden; background: ${FARBEN.pille}; border: 1px solid ${FARBEN.rand}; box-sizing: border-box; }
  .avatar-bild img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .spec { position: absolute; right: -4px; bottom: -4px; width: 20px; height: 20px; border-radius: 50%; box-shadow: 0 0 0 2px ${FARBEN.huelle}; }
  .namen { min-width: 0; }
  .name { font-size: 17px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; color: ${FARBEN.titel}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .titel, .zeile { overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance; font-size: 12.5px; line-height: 1.3; }
  .titel { color: ${FARBEN.label}; }
  .zeile { grid-column: 1 / -1; margin-top: 8px; color: ${FARBEN.sek}; }
  .pillen { grid-column: 1 / -1; margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
  .pille { display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px; border-radius: 10px; background: ${FARBEN.pille}; border: 1px solid ${FARBEN.rand}; font-size: 12px; font-weight: 600; color: ${FARBEN.label}; white-space: nowrap; }
  .pille b { color: ${FARBEN.text}; font-weight: 750; }
  .mitte {
    display: grid; row-gap: 5px; column-gap: 6px;
    grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr) auto;
    grid-template-areas:
      "l1 bild bild r1" "l2 bild bild r2" "l3 bild bild r3" "l4 bild bild r4"
      "l5 bild bild r5" "l6 bild bild r6" "l7 bild bild r7" "l8 bild bild r8"
      ". w1 w2 .";
  }
  .bild { position: relative; overflow: hidden; border-radius: 16px; min-width: 0; min-height: 0; }
  .bild img { position: absolute; left: 50%; top: 50%; height: 140%; width: auto; max-width: none; transform: translate(-50%, -52%); }
  .platz {
    display: flex; align-items: center; gap: 4px; padding: 0; margin: 0; border: none; background: none;
    color: inherit; font: inherit; cursor: pointer; border-radius: 8px;
  }
  .platz[disabled] { cursor: default; }
  .platz.links { justify-self: start; }
  .platz.rechts { justify-self: end; }
  .platz.w1 { justify-self: end; margin-right: 3px; margin-top: 1px; }
  .platz.w2 { justify-self: start; margin-left: 3px; margin-top: 1px; }
  .platz:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
  .symbol { position: relative; flex: none; width: 34px; height: 34px; box-sizing: border-box; border-radius: 8px; border: 2px solid; background: ${FARBEN.kachel}; overflow: hidden; }
  .symbol img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .symbol.leer { border: 1px dashed ${FARBEN.rand}; }
  .punkt { position: absolute; top: 2px; right: 2px; width: 9px; height: 9px; border-radius: 50%; background: ${FARBEN.amber}; box-shadow: 0 0 0 2px ${FARBEN.huelle}; }
  .stufe { min-width: 22px; font-size: 11.5px; font-weight: 650; color: ${FARBEN.label}; }
  .platz.links .stufe { text-align: left; }
  .platz.rechts .stufe { text-align: right; }
  .leiste { display: grid; gap: 6px; margin-top: 9px; }
  .kachel { min-width: 0; padding: 8px 6px; border-radius: 13px; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; text-align: center; }
  .kachel-wert { font-size: 15px; font-weight: 750; color: ${FARBEN.text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kachel-name { margin-top: 2px; font-size: 11.5px; line-height: 1.25; color: ${FARBEN.sek}; overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
  .tipp { position: absolute; z-index: 5; padding: 12px; border-radius: 14px; background: ${FARBEN.erhoeht}; box-shadow: 0 12px 32px -12px rgba(0, 0, 0, 0.8); pointer-events: none; box-sizing: border-box; }
  .tipp .block { padding: 6px 0 0; border: none; border-top: 1px solid ${FARBEN.rand}; border-radius: 0; background: none; }
  .tooltip { display: grid; gap: 6px; text-align: left; font-size: 13px; line-height: 1.35; color: ${FARBEN.text}; overflow-wrap: break-word; }
  .tkopf { display: flex; gap: 10px; align-items: center; }
  .tbild { flex: none; width: 40px; height: 40px; box-sizing: border-box; border-radius: 9px; border: 2px solid; overflow: hidden; }
  .tbild img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .tkopf-text { min-width: 0; display: grid; gap: 4px; }
  .tname { font-size: 15px; font-weight: 700; line-height: 1.25; color: ${FARBEN.titel}; }
  .tqual { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-weight: 600; }
  .qpille { display: inline-flex; padding: 2px 8px; border-radius: 9px; border: 1.5px solid; font-size: 12px; font-weight: 650; color: ${FARBEN.label}; white-space: nowrap; }
  .block { padding: 8px 12px; border-radius: 14px; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; display: grid; gap: 2px; }
  .tz { display: flex; justify-content: space-between; gap: 12px; }
  .tz span:first-child { min-width: 0; }
  .rechts { flex: none; text-align: right; }
  .tbeschr { font-style: italic; color: ${FARBEN.label}; }
  .tfuss { display: grid; gap: 1px; font-size: 12px; color: ${FARBEN.sek}; padding: 0 2px; }
  .sek { color: ${FARBEN.sek}; }
  .overlay { position: fixed; inset: 0; z-index: 999; background: rgba(0, 0, 0, 0.62); display: flex; align-items: center; justify-content: center; padding: 8px; box-sizing: border-box; }
  .dialog { width: min(440px, 100%); max-height: 90vh; overflow: auto; box-sizing: border-box; padding: 12px 14px 14px; border-radius: 22px; background: ${FARBEN.huelle}; color: ${FARBEN.text}; box-shadow: 0 18px 44px -12px rgba(0, 0, 0, 0.8); }
  .dkopf { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .dtitel { font-size: 16px; font-weight: 700; color: ${FARBEN.titel}; }
  .zu { flex: none; width: 32px; height: 32px; border-radius: 50%; border: 1px solid ${FARBEN.rand}; background: ${FARBEN.pille}; color: ${FARBEN.label}; font-size: 14px; cursor: pointer; }
`;

if (!customElements.get("wow-arsenal-card")) {
  customElements.define("wow-arsenal-card", WowArsenalCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-arsenal-card",
    name: "WoW Arsenal",
    description: "Charakterseite wie im Arsenal: Ausrüstung mit Tooltips, Kennzahlen.",
  });
}
