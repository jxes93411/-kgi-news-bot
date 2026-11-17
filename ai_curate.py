"""用 Claude 挑選新聞並產出六欄位內容。

設計重點：標題、來源、日期、連結一律取自原始資料（以 id 對應），
AI 只負責「挑選 + 摘要 + 觀點 + 延伸需求」，確保標題與連結是真的。
"""
import json
import os

import anthropic

from sources import NEWS_PER_DAY

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SYSTEM = f"""你是凱基人壽北一區域中心的資深保險財經編輯，服務對象是第一線業務同仁。
每天從候選新聞中挑出 {NEWS_PER_DAY} 則最值得業務員拿來和客戶聊的新聞，並為每則撰寫內容。

挑選原則：
1. 官方來源（金管會、壽險公會、財政部、衛福部、央行）優先，媒體新聞補充。
2. 與保險、退休、醫療、長照、稅務傳承、利率匯率相關性高者優先。
3. 主題盡量多元，不要多則講同一件事。

撰寫規則：
- summary：100～150 個中文字，只能根據提供的內文或 RSS 摘要，不得補充原文沒有的數字或事實。
- ai_view：這則新聞與保險規劃的關聯，2～3 句。
- extended_needs：3～5 個可延伸討論的保障或財務規劃議題（短詞）。

法遵限制（務必遵守）：
- 不得提及特定商品名稱、不得保證收益或報酬率、不得與其他公司比較。
- 不得誇大或製造恐慌，不得引用未經證實的數據。
"""

TOOL = {
    "name": "publish_daily_news",
    "description": "輸出今日精選新聞",
    "input_schema": {
        "type": "object",
        "properties": {
            "news": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "候選新聞的 id"},
                        "category": {"type": "string", "description": "主題標籤，如：退休規劃、醫療長照、稅務傳承、利率匯率、金融監理"},
                        "summary": {"type": "string"},
                        "ai_view": {"type": "string"},
                        "extended_needs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "category", "summary", "ai_view", "extended_needs"],
                },
            }
        },
        "required": ["news"],
    },
}


def curate(candidates: list[dict]) -> list[dict]:
    payload = [
        {
            "id": c["id"],
            "source": c["source"],
            "date": c["date"],
            "title": c["title"],
            "content": c["content"] or c["rss_summary"],
        }
        for c in candidates
    ]
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "publish_daily_news"},
        messages=[{
            "role": "user",
            "content": "以下是今日候選新聞（JSON）：\n" + json.dumps(payload, ensure_ascii=False),
        }],
    )
    picked = next(b.input for b in resp.content if b.type == "tool_use")["news"]

    by_id = {c["id"]: c for c in candidates}
    result = []
    for p in picked:
        src = by_id.get(p["id"])
        if not src:  # AI 回了不存在的 id → 丟掉，避免捏造新聞
            continue
        result.append({
            "title": src["title"],
            "source": src["source"],
            "date": src["date"],
            "link": src["link"],
            **{k: p[k] for k in ("category", "summary", "ai_view", "extended_needs")},
        })
    return result[:NEWS_PER_DAY]
