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

console.log("LP Trend result marker tests: OK");
