(function (global) {
  "use strict";

  const SUPPORT_METRICS = [
    { key: "avgVisionScore", label: "Vision Score", digits: 1 },
    { key: "vspm", label: "VS/m", digits: 2 },
    { key: "avgWardsPlaced", label: "Ward設置", digits: 1 },
    { key: "avgWardsKilled", label: "Ward破壊", digits: 1 },
    { key: "avgControlWardsBought", label: "Control Ward購入", digits: 1 },
    { key: "avgDeaths", label: "Death", digits: 1 },
    { key: "killParticipation", label: "Kill Participation", digits: 1, suffix: "%" },
  ];
  const LANE_METRICS = [
    { key: "cspm", label: "CS/m", digits: 2 },
    { key: "damagePerMinute", label: "Damage/m", digits: 0 },
    { key: "avgDeaths", label: "Death", digits: 1 },
    { key: "killParticipation", label: "Kill Participation", digits: 1, suffix: "%" },
    { key: "vspm", label: "VS/m", digits: 2 },
  ];
  const ROLE_METRICS = {
    UTILITY: SUPPORT_METRICS,
    MIDDLE: LANE_METRICS,
    TOP: LANE_METRICS,
    BOTTOM: LANE_METRICS,
    JUNGLE: LANE_METRICS,
  };

  function metricValue(metrics, definition) {
    const value = metrics[definition.key];
    if (!metrics.games || value === null || value === undefined) return "-";
    return `${global.RoleMetrics.formatDecimal(value, definition.digits)}` +
      (definition.suffix || "");
  }

  function renderRoleOverview(matches) {
    const section = global.document.querySelector("[data-role-overview]");
    if (!section) return null;
    const definitions = ROLE_METRICS[section.dataset.roleOverview] || [];
    const metrics = global.RoleMetrics.aggregateMatches(matches);
    const cards = global.document.getElementById("role-overview-cards");
    cards.replaceChildren(
      ...definitions.map((definition) => {
        const card = global.document.createElement("div");
        card.className = "card";
        const label = global.document.createElement("div");
        label.className = "stat-label";
        label.textContent = definition.label;
        const value = global.document.createElement("div");
        value.className = "stat-value";
        value.dataset.roleMetric = definition.key;
        value.textContent = metricValue(metrics, definition);
        card.append(label, value);
        return card;
      })
    );
    return metrics;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => {
      renderRoleOverview(event.detail.matches);
    });
  }

  const api = { render: renderRoleOverview };
  global.RoleSpecificOverview = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
