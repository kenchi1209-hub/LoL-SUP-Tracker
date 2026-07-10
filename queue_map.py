QUEUE_NAME_MAP = {
    "400": "ドラフト",
    "420": "ランク(ソロ/デュオ)",
    "440": "ランク(フレックス)",
    "470": "ランク(5v5)",
    "430": "ブラインド",
    "450": "ARAM",
    "480": "スイフト",
    "700": "Clash",
    "830": "AI戦 Intro",
    "840": "AI戦 Beginner",
    "850": "AI戦 Intermediate",
    "870": "AI戦 Intro",
    "880": "AI戦 Beginner",
    "890": "AI戦 Intermediate",
}
ALLOWED_QUEUE_IDS = {
    "400",
    "420",
    "440",
    "470",
}
def queue_id_to_name(queue_id):
    return QUEUE_NAME_MAP.get(str(queue_id), f"Queue{queue_id}")
def is_allowed_queue_id(queue_id):
    return str(queue_id) in ALLOWED_QUEUE_IDS