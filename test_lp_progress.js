const assert = require("assert");

const lpProgress = require("./site_builder/assets/lp-progress.js");

const officialWin = lpProgress.resultMarkerStyle({ kind: "exact", win: true });
const officialLoss = lpProgress.resultMarkerStyle({ kind: "exact", win: false });
const historicalWin = lpProgress.resultMarkerStyle({ kind: "historical", win: true, source: "blitz_historical" });
const historicalLoss = lpProgress.resultMarkerStyle({ kind: "historical", win: false, source: "mobalytics_historical" });
const correctedLoss = lpProgress.resultMarkerStyle({
  kind: "exact", win: false, lp_status: "corrected", lp_delta: 0, observed_lp_delta: -19,
});

assert.strictEqual(officialWin.shape, "circle");
assert.strictEqual(officialWin.color, "#4f9dff");
assert.strictEqual(officialLoss.shape, "circle");
assert.strictEqual(officialLoss.color, "#ff6b81");
assert.strictEqual(historicalWin.shape, "circle");
assert.strictEqual(historicalWin.color, "#4f9dff");
assert.strictEqual(historicalLoss.shape, "circle");
assert.strictEqual(historicalLoss.color, "#ff6b81");
assert(officialWin.fillOpacity > historicalWin.fillOpacity);
assert.strictEqual(correctedLoss.shape, "circle");
assert.strictEqual(correctedLoss.color, "#ff6b81");

global.document = {
  createElementNS(_namespace, name) {
    return {
      name,
      attributes: {},
      setAttribute(key, value) { this.attributes[key] = String(value); },
    };
  },
};
assert.strictEqual(lpProgress.pointShape({ kind: "exact", win: true }, 1, 2).name, "circle");
assert.strictEqual(lpProgress.pointShape({ kind: "historical", win: false }, 1, 2).name, "circle");
assert.strictEqual(lpProgress.pointShape({ kind: "baseline" }, 1, 2).name, "path");
assert.strictEqual(lpProgress.pointShape({ kind: "checkpoint" }, 1, 2).name, "circle");
const unresolved = lpProgress.pointShape({ kind: "unresolved", win: false }, 1, 2);
assert.strictEqual(unresolved.name, "circle");
assert.strictEqual(unresolved.attributes.fill, "#171d2b");
assert.strictEqual(unresolved.attributes.stroke, "#ff6b81");
const coverage = lpProgress.rankedMatchesForCoverage({
  usable_matches: [{ match_id: "exact", game_number: 136, lp_delta: 5 }],
  unresolved_matches: [{ match_id: "loss", game_number: 137, lp_delta: null }],
});
assert.deepStrictEqual(coverage.map((match) => match.match_id), ["exact", "loss"]);

const manualTooltip = lpProgress.tooltipDetails({
  kind: "exact", game_number: 145, win: false, lp_delta: -20,
  champion_name: "ナミ", role: "SUP",
  before: { tier: "SILVER", division: "IV", lp: 20 },
  after: { tier: "SILVER", division: "IV", lp: 0 },
  record_before: { wins: 63, losses: 81 },
  record_after: { wins: 63, losses: 82 },
  capture_mode: "manual_recovery", confidence: "user_confirmed_with_lcu_anchor",
  match_id: "JP1_MANUAL",
});
assert.strictEqual(manualTooltip.game, "第145戦");
assert.strictEqual(manualTooltip.result, "LOSS");
assert.strictEqual(manualTooltip.delta, "-20");
assert.strictEqual(manualTooltip.champion, "ナミ / SUP");
assert.strictEqual(manualTooltip.rank, "SILVER IV 20 LP → SILVER IV 0 LP");
assert.strictEqual(manualTooltip.record, "63W81L → 63W82L");
assert.deepStrictEqual(manualTooltip.badges, ["Manual recovery", "User confirmed"]);

const unresolvedTooltip = lpProgress.tooltipDetails({ kind: "unresolved", game_number: 148, win: true, lp_delta: null });
assert.strictEqual(unresolvedTooltip.delta, "LP 未確定");
assert.deepStrictEqual(unresolvedTooltip.badges, ["LP未確定", "LP値は補間していません"]);
assert.strictEqual(lpProgress.tooltipDetails({ kind: "baseline", game_number: 95, rank: { tier: "SILVER", division: "IV", lp: 23 } }).delta, "");

const rightEdge = lpProgress.tooltipPlacement(
  { left: 280, right: 290, top: 50, bottom: 60, width: 10, height: 10 },
  { left: 0, top: 0, width: 320, height: 360 },
  { width: 180, height: 100 },
);
assert(rightEdge.left < 100);
assert.strictEqual(rightEdge.top, 74);
const topEdge = lpProgress.tooltipPlacement(
  { left: 80, right: 90, top: 6, bottom: 16, width: 10, height: 10 },
  { left: 0, top: 0, width: 320, height: 360 },
  { width: 180, height: 100 },
);
assert.strictEqual(topEdge.top, 30);

console.log("LP Trend result marker tests: OK");
