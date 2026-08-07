(function (global) {
  "use strict";

  function normalizePatch(value) {
    const match = String(value || "").trim().match(/^(\d+)\.(\d+)/);
    return match ? `${Number(match[1])}.${Number(match[2])}` : "Unknown";
  }

  function patchParts(patch) {
    const match = String(patch).match(/^(\d+)\.(\d+)$/);
    return match ? [Number(match[1]), Number(match[2])] : [-1, -1];
  }

  function comparePatches(left, right) {
    const leftParts = patchParts(left);
    const rightParts = patchParts(right);
    return rightParts[0] - leftParts[0] || rightParts[1] - leftParts[1] ||
      String(left).localeCompare(String(right));
  }

  function topChampions(matches, limit) {
    const champions = new Map();
    matches.forEach((match) => {
      const name = String(match.champion || "").trim();
      if (!name) return;
      const current = champions.get(name) || { name, games: 0, wins: 0 };
      current.games += 1;
      current.wins += match.win ? 1 : 0;
      champions.set(name, current);
    });
    return Array.from(champions.values())
      .map((champion) => ({
        ...champion,
        winrate: (champion.wins / champion.games) * 100,
      }))
      .sort((left, right) =>
        right.games - left.games || right.winrate - left.winrate ||
        left.name.localeCompare(right.name)
      )
      .slice(0, limit === undefined ? 3 : limit);
  }

  function groupMatches(matches) {
    const groups = new Map();
    matches.forEach((match) => {
      const patch = normalizePatch(match.patch || match.gameVersion);
      if (!groups.has(patch)) groups.set(patch, []);
      groups.get(patch).push(match);
    });
    return Array.from(groups.entries())
      .map(([patch, patchMatches]) => {
        const dates = patchMatches
          .map((match) => String(match.date || "").slice(0, 10))
          .filter(Boolean)
          .sort();
        return {
          patch,
          startDate: dates.length ? dates[0] : "",
          endDate: dates.length ? dates[dates.length - 1] : "",
          metrics: global.RoleMetrics.aggregateMatches(patchMatches),
          champions: topChampions(patchMatches, 3),
          matches: patchMatches.slice(),
          reference: patchMatches.length < 5,
        };
      })
      .sort((left, right) => comparePatches(left.patch, right.patch));
  }

  const api = { normalizePatch, comparePatches, topChampions, groupMatches };
  global.RolePatchMetrics = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
