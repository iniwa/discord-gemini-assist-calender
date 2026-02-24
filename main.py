# main.py
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
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

# -------------------------------------
# 1. Discord Botの基本設定
# -------------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def _is_dm(interaction: discord.Interaction) -> bool:
    """DMチャンネルかどうかを判定する"""
    return isinstance(interaction.channel, discord.DMChannel)


async def _require_dm(interaction: discord.Interaction) -> bool:
    """DM以外なら案内メッセージを送り、Falseを返す"""
    if _is_dm(interaction):
        return True
    await interaction.response.send_message(
        "このBotはDM(ダイレクトメッセージ)でのみ利用できます。\nBotのアイコンをクリックして「メッセージを送信」からDMを開いてください。",
        ephemeral=True
    )
    return False

# -------------------------------------
# 2. 定期実行タスク
# -------------------------------------
@tasks.loop(seconds=60)
async def check_timeouts():
    timeout_minutes = 5
    stale_user_ids = db.get_stale_users(timeout_minutes)

    for user_id in stale_user_ids:
        db.clear_user_state(user_id)
        try:
            user = await bot.fetch_user(int(user_id))
            dm_channel = await user.create_dm()
            await dm_channel.send("⏰ 時間切れのため、カレンダー登録を中断しました。もう一度 `/calendar` からやり直してください。")
        except Exception as e:
            logging.error(f"Failed to send timeout message to {user_id}: {e}")

# -------------------------------------
# 3. Botイベントハンドラ
# -------------------------------------
@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')

    try:
        db.init_db()
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")

    # サービスアカウントのメールアドレスを表示
    sa_email = gcal.get_service_account_email()
    if sa_email:
        logging.info(f"Service account email: {sa_email}")
    else:
        logging.warning("GOOGLE_CREDENTIALS_JSON is not set or invalid.")

    # コマンドの同期
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

    if not check_timeouts.is_running():
        check_timeouts.start()

# -------------------------------------
# 4. スラッシュコマンド
# -------------------------------------
@bot.tree.command(name="help", description="Botの使い方を表示します。")
async def help_command(interaction: discord.Interaction):
    if not await _require_dm(interaction):
        return

    sa_email = gcal.get_service_account_email() or "(未設定)"

    embed = discord.Embed(
        title="🗓️ GeminiカレンダーBotの使い方",
        description="チャットから簡単にGoogleカレンダーへ予定を登録します。\nこのBotはDMでのみ利用できます。",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="📋 初回セットアップ",
        value=(
            "**ステップ1:** Googleカレンダーを開き、対象カレンダーの「設定と共有」を開きます。\n"
            "**ステップ2:** 「特定のユーザーまたはグループと共有する」で以下のメールアドレスを追加し、\n"
            "権限を **「予定の変更」** に設定してください。\n"
            f"```\n{sa_email}\n```\n"
            "**ステップ3:** 同じ設定画面の「カレンダーの統合」セクションにある **カレンダーID** をコピーします。\n"
            "**ステップ4:** このDMで以下のコマンドを実行します:\n"
            "```\n/register <カレンダーID>\n```"
        ),
        inline=False
    )

    embed.add_field(
        name="🗓️ 予定の登録",
        value=(
            "**1.** `/calendar` と送信\n"
            "**2.** 予定の内容を自然文で送信\n"
            "（例: 「明日14時から会議」「3/1 終日 出張」）"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ その他のコマンド",
        value=(
            "`/register <カレンダーID>` — カレンダーを登録\n"
            "`/unregister` — カレンダー登録を解除\n"
            "`/calendar` — 予定の登録を開始\n"
            "`/cancel` — 進行中の登録作業を中断"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="register", description="GoogleカレンダーIDを登録します。")
@app_commands.describe(calendar_id="GoogleカレンダーID（メールアドレス形式）")
async def register_command(interaction: discord.Interaction, calendar_id: str):
    if not await _require_dm(interaction):
        return

    discord_id = str(interaction.user.id)
    db.save_calendar_id(discord_id, calendar_id.strip())
    await interaction.response.send_message(
        f"✅ カレンダーIDを登録しました:\n`{calendar_id.strip()}`\n\n"
        "`/calendar` で予定の登録を開始できます。"
    )


@bot.tree.command(name="unregister", description="カレンダー登録を解除します。")
async def unregister_command(interaction: discord.Interaction):
    if not await _require_dm(interaction):
        return

    discord_id = str(interaction.user.id)
    deleted = db.delete_calendar_id(discord_id)

    if deleted:
        await interaction.response.send_message("✅ カレンダー登録を解除しました。")
    else:
        await interaction.response.send_message("登録されているカレンダーはありません。")


@bot.tree.command(name="calendar", description="カレンダーへの予定登録を開始します。")
async def calendar_command(interaction: discord.Interaction):
    if not await _require_dm(interaction):
        return

    discord_id = str(interaction.user.id)

    # カレンダーID未登録チェック
    calendar_id = db.get_calendar_id(discord_id)
    if not calendar_id:
        await interaction.response.send_message(
            "⚠️ カレンダーIDが登録されていません。\n"
            "先に `/register <カレンダーID>` でカレンダーを登録してください。\n"
            "詳しくは `/help` をご覧ください。"
        )
        return

    db.set_user_state(discord_id, "waiting_for_details")
    await interaction.response.send_message("カレンダーに登録したい予定の内容を送信してください。")


@bot.tree.command(name="cancel", description="カレンダー登録作業を中断します。")
async def cancel_command(interaction: discord.Interaction):
    if not await _require_dm(interaction):
        return

    discord_id = str(interaction.user.id)
    current_state = db.get_user_state(discord_id)

    if current_state:
        db.clear_user_state(discord_id)
        await interaction.response.send_message("✅ カレンダー登録を中断しました。")
    else:
        await interaction.response.send_message("現在、進行中の作業はありません。")

# -------------------------------------
# 5. メッセージ処理 (DM限定)
# -------------------------------------
@bot.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author == bot.user:
        return

    # DM以外は無視
    if not isinstance(message.channel, discord.DMChannel):
        return

    discord_id = str(message.author.id)
    user_state = db.get_user_state(discord_id)

    # 待機状態でない場合は無視
    if user_state != "waiting_for_details":
        return

    # --- 待機状態の場合の処理 ---

    # 状態をクリアして多重処理を防ぐ
    db.clear_user_state(discord_id)

    # ユーザーのカレンダーIDを取得
    calendar_id = db.get_calendar_id(discord_id)
    if not calendar_id:
        await message.reply(
            "⚠️ カレンダーIDが登録されていません。\n"
            "`/register <カレンダーID>` でカレンダーを登録してください。"
        )
        return

    async with message.channel.typing():
        # 1. Gemini APIで予定を解析
        event_details, gemini_error = await gemini_handler.parse_event_details(message.content)

        if gemini_error:
            await message.reply(f"⚠️ **解析失敗 (Gemini)**\nAIからの応答:\n```text\n{gemini_error}\n```")
            return

        if not event_details:
            await message.reply("エラー: 解析結果が空でした。")
            return

        # デバッグ表示
        json_debug = json.dumps(event_details, indent=2, ensure_ascii=False)
        await message.reply(f"🤖 **解析成功！この内容で登録を試みます:**\n```json\n{json_debug}\n```")

        # 2. Google Calendar APIの準備
        try:
            service = gcal.get_calendar_service()
        except Exception as e:
            logging.error(f"Failed to get calendar service: {e}")
            await message.reply(f"❌ **Googleカレンダーへの接続に失敗しました**\n```text\n{e}\n```")
            return

        # 3. 各イベントをループで登録
        success_count = 0
        error_count = 0
        total_events = len(event_details)

        for i, event_data in enumerate(event_details, 1):
            try:
                created_event, calendar_error = gcal.create_calendar_event(service, event_data, calendar_id)
            except Exception as e:
                logging.error(f"Unexpected error creating event: {e}")
                created_event = None
                calendar_error = str(e)

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

        # 4. 最終結果のサマリー (複数の場合のみ)
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
    bot.run(DISCORD_BOT_TOKEN)
