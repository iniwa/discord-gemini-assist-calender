# gemini_handler.py
import os
import google.generativeai as genai
import json
from datetime import datetime

# Gemini APIキーの設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in the environment variables.")

genai.configure(api_key=GEMINI_API_KEY)

# Geminiモデルの設定
generation_config = {
    "temperature": 0.3,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
    "response_mime_type": "application/json",
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest",
    generation_config=generation_config,
    safety_settings=safety_settings
)

def _create_prompt(text: str) -> str:
    """Gemini APIに送信するためのプロンプトを作成する"""
    today = datetime.now().strftime('%Y-%m-%d')
    return f"""
    以下のテキストを解析し、Googleカレンダーのイベント情報としてJSON形式で抽出してください。

    # 制約条件
    - 今日の日付は {today} です。これを基準に相対的な日付（「明日」「来週の月曜」など）を解釈してください。
    - 時刻が指定されていない場合は、終日イベントとして扱ってください。
    - 終日イベントの場合、`start_time`と`end_time`は`null`にしてください。`end_date`は`start_date`の翌日に設定してください。
    - 時間が指定されている場合、`start_date`と`end_date`は同じ日付にしてください。終了時刻が不明な場合は、開始時刻の1時間後を終了時刻としてください。
    - 出力は必ずJSON形式で、以下のキーを含めてください。
      - `summary`: イベントのタイトル（必須）
      - `location`: 場所（任意）
      - `description`: 詳細な説明（任意）
      - `start_date`: 開始日 (YYYY-MM-DD)
      - `start_time`: 開始時刻 (HH:MM:SS)
      - `end_date`: 終了日 (YYYY-MM-DD)
      - `end_time`: 終了時刻 (HH:MM:SS)
    - どの項目にも該当しない、または情報が不足していてイベントが作成できない場合は、`"error": "情報が不足しています"` というJSONを返してください。

    # テキスト
    {text}
    """

async def parse_event_details(text: str) -> dict | None:
    """
    テキストからカレンダーのイベント詳細を抽出し、JSON形式で返す
    """
    prompt = _create_prompt(text)
    try:
        response = await model.generate_content_async(prompt)
        # レスポンスがJSON形式でない場合や、予期せぬ形式の場合があるためパースを試みる
        # response.textは時にマークダウン(` ```json ... ``` `)で返ることがある
        cleaned_response_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        
        event_data = json.loads(cleaned_response_text)
        
        # エラーキーがあるか、または必須のsummaryがない場合はNoneを返す
        if "error" in event_data or not event_data.get("summary"):
            return None
        
        return event_data

    except Exception as e:
        print(f"Error in Gemini API call: {e}")
        print(f"Raw response from Gemini: {response.text if 'response' in locals() else 'No response'}")
        return None

if __name__ == '__main__':
    # テスト用のコード
    import asyncio

    async def main_test():
        test_cases = [
            "明日の15時から1時間、山田さんと打ち合わせ。場所は第3会議室。",
            "来週の月曜、終日で福岡出張",
            "今日の夜、田中さんと会食",
            "2月20日の10時からクライアントとの定例MTG。詳細は別途。",
            "こんにちは"
        ]
        for case in test_cases:
            print(f"--- Testing: {case} ---")
            result = await parse_event_details(case)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("
")

    asyncio.run(main_test())
