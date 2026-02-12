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
    あなたはユーザーのチャット発言からスケジュールを抽出する有能な秘書です。
    ゲームの予定、食事、作業、遊びなど、あらゆる活動をカレンダーイベントとして抽出してください。

    # 入力テキスト
    {text}

    # 今日の日付
    {today} (これを基準に「明日」「来週」などを判定)

    # 抽出ルール (最優先)
    1. **概要 (summary)**: 
       - 「Enshroudやる」「飲み会」など、活動内容を短いタイトルにしてください。
    2. **時間補完**:
       - 開始時刻のみで終了時刻がない場合 -> **開始時刻の1時間後** を終了時刻として設定してください。
       - 時刻がない場合 -> 終日イベント (null) にしてください。
    3. **柔軟な解釈**:
       - 文脈から日付が特定できない場合のみ、今日の日付を使用してください。
       - 多少曖昧でも、可能な限り情報を埋めてJSONを生成してください。errorを返すのは、文章が全く意味不明な場合だけにしてください。

    # 出力フォーマット (JSON)
    {{
      "summary": "イベント名 (必須)",
      "location": "場所 (任意, なければnull)",
      "description": "原文や補足 (任意, なければnull)",
      "start_date": "YYYY-MM-DD",
      "start_time": "HH:MM:SS (または null)",
      "end_date": "YYYY-MM-DD",
      "end_time": "HH:MM:SS (または null)"
    }}
    """

async def parse_event_details(text: str) -> dict | None:
    """
    テキストからカレンダーのイベント詳細を抽出し、JSON形式で返す
    """
    prompt = _create_prompt(text)
    try:
        response = await model.generate_content_async(prompt)
        # レスポンスのクリーニング (Markdown記法への対策)
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        event_data = json.loads(cleaned_response_text)
        
        # エラーキーがあるか、または必須のsummaryがない場合はNoneを返す
        if "error" in event_data:
            return None
        if not event_data.get("summary"):
            return None
        
        return event_data

    except Exception as e:
        print(f"Error in Gemini API call: {e}")
        # デバッグ用にエラー時のレスポンスを表示
        if 'response' in locals():
            print(f"Raw response: {response.text}")
        return None