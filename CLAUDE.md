# CLAUDE.md

> Detailed notes (Japanese): CLAUDE_ja.md

## Communication
- User writes in Japanese; **respond in English** unless instructed otherwise.
- Write lightweight, efficient code. Prefer minimal dependencies.

## Environment
- Host: Raspberry Pi 4 (8GB RAM), `linux/arm64`
- Docker management: Portainer — Stack Web Editor only (no direct compose files)

## Build & Deploy
- Build target: `linux/arm64`
- Image: `ghcr.io/iniwa/{tool-name}:latest`
- Flow: push to `main` → GitHub Actions → GHCR → Portainer Stack paste
- All containers require: `restart: unless-stopped`, `TZ=Asia/Tokyo`

## Storage
| Data | Path | Backend |
|------|------|---------|
| Container data / DB | `/home/iniwa/docker/{tool-name}/` | SSD (primary) |
| Git repo / LFS | `/mnt/nas/git-data/` | NFS |
| Media (read-only) | `/mnt/nas/photo/`, `/mnt/nas/video/` | SMB |

## NAS Mounts (Synology DS420j @ 192.168.1.190)
- **SMB**: `/mnt/nas/photo`, `/mnt/nas/video`, `/mnt/nas/pi_backup`, `/mnt/nas/docker` *(legacy, unused)*
- **NFS**: `/mnt/nas/git-data`, `/mnt/nas/NetBackup`

## External Access
Cloudflared (Cloudflare Tunnel) is installed. Configure tunnel when exposing a service externally.

## New Tool Checklist
- [ ] arm64-compatible base image (`alpine` preferred)
- [ ] `TZ=Asia/Tokyo` in environment
- [ ] `restart: unless-stopped`
- [ ] Image: `ghcr.io/iniwa/{tool-name}:latest`
- [ ] GitHub Actions workflow at `.github/workflows/docker-publish.yml`
- [ ] `.claudeignore` in project root
- [ ] Verify deployment via Portainer Stack
- [ ] Configure Cloudflare Tunnel if external access is needed
