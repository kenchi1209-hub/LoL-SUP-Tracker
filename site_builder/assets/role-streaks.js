(function (global) {
  "use strict";

  function chronologicalMatches(matches) {
    return matches
      .slice()
      .sort((left, right) => String(left.date).localeCompare(String(right.date)));
  }

  function streakSegments(results) {
    const segments = [];
    for (const win of results) {
      const current = segments[segments.length - 1];
      if (current && current.win === win) {
        current.length += 1;
      } else {
        segments.push({ win, length: 1 });
      }
    }
    return segments;
  }

  function averageLongStreak(segments, win) {
    const lengths = segments
      .filter((segment) => segment.win === win && segment.length >= 2)
      .map((segment) => segment.length);
    if (!lengths.length) return null;
    return lengths.reduce((total, length) => total + length, 0) / lengths.length;
  }

  function afterTwo(results, win) {
    let games = 0;
    let wins = 0;
    for (let index = 2; index < results.length; index += 1) {
      if (results[index - 2] === win && results[index - 1] === win) {
        games += 1;
        wins += results[index] ? 1 : 0;
      }
    }
    return {
      games,
      wins,
      losses: games - wins,
      winrate: games ? (wins / games) * 100 : null,
    };
  }

  function classifyForm(winrate, games) {
    if (games <= 4 || winrate === null) {
      return { label: "データ不足", reference: false, tone: "neutral" };
    }
    let label;
    let tone;
    if (winrate >= 70) {
      label = "絶好調";
      tone = "good";
    } else if (winrate >= 60) {
      label = "好調";
      tone = "good";
    } else if (winrate >= 50) {
      label = "普通";
      tone = "neutral";
    } else if (winrate >= 40) {
      label = "不調";
      tone = "bad";
    } else {
      label = "絶不調";
      tone = "bad";
    }
    return { label, reference: games < 10, tone };
  }

  function analyzeForm(matches) {
    const chronological = chronologicalMatches(matches);
    const results = chronological.map((match) => Boolean(match.win));
    const segments = streakSegments(results);
    const current = segments.length ? segments[segments.length - 1] : null;
    const winSegments = segments.filter((segment) => segment.win);
    const lossSegments = segments.filter((segment) => !segment.win);
    const recent = chronological.slice(-20);
    const recentWins = recent.filter((match) => match.win).length;
    const recentGames = recent.length;
    const recentWinrate = recentGames ? (recentWins / recentGames) * 100 : null;

    return {
      currentStreak: current,
      maxWinStreak: winSegments.length
        ? Math.max(...winSegments.map((segment) => segment.length))
        : null,
      maxLossStreak: lossSegments.length
        ? Math.max(...lossSegments.map((segment) => segment.length))
        : null,
      avgWinStreak: averageLongStreak(segments, true),
      avgLossStreak: averageLongStreak(segments, false),
      afterTwoWins: afterTwo(results, true),
      afterTwoLosses: afterTwo(results, false),
      form: {
        games: recentGames,
        wins: recentWins,
        losses: recentGames - recentWins,
        winrate: recentWinrate,
        classification: classifyForm(recentWinrate, recentGames),
        matches: recent,
      },
    };
  }

  const api = { analyzeForm, classifyForm, streakSegments };
  global.RoleStreaks = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
