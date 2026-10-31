/*
 * Karte "WoW Spielwelt" fuer die Integration WoW Charakter.
 *
 * Was fuer alle Charaktere einer Region gilt, aus dem Geraet "WoW-Spielwelt":
 *   Kopf     Countdown bis zum woechentlichen Reset und dessen Zeitpunkt
 *   Kacheln  Mythic+-Season ueber die ganze Breite: Name, Season-Woche und
 *            Fortschritt der laufenden Woche als Balken; darunter Preis der
 *            WoW-Marke in Gold und je Realm Server online/offline,
 *            Bevoelkerung und Warteschlange
 *   Verlauf  Preis der WoW-Marke der letzten 7 Tage als Stundenmittel aus dem
 *            Verlauf von Home Assistant (die Standard-Aufbewahrung von 10
 *            Tagen reicht); mit der Maus oder per Tippen Wert und Zeitpunkt
 * Realms: alle Server-Sensoren des Geraets, also jeder Realm, auf dem ein
 * Charakter angelegt ist. Server, Warteschlange und Bevoelkerung eines Realms
 * ordnet die Karte ueber das Attribut realm zu (seit 0.33.9).
 *
 * Season: aus den Attributen des Sensors "Woechentlicher Reset" (season_name,
 * season_start, season_end). Der Kurzname ist der Teil in Klammern am Ende von
 * season_name ("Dungeons auf Mythisch+ (Midnight Saison 2)" -> "Midnight
 * Saison 2"), sonst der ganze Name. Die Season-Woche zaehlt ganze Wochen seit
 * season_start plus 1; der Balken zeigt, wie viel der Woche bis zum Reset
 * vergangen ist. Ohne die Attribute (Classic) faellt die Kachel weg.
 *
 * WoW Classic: Die Spielwelt einer Classic-Version hat keinen woechentlichen
 * Reset und die WoW-Marke nur, wenn die API einen Preis liefert; was fehlt,
 * faellt weg.
 *
 * Konfiguration (im Editor nur die Spielwelt waehlen):
 *   type: custom:wow-world-card
 *   entity: sensor.wow_spielwelt_eu_wow_marke   # eine Entitaet der Spielwelt
 *
 * Farben: Nachtblau-Theme-Variablen mit dunklem Rueckfall wie in
 * wow-spielwelt-karte.yaml, Akzent Rose (Bereich Freizeit). Server online
 * Gruen, offline Rot, Warteschlange Amber (Hinweis); der Zustand steht immer
 * auch als Wort in der Pille. Der Verlauf folgt den Theme-Variablen direkt,
 * auch beim Wechsel des Modus.
 */

const FARBEN = {
  akzent: "var(--nachtblau-rose, #e6a0c4)",
  gruen: "var(--nachtblau-gruen, #a6d49e)",
  amber: "var(--nachtblau-amber, #e6b566)",
  rot: "var(--nachtblau-rot, #f0736a)",
  text: "var(--nachtblau-text, #f2f5f8)",
  label: "var(--nachtblau-label, #b4c0cf)",
  sek: "var(--nachtblau-text-sekundaer, #8794a5)",
  kachel: "var(--nachtblau-unterkachel, rgba(255, 255, 255, 0.028))",
  rand: "var(--nachtblau-unterkachel-rand, rgba(255, 255, 255, 0.06))",
  erhoeht: "var(--nachtblau-flaeche-erhoeht, #222b3c)",
  schatten: "var(--nachtblau-schatten, rgba(0, 0, 0, 0.7))",
};

const STUNDE = 3600000;
const WOCHE = 7 * 86400000;
// Verlauf neu laden: hoechstens alle 5 Minuten bei neuem Preis, sonst alle 30
const NEU_LADEN = 5 * 60000;
const VERALTET = 30 * 60000;

const TEXT = {
  de: {
    title: "Spielwelt",
    resetIn: (rest) => `Reset in ${rest}`,
    resetUnknown: "Reset unbekannt",
    days: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    units: { d: "T", h: "h", m: "min" },
    season: "Mythic+-Season",
    week: (n) => `Woche ${n}`,
    weekDone: (p) => `Woche zu ${p} % vorbei`,
    since: (d) => `seit ${d}`,
    until: (d) => `bis ${d}`,
    token: "WoW-Marke",
    tokenSub: "Preis im Auktionshaus",
    online: "online",
    offline: "offline",
    noData: "keine Daten",
    queue: "Warteschlange",
    noQueue: "keine Warteschlange",
    population: "Bevölkerung",
    populations: { full: "Voll", high: "Hoch", medium: "Mittel", low: "Niedrig", recommended: "Empfohlen" },
    chart: "WoW-Marke · 7 Tage, Stundenmittel",
    loading: "Verlauf wird geladen …",
    noHistory: "Kein Verlauf der letzten 7 Tage.",
    missing: "Keine Entitäten der Integration „WoW Charakter“ zu",
  },
  en: {
    title: "Game world",
    resetIn: (rest) => `Reset in ${rest}`,
    resetUnknown: "Reset unknown",
    days: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    units: { d: "d", h: "h", m: "min" },
    season: "Mythic+ season",
    week: (n) => `week ${n}`,
    weekDone: (p) => `${p} % of the week passed`,
    since: (d) => `since ${d}`,
    until: (d) => `until ${d}`,
    token: "WoW Token",
    tokenSub: "Auction house price",
    online: "online",
    offline: "offline",
    noData: "no data",
    queue: "Queue",
    noQueue: "no queue",
    population: "Population",
    populations: { full: "Full", high: "High", medium: "Medium", low: "Low", recommended: "Recommended" },
    chart: "WoW Token · 7 days, hourly average",
    loading: "Loading history …",
    noHistory: "No history for the last 7 days.",
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

// Leerer Wert ist kein Datum (new Date(null) waere der 01.01.1970)
function zeitpunkt(v) {
  const d = v ? new Date(v) : null;
  return d && !Number.isNaN(d.getTime()) ? d : null;
}

// Stundenmittel von start bis ende; Stunden ohne Wert behalten den letzten
// Wert davor, vor dem ersten Wert bleibt die Stunde leer (null)
export function stundenmittel(punkte, start, ende) {
  const sortiert = [...punkte].sort((a, b) => a.t - b.t);
  const werte = [];
  let i = 0;
  let letzter = null;
  for (let t = start; t < ende; t += STUNDE) {
    while (i < sortiert.length && sortiert[i].t < t) {
      letzter = sortiert[i].v;
      i += 1;
    }
    const drin = [];
    while (i < sortiert.length && sortiert[i].t < t + STUNDE) {
      drin.push(sortiert[i].v);
      letzter = sortiert[i].v;
      i += 1;
    }
    werte.push({ t, v: drin.length ? drin.reduce((a, b) => a + b, 0) / drin.length : letzter });
  }
  return werte;
}

class WowWorldCard extends HTMLElement {
  static getStubConfig(hass) {
    const keys = ["token", "weekly_reset", "realm_status"];
    const entries = Object.values(hass.entities || {}).filter(
      (e) => e.platform === "wow_character" && keys.includes(e.translation_key)
    );
    const entry = keys.map((k) => entries.find((e) => e.translation_key === k)).find(Boolean);
    return { entity: entry?.entity_id || "" };
  }

  static async getConfigElement() {
    // Auswahl der Spielwelten (wow-card-editor.js), mit Version im Pfad
    const { editor } = await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url));
    return editor({ name: "entity", welt: true });
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity fehlt / entity is required");
    }
    this._config = { ...config };
    this._signatur = undefined;
    this._quelle = undefined;
    this._verlauf = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  connectedCallback() {
    // Countdown und Wochenbalken jede Minute, Verlauf alle 30 Minuten
    this._takt = setInterval(() => {
      this._render();
      this._verlaufPruefen();
    }, 60000);
  }

  disconnectedCallback() {
    clearInterval(this._takt);
  }

  set hass(hass) {
    this._hass = hass;
    if (this._quelle !== hass.entities || this._geraete !== hass.devices) {
      this._finden(hass);
      this._quelle = hass.entities;
      this._geraete = hass.devices;
      this._signatur = undefined;
    }
    this._verlaufPruefen();
    const signatur = [...this._alle.map((id) => hass.states[id]), hass.locale?.language];
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
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _lang() {
    return (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
  }

  _locale() {
    return this._hass?.locale?.language || "de";
  }

  _t(key) {
    return (TEXT[this._lang()] || TEXT.en)[key];
  }

  _finden(hass) {
    // Entitaeten der Spielwelt nach Uebersetzungsschluessel; Server,
    // Warteschlange und Bevoelkerung gibt es je Realm
    const entities = hass.entities || {};
    const device = entities[this._config.entity]?.device_id;
    this._device = device ? (hass.devices || {})[device] : undefined;
    this._ids = { realm_status: [], realm_queue: [], realm_population: [] };
    this._alle = [];
    if (!device) {
      return;
    }
    for (const e of Object.values(entities)) {
      if (e.device_id !== device || e.platform !== "wow_character" || !e.translation_key) {
        continue;
      }
      this._alle.push(e.entity_id);
      if (Array.isArray(this._ids[e.translation_key])) {
        this._ids[e.translation_key].push(e.entity_id);
      } else {
        this._ids[e.translation_key] = e.entity_id;
      }
    }
  }

  _st(key) {
    const id = this._ids?.[key];
    return typeof id === "string" ? this._hass.states[id] : undefined;
  }

  _verlaufPruefen() {
    const id = this._ids?.token;
    const marke = id && this._hass?.states[id];
    if (!marke || typeof this._hass.callWS !== "function" || this._laedt) {
      return;
    }
    const v = this._verlauf;
    const alter = v ? Date.now() - v.zeit : Infinity;
    // Neu laden: anderer Sensor, aelter als 30 Minuten oder neuer Preis
    // (dann hoechstens alle 5 Minuten)
    if (!v || v.id !== id || alter > VERALTET || (v.stand !== marke.last_updated && alter > NEU_LADEN)) {
      this._verlaufLaden(id, marke.last_updated);
    }
  }

  async _verlaufLaden(id, stand) {
    this._laedt = true;
    const ende = new Date();
    const start = new Date(ende.getTime() - WOCHE);
    let punkte = [];
    try {
      const antwort = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: ende.toISOString(),
        entity_ids: [id],
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      // Kurzform des Verlaufs (frontend src/data/history.ts,
      // EntityHistoryState): s = Zustand, lu = last_updated, lc = last_changed
      // nur wenn abweichend; Zeit in Sekunden, wie im Frontend lc vor lu
      punkte = (antwort?.[id] || [])
        .map((x) => ({ t: (x.lc || x.lu) * 1000, v: parseFloat(x.s) }))
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v));
    } catch (err) {
      // Ohne Verlauf (z. B. Recorder aus) bleibt der Hinweis
    }
    this._verlauf = { id, stand, zeit: Date.now(), punkte };
    this._laedt = false;
    this._render();
  }

  _datum(d) {
    return `${this._t("days")[d.getDay()]} ${d.toLocaleDateString(this._locale(), {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    })}`;
  }

  _uhr(d) {
    return d.toLocaleTimeString(this._locale(), { hour: "2-digit", minute: "2-digit" });
  }

  _gold(v) {
    return `${Math.round(v).toLocaleString(this._locale())} g`;
  }

  _render() {
    if (!this.shadowRoot || !this._hass || !this._ids) {
      return;
    }
    const geraet = this._device?.name_by_user || this._device?.name || "";
    let titel = geraet.replace(/^WoW[- ]/, "");
    titel = titel ? titel.charAt(0).toUpperCase() + titel.slice(1) : this._t("title");
    const marke = this._st("token");
    const body =
      !marke && !this._ids.realm_status.length && !this._st("weekly_reset")
        ? `<div class="hinweis">${esc(this._t("missing"))} ${esc(this._config.entity)}.</div>`
        : `<div class="kacheln">${this._kacheln(marke)}</div>${marke ? this._chart() : ""}`;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="kopf">
          <div class="symbol"><ha-icon icon="mdi:earth"></ha-icon></div>
          <div class="name">${esc(titel)}</div>
          <div class="label">${esc(this._reset())}</div>
        </div>
        <div class="body">${body}</div>
      </ha-card>`;
    this._verbinden();
  }

  _reset() {
    const e = this._st("weekly_reset");
    // Ohne Sensor (Classic) keine Zeile
    if (!e) {
      return "";
    }
    const d = zeitpunkt(e.state);
    if (!d) {
      return this._t("resetUnknown");
    }
    const u = this._t("units");
    const min = Math.max(0, Math.round((d - Date.now()) / 60000));
    const t = Math.floor(min / 1440);
    const h = Math.floor((min % 1440) / 60);
    const m = min % 60;
    const rest = t >= 1 ? `${t} ${u.d} ${h} ${u.h}` : h >= 1 ? `${h} ${u.h} ${m} ${u.m}` : `${m} ${u.m}`;
    return `${this._t("resetIn")(rest)} · ${this._t("days")[d.getDay()]} ${this._uhr(d)}`;
  }

  _pille(farbe, text) {
    return `<span class="pille" style="color:${farbe};background:color-mix(in srgb, ${farbe} 12%, transparent);border-color:color-mix(in srgb, ${farbe} 24%, transparent)"><span class="ppunkt" style="background:${farbe}"></span>${esc(text)}</span>`;
  }

  _kacheln(marke) {
    const kacheln = [];
    // Mythic+-Season aus den Attributen des Reset-Sensors
    const reset = this._st("weekly_reset");
    const sa = reset?.attributes || {};
    if (sa.season_name || sa.season_start) {
      const start = zeitpunkt(sa.season_start);
      const ende = zeitpunkt(sa.season_end);
      const nr = start ? Math.floor((Date.now() - start) / WOCHE) + 1 : null;
      const voll = String(sa.season_name || (sa.season_id ? `Season ${sa.season_id}` : "Mythic+"));
      const kurz = (voll.match(/\(([^()]+)\)\s*$/) || [])[1] || voll;
      const naechster = zeitpunkt(reset.state);
      const anteil = naechster
        ? Math.round(Math.min(1, Math.max(0, 1 - (naechster - Date.now()) / WOCHE)) * 100)
        : null;
      const zeit = [start ? this._t("since")(this._datum(start)) : "", ende ? this._t("until")(this._datum(ende)) : ""]
        .filter(Boolean)
        .join(" · ");
      kacheln.push(`
        <div class="kachel breit">
          <div class="klein">${esc(this._t("season"))}${nr ? ` · ${esc(this._t("week")(nr))}` : ""}</div>
          <div class="kname">${esc(kurz)}</div>
          ${
            anteil === null
              ? ""
              : `<div class="spur"><div class="balken" style="width:${anteil}%"></div></div>
                 <div class="klein">${esc(this._t("weekDone")(anteil))}</div>`
          }
          ${zeit ? `<div class="klein">${esc(zeit)}</div>` : ""}
        </div>`);
    }
    if (marke) {
      const gold = parseFloat(marke.state);
      kacheln.push(`
        <div class="kachel">
          <div class="klein">${esc(this._t("token"))}</div>
          <div class="preis">${Number.isNaN(gold) ? "–" : esc(this._gold(gold))}</div>
          <div class="klein">${esc(this._t("tokenSub"))}</div>
        </div>`);
    }
    for (const realm of this._realms()) {
      const status =
        realm.server?.state === "on"
          ? this._pille(FARBEN.gruen, this._t("online"))
          : realm.server?.state === "off"
            ? this._pille(FARBEN.rot, this._t("offline"))
            : `<span class="klein">${esc(this._t("noData"))}</span>`;
      const warte =
        realm.schlange?.state === "on"
          ? `<div>${this._pille(FARBEN.amber, this._t("queue"))}</div>`
          : `<div class="klein">${esc(this._t("noQueue"))}</div>`;
      const volk =
        realm.volk && !["unknown", "unavailable", ""].includes(realm.volk.state)
          ? `<div class="klein">${esc(this._t("population"))}: <span class="wert">${esc(this._volkText(realm.volk))}</span></div>`
          : "";
      kacheln.push(`
        <div class="kachel">
          <div class="kname">${esc(realm.name)}</div>
          <div>${status}</div>${volk}${warte}
        </div>`);
    }
    return kacheln.join("");
  }

  // Server, Warteschlange und Bevoelkerung je Realm, nach Name sortiert
  _realms() {
    const realms = new Map();
    const eintrag = (stateObj) => {
      const name = stateObj.attributes?.realm || stateObj.entity_id;
      if (!realms.has(name)) {
        realms.set(name, { name });
      }
      return realms.get(name);
    };
    for (const [key, feld] of [
      ["realm_status", "server"],
      ["realm_queue", "schlange"],
      ["realm_population", "volk"],
    ]) {
      for (const id of this._ids[key]) {
        const s = this._hass.states[id];
        if (s) {
          eintrag(s)[feld] = s;
        }
      }
    }
    return [...realms.values()]
      .filter((r) => r.server)
      .sort((a, b) => a.name.localeCompare(b.name, this._locale()));
  }

  // Bevoelkerung: Zustand ist der Schluessel (full, medium, ...); uebersetzt
  // ihn das Frontend nicht, gilt die eigene Liste, sonst der Rohwert
  _volkText(stateObj) {
    try {
      const t = this._hass.formatEntityState?.(stateObj);
      if (t && t !== stateObj.state) {
        return t;
      }
    } catch (err) {
      // Rohwert
    }
    return this._t("populations")[stateObj.state] || stateObj.state;
  }

  _chart() {
    const kopf = `<div class="ctitel">${esc(this._t("chart"))}</div>`;
    const v = this._verlauf;
    if (!v || v.id !== this._ids.token) {
      return `<div class="chart">${kopf}<div class="hinweis">${esc(this._t("loading"))}</div></div>`;
    }
    const ende = Math.floor(Date.now() / STUNDE) * STUNDE + STUNDE;
    const start = ende - WOCHE - STUNDE;
    const werte = stundenmittel(v.punkte, start, ende);
    const da = werte.filter((w) => w.v !== null);
    if (!da.length) {
      return `<div class="chart">${kopf}<div class="hinweis">${esc(this._t("noHistory"))}</div></div>`;
    }
    this._werte = werte;
    this._bereich = [start, ende];
    let min = Math.min(...da.map((w) => w.v));
    let max = Math.max(...da.map((w) => w.v));
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const puffer = (max - min) * 0.08;
    const unten = min - puffer;
    const oben = max + puffer;
    this._skala = [unten, oben];
    // Pfad in einem Feld 0..1000 x 0..100, gestreckt auf die Breite
    const x = (t) => (((t + STUNDE / 2 - start) / (ende - start)) * 1000).toFixed(1);
    const y = (w) => ((1 - (w - unten) / (oben - unten)) * 100).toFixed(2);
    let pfad = "";
    let neu = true;
    for (const w of werte) {
      if (w.v === null) {
        neu = true;
        continue;
      }
      pfad += `${neu ? "M" : "L"}${x(w.t)},${y(w.v)} `;
      neu = false;
    }
    const linien = [min, (min + max) / 2, max]
      .map((w) => `<line x1="0" x2="1000" y1="${y(w)}" y2="${y(w)}" class="gitter"></line>`)
      .join("");
    const achse = [max, (min + max) / 2, min]
      .map((w) => `<span style="top:${y(w)}%">${esc(Math.round(w).toLocaleString(this._locale()))}</span>`)
      .join("");
    // Tage: Beschriftung je Mitternacht im Bereich
    const tage = [];
    const d = new Date(start);
    d.setHours(24, 0, 0, 0);
    for (; d.getTime() < ende; d.setDate(d.getDate() + 1)) {
      const links = ((d.getTime() - start) / (ende - start)) * 100;
      if (links > 3 && links < 97) {
        tage.push(`<span style="left:${links.toFixed(2)}%">${esc(this._t("days")[d.getDay()])}</span>`);
      }
    }
    return `
      <div class="chart">
        ${kopf}
        <div class="plot">
          <div class="yachse">${achse}</div>
          <div class="flaeche">
            <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
              ${linien}<path d="${pfad.trim()}" class="linie"></path>
            </svg>
            <div class="marker" hidden><span class="mpunkt"></span></div>
            <div class="ctipp" hidden></div>
          </div>
          <div></div>
          <div class="xachse">${tage.join("")}</div>
        </div>
      </div>`;
  }

  _verbinden() {
    const flaeche = this.shadowRoot.querySelector(".flaeche");
    if (!flaeche || !this._werte) {
      return;
    }
    const marker = flaeche.querySelector(".marker");
    const tipp = flaeche.querySelector(".ctipp");
    const zeigen = (ev) => {
      const r = flaeche.getBoundingClientRect();
      const [start, ende] = this._bereich;
      const anteil = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      const i = Math.min(this._werte.length - 1, Math.floor((anteil * (ende - start)) / STUNDE));
      const w = this._werte[i];
      if (!w || w.v === null) {
        marker.hidden = true;
        tipp.hidden = true;
        return;
      }
      const [unten, oben] = this._skala;
      const links = ((w.t + STUNDE / 2 - start) / (ende - start)) * 100;
      marker.hidden = false;
      marker.style.left = `${links}%`;
      marker.querySelector(".mpunkt").style.top = `${(1 - (w.v - unten) / (oben - unten)) * 100}%`;
      const d = new Date(w.t);
      tipp.textContent = `${this._t("days")[d.getDay()]} ${d.toLocaleDateString(this._locale(), {
        day: "2-digit",
        month: "2-digit",
      })} ${this._uhr(d)} · ${this._gold(w.v)}`;
      tipp.hidden = false;
      const breite = tipp.offsetWidth;
      const px = (links / 100) * r.width;
      tipp.style.left = `${Math.max(0, Math.min(px - breite / 2, r.width - breite))}px`;
    };
    flaeche.addEventListener("pointermove", zeigen);
    flaeche.addEventListener("pointerdown", zeigen);
    flaeche.addEventListener("pointerleave", (ev) => {
      if (ev.pointerType === "mouse") {
        marker.hidden = true;
        tipp.hidden = true;
      }
    });
  }
}

const ZWEIZEILIG =
  "overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: balance;";

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; padding: 14px 16px 12px; border-radius: 22px; cursor: default;
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
  .kacheln { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .kachel { min-width: 0; background: ${FARBEN.kachel}; border: 1px solid ${FARBEN.rand}; border-radius: 14px; padding: 10px 12px; display: grid; gap: 5px; align-content: start; }
  .kachel.breit { grid-column: 1 / -1; }
  .klein { font-size: 12px; color: ${FARBEN.sek}; }
  .wert { color: ${FARBEN.label}; }
  .kname { min-width: 0; font-size: 13px; font-weight: 700; line-height: 1.3; color: ${FARBEN.text}; ${ZWEIZEILIG} }
  .preis { font-size: 18px; font-weight: 750; letter-spacing: -0.01em; color: ${FARBEN.text}; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .spur { height: 6px; border-radius: 3px; background: ${FARBEN.rand}; overflow: hidden; }
  .balken { height: 100%; border-radius: 3px; background: ${FARBEN.akzent}; }
  .pille { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 9px; border: 1px solid; font-size: 12px; font-weight: 700; white-space: nowrap; }
  .ppunkt { width: 6px; height: 6px; border-radius: 50%; }
  .chart { display: grid; gap: 6px; padding-top: 4px; min-width: 0; }
  .ctitel { font-size: 12px; color: ${FARBEN.sek}; padding: 0 2px; }
  .plot { display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-rows: 110px 16px; column-gap: 6px; }
  .yachse { position: relative; min-width: 46px; }
  .yachse span { position: absolute; right: 0; transform: translateY(-50%); font-size: 11px; color: ${FARBEN.sek}; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .flaeche { position: relative; min-width: 0; touch-action: pan-y; cursor: crosshair; }
  .flaeche svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
  .gitter { stroke: ${FARBEN.rand}; stroke-width: 1; vector-effect: non-scaling-stroke; }
  .linie { fill: none; stroke: ${FARBEN.akzent}; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
  .xachse { position: relative; }
  .xachse span { position: absolute; top: 2px; transform: translateX(-50%); font-size: 11px; color: ${FARBEN.sek}; white-space: nowrap; }
  .marker { position: absolute; top: 0; bottom: 0; width: 0; border-left: 1px dashed ${FARBEN.sek}; pointer-events: none; }
  .mpunkt { position: absolute; left: -4px; width: 8px; height: 8px; margin-top: -4px; border-radius: 50%; background: ${FARBEN.akzent}; }
  .ctipp {
    position: absolute; top: -6px; transform: translateY(-100%); padding: 4px 8px; border-radius: 8px; pointer-events: none;
    background: ${FARBEN.erhoeht}; border: 1px solid ${FARBEN.rand}; box-shadow: 0 8px 20px -10px ${FARBEN.schatten};
    font-size: 12px; color: ${FARBEN.text}; white-space: nowrap; font-variant-numeric: tabular-nums;
  }
`;

if (!customElements.get("wow-world-card")) {
  customElements.define("wow-world-card", WowWorldCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-world-card",
    name: "WoW Spielwelt",
    description: "Spielwelt einer Region: Reset, Mythic+-Season, WoW-Marke mit Verlauf und Server.",
  });
}
