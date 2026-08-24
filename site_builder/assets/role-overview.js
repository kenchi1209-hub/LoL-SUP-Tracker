(function (global) {
  "use strict";

  function metricElement(name) {
    return global.document.querySelector(`[data-overview="${name}"]`);
  }

  function setMetricText(name, value) {
    const element = metricElement(name);
    if (element) element.textContent = value;
  }

  function renderOverview(matches) {
    const metrics = global.RoleMetrics.aggregateMatches(matches);
    setMetricText("games", `${metrics.games}戦`);
    setMetricText("record", `${metrics.wins}勝 ${metrics.losses}敗`);

    const winrate = metricElement("winrate");
    winrate.classList.remove("good", "bad");
    if (!metrics.games) {
      winrate.textContent = "-";
      setMetricText("avg-kda", "-");
      setMetricText("kda", "-");
      setMetricText("cspm", "-");
      setMetricText("vspm", "-");
      setMetricText("duration", "-");
      return metrics;
    }

    winrate.textContent = `${global.RoleMetrics.formatDecimal(metrics.winrate, 1)}%`;
    winrate.classList.add(metrics.winrate >= 50 ? "good" : "bad");
    setMetricText("avg-kda", [
      global.RoleMetrics.formatDecimal(metrics.avgKills, 1),
      global.RoleMetrics.formatDecimal(metrics.avgDeaths, 1),
      global.RoleMetrics.formatDecimal(metrics.avgAssists, 1),
    ].join(" / "));
    setMetricText("kda", global.RoleMetrics.formatDecimal(metrics.kda, 2));
    setMetricText("cspm", global.RoleMetrics.formatDecimal(metrics.cspm, 2));
    setMetricText("vspm", global.RoleMetrics.formatDecimal(metrics.vspm, 2));
    setMetricText(
      "duration",
      global.RoleMetrics.formatDuration(metrics.avgDurationSeconds)
    );
    return metrics;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => {
      renderOverview(event.detail.matches);
    });
  }

  const api = { render: renderOverview };
  global.RoleOverview = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
