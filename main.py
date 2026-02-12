# main.py
import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import uuid
from urllib.parse import urlparse, parse_qs
import logging

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
# 認証セッションを管理するための辞書
# key: state (uuid), value: {"code": str | None, "event": asyncio.Event}
auth_sessions = {}

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_sessions
        
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get("code", [None])[0]
        state = query_components.get("state", [None])[0]

        if code and state and state in auth_sessions:
            session = auth_sessions[state]
            session["code"] = code
            
            # botのスレッドでイベントを設定する
            bot.loop.call_soon_threadsafe(session["event"].set)
            
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window now.</p>")
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication failed. Invalid request.</h1>")

def run_server():
    """HTTPサーバーを永続的に実行する"""
    try:
        parsed_uri = urlparse(OAUTH_REDIRECT_URI)
        host, port = parsed_uri.hostname, parsed_uri.port
        server_address = (host, port)
        httpd = HTTPServer(server_address, OAuthCallbackHandler)
        logging.info(f"Starting OAuth callback server on {host}:{port}")
        httpd.serve_forever()
    except Exception as e:
        logging.error(f"Failed to start HTTP server: {e}")

# 3. Botイベントハンドラ
# -------------------------------------
@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')
    db.init_db()

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

    # HTTPサーバーを別スレッドで起動
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

# -------------------------------------
# 4. スラッシュコマンド
# -------------------------------------
@bot.tree.command(name="help", description="Botの使い方を表示します。")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🗓️ GeminiカレンダーBotの使い方",
        description="チャットから簡単にGoogleカレンダーへ予定を登録します。",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="ステップ1: 登録準備",
        value="""`/calendar` とコマンドを送信してください。
Botがあなたの次のメッセージを待機する状態になります。""",
        inline=False
    )
    embed.add_field(
        name="ステップ2: 予定を送信",
        value="""待機状態で、カレンダーに登録したい予定を自然な文章で送信します。
例: `明日の15時から1時間、山田さんと打ち合わせ。場所は第3会議室。`""",
        inline=False
    )
    embed.add_field(
        name="ステップ3: Google認証 (初回のみ)",
        value="""BotからGoogleアカウント連携のためのURLがDMで送られてきます。
URLにアクセスし、連携を許可してください。""",
        inline=False
    )
    embed.add_field(
        name="完了！",
        value="Botが内容を解析し、カレンダー登録が完了すると通知します。",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="calendar", description="カレンダーへの予定登録を開始します。")
async def calendar_command(interaction: discord.Interaction):
    if interaction.channel_id != TARGET_CHANNEL_ID:
        await interaction.response.send_message("このコマンドはこのチャンネルでは使用できません。", ephemeral=True)
        return
        
    discord_id = str(interaction.user.id)
    db.set_user_state(discord_id, "waiting_for_details")
    await interaction.response.send_message("カレンダーに登録したい予定の内容を送信してください。", ephemeral=True)

# -------------------------------------
# 5. メッセージ処理
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

    # 待機状態でない場合は、コマンドを使うように促す
    if user_state != "waiting_for_details":
        await message.reply(f"まずは `/calendar` とコマンドを送信してくださいね。", delete_after=10)
        return
    
    # --- 待機状態の場合の処理 ---
    # 状態をクリアして多重処理を防ぐ
    db.clear_user_state(discord_id)
    
    async with message.channel.typing():
        # 1. Google認証の確認と実行
        creds_json = db.get_token(discord_id)
        if not creds_json:
            await message.reply("Googleアカウントの認証が必要です。DMを確認してください。")
            
            # --- OAuthフローを開始 ---
            global oauth_code, oauth_user_id
            oauth_code = None
            oauth_user_id = None
            
            server_thread = threading.Thread(target=run_server)
            server_thread.start()
            
            auth_url = gcal.get_auth_url() + f"&state={discord_id}"
            
            try:
                dm_channel = await message.author.create_dm()
                await dm_channel.send(
                    f"こんにちは！カレンダー登録のためにGoogleアカウントとの連携をお願いします。
"
                    f"以下のURLにアクセスして認証を完了してください。

{auth_url}"
                )
                webbrowser.open(auth_url)
            except discord.Forbidden:
                await message.reply("DMを送信できませんでした。プライバシー設定を確認してください。")
                db.clear_user_state(discord_id)
                await shutdown_server_async()
                return

            # 認証コードが得られるまで待機 (タイムアウト付き)
            timeout = 300 # 5分
            for _ in range(timeout):
                if oauth_code and oauth_user_id == discord_id:
                    break
                await asyncio.sleep(1)

            if not oauth_code:
                await message.author.send("認証がタイムアウトしました。もう一度 `/calendar` からやり直してください。")
                await shutdown_server_async()
                return

            # トークンを取得して保存
            try:
                creds_json = gcal.get_credentials_from_code(oauth_code)
                db.save_token(discord_id, creds_json)
                await message.author.send("✅ 認証が完了しました！")
            except Exception as e:
                await message.author.send(f"認証トークンの取得に失敗しました: {e}")
                db.clear_user_state(discord_id)
                return
            finally:
                server_thread.join(timeout=1.0)


        # 2. Gemini APIで予定を解析
        event_details = await gemini_handler.parse_event_details(message.content)
        if not event_details:
            await message.reply("""うーん、うまく内容を読み取れませんでした...。
もう少し具体的に書いてもう一度試してもらえますか？""")
            return

        # 3. Google Calendar APIでイベント作成
        # 最新の認証情報でサービスを再取得
        creds_json = db.get_token(discord_id)
        service, updated_creds_json = gcal.get_calendar_service(creds_json)
        
        if updated_creds_json:
            db.save_token(discord_id, updated_creds_json) # リフレッシュされたトークンを保存

        if not service:
            await message.reply("Googleカレンダーへのアクセスに失敗しました。再度認証が必要かもしれません。")
            db.save_token(discord_id, "") # トークンをクリア
            return
            
        created_event = gcal.create_calendar_event(service, event_details)

        # 4. 結果をユーザーに通知
        if created_event and created_event.get('htmlLink'):
            embed = discord.Embed(
                title="✅ カレンダーに登録しました！",
                description=f"**{created_event['summary']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="日時", value=f"{event_details['start_date']} {event_details.get('start_time', '終日')}", inline=False)
            embed.add_field(name="リンク", value=f"[カレンダーで表示]({created_event['htmlLink']})", inline=False)
            await message.reply(embed=embed)
        else:
            await message.reply("カレンダーへの登録に失敗しました。")


# -------------------------------------
# Botの実行
# -------------------------------------
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN is None:
        raise ValueError("DISCORD_BOT_TOKEN is not set in the environment variables.")
    if not TARGET_CHANNEL_ID:
        raise ValueError("TARGET_CHANNEL_ID is not set in the environment variables.")
    bot.run(DISCORD_BOT_TOKEN)
