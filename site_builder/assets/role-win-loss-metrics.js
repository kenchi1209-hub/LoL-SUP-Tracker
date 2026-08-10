(function (global) {
  "use strict";

  const SUPPORT_METRICS = [
    { key: "kda", label: "K/D/A（KDA）", digits: 2, format: "kdaDetails", direction: "high" },
    { key: "avgDeaths", label: "Death", digits: 1, direction: "low" },
    { key: "vspm", label: "VS/m", digits: 2, direction: "high" },
    { key: "avgVisionScore", label: "Vision Score", digits: 1, direction: "high" },
    { key: "avgWardsPlaced", label: "Ward設置", digits: 1, direction: "high" },
    { key: "avgWardsKilled", label: "Ward破壊", digits: 1, direction: "high" },
    { key: "avgControlWardsBought", label: "Control Ward購入", digits: 1, direction: "high" },
    { key: "cspm", label: "CS/m", digits: 2, direction: "high" },
    { key: "damagePerMinute", label: "Damage/m", digits: 0, direction: "high" },
    { key: "avgDurationSeconds", label: "平均ゲーム時間", format: "duration", direction: "neutral" },
  ];
  const LANE_METRICS = [
    { key: "kda", label: "K/D/A（KDA）", digits: 2, format: "kdaDetails", direction: "high" },
    { key: "avgDeaths", label: "Death", digits: 1, direction: "low" },
    { key: "cspm", label: "CS/m", digits: 2, direction: "high" },
    { key: "damagePerMinute", label: "Damage/m", digits: 0, direction: "high" },
    { key: "killParticipation", label: "Kill Participation", digits: 1, suffix: "%", direction: "high" },
    { key: "vspm", label: "VS/m", digits: 2, direction: "high" },
    { key: "avgDurationSeconds", label: "平均ゲーム時間", format: "duration", direction: "neutral" },
  ];
  const ROLE_METRICS = {
    UTILITY: SUPPORT_METRICS,
    MIDDLE: LANE_METRICS,
    TOP: LANE_METRICS,
    BOTTOM: LANE_METRICS,
    JUNGLE: LANE_METRICS,
  };

  function differenceTone(difference, direction) {
    if (difference === null || direction === "neutral" || difference === 0) {
      return "neutral";
    }
    const desirable = direction === "high" ? difference > 0 : difference < 0;
    return desirable ? "good" : "bad";
  }

  function compareMatches(matches, role) {
    const winMatches = matches.filter((match) => Boolean(match.win));
    const lossMatches = matches.filter((match) => !match.win);
    const wins = global.RoleMetrics.aggregateMatches(winMatches);
    const losses = global.RoleMetrics.aggregateMatches(lossMatches);
    const definitions = ROLE_METRICS[role] || [];
    const rows = definitions.map((definition) => {
      const winValue = wins.games ? wins[definition.key] : null;
      const lossValue = losses.games ? losses[definition.key] : null;
      const difference =
        winValue === null || winValue === undefined ||
        lossValue === null || lossValue === undefined
          ? null
          : winValue - lossValue;
      return {
        definition,
        winValue,
        lossValue,
        winAggregate: wins,
        lossAggregate: losses,
        difference,
        tone: differenceTone(difference, definition.direction),
      };
    });
    return { winGames: wins.games, lossGames: losses.games, rows };
  }

  const api = { ROLE_METRICS, compareMatches, differenceTone };
  global.RoleWinLossMetrics = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
