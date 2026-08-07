(function (global) {
  "use strict";

  function numberValue(value) {
    return global.SiteUtils.numberValue(value);
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
        avgVisionScore: null,
        avgWardsPlaced: null,
        avgWardsKilled: null,
        avgControlWardsBought: null,
        damagePerMinute: null,
        killParticipation: null,
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
        result.wardsPlaced += numberValue(match.wards_placed);
        result.wardsKilled += numberValue(match.wards_killed);
        result.controlWardsBought += numberValue(match.control_wards_bought);
        result.damageToChampions += numberValue(match.damage_to_champions);
        result.durationSeconds += numberValue(match.game_duration_seconds);
        const teamKills = numberValue(match.team_kills);
        if (teamKills > 0) {
          result.killParticipationTotal +=
            (numberValue(match.kills) + numberValue(match.assists)) / teamKills;
          result.killParticipationGames += 1;
        }
        return result;
      },
      {
        wins: 0,
        kills: 0,
        deaths: 0,
        assists: 0,
        cs: 0,
        visionScore: 0,
        wardsPlaced: 0,
        wardsKilled: 0,
        controlWardsBought: 0,
        damageToChampions: 0,
        durationSeconds: 0,
        killParticipationTotal: 0,
        killParticipationGames: 0,
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
      avgVisionScore: totals.visionScore / games,
      avgWardsPlaced: totals.wardsPlaced / games,
      avgWardsKilled: totals.wardsKilled / games,
      avgControlWardsBought: totals.controlWardsBought / games,
      damagePerMinute: totalMinutes ? totals.damageToChampions / totalMinutes : 0,
      killParticipation: totals.killParticipationGames
        ? (totals.killParticipationTotal / totals.killParticipationGames) * 100
        : null,
      avgDurationSeconds: totals.durationSeconds / games,
    };
  }

  function formatDecimal(value, digits) {
    return global.SiteUtils.formatDecimal(value, digits);
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
