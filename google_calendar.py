# google_calendar.py
import os
import json
import datetime  # 追加: 時間計算用
from typing import Dict, Any

import google.oauth2.credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# スコープの定義
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# 環境変数から設定を読み込み
CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8080")

def create_oauth_flow() -> Flow:
    """OAuth 2.0 Flowオブジェクトを作成して返す"""
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI
    )
    return flow

def get_auth_url(state: str = None) -> str:
    """ユーザーに提示する認証URLを生成する"""
    flow = create_oauth_flow()
    auth_url, _ = flow.authorization_url(prompt='consent', state=state)
    return auth_url

def get_credentials_from_code(code: str) -> str:
    """認証コードから資格情報(JSON文字列)を取得する"""
    flow = create_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return credentials_to_json(credentials)

def credentials_to_json(credentials: google.oauth2.credentials.Credentials) -> str:
    return json.dumps({
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    })

def _get_credentials_from_json(creds_json: str) -> google.oauth2.credentials.Credentials | None:
    try:
        creds_data = json.loads(creds_json)
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error loading credentials from JSON: {e}")
        return None

def get_calendar_service(creds_json: str) -> tuple[Resource | None, str | None]:
    creds = _get_credentials_from_json(creds_json)
    if not creds or not creds.valid:
        return None, None
    try:
        service = build('calendar', 'v3', credentials=creds)
        updated_creds_json = credentials_to_json(creds)
        return service, updated_creds_json
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None, None

# ▼▼▼ 修正箇所: 戻り値を (イベント, エラーメッセージ) に変更し、時間補完ロジックを追加 ▼▼▼
def create_calendar_event(service: Resource, event_details: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str | None]:
    event_body = {
        'summary': event_details.get('summary'),
        'location': event_details.get('location'),
        'description': event_details.get('description'),
    }

    start_date = event_details.get('start_date')
    start_time = event_details.get('start_time')
    end_date = event_details.get('end_date')
    end_time = event_details.get('end_time')

    # 時間指定がある場合
    if start_time:
        # 終了時間がない場合、開始時間の1時間後に自動設定する (救済措置)
        if not end_time:
            try:
                dt_start = datetime.datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # 秒がない場合(HH:MM)のケア
                try:
                    dt_start = datetime.datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
                except ValueError as e:
                    return None, f"時間のフォーマットエラー: {e}"
            
            dt_end = dt_start + datetime.timedelta(hours=1)
            end_date = dt_end.strftime("%Y-%m-%d")
            end_time = dt_end.strftime("%H:%M:%S")

        event_body['start'] = {
            'dateTime': f"{start_date}T{start_time}",
            'timeZone': 'Asia/Tokyo',
        }
        event_body['end'] = {
            'dateTime': f"{end_date}T{end_time}",
            'timeZone': 'Asia/Tokyo',
        }
    
    # 終日イベントの場合
    else:
        event_body['start'] = {'date': start_date}
        # 終日イベントで終了日がない、または開始日と同じ場合、Googleカレンダー仕様に合わせて+1日する
        if not end_date or end_date == start_date:
            try:
                dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                dt_end = dt_start + datetime.timedelta(days=1)
                end_date = dt_end.strftime("%Y-%m-%d")
            except ValueError as e:
                 return None, f"日付のフォーマットエラー: {e}"
                 
        event_body['end'] = {'date': end_date}

    try:
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return event, None
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else str(error)
        return None, f"Google API Error: {error_content}"