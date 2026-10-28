/*
 * Karte "WoW Talentbaum" fuer die Integration WoW Charakter.
 *
 * Zeichnet Klassen-, Spezialisierungs- und Heldenbaum aus den Attributen des
 * Sensors "Talentbaum" (class_nodes, spec_nodes, hero_nodes, gates). Lage,
 * Raenge, Wahl, Pfeile und Schwellen kommen aus der Battle.net API; die Karte
 * rechnet nichts dazu.
 *
 * Konfiguration:
 *   type: custom:wow-talent-tree-card
 *   entity: sensor.<charakter>_talentbaum
 *   trees: [class, spec, hero]   # optional, Reihenfolge und Auswahl
 */

const CELL = 56; // Abstand der Knoten in SVG-Einheiten
const ICON = 40; // Kantenlaenge eines Symbols
const PAD = 8; // Rand um den Baum
const LABEL = 46; // Platz rechts fuer die Beschriftung der Schwellen

const TEXT = {
  de: {
    class: "Klasse",
    spec: "Spezialisierung",
    hero: "Heldentalente",
    points: "Punkte",
    choice: "Wahl",
    rank: "Rang",
    notTaken: "nicht vergeben",
    noData: "Keine Talentdaten",
    missing: "Entität nicht gefunden",
    hint: "Talent antippen für Details",
  },
  en: {
    class: "Class",
    spec: "Specialization",
    hero: "Hero talents",
    points: "points",
    choice: "Choice",
    rank: "Rank",
    notTaken: "not taken",
    noData: "No talent data",
    missing: "Entity not found",
    hint: "Tap a talent for details",
  },
};

const TREES = ["class", "spec", "hero"];

function escape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function shownTalent(node) {
  // Gewaehltes Talent; bei nicht vergebenen Wahlknoten das erste.
  const talents = node.talents || [];
  return talents.find((t) => t.id === node.talent) || talents[0] || {};
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .map((part) => part[0] || "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

class WowTalentTreeCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.class_nodes
    );
    return { entity: entity || "" };
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
    const trees = config.trees || TREES;
    if (!Array.isArray(trees) || trees.some((t) => !TREES.includes(t))) {
      throw new Error(`trees: nur ${TREES.join(", ")}`);
    }
    this._config = { ...config, trees };
    this._stateObj = undefined;
    this._selected = undefined;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const stateObj = hass.states[this._config.entity];
    // Nur neu zeichnen, wenn sich der Sensor geaendert hat.
    if (stateObj === this._stateObj) {
      return;
    }
    this._stateObj = stateObj;
    this._render();
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key];
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    const stateObj = this._stateObj;
    let body;
    if (!stateObj) {
      body = `<div class="note">${escape(this._t("missing"))}: ${escape(this._config.entity)}</div>`;
    } else if (!stateObj.attributes.class_nodes) {
      body = `<div class="note">${escape(this._t("noData"))}</div>`;
    } else {
      body = this._renderTrees(stateObj.attributes);
    }
    const title = stateObj
      ? [stateObj.state, stateObj.attributes.hero].filter((v) => v && v !== "unknown").join(" · ")
      : "";
    const name = stateObj?.attributes.friendly_name || "";
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="header">
          <div class="name">${escape(name)}</div>
          <div class="spec">${escape(title)}</div>
        </div>
        ${body}
      </ha-card>`;
    this.shadowRoot.querySelectorAll("[data-node]").forEach((el) => {
      const select = () => {
        const key = el.getAttribute("data-node");
        this._selected = this._selected === key ? undefined : key;
        this._render();
      };
      el.addEventListener("click", select);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          select();
        }
      });
    });
  }

  _renderTrees(attrs) {
    const parts = this._config.trees
      .map((tree) => {
        const nodes = attrs[`${tree}_nodes`] || [];
        if (!nodes.length) {
          return "";
        }
        const gates = (attrs.gates || []).filter((g) => g.tree === tree);
        const label = tree === "hero" && attrs.hero ? attrs.hero : this._t(tree);
        return `
          <div class="tree tree-${tree}">
            <div class="title">${escape(label)} · ${this._spent(nodes)} ${escape(this._t("points"))}</div>
            ${this._renderSvg(tree, nodes, gates)}
            ${this._renderDetails(tree, nodes)}
          </div>`;
      })
      .join("");
    return `<div class="trees">${parts}</div>
      <div class="hint">${escape(this._t("hint"))}</div>`;
  }

  _spent(nodes) {
    // Summe der vergebenen Raenge, wie sie die API nennt.
    return nodes.reduce((sum, n) => sum + (n.rank > 0 ? n.rank : 0), 0);
  }

  _renderSvg(tree, nodes, gates) {
    const rows = nodes.map((n) => n.row);
    const cols = nodes.map((n) => n.col);
    const minRow = Math.min(...rows);
    const maxRow = Math.max(...rows);
    const minCol = Math.min(...cols);
    const maxCol = Math.max(...cols);
    const label = gates.length ? LABEL : 0;
    const width = (maxCol - minCol + 1) * CELL + 2 * PAD + label;
    const height = (maxRow - minRow + 1) * CELL + 2 * PAD;
    const x = (col) => PAD + (col - minCol + 0.5) * CELL;
    const y = (row) => PAD + (row - minRow + 0.5) * CELL;
    const byId = new Map(nodes.map((n) => [n.id, n]));

    const lines = [];
    for (const node of nodes) {
      for (const target of node.unlocks || []) {
        const to = byId.get(target);
        if (!to) {
          continue;
        }
        const active = node.rank > 0 && to.rank > 0;
        const [x1, y1, x2, y2] = [x(node.col), y(node.row), x(to.col), y(to.row)];
        const len = Math.hypot(x2 - x1, y2 - y1) || 1;
        const r = ICON / 2 + 2;
        lines.push(
          `<line class="link${active ? " active" : ""}"
            x1="${x1 + ((x2 - x1) * r) / len}" y1="${y1 + ((y2 - y1) * r) / len}"
            x2="${x2 - ((x2 - x1) * r) / len}" y2="${y2 - ((y2 - y1) * r) / len}"/>`
        );
      }
    }

    const gateMarks = gates
      .filter((g) => g.row > minRow && g.row < maxRow + 1)
      .map((g) => {
        const gy = y(g.row);
        return `<line class="gate" x1="${PAD}" y1="${gy}" x2="${width - PAD}" y2="${gy}"/>
          <text class="gate-label" x="${width - PAD}" y="${gy - 4}" text-anchor="end">${escape(
            g.points
          )} ${escape(this._t("points"))}</text>`;
      });

    const icons = nodes.map((node) => this._renderNode(tree, node, x(node.col), y(node.row)));

    return `<svg viewBox="0 0 ${width} ${height}" style="max-width:${width * 1.4}px"
        role="img" aria-label="${escape(this._t(tree))}">
      <defs>
        <clipPath id="c-${tree}-ACTIVE" clipPathUnits="objectBoundingBox">
          <rect width="1" height="1" rx="0.12"/>
        </clipPath>
        <clipPath id="c-${tree}-PASSIVE" clipPathUnits="objectBoundingBox">
          <circle cx="0.5" cy="0.5" r="0.5"/>
        </clipPath>
        <clipPath id="c-${tree}-CHOICE" clipPathUnits="objectBoundingBox">
          <polygon points="0.3,0 0.7,0 1,0.3 1,0.7 0.7,1 0.3,1 0,0.7 0,0.3"/>
        </clipPath>
        <filter id="grey-${tree}"><feColorMatrix type="saturate" values="0"/></filter>
      </defs>
      ${gateMarks.join("")}
      ${lines.join("")}
      ${icons.join("")}
    </svg>`;
  }

  _renderNode(tree, node, cx, cy) {
    const talent = shownTalent(node);
    const type = ["ACTIVE", "PASSIVE", "CHOICE"].includes(node.type) ? node.type : "ACTIVE";
    const taken = node.rank > 0;
    const full = taken && node.rank >= node.max_rank;
    const key = `${tree}:${node.id}`;
    const left = cx - ICON / 2;
    const top = cy - ICON / 2;
    const state = taken ? (full ? "full" : "partial") : "empty";
    const clip = `url(#c-${tree}-${type})`;
    const picture = talent.icon
      ? `<image href="${escape(talent.icon)}" x="${left}" y="${top}" width="${ICON}"
          height="${ICON}" clip-path="${clip}" ${taken ? "" : `filter="url(#grey-${tree})"`}/>`
      : `<g clip-path="${clip}"><rect class="placeholder" x="${left}" y="${top}"
          width="${ICON}" height="${ICON}"/></g>
         <text class="initials" x="${cx}" y="${cy + 4}" text-anchor="middle">${escape(
           initials(talent.name)
         )}</text>`;
    const outline =
      type === "PASSIVE"
        ? `<circle class="frame ${state}" cx="${cx}" cy="${cy}" r="${ICON / 2}"/>`
        : type === "CHOICE"
          ? `<polygon class="frame ${state}" points="${[
              [0.3, 0], [0.7, 0], [1, 0.3], [1, 0.7], [0.7, 1], [0.3, 1], [0, 0.7], [0, 0.3],
            ]
              .map(([px, py]) => `${left + px * ICON},${top + py * ICON}`)
              .join(" ")}"/>`
          : `<rect class="frame ${state}" x="${left}" y="${top}" width="${ICON}"
              height="${ICON}" rx="${ICON * 0.12}"/>`;
    // Rang zeigen, wenn mehr als einer moeglich ist oder die API mehr meldet.
    const badge =
      node.max_rank > 1 || node.rank > node.max_rank
        ? `<rect class="badge" x="${cx + 4}" y="${cy + ICON / 2 - 9}" width="24" height="13" rx="3"/>
           <text class="badge-text" x="${cx + 16}" y="${cy + ICON / 2 + 1}" text-anchor="middle">${escape(
             `${node.rank}/${node.max_rank}`
           )}</text>`
        : "";
    const selected = this._selected === key ? " selected" : "";
    const label = `${talent.name || ""} ${node.rank}/${node.max_rank}`;
    return `<g class="node${taken ? "" : " dim"}${selected}" data-node="${escape(key)}"
        tabindex="0" role="button" aria-label="${escape(label)}">
      <title>${escape(label)}</title>
      <rect class="hit" x="${left - 4}" y="${top - 4}" width="${ICON + 8}" height="${ICON + 8}"/>
      ${picture}${outline}${badge}
    </g>`;
  }

  _renderDetails(tree, nodes) {
    // Details direkt unter dem Baum des angetippten Knotens.
    const [selectedTree, id] = (this._selected || "").split(":");
    if (selectedTree !== tree) {
      return "";
    }
    const node = nodes.find((n) => String(n.id) === id);
    if (!node) {
      return "";
    }
    const status =
      node.rank > 0
        ? `${this._t("rank")} ${node.rank}/${node.max_rank}`
        : this._t("notTaken");
    const talents = (node.talents || [])
      .map((t) => {
        const chosen = node.talents.length > 1 && t.id === node.talent ? " ✓" : "";
        return `<div class="talent">
          <div class="talent-name">${escape(t.name)}${chosen}</div>
          <div class="talent-desc">${escape(t.description || "")}</div>
        </div>`;
      })
      .join("");
    const kind = node.talents && node.talents.length > 1 ? ` · ${this._t("choice")}` : "";
    return `<div class="details">
      <div class="details-status">${escape(status + kind)}</div>
      ${talents}
    </div>`;
  }
}

const STYLE = `
  ha-card { padding: 12px 12px 8px; }
  .header { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  .name { font-size: 1.1em; font-weight: 500; }
  .spec { color: var(--secondary-text-color); }
  .trees { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
  .tree { flex: 1 1 260px; min-width: 0; }
  .tree-hero { flex: 0 1 220px; }
  .title { font-size: 0.9em; color: var(--secondary-text-color); margin-bottom: 4px; }
  svg { width: 100%; height: auto; display: block; }
  .link { stroke: var(--divider-color, #555); stroke-width: 2.5; }
  .link.active { stroke: #e6b422; }
  .gate { stroke: var(--secondary-text-color); stroke-width: 1; stroke-dasharray: 4 4; opacity: 0.6; }
  .gate-label { fill: var(--secondary-text-color); font-size: 9px; }
  .frame { fill: none; stroke-width: 2.5; }
  .frame.full { stroke: #e6b422; }
  .frame.partial { stroke: #3fbf3f; }
  .frame.empty { stroke: var(--divider-color, #555); }
  .dim image, .dim .placeholder { opacity: 0.45; }
  .placeholder { fill: var(--secondary-background-color, #333); }
  .initials { fill: var(--primary-text-color); font-size: 12px; font-weight: 600; pointer-events: none; }
  .badge { fill: var(--card-background-color, #222); stroke: var(--divider-color, #555); }
  .badge-text { fill: var(--primary-text-color); font-size: 9px; }
  .node { cursor: pointer; outline: none; }
  .hit { fill: transparent; }
  .node:focus-visible .hit, .node.selected .hit { stroke: var(--primary-color); stroke-width: 2; }
  .hint, .note { color: var(--secondary-text-color); font-size: 0.85em; margin-top: 6px; }
  .details { border-top: 1px solid var(--divider-color); margin-top: 8px; padding-top: 8px; }
  .details-status { color: var(--secondary-text-color); font-size: 0.85em; margin-bottom: 4px; }
  .talent + .talent { margin-top: 6px; }
  .talent-name { font-weight: 500; }
  .talent-desc { font-size: 0.9em; }
`;

if (!customElements.get("wow-talent-tree-card")) {
  customElements.define("wow-talent-tree-card", WowTalentTreeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "wow-talent-tree-card",
    name: "WoW Talentbaum",
    description: "Talentbäume eines Charakters aus der Integration WoW Charakter.",
  });
}
