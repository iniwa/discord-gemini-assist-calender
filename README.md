# Discord Calendar Bot with Gemini API

DiscordのDMに送ったメッセージをGoogle Gemini AIで解析し、ユーザー個別のGoogleカレンダーに予定を登録するBotです。

## 主な機能

- **カレンダー登録:** 自然言語で書いた内容からイベント名・日時・場所を抽出して登録
- **マルチユーザー対応:** ユーザーごとに異なるGoogleカレンダーへ登録可能
- **DM専用:** すべての操作はDM（ダイレクトメッセージ）で完結
- **レート制限:** 1ユーザーにつき1分間に1回まで利用可能
- **エラー通知:** エラー発生時にDiscord Webhookで管理者へ通知（詳細は非表示）
- **サービスアカウント認証:** OAuthトークンの期限切れ問題なし

## コマンド一覧

| コマンド | 説明 | 権限 |
|---|---|---|
| `/help` | 使い方とセットアップ手順を表示 | 全員 |
| `/register <カレンダーID>` | GoogleカレンダーIDを登録 | 全員 |
| `/unregister` | カレンダー登録を解除 | 全員 |
| `/calendar` | 予定の登録を開始 | 全員 |
| `/cancel` | 進行中の登録を中断 | 全員 |
| `/webhook <URL>` | エラー通知用Webhook URLを登録 | 管理者のみ |
| `/webhook_remove` | Webhook URLを解除 | 管理者のみ |
| `/webhook_test` | Webhook通知のテスト送信 | 管理者のみ |

## 技術スタック

- **言語:** Python 3.11
- **実行環境:** Docker (Raspberry Pi 4 / linux/arm64)
- **主要ライブラリ:**
  - `discord.py`: Discord APIラッパー
  - `google-api-python-client`: Google Calendar API
  - `google-generativeai`: Gemini API
  - `python-dotenv`: 環境変数管理
- **認証:** Googleサービスアカウント
- **データベース:** SQLite（ユーザーカレンダーID・状態・レート制限管理）
- **CI/CD:** GitHub Actions (ghcr.io への自動ビルド＆プッシュ)

---

## セットアップ

### 1. Google Cloud Platform の設定

#### 1.1. プロジェクトの作成・APIの有効化

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成します。
2. 「APIとサービス」>「ライブラリ」から **Google Calendar API** を有効にします。

#### 1.2. サービスアカウントの作成

1. 「APIとサービス」>「認証情報」>「+ 認証情報を作成」>「サービスアカウント」を選択します。
2. 任意の名前でサービスアカウントを作成します。
3. 作成したサービスアカウントを開き、「キー」タブ>「鍵を追加」>「新しい鍵を作成」>「JSON」でキーをダウンロードします。
4. ダウンロードしたJSONファイルを `service_account.json` という名前でサーバーの所定のパスに配置します。

### 2. Gemini APIキーの取得

1. [Google AI Studio](https://ai.google.dev/) にアクセスし、APIキーを生成します。

### 3. Discord Botの作成

1. [Discord Developer Portal](https://discord.com/developers/applications) で新しいアプリケーションを作成します。
2. 「Bot」タブでトークンを生成し、**MESSAGE CONTENT INTENT** を有効にします。
3. 「OAuth2」>「URL Generator」で `bot` と `applications.commands` スコープ、`Send Messages` / `Read Message History` 権限を選択し、生成されたURLでBotをサーバーに招待します。

### 4. デプロイ (Portainer Stacks)

`compose.yml` を以下のように設定してPortainerのStack Web Editorに貼り付けます。

```yaml
services:
  discord-calendar-bot:
    image: ghcr.io/iniwa/discord-gemini-assist-calender:latest
    container_name: discord-calendar-bot
    restart: unless-stopped
    volumes:
      - /home/iniwa/docker/discord-calendar/data:/data
      - /home/iniwa/docker/discord-calendar/service_account.json:/usr/src/app/service_account.json:ro
    environment:
      - DISCORD_BOT_TOKEN=your_token_here
      - GEMINI_API_KEY=your_key_here
      - BOT_ADMIN_ID=your_discord_user_id
    user: "1000:1000"
```

**`service_account.json` の配置:**
```
/home/iniwa/docker/discord-calendar/service_account.json
```

---

## ユーザー向けセットアップ手順

Botを利用するには、Googleカレンダーをサービスアカウントと共有する必要があります。

1. Googleカレンダーを開き、対象カレンダーの「設定と共有」を開きます。
2. 「特定のユーザーまたはグループと共有する」でサービスアカウントのメールアドレスを追加し、権限を「予定の変更」に設定します。
   - サービスアカウントのメールアドレスは `/help` コマンドで確認できます。
3. 同じ設定画面の「カレンダーの統合」セクションにある**カレンダーID**をコピーします。
4. BotにDMで `/register <カレンダーID>` を実行します。

---

## 使い方

```
1. BotにDMを開く（Botのアイコンをクリック →「メッセージを送信」）
2. /calendar と送信
3. 予定の内容を自然文で送信
   例: 「明日14時から1時間、田中さんと打ち合わせ」
       「3/15 終日 東京出張」
4. Botが解析して自動でカレンダーに登録される
```

**注意:** 1分間に1回のみ利用可能です。

---

## エラー通知のセットアップ（管理者向け）

1. Discord でWebhook URLを取得します（通知を受け取りたいチャンネルの「チャンネルの編集」>「連携サービス」>「ウェブフック」）。
2. BotにDMで以下を実行します:
   ```
   /webhook <Webhook URL>
   ```
3. `/webhook_test` でテスト通知を送信して動作確認します。

エラー発生時は「エラーが発生しました」という事実のみが通知されます（詳細情報は含まれません）。
