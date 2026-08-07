(function (global) {
  "use strict";

  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
  const minutes = (match) => number(match.game_duration_seconds) / 60;
  const rate = (value, match) => minutes(match) ? number(value) / minutes(match) : 0;

  const SORTS = {
    date: { label: "日時", value: (match) => String(match.date || "") },
    kda: { label: "KDA", value: (match) => (number(match.kills) + number(match.assists)) / Math.max(number(match.deaths), 1) },
    kills: { label: "Kill", value: (match) => number(match.kills) },
    deaths: { label: "Death", value: (match) => number(match.deaths) },
    assists: { label: "Assist", value: (match) => number(match.assists) },
    cs: { label: "CS", value: (match) => number(match.cs) },
    cspm: { label: "CS/m", value: (match) => rate(match.cs, match) },
    vision: { label: "VS", value: (match) => number(match.vision_score) },
    vspm: { label: "VS/m", value: (match) => rate(match.vision_score, match) },
    damage: { label: "Damage", value: (match) => number(match.damage_to_champions) },
    damagePerMinute: { label: "Damage/m", value: (match) => rate(match.damage_to_champions, match) },
    duration: { label: "試合時間", value: (match) => number(match.game_duration_seconds) },
  };

  function compareValues(left, right) {
    if (typeof left === "string" || typeof right === "string") {
      return String(left).localeCompare(String(right));
    }
    return number(left) - number(right);
  }

  function sortMatches(matches, key, direction) {
    const definition = SORTS[key] || SORTS.date;
    const multiplier = direction === "asc" ? 1 : -1;
    return matches.map((match, index) => ({ match, index })).sort((left, right) => {
      const primary = compareValues(definition.value(left.match), definition.value(right.match));
      if (primary) return primary * multiplier;
      const newest = String(right.match.date || "").localeCompare(String(left.match.date || ""));
      return newest || left.index - right.index;
    }).map((item) => item.match);
  }

  function monthBounds(now) {
    const localDate = (date) => [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), "01"].join("-");
    return {
      current: localDate(new Date(now.getFullYear(), now.getMonth(), 1)),
      next: localDate(new Date(now.getFullYear(), now.getMonth() + 1, 1)),
      previous: localDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    };
  }

  function filterTopMatches(matches, filters, now) {
    const bounds = monthBounds(now || new Date());
    let filtered = matches.filter((match) => ["400", "420"].includes(String(match.queue_id)));
    if (filters.champion !== "ALL") filtered = filtered.filter((match) => match.champion === filters.champion);
    if (filters.queue === "ranked") filtered = filtered.filter((match) => String(match.queue_id) === "420");
    if (filters.queue === "draft") filtered = filtered.filter((match) => String(match.queue_id) === "400");
    if (filters.role !== "ALL") filtered = filtered.filter((match) => match.role === filters.role);
    if (filters.result !== "ALL") filtered = filtered.filter((match) => match.win === (filters.result === "WIN"));
    filtered = filtered.filter((match) => {
      const date = String(match.date || "").slice(0, 10);
      if (filters.period === "two_months") return date >= bounds.previous && date < bounds.next;
      if (filters.period === "current_month") return date >= bounds.current && date < bounds.next;
      if (filters.period === "previous_month") return date >= bounds.previous && date < bounds.current;
      if (filters.period === "custom") return (!filters.start || date >= filters.start) && (!filters.end || date <= filters.end);
      return true;
    });
    if (filters.period === "recent20") return sortMatches(filtered, "date", "desc").slice(0, 20);
    return filtered;
  }

  const api = { SORTS, filterTopMatches, sortMatches, rate };
  global.MatchHistoryMetrics = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
