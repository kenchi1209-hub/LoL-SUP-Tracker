(function (global) {
  "use strict";

  function numberValue(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function aggregateMatches(matches) {
    const games = matches.length;
    if (!games) {
      return {
        games: 0,
        wins: 0,
        losses: 0,
        winrate: null,
        avgKills: null,
        avgDeaths: null,
        avgAssists: null,
        kda: null,
        cspm: null,
        vspm: null,
        avgDurationSeconds: null,
      };
    }

    const totals = matches.reduce(
      (result, match) => {
        result.wins += match.win ? 1 : 0;
        result.kills += numberValue(match.kills);
        result.deaths += numberValue(match.deaths);
        result.assists += numberValue(match.assists);
        result.cs += numberValue(match.cs);
        result.visionScore += numberValue(match.vision_score);
        result.durationSeconds += numberValue(match.game_duration_seconds);
        return result;
      },
      {
        wins: 0,
        kills: 0,
        deaths: 0,
        assists: 0,
        cs: 0,
        visionScore: 0,
        durationSeconds: 0,
      }
    );
    const totalMinutes = totals.durationSeconds / 60;

    return {
      games,
      wins: totals.wins,
      losses: games - totals.wins,
      winrate: (totals.wins / games) * 100,
      avgKills: totals.kills / games,
      avgDeaths: totals.deaths / games,
      avgAssists: totals.assists / games,
      kda: (totals.kills + totals.assists) / Math.max(totals.deaths, 1),
      cspm: totalMinutes ? totals.cs / totalMinutes : 0,
      vspm: totalMinutes ? totals.visionScore / totalMinutes : 0,
      avgDurationSeconds: totals.durationSeconds / games,
    };
  }

  function formatDecimal(value, digits) {
    const factor = 10 ** digits;
    const scaled = numberValue(value) * factor;
    const lower = Math.floor(scaled);
    const fraction = scaled - lower;
    let rounded;
    if (Math.abs(fraction - 0.5) < 1e-9) {
      rounded = lower % 2 === 0 ? lower : lower + 1;
    } else {
      rounded = Math.round(scaled);
    }
    return (rounded / factor).toFixed(digits);
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return "-";
    const rounded = Math.max(0, Math.round(numberValue(seconds)));
    const minutes = Math.floor(rounded / 60);
    const remainingSeconds = rounded % 60;
    return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
  }

  const api = { aggregateMatches, formatDecimal, formatDuration };
  global.RoleMetrics = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
