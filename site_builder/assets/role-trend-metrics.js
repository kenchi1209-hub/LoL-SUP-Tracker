(function (global) {
  "use strict";

  const METRICS = {
    winrate: { label: "勝率", digits: 1, suffix: "%" },
    kda: { label: "KDA", digits: 2, suffix: "" },
    avgDeaths: { label: "Death", digits: 1, suffix: "" },
    cspm: { label: "CS/m", digits: 2, suffix: "" },
    vspm: { label: "VS/m", digits: 2, suffix: "" },
    damagePerMinute: { label: "Damage/m", digits: 0, suffix: "" },
  };
  const DEFAULT_METRICS = {
    UTILITY: "vspm",
    MIDDLE: "damagePerMinute",
    TOP: "cspm",
    BOTTOM: "damagePerMinute",
    JUNGLE: "damagePerMinute",
  };

  function chronologicalMatches(matches) {
    return matches
      .slice()
      .sort((left, right) => String(left.date).localeCompare(String(right.date)));
  }

  function pointFor(matches, label, metric) {
    const aggregate = global.RoleMetrics.aggregateMatches(matches);
    return {
      label,
      games: aggregate.games,
      wins: aggregate.wins,
      losses: aggregate.losses,
      value: aggregate[metric],
    };
  }

  function movingPoints(matches, metric, size) {
    if (matches.length < size) return [];
    const points = [];
    for (let index = size - 1; index < matches.length; index += 1) {
      const windowMatches = matches.slice(index - size + 1, index + 1);
      points.push(
        pointFor(windowMatches, String(matches[index].date).slice(0, 10), metric)
      );
    }
    return points;
  }

  function monthlyPoints(matches, metric) {
    const months = new Map();
    for (const match of matches) {
      const month = String(match.date).slice(0, 7);
      if (!months.has(month)) months.set(month, []);
      months.get(month).push(match);
    }
    return Array.from(months, ([month, monthMatches]) =>
      pointFor(monthMatches, month, metric)
    );
  }

  function buildTrend(matches, metric, grouping) {
    if (!METRICS[metric]) throw new Error(`Unknown trend metric: ${metric}`);
    const chronological = chronologicalMatches(matches);
    let points;
    if (grouping === "moving5") {
      points = movingPoints(chronological, metric, 5);
    } else if (grouping === "moving10") {
      points = movingPoints(chronological, metric, 10);
    } else if (grouping === "monthly") {
      points = monthlyPoints(chronological, metric);
    } else {
      throw new Error(`Unknown trend grouping: ${grouping}`);
    }
    const overall = global.RoleMetrics.aggregateMatches(chronological)[metric];
    const current = points.length ? points[points.length - 1].value : null;
    return {
      metric,
      grouping,
      points,
      current,
      overall: chronological.length ? overall : null,
      difference:
        current === null || current === undefined ? null : current - overall,
    };
  }

  const api = {
    METRICS,
    DEFAULT_METRICS,
    buildTrend,
    chronologicalMatches,
  };
  global.RoleTrendMetrics = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
