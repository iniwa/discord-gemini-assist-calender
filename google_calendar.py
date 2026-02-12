# google_calendar.py
import os
import json
from typing import Dict, Any

import google.oauth2.credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# スコープの定義: カレンダーのイベントを読み書きする権限
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

def get_auth_url() -> str:
    """ユーザーに提示する認証URLを生成する"""
    flow = create_oauth_flow()
    auth_url, _ = flow.authorization_url(prompt='consent')
    return auth_url

def get_credentials_from_code(code: str) -> str:
    """認証コードから資格情報(JSON文字列)を取得する"""
    flow = create_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return credentials_to_json(credentials)

def credentials_to_json(credentials: google.oauth2.credentials.Credentials) -> str:
    """CredentialsオブジェクトをJSON文字列に変換する"""
    return json.dumps({
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    })

def _get_credentials_from_json(creds_json: str) -> google.oauth2.credentials.Credentials | None:
    """JSON文字列からCredentialsオブジェクトを復元する"""
    try:
        creds_data = json.loads(creds_json)
        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data, SCOPES)
        
        # トークンが期限切れの場合、リフレッシュする
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        return creds
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error loading credentials from JSON: {e}")
        return None

def get_calendar_service(creds_json: str) -> tuple[Resource | None, str | None]:
    """
    資格情報のJSON文字列からGoogle Calendar APIサービスと更新された資格情報JSONを構築して返す
    """
    creds = _get_credentials_from_json(creds_json)
    if not creds or not creds.valid:
        return None, None
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        updated_creds_json = credentials_to_json(creds) # リフレッシュされた可能性のあるトークン
        return service, updated_creds_json
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None, None

def create_calendar_event(service: Resource, event_details: Dict[str, Any]) -> Dict[str, Any] | None:
    """Googleカレンダーにイベントを作成する"""
    event_body = {
        'summary': event_details.get('summary'),
        'location': event_details.get('location'),
        'description': event_details.get('description'),
    }

    # 時間指定イベントか終日イベントかを判定
    if event_details.get('start_time') and event_details.get('end_time'):
        # 時間指定イベント
        event_body['start'] = {
            'dateTime': f"{event_details['start_date']}T{event_details['start_time']}",
            'timeZone': 'Asia/Tokyo',
        }
        event_body['end'] = {
            'dateTime': f"{event_details['end_date']}T{event_details['end_time']}",
            'timeZone': 'Asia/Tokyo',
        }
    else:
        # 終日イベント
        event_body['start'] = {
            'date': event_details['start_date'],
        }
        event_body['end'] = {
            'date': event_details['end_date'],
        }

    try:
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        print(f"Event created: {event.get('htmlLink')}")
        return event
    except HttpError as error:
        print(f'An error occurred while creating event: {error}')
        return None
