# CLAUDE_ja.md - Docker Tool Development on Raspberry Pi 4（詳細版）

> AI が実際に読む指示書は `CLAUDE.md`（英語・簡潔版）です。このファイルは人間向けの詳細リファレンスです。

このファイルは、Raspberry Pi 4 上で動作する Docker ツール開発時の環境・規約をまとめた日本語ドキュメントです。

---

## 実行環境

| 項目 | 詳細 |
|------|------|
| ホストデバイス | Raspberry Pi 4 Model B (RAM 8GB) |
| アーキテクチャ | `linux/arm64` |
| OS | Raspberry Pi OS (64-bit) |
| ストレージ | SSD 接続済み（コンテナデータ・DB 置き場: `/home/iniwa/docker/`） |
| Docker 管理 | Portainer |
| 外部アクセス | Cloudflared (Cloudflare Tunnel) |

> **注意**: イメージをビルドする際は `linux/arm64` をターゲットアーキテクチャとすること。
> マルチアーキテクチャ対応が必要な場合は `linux/amd64,linux/arm64` を指定する。

---

## Docker / Portainer 運用ルール

- コンテナの管理は **Portainer の Stack (Web Editor)** で行う
- `docker-compose.yml` は直接ファイルとして置かず、**Stack の Web Editor に貼り付ける形**を基本とする
- Stack 名はツール名と合わせる（例: `tool-name`）
- ローカルの compose ファイルを書く場合も、**Portainer Stack にそのまま貼れる形式**にすること

### compose ファイルの基本構造

```yaml
services:
  tool-name:
    image: ghcr.io/iniwa/TOOL_NAME:latest
    container_name: tool-name
    restart: unless-stopped
    ports:
      - "XXXX:XXXX"
    volumes:
      - /home/iniwa/docker/TOOL_NAME/data:/data
    environment:
      - TZ=Asia/Tokyo
```

---

## GitHub Actions / GHCR によるデプロイフロー

### 基本方針

1. ソースコードを GitHub リポジトリで管理する
2. `main` ブランチへの push をトリガーに GitHub Actions が起動する
3. Actions がコンテナイメージをビルドし、GHCR (GitHub Container Registry) へ push する
4. Portainer の Stack で `image: ghcr.io/...` を指定してデプロイする

### GHCR イメージ命名規則

```
ghcr.io/iniwa/{tool-name}:latest
```

- GitHub ユーザー名: `iniwa`
- `{tool-name}` はリポジトリ名と合わせる（小文字ケバブケース）
- タグは基本 `latest` のみ。バージョン管理が必要な場合は `v1.0.0` 形式を追加

### GitHub Actions ワークフロー雛形

`.github/workflows/docker-publish.yml` に以下を配置する:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches:
      - main
    tags:
      - 'v*'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up QEMU (for arm64 cross-build)
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## NAS (Synology DS420j) マウント構成

Synology DS420j を Raspberry Pi にマウントして利用している。

### マウント方式

| 用途 | プロトコル | 対象 |
|------|-----------|------|
| Windows PC と共有するフォルダ | SMB | Windows 2台 + Raspberry Pi で共用 |
| Raspberry Pi 専用フォルダ | NFS | Raspberry Pi のみ使用 |

### マウントポイント一覧

NAS の IP アドレス: `192.168.1.190`

#### SMB マウント（Windows PC 2台 + Raspberry Pi で共用）

| NAS 共有名 | マウントポイント | 用途 |
|-----------|----------------|------|
| `photo` | `/mnt/nas/photo` | 写真データ |
| `pi_backup` | `/mnt/nas/pi_backup` | Raspberry Pi のバックアップ |
| `video` | `/mnt/nas/video` | 動画データ |
| `docker` | `/mnt/nas/docker` | ※旧環境の名残。現在はほぼ未使用 |

#### NFS マウント（Raspberry Pi 専用）

| NAS ボリュームパス | マウントポイント | 用途 |
|------------------|----------------|------|
| `/volume1/git-data` | `/mnt/nas/git-data` | Git リポジトリ本体・LFS などの大容量データ |
| `/volume1/NetBackup` | `/mnt/nas/NetBackup` | ネットワークバックアップ |

### ストレージ使い分け方針

| データ種別 | 保存先 | 理由 |
|-----------|--------|------|
| コンテナデータ全般・DB | `/home/iniwa/docker/{tool-name}/` | SSD 直結で I/O 速度が高い |
| Git リポジトリ・LFS | `/mnt/nas/git-data/` | 大容量のため NAS（NFS）に退避 |
| 写真・動画（参照のみ） | `/mnt/nas/photo/`, `/mnt/nas/video/` | Windows とも共有する既存データ |

> **基本原則**: Docker ツールのデータ置き場は `/home/iniwa/docker/{tool-name}/` を使う。
> NAS を使うのは「大容量データの参照・保存」か「Windows との共有」が必要な場合のみ。

### compose でのボリューム指定例

```yaml
volumes:
  # 通常のコンテナデータ・DB（SSD）← 基本はこちら
  - /home/iniwa/docker/{tool-name}/data:/data
  - /home/iniwa/docker/{tool-name}/db:/var/lib/postgresql/data  # DB 例

  # 大容量データ（NFS）← リポジトリ・LFS など
  - /mnt/nas/git-data/{tool-name}:/repo

  # メディア参照（SMB・読み取り専用推奨）
  - /mnt/nas/photo:/media/photo:ro
  - /mnt/nas/video:/media/video:ro
```

> **注意**: NAS マウントが前提のコンテナは、マウントが外れた場合に備えて `restart: unless-stopped` を使うこと。

---

## ネットワーク / 外部アクセス

- **ローカルアクセス**: 各コンテナのポートへ直接アクセス（例: `http://raspberrypi.local:8080`）
- **外部アクセス**: Cloudflared (Cloudflare Tunnel) 経由でインターネットから安全にアクセス可能
  - Cloudflared は Raspberry Pi にインストール済み
  - 新しいツールを外部公開する場合は Cloudflare の設定も必要

---

## 開発時の注意事項

### アーキテクチャ

- ベースイメージは `arm64` 対応のものを選ぶこと
- `alpine` ベースは軽量で arm64 対応済みのため推奨
- `debian`/`ubuntu` ベースも arm64 対応済み
- **注意**: `amd64` のみのイメージは Raspberry Pi で動作しない

### 推奨ベースイメージ例

```dockerfile
# Python ツールの場合
FROM python:3.12-slim

# Node.js ツールの場合
FROM node:20-alpine

# Go ツールの場合 (マルチステージビルド)
FROM golang:1.22-alpine AS builder
FROM alpine:3.19
```

### リソース制限

RAM 8GB の Raspberry Pi でも、複数コンテナが同時稼働するため、必要に応じてリソース制限を設ける:

```yaml
services:
  tool-name:
    image: ghcr.io/iniwa/TOOL_NAME:latest
    # 必要に応じて追加
    deploy:
      resources:
        limits:
          memory: 512m
```

### タイムゾーン

全コンテナに `TZ=Asia/Tokyo` を設定すること:

```yaml
environment:
  - TZ=Asia/Tokyo
```

---

## .claudeignore

Claude Code がコードを読む際に除外するファイル・ディレクトリを指定する。
各プロジェクトのルートに `.claudeignore` を配置すること。

### 内容テンプレート

```gitignore
# Git 内部ファイル
.git/

# ログファイル
*.log
*.log.*
logs/

# 一時ファイル
*.tmp
*.temp
tmp/
temp/
.cache/

# バックアップファイル
*.bak
*.backup
*.orig
*~

# ビルド成果物
dist/
build/
out/

# 言語別キャッシュ・依存関係
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
node_modules/
.next/
target/          # Rust / Maven

# エディタ・OS 生成ファイル
.DS_Store
Thumbs.db
*.swp
*.swo
.idea/
.vscode/

# 機密情報（誤って読まれないように）
.env
.env.*
*.pem
*.key
secrets/
```

> `.claudeignore` の書式は `.gitignore` と同じ。
> 機密情報を含むファイルは必ず除外しておくこと。

---

## プロジェクト構成の雛形

```
tool-name/
├── .github/
│   └── workflows/
│       └── docker-publish.yml   # GitHub Actions
├── Dockerfile
├── docker-compose.yml           # ローカルテスト用 or Portainer 貼り付け用
├── .dockerignore
├── .claudeignore                # Claude Code の除外設定
├── README.md
└── src/                         # アプリケーションコード
```

---

## チェックリスト（新規ツール作成時）

- [ ] ベースイメージが `arm64` 対応か確認
- [ ] `TZ=Asia/Tokyo` を environment に追加
- [ ] `restart: unless-stopped` を設定
- [ ] GHCR イメージ名を正しい形式で記述
- [ ] GitHub Actions ワークフローを `.github/workflows/` に配置
- [ ] `.claudeignore` をプロジェクトルートに配置
- [ ] Portainer Stack への貼り付けで動作確認
- [ ] 外部公開が必要なら Cloudflare Tunnel の設定を追加
- [ ] NAS マウントを使う場合、マウントポイントのパスが正しいか確認
