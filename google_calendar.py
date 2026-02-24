# google_calendar.py
import os
import json
import datetime
import logging
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

# スコープの定義
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# 環境変数から設定を読み込み
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")


def get_calendar_service() -> Resource:
    """サービスアカウントを使用してGoogle Calendar APIサービスを返す"""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable is not set.")

    creds_data = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    return service


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
        event = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
        return event, None
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else str(error)
        return None, f"Google API Error: {error_content}"
