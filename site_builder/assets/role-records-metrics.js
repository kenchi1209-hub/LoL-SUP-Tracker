(function (global) {
  "use strict";

  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
  const minutes = (match) => number(match.game_duration_seconds) / 60;
  const perMinute = (value, match) => minutes(match) ? number(value) / minutes(match) : 0;
  const newest = (left, right) => String(right.date).localeCompare(String(left.date)) ||
    String(right.match_id).localeCompare(String(left.match_id));
  const descending = (getter) => (left, right) => getter(right) - getter(left);
  const ascending = (getter) => (left, right) => getter(left) - getter(right);
  const winning = descending((item) => item.match.win ? 1 : 0);
  const byDate = (left, right) => newest(left.match, right.match);

  function chain(comparators) {
    return (left, right) => {
      for (const compare of comparators) {
        const result = compare(left, right);
        if (result) return result;
      }
      return byDate(left, right);
    };
  }

  function decorated(match) {
    return { match, metrics: global.RoleMetrics.aggregateMatches([match]) };
  }

  const raw = (key) => (item) => number(item.match[key]);
  const metric = (key) => (item) => number(item.metrics[key]);
  const combined = (item) => raw("kills")(item) + raw("assists")(item);
  const duration = raw("game_duration_seconds");
  const wardRate = (key) => (item) => perMinute(item.match[key], item.match);
  const displayed = (getter, digits) => (item) =>
    Number(global.RoleMetrics.formatDecimal(getter(item), digits));

  const DEFINITIONS = [
    { key: "kda", label: "最高KDA", value: metric("kda"), tie: displayed(metric("kda"), 2), digits: 2,
      compare: chain([ascending(raw("deaths")), descending(combined), descending(raw("kills"))]) },
    { key: "kills", label: "最多Kill", value: raw("kills"), digits: 0,
      compare: chain([ascending(raw("deaths")), descending(raw("assists")), winning]) },
    { key: "assists", label: "最多Assist", value: raw("assists"), digits: 0,
      compare: chain([ascending(raw("deaths")), descending(raw("kills")), winning]) },
    { key: "cs", label: "最多CS", value: raw("cs"), digits: 0,
      compare: chain([descending(metric("cspm")), ascending(duration), winning]) },
    { key: "cspm", label: "最高CS/m", value: metric("cspm"), tie: displayed(metric("cspm"), 2), digits: 2,
      compare: chain([descending(raw("cs")), descending(duration), winning]) },
    { key: "vision", label: "最高VS", value: raw("vision_score"), digits: 0,
      compare: chain([descending(metric("vspm")), ascending(duration), winning]) },
    { key: "vspm", label: "最高VS/m", value: metric("vspm"), tie: displayed(metric("vspm"), 2), digits: 2,
      compare: chain([descending(raw("vision_score")), descending(duration), winning]) },
    { key: "wardsPlaced", label: "最多Ward設置", value: raw("wards_placed"), digits: 0,
      compare: chain([descending(wardRate("wards_placed")), ascending(duration), winning]) },
    { key: "wardsKilled", label: "最多Ward破壊", value: raw("wards_killed"), digits: 0,
      compare: chain([descending(wardRate("wards_killed")), ascending(duration), winning]) },
    { key: "controlWards", label: "最多Control Ward購入", value: raw("control_wards_bought"), digits: 0,
      compare: chain([descending(wardRate("control_wards_bought")), ascending(duration), winning]) },
    { key: "damage", label: "最高Damage", value: raw("damage_to_champions"), digits: 0,
      compare: chain([descending(metric("damagePerMinute")), ascending(duration), winning]) },
    { key: "damagePerMinute", label: "最高Damage/m", value: metric("damagePerMinute"), tie: displayed(metric("damagePerMinute"), 0), digits: 0,
      compare: chain([descending(raw("damage_to_champions")), descending(duration), winning]) },
    { key: "duration", label: "最長試合", value: duration, tie: duration, format: "duration",
      compare: chain([winning, descending(metric("kda"))]) },
  ];

  function matchRecord(matches, definition) {
    if (!matches.length) return { ...definition, winner: null, ties: [] };
    const items = matches.map(decorated);
    const tieValue = definition.tie || definition.value;
    const maximum = Math.max(...items.map(tieValue));
    const ties = items.filter((item) => tieValue(item) === maximum);
    const ranked = ties.slice().sort(definition.compare);
    return { ...definition, winner: ranked[0], ties: ties.slice().sort(byDate), recordValue: maximum };
  }

  function streakRecord(matches, win) {
    const key = win ? "winStreak" : "lossStreak";
    const label = win ? "最長連勝" : "最長連敗";
    const runs = global.RoleStreaks.streakRuns(matches).filter((run) => run.win === win);
    if (!runs.length) return { key, label, streak: true, win, winner: null, ties: [] };
    const maximum = Math.max(...runs.map((run) => run.length));
    const enriched = runs.filter((run) => run.length === maximum).map((run) => ({
      ...run,
      metrics: global.RoleMetrics.aggregateMatches(run.matches),
      startDate: String(run.matches[0].date).slice(0, 10),
      endDate: String(run.matches[run.matches.length - 1].date).slice(0, 10),
    }));
    const compare = win
      ? chain([descending((item) => item.metrics.kda), descending((item) => item.metrics.vspm)])
      : chain([descending((item) => item.metrics.kda), ascending((item) => item.metrics.avgDeaths)]);
    const ranked = enriched.slice().sort((left, right) => compare(
      { ...left, match: left.matches[left.matches.length - 1] },
      { ...right, match: right.matches[right.matches.length - 1] }
    ));
    const ties = enriched.slice().sort((left, right) => String(right.endDate).localeCompare(String(left.endDate)));
    return { key, label, streak: true, win, winner: ranked[0], ties, recordValue: maximum };
  }

  function analyzeRecords(matches) {
    return DEFINITIONS.map((definition) => matchRecord(matches, definition)).concat([
      streakRecord(matches, true), streakRecord(matches, false),
    ]);
  }

  const api = { DEFINITIONS, analyzeRecords, matchRecord, streakRecord };
  global.RoleRecordsMetrics = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
