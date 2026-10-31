/*
 * Editor "Charakter auswaehlen" fuer die Karten der Integration WoW Charakter.
 *
 * Statt aller Sensoren der Integration bietet er nur die Charaktere an
 * ("Name – Realm · Spielversion"). Gespeichert wird wie bisher eine Entitaet
 * des Charakters, der Level-Sensor; die Karten finden die uebrigen
 * Entitaeten ueber dessen Geraet. Steht in der Konfiguration eine andere
 * Entitaet des Charakters (z. B. aus einer aelteren Version), zeigt der
 * Editor trotzdem den passenden Charakter.
 *
 * Die Karten laden diese Datei in getConfigElement() selbst nach und setzen
 * die Optionen des Editors:
 *   name      Schluessel in der Konfiguration ("entity" oder "entities")
 *   multiple  mehrere Charaktere (leer: alle)
 *   require   nur Charaktere mit einer Entitaet dieses Schluessels
 *             (z. B. "talent_tree")
 *   extra     weitere ha-form-Felder, als Liste oder als Funktion der Sprache
 *             ("de", "en", ...) fuer uebersetzte Auswahltexte;
 *             labels: {name: {de, en}}
 */

const TEXT = {
  de: {
    entity: "Charakter",
    entities: "Charaktere (leer: alle)",
    unknown: "nicht gefunden",
    none: "Keine Charaktere der Integration „WoW Charakter“ gefunden.",
  },
  en: {
    entity: "Character",
    entities: "Characters (empty: all)",
    unknown: "not found",
    none: "No characters of the integration “WoW Charakter” found.",
  },
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

// Charaktere: Geraete der Integration mit Level-Sensor, sortiert nach Name
export function charaktere(hass, require) {
  const entities = Object.values(hass?.entities || {});
  const geraete = {};
  for (const e of entities) {
    if (e.platform === "wow_character" && e.device_id && e.translation_key) {
      (geraete[e.device_id] = geraete[e.device_id] || {})[e.translation_key] = e.entity_id;
    }
  }
  return Object.entries(geraete)
    .filter(([, keys]) => keys.level && (!require || keys[require]))
    .map(([id, keys]) => {
      const g = (hass.devices || {})[id] || {};
      const name = g.name_by_user || g.name || keys.level;
      const version = spielversion(g.model);
      return { device: id, entity: keys.level, label: version ? `${name} · ${version}` : name };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

class WowCharacterEditor extends HTMLElement {
  constructor() {
    super();
    this.optionen = { name: "entity" };
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key];
  }

  // Konfigurierte Entitaet -> Level-Sensor desselben Charakters
  _zuLevel(id, liste) {
    const device = (this._hass?.entities || {})[id]?.device_id;
    return liste.find((c) => c.entity === id || (device && c.device === device))?.entity || id;
  }

  _render() {
    if (!this._hass || !this._config) {
      return;
    }
    const o = this.optionen;
    const liste = charaktere(this._hass, o.require);
    const optionen = liste.map((c) => ({ value: c.entity, label: c.label }));
    const werte = o.multiple ? this._config[o.name] || [] : [this._config[o.name]].filter(Boolean);
    const daten = { ...this._config };
    const gezeigt = werte.map((id) => this._zuLevel(id, liste));
    // Unbekannte Entitaet sichtbar lassen statt still zu verwerfen
    for (const id of gezeigt) {
      if (!optionen.some((x) => x.value === id)) {
        optionen.push({ value: id, label: `${id} (${this._t("unknown")})` });
      }
    }
    daten[o.name] = o.multiple ? gezeigt : gezeigt[0];
    const lang = (this._hass.locale?.language || "en").slice(0, 2);
    const extra = typeof o.extra === "function" ? o.extra(lang) : o.extra || [];
    const schema = [
      {
        name: o.name,
        required: !o.multiple,
        selector: { select: { mode: o.multiple ? "list" : "dropdown", multiple: !!o.multiple, options: optionen } },
      },
      ...extra,
    ];
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => this._geaendert(ev.detail.value));
      this.appendChild(this._form);
    }
    if (!liste.length) {
      this._hinweis = this._hinweis || this.insertBefore(document.createElement("p"), this._form);
      this._hinweis.textContent = this._t("none");
    } else if (this._hinweis) {
      this._hinweis.remove();
      this._hinweis = undefined;
    }
    this._form.hass = this._hass;
    this._form.data = daten;
    this._form.schema = schema;
    this._form.computeLabel = (s) => {
      if (s.name === o.name) {
        return this._t(o.multiple ? "entities" : "entity");
      }
      const label = (o.labels || {})[s.name];
      return label ? label[lang] || label.en : undefined;
    };
  }

  _geaendert(value) {
    const config = { ...this._config, ...value };
    // Leere optionale Felder nicht als null speichern
    for (const [k, v] of Object.entries(config)) {
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length && k !== "type")) {
        delete config[k];
      }
    }
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("wow-character-editor")) {
  customElements.define("wow-character-editor", WowCharacterEditor);
}

// ha-form laedt Home Assistant erst mit dem ersten eingebauten Karten-Editor.
// Fehlt es noch, den Editor der Karte "entities" anfordern, der es mitbringt.
async function haFormLaden() {
  if (customElements.get("ha-form")) {
    return;
  }
  try {
    const helpers = await window.loadCardHelpers?.();
    const karte = helpers?.createCardElement({ type: "entities", entities: [] });
    await karte?.constructor?.getConfigElement?.();
  } catch (err) {
    // Ohne ha-form bleibt der Editor leer; YAML-Modus geht weiterhin.
  }
}

// Editor mit Optionen erzeugen. Die Karten importieren diese Datei relativ zu
// sich selbst und mit ihrer Version im Pfad, z. B.
//   await import(new URL(`wow-card-editor.js${new URL(import.meta.url).search}`, import.meta.url))
export async function editor(optionen) {
  await haFormLaden();
  const el = document.createElement("wow-character-editor");
  el.optionen = { name: "entity", ...optionen };
  return el;
}
