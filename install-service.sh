#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gateway-monitor}"
APP_SUBDIR="${APP_SUBDIR:-gateway-monitor}"
SERVICE_NAME="${SERVICE_NAME:-gateway-monitor}"
SERVICE_USER="${SERVICE_USER:-gateway-monitor}"
PROJECT_DIR="$APP_DIR/src/$APP_SUBDIR"

info() {
  printf '\033[1;34m[Gateway Monitor]\033[0m %s\n' "$1"
}

fail() {
  printf '\033[1;31m[Gateway Monitor]\033[0m %s\n' "$1" >&2
  exit 1
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

main() {
  [ -d "$PROJECT_DIR" ] || fail "Projeto nao encontrado em $PROJECT_DIR"
  [ -x "$PROJECT_DIR/.venv/bin/uvicorn" ] || fail "Virtualenv nao encontrado em $PROJECT_DIR/.venv"

  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    info "Criando usuario de servico $SERVICE_USER..."
    as_root useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  fi

  info "Ajustando permissoes..."
  as_root chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

  info "Criando servico systemd $SERVICE_NAME..."
  as_root tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<SERVICE
[Unit]
Description=Gateway Monitor
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStartPre=$PROJECT_DIR/.venv/bin/alembic upgrade head
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

  as_root systemctl daemon-reload
  as_root systemctl enable "$SERVICE_NAME"
  as_root systemctl restart "$SERVICE_NAME"

  info "Servico criado. Use: systemctl status $SERVICE_NAME"
}

main "$@"
