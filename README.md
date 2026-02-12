# Discord Calendar Bot with Gemini API

Discordに投稿されたチャットログをGoogle Gemini APIで解析し、ユーザー個別のGoogleカレンダーに予定を登録するBotです。

## 概要

特定のチャンネルで `/calendar` コマンドを実行し、その後に予定の内容を投稿すると、Botが内容を解析してGoogleカレンダーにイベントとして登録します。初回利用時にはGoogleアカウントとの連携（認証）が必要です。

## 主な機能

-   **カレンダー登録:** 自然言語で投稿された内容から、イベント名、日時、場所、詳細を抽出してカレンダーに登録します。
-   **Googleアカウント連携:** OAuth 2.0を用いて、ユーザーごとに安全にGoogleカレンダーへのアクセスを許可します。
-   **コマンド:**
    -   `/calendar`: 予定登録モードを開始します。
    -   `/help`: Botの使い方やコマンド一覧を表示します。

## 技術スタック

-   **言語:** Python 3.11
-   **実行環境:** Docker (Raspberry Pi 4 / linux/arm64 対応)
-   **主要ライブラリ:**
    -   `discord.py`: Discord APIラッパー
    -   `google-api-python-client`: Google Calendar API
    -   `google-generativeai`: Gemini API
    -   `python-dotenv`: 環境変数管理
-   **データベース:** SQLite (ユーザー認証トークン管理)
-   **CI/CD:** GitHub Actions (ghcr.ioへの自動ビルド＆プッシュ)

---

## 準備とセットアップ

### 1. Google Cloud Platform (GCP) プロジェクトの設定

#### 1.1. GCPプロジェクトの作成

1.  [Google Cloud Console](https://console.cloud.google.com/)にアクセスします。
2.  画面上部のプロジェクト選択メニューから「新しいプロジェクト」をクリックし、任意のプロジェクト名（例: `discord-calendar-bot`）を入力してプロジェクトを作成します。

#### 1.2. APIの有効化

1.  作成したプロジェクトを選択した状態で、ナビゲーションメニューから「APIとサービス」>「ライブラリ」に移動します。
2.  以下の2つのAPIを検索し、それぞれ「有効にする」ボタンをクリックします。
    -   **Google Calendar API**
    -   **Vertex AI API** (Gemini APIはこちらに含まれます)

#### 1.3. OAuth同意画面の設定

1.  ナビゲーションメニューから「APIとサービス」>「OAuth同意画面」に移動します。
2.  **User Type**で「外部」を選択し、「作成」をクリックします。
3.  **アプリ情報**を入力します。
    -   アプリ名: `Discord Calendar Bot` など分かりやすい名前
    -   ユーザーサポートメール: ご自身のメールアドレス
    -   （任意）アプリのロゴなど
4.  **デベロッパーの連絡先情報**にご自身のメールアドレスを入力し、「保存して次へ」をクリックします。
5.  **スコープ**の画面では、「スコープを追加または削除」をクリックします。
6.  フィルタに `Google Calendar API` と入力し、表示されたスコープの中から以下のものを選択して「更新」ボタンをクリックします。
    -   `.../auth/calendar.events` (カレンダーの予定の表示、編集、共有、完全削除)
7.  「保存して次へ」をクリックします。
8.  **テストユーザー**の画面では、「+ ADD USERS」をクリックし、Botを利用するご自身のGoogleアカウントのメールアドレスを登録します。
9.  「保存して次へ」をクリックし、概要を確認してダッシュボードに戻ります。
10. **重要:** 後ほど「アプリを公開」ボタンをクリックして本番環境に移行できますが、テスト中はテストユーザーのみが利用可能です。

#### 1.4. 認証情報 (OAuth 2.0 クライアント ID) の作成

1.  ナビゲーションメニューから「APIとサービス」>「認証情報」に移動します。
2.  画面上部の「+ 認証情報を作成」をクリックし、「OAuth 2.0 クライアント ID」を選択します。
3.  **アプリケーションの種類**で「ウェブ アプリケーション」を選択します。
4.  **名前**に分かりやすい名前（例: `Discord Bot Web Client`）を入力します。
5.  **承認済みのリダイレクト URI** の「+ URI を追加」をクリックし、`.env` ファイルの `OAUTH_REDIRECT_URI` に設定するURLを入力します。（例: `http://localhost:8080`）
    -   **注意:** このURLは、後述の認証フローで一時的に利用するローカルサーバーのものです。ご自身の環境に合わせて変更してください。
6.  「作成」をクリックします。
7.  作成されたクライアントIDとクライアントシークレットが表示されます。**「JSONをダウンロード」** をクリックし、`client_secret_****.json` というファイルをダウンロードします。
8.  ダウンロードしたファイル名を `client_secret.json` に変更し、このプロジェクトのルートディレクトリに配置します。

### 2. Gemini APIキーの取得

1.  [Google AI for Developers](https://ai.google.dev/) にアクセスします。
2.  「Get API key in Google AI Studio」をクリックします。
3.  「Create API key in new project」をクリックし、APIキーを生成します。
4.  生成されたAPIキーをコピーしておきます。

### 3. Discord Botの作成とトークンの取得

1.  [Discord Developer Portal](https://discord.com/developers/applications) にアクセスし、「New Application」をクリックします。
2.  Botの名前を付けて「Create」をクリックします。
3.  左側のメニューから「Bot」タブに移動します。
4.  「Reset Token」をクリックしてBotトークンを生成・コピーします。（一度しか表示されないため、必ず控えてください）
5.  **Privileged Gateway Intents** のセクションで、以下の項目を**有効**にします。
    -   `MESSAGE CONTENT INTENT`
6.  左側のメニューから「OAuth2」>「URL Generator」に移動します。
7.  **SCOPES** で `bot` と `applications.commands` を選択します。
8.  **BOT PERMISSIONS** で以下の権限を選択します。
    -   `Send Messages`
    -   `Read Message History`
9.  生成されたURLをコピーし、ブラウザでアクセスして、BotをあなたのDiscordサーバーに招待します。

### 4. Botの実行

1.  プロジェクトをクローンまたはダウンロードします。
2.  `.env.example` をコピーして `.env` ファイルを作成します。
3.  `.env` ファイルを編集し、取得した各値を設定します。
    -   `DISCORD_BOT_TOKEN`: Discord Botのトークン
    -   `TARGET_CHANNEL_ID`: Botが監視するチャンネルのID (チャンネルを右クリックして「IDをコピー」)
    -   `GEMINI_API_KEY`: Gemini APIキー
    -   `OAUTH_REDIRECT_URI`: GCPで設定したものと同じリダイレクトURI
4.  Dockerがインストールされている環境で、以下のコマンドを実行します。
    ```bash
    # Raspberry Pi (arm64) の場合
    docker build -t discord-calendar-bot .
    docker run --rm -it --env-file .env discord-calendar-bot
    ```
5.  Botがオンラインになれば成功です。

---

## 使い方

1.  `.env` で指定した特定のチャンネルで `/help` と入力し、Botが反応することを確認します。
2.  `/calendar` と入力します。Botから「カレンダーに登録したい予定の内容を送信してください。」と返信が来ます。
3.  **初回利用時のみ:** BotからGoogleの認証URLがDMで送られます。URLにアクセスし、アカウントを選択してアクセスを許可してください。ブラウザに「認証が完了しました」と表示されればOKです。
4.  予定の内容をチャットに送信します。（例: `来週の月曜15時から30分、Aさんと定例ミーティング。場所はオンライン`）
5.  Botが内容を解析し、カレンダーに登録が完了すると「カレンダーに登録しました！」と返信します。

