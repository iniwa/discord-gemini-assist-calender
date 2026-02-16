# main.py
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks # tasksを追加
from dotenv import load_dotenv
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging
import json

# ローカルモジュールのインポート
import database as db
import google_calendar as gcal
import gemini_handler

# ロギング設定
logging.basicConfig(level=logging.INFO)

# .envファイルから環境変数を読み込む
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
_target_channel_id_str = os.getenv("TARGET_CHANNEL_ID")
TARGET_CHANNEL_ID = int(_target_channel_id_str) if _target_channel_id_str else None
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8080")

# -------------------------------------
# 1. Discord Botの基本設定
# -------------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------------
# 2. OAuthコールバック用HTTPサーバー
# -------------------------------------

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get("code", [None])[0]
        # stateにはdiscord_idが入っている想定
        state = query_components.get("state", [None])[0]

        if code and state:
            try:
                # 認証コードからトークンを取得してDBに保存
                creds_json = gcal.get_credentials_from_code(code)
                db.save_token(state, creds_json) # state=discord_id
                
                # ユーザーに通知 (BotからDMを送る処理はここからは直接呼べないので、DB保存だけでOK)
                # 必要であれば、ここでDiscordのAPIを叩いて通知することも可能ですが、複雑になるため割愛
                
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window now and return to Discord.</p>")
                logging.info(f"Successfully authenticated user: {state}")
            except Exception as e:
                logging.error(f"Authentication failed for user {state}: {e}")
                self.send_response(500)
                self.wfile.write(b"<h1>Authentication failed.</h1>")
        else:
            self.send_response(400)
            self.wfile.write(b"<h1>Invalid request.</h1>")

def run_server():
    """HTTPサーバーを永続的に実行する"""
    try:
        host = "0.0.0.0"
        port = 8080
        server_address = (host, port)

        httpd = HTTPServer(server_address, OAuthCallbackHandler)
        logging.info(f"Starting OAuth callback server on {host}:{port}")
        httpd.serve_forever()
    except Exception as e:
        logging.error(f"Failed to start HTTP server: {e}")

# -------------------------------------
# 3. 定期実行タスク
# -------------------------------------
@tasks.loop(seconds=60)
async def check_timeouts():
    # 5分以上放置されているユーザーを取得
    timeout_minutes = 5
    stale_user_ids = db.get_stale_users(timeout_minutes)
    
    if stale_user_ids:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        for user_id in stale_user_ids:
            db.clear_user_state(user_id)
            if channel:
                try:
                    # メンションで通知
                    await channel.send(f"<@{user_id}> ⏰ 時間切れのため、カレンダー登録を中断しました。もう一度 `/calendar` からやり直してください。")
                except Exception as e:
                    logging.error(f"Failed to send timeout message: {e}")

# -------------------------------------
# 4. Botイベントハンドラ
# -------------------------------------
@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')
    
    # DB初期化 (テーブル作成など)
    # database.py内のinit_db()の中身を適切に実装している前提
    try:
        db.init_db() 
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")

    # ターゲットチャンネルの存在確認
    if TARGET_CHANNEL_ID:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            logging.error(f"Error: Target channel with ID {TARGET_CHANNEL_ID} not found.")
        else:
            logging.info(f"Monitoring channel: #{channel.name} ({TARGET_CHANNEL_ID})")
    else:
        logging.error("Error: TARGET_CHANNEL_ID is not set in the environment variables.")

    # コマンドの同期
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

    # HTTPサーバーを別スレッドで起動 (重複起動防止のためチェックは不要、on_readyは通常1回だが再接続で呼ばれる可能性はあるので注意)
    # 簡易的に、デーモンスレッドとして起動しっぱなしにする
    # 厳密にはロックが必要だが、実用上は起動時に一度だけ走るようにすればよい
    if not any(t.name == "OAuthServerThread" for t in threading.enumerate()):
        server_thread = threading.Thread(target=run_server, daemon=True, name="OAuthServerThread")
        server_thread.start()

    if not check_timeouts.is_running():
        check_timeouts.start()

# -------------------------------------
# 5. スラッシュコマンド
# -------------------------------------
@bot.tree.command(name="help", description="Botの使い方を表示します。")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🗓️ GeminiカレンダーBotの使い方",
        description="チャットから簡単にGoogleカレンダーへ予定を登録します。",
        color=discord.Color.blue()
    )
    # ... (内容は変更なし) ...
    embed.add_field(name="ステップ1", value="`/calendar` と送信", inline=False)
    embed.add_field(name="ステップ2", value="予定の内容を送信", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="calendar", description="カレンダーへの予定登録を開始します。")
async def calendar_command(interaction: discord.Interaction):
    if interaction.channel_id != TARGET_CHANNEL_ID:
        await interaction.response.send_message("このコマンドはこのチャンネルでは使用できません。", ephemeral=True)
        return
        
    discord_id = str(interaction.user.id)
    db.set_user_state(discord_id, "waiting_for_details")
    await interaction.response.send_message("カレンダーに登録したい予定の内容を送信してください。", ephemeral=True)

@bot.tree.command(name="cancel", description="カレンダー登録作業を中断します。")
async def cancel_command(interaction: discord.Interaction):
    if interaction.channel_id != TARGET_CHANNEL_ID:
        await interaction.response.send_message("このコマンドはこのチャンネルでは使用できません。", ephemeral=True)
        return
        
    discord_id = str(interaction.user.id)
    current_state = db.get_user_state(discord_id)
    
    if current_state:
        db.clear_user_state(discord_id)
        await interaction.response.send_message("✅ カレンダー登録を中断しました。", ephemeral=True)
    else:
        await interaction.response.send_message("現在、進行中の作業はありません。", ephemeral=True)

# -------------------------------------
# 6. メッセージ処理
# -------------------------------------
@bot.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author == bot.user:
        return

    # 特定のチャンネル以外からのメッセージは無視
    if message.channel.id != TARGET_CHANNEL_ID:
        return
        
    discord_id = str(message.author.id)
    user_state = db.get_user_state(discord_id)

    # 待機状態でない場合は無視（またはリプライで誘導）
    if user_state != "waiting_for_details":
        # await message.reply(f"まずは `/calendar` とコマンドを送信してくださいね。", delete_after=10)
        return
    
    # --- 待機状態の場合の処理 ---
    
    # 1. Google認証情報の確認
    creds_json = db.get_token(discord_id)
    
    # トークンが無い、または空の場合は認証フローへ
    if not creds_json:
        auth_url = gcal.get_auth_url(state=discord_id)
        
        try:
            dm_channel = await message.author.create_dm()
            await dm_channel.send(
                f"""⚠️ **Googleアカウントの連携が必要です**

以下のURLにアクセスして認証を完了してください。
認証完了後、ブラウザに「Authentication successful!」と表示されたら、
**もう一度Discordで予定の内容を送信してください。**

{auth_url}"""
            )
            # 認証待ちの状態は維持しない（タイムアウト管理が複雑になるため）
            # もしくは、認証完了を待たずに一旦ここでリターンし、ユーザーに再送を促すのが安全
            await message.reply("認証用のURLをDMで送信しました。認証完了後、もう一度予定を送ってください。")
            db.clear_user_state(discord_id) # 一旦状態をクリアして、再度/calendarからやらせるか、状態を残すか。
            # 今回は「状態を残すとタイムアウト処理が必要」なので、一旦クリアして再入力を促すのがシンプルです。
            return

        except discord.Forbidden:
            await message.reply("DMを送信できませんでした。プライバシー設定を確認してください。")
            db.clear_user_state(discord_id)
            return

    # --- 以下、トークンがある場合の処理 ---
    
    # 状態をクリアして多重処理を防ぐ (ここ重要)
    db.clear_user_state(discord_id)
    
    async with message.channel.typing():
        # 2. Gemini APIで予定を解析
        event_details, gemini_error = await gemini_handler.parse_event_details(message.content)
        
        # Geminiのエラーハンドリング
        if gemini_error:
            await message.reply(f"⚠️ **解析失敗 (Gemini)**\nAIからの応答:\n```text\n{gemini_error}\n```")
            return

        if not event_details:
            await message.reply("エラー: 解析結果が空でした。")
            return

        # ▼▼▼ デバッグ表示: AIが読み取った内容を表示する ▼▼▼
        json_debug = json.dumps(event_details, indent=2, ensure_ascii=False)
        await message.reply(f"🤖 **解析成功！この内容で登録を試みます:**\n```json\n{json_debug}\n```")
        # ▲▲▲ 追加ここまで ▲▲▲

        # 3. Google Calendar APIの準備
        service, updated_creds_json = gcal.get_calendar_service(creds_json)
        
        if updated_creds_json:
            db.save_token(discord_id, updated_creds_json)

        if not service:
            await message.reply("Googleカレンダーへのアクセスに失敗しました（認証切れの可能性があります）。再度 `/calendar` から認証を行ってください。")
            db.save_token(discord_id, "")
            return
            
        # 4. 各イベントをループで登録
        success_count = 0
        error_count = 0
        total_events = len(event_details)

        for i, event_data in enumerate(event_details, 1):
            created_event, calendar_error = gcal.create_calendar_event(service, event_data)

            if created_event and created_event.get('htmlLink'):
                success_count += 1
                embed = discord.Embed(
                    title=f"✅ カレンダー登録成功 ({i}/{total_events})",
                    description=f"**{created_event.get('summary', 'N/A')}**",
                    color=discord.Color.green()
                )
                start_display = f"{event_data.get('start_date', '')} {event_data.get('start_time', '終日')}".strip()
                embed.add_field(name="日時", value=start_display if start_display else "日時不明", inline=False)
                embed.add_field(name="場所", value=event_data.get('location', '指定なし'), inline=False)
                embed.add_field(name="リンク", value=f"[カレンダーで表示]({created_event['htmlLink']})", inline=False)
                await message.reply(embed=embed)
            else:
                error_count += 1
                error_embed = discord.Embed(
                    title=f"❌ カレンダー登録エラー ({i}/{total_events})",
                    description=f"予定: `{event_data.get('summary', 'N/A')}`",
                    color=discord.Color.red()
                )
                error_embed.add_field(name="エラー詳細", value=f"```text\n{calendar_error}\n```", inline=False)
                await message.reply(embed=error_embed)
        
        # 5. 最終結果のサマリー (複数の場合のみ)
        if total_events > 1:
            summary_embed = discord.Embed(
                title="全件処理完了",
                description=f"**{success_count}** 件成功、**{error_count}** 件失敗しました。",
                color=discord.Color.blue()
            )
            await message.reply(embed=summary_embed)


# -------------------------------------
# Botの実行
# -------------------------------------
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN is None:
        raise ValueError("DISCORD_BOT_TOKEN is not set in the environment variables.")
    if not TARGET_CHANNEL_ID:
        raise ValueError("TARGET_CHANNEL_ID is not set in the environment variables.")
    bot.run(DISCORD_BOT_TOKEN)