const assert = require("assert");

global.SiteUtils = {
  formatDecimal(value, digits) {
    return Number(value).toFixed(digits);
  },
};

const history = require("./site_builder/assets/match-history.js");

function sampleMatch(overrides = {}) {
  return {
    match_id: "JP1_COPY_ONE",
    date: "2026-09-03 20:30:00",
    patch: "16.17",
    queue_name: "Solo/Duo",
    role: "UTILITY",
    champion_name: "レオナ",
    champion: "Leona",
    win: true,
    kills: 2,
    deaths: 3,
    assists: 12,
    cs: 42,
    vision_score: 76,
    wards_placed: 18,
    wards_killed: 4,
    control_wards_bought: 6,
    gold_earned: 8400,
    damage_to_champions: 9200,
    team_kills: 22,
    team_deaths: 16,
    team_assists: 45,
    game_duration_seconds: 1800,
    my_fights: 2,
    fight_wins: 1,
    fight_evens: 0,
    fight_losses: 1,
    survived_fights: 1,
    teamfights: 1,
    objective_before_gain: 1,
    objective_during_gain: 0,
    objective_after_gain: 1,
    detail: { side: "BLUE", participants: [{ is_self: true, relation: "ALLY", rank: "SILVER IV 44 LP", damage_to_champions: 9200 }] },
    fights: [{ fight_id: 3, start_timestamp: 60000, end_timestamp: 75000, phase: "EARLY", scale: "SMALL", result: "WIN", survival: "SURVIVED", player_involved: true, my_kda: { kills: 1, deaths: 0, assists: 2 }, friendly_kills: 2, enemy_kills: 1, participants: [{ role: "SUP", champion: "Leona", relation: "FRIENDLY" }], events: [], objective_context: { before: "NONE", during: "GAIN", after: "NONE" }}],
    all_fights: [{ fight_id: 3, player_involved: true }],
    ...overrides,
  };
}

const labels = {
  UTILITY: "視界 / 支援",
  BOTTOM: "レーン / 火力",
  MIDDLE: "レーン / ローム",
  TOP: "レーン / 耐久",
  JUNGLE: "ガンク / オブジェクト",
};
Object.entries(labels).forEach(([role, title]) => {
  const definition = history.roleSummaryDefinition(role);
  assert.strictEqual(definition.title, title);
  assert.strictEqual(definition.fields(sampleMatch({ role })).length, 5);
});

const match = sampleMatch();
const summary = history.fightSummaryEntries(match);
assert.deepStrictEqual(summary.map(([label]) => label), ["My Fights", "W-E-L", "Fight勝率", "生存率", "Teamfight"]);
assert.strictEqual(summary[1][1], "1W-0E-1L");

const defaults = history.copyTextForSelection(match, { overview: true, selfFights: false, allFights: true, details: true });
assert(defaults.includes("【試合概要】"));
assert(defaults.includes("Match ID: JP1_COPY_ONE"));
assert(defaults.includes("【戦闘詳細（全体）】"));
assert(defaults.includes("【試合詳細】"));
assert(!defaults.includes("【戦闘詳細（自分）】"));

const withSelf = history.copyTextForSelection(match, { overview: false, selfFights: true, allFights: false, details: false });
assert(withSelf.includes("【戦闘詳細（自分）】"));
assert(!withSelf.includes("【試合概要】"));

const other = history.copyTextForSelection(sampleMatch({ match_id: "JP1_COPY_TWO", champion_name: "ナミ" }), { overview: true, selfFights: false, allFights: false, details: false });
assert(other.includes("ナミ"));
assert(!other.includes("JP1_COPY_ONE"));

console.log("match history detail/copy tests: OK");
