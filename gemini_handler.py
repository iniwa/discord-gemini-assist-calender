# gemini_handler.py
import os
import google.generativeai as genai
import json
import re
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

# ▼▼▼ 修正1: バージョン付きのモデル名に変更 ▼▼▼
# もしこれでもダメなら "gemini-pro" (1.0) を試してみてください
MODEL_NAME = "gemini-flash-latest" 

model = genai.GenerativeModel(
    model_name=MODEL_NAME,
    generation_config=generation_config,
    safety_settings=safety_settings
)

def _create_prompt(text: str) -> str:
    """Gemini APIに送信するためのプロンプトを作成する"""
    today = datetime.now().strftime('%Y-%m-%d')
    return f"""
    あなたはユーザーのチャット発言からスケジュールを抽出する有能な秘書です。
    
    # 入力テキスト
    {text}

    # 今日の日付
    {today}

    # 指示
    - ユーザーの発言を解析し、JSONフォーマットで出力してください。
    - 複数の予定が含まれる場合は、JSONの配列にしてください。
    - 日付や時間が明示されていない場合は、文脈から推測するか、nullにしてください。
    - 予定の内容 (summary) は必須です。
    - JSON以外の余計な説明は一切不要です。

    # 出力形式 (単一の予定)
    ```json
    {{
      "summary": "イベント名",
      "location": "場所 (任意)",
      "description": "詳細 (任意)",
      "start_date": "YYYY-MM-DD",
      "start_time": "HH:MM:SS",
      "end_date": "YYYY-MM-DD",
      "end_time": "HH:MM:SS"
    }}
    ```

    # 出力形式 (複数の予定)
    ```json
    [
      {{
        "summary": "イベント名1",
        "start_date": "YYYY-MM-DD",
        "start_time": "HH:MM:SS",
        "end_date": "YYYY-MM-DD",
        "end_time": "HH:MM:SS"
      }},
      {{
        "summary": "イベント名2",
        "start_date": "YYYY-MM-DD",
        "start_time": "HH:MM:SS",
        "end_date": "YYYY-MM-DD",
        "end_time": "HH:MM:SS"
      }}
    ]
    ```
    """

async def parse_event_details(text: str) -> tuple[list[dict] | None, str | None]:
    """
    テキストからカレンダーのイベント詳細を抽出する。
    戻り値: (イベント情報の辞書のリスト, エラーメッセージ)
    """
    prompt = _create_prompt(text)
    
    try:
        response = await model.generate_content_async(prompt)
        response_text = response.text
        
        json_str = ""
        # マークダウンブロックからJSONを抽出
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", response_text)
        if match:
            json_str = match.group(1).strip()
        else:
            # マークダウンがない場合、レスポンス全体をJSONとして扱う
            json_str = response_text.strip()

        events = json.loads(json_str)
        
        # 常にリストを返すように正規化
        if isinstance(events, dict):
            events = [events]
        
        # summaryの存在チェック
        if not isinstance(events, list) or not all(isinstance(e, dict) and e.get("summary") for e in events):
            return None, f"summary(予定のタイトル)が取得できない、または不正な形式のデータです。\nRaw: {json_str}"
            
        return events, None

    except json.JSONDecodeError as e:
        return None, f"JSON解析エラー: {e}\nRaw: {response_text[:500] if 'response_text' in locals() else 'None'}"
    except Exception as e:
        # ▼▼▼ 修正2: エラー時に利用可能なモデル一覧を表示してデバッグしやすくする ▼▼▼
        error_msg = f"予期せぬエラー: {e}"
        if "404" in str(e) or "not found" in str(e):
            try:
                available_models = [m.name for m in genai.list_models()]
                error_msg += f"\n\n【デバッグ情報】利用可能なモデル一覧:\n{', '.join(available_models)}"
            except Exception as list_error:
                error_msg += f"\n(モデル一覧の取得にも失敗: {list_error})"
        
        return None, error_msg