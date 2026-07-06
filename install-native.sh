#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/rodrigsilvabjm/monitor-ATA.git}"
APP_DIR="${APP_DIR:-/opt/gateway-monitor}"
APP_SUBDIR="${APP_SUBDIR:-gateway-monitor}"
SERVICE_NAME="${SERVICE_NAME:-gateway-monitor}"
SERVICE_USER="${SERVICE_USER:-gateway-monitor}"

info() {
  printf '\033[1;34m[Gateway Monitor]\033[0m %s\n' "$1"
}

warn() {
  printf '\033[1;33m[Gateway Monitor]\033[0m %s\n' "$1"
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

detect_os() {
  [ -f /etc/os-release ] || fail "Nao foi possivel detectar o sistema operacional."
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_CODENAME="${VERSION_CODENAME:-}"
}

install_packages() {
  detect_os

  case "$OS_ID" in
    ubuntu|debian)
      info "Instalando pacotes do sistema..."
      as_root apt-get update
      as_root apt-get install -y \
        build-essential \
        ca-certificates \
        curl \
        git \
        libpq-dev \
        openssl \
        postgresql \
        postgresql-contrib \
        gnupg \
        python3-dev \
        python3-pip \
        python3-venv
      ;;
    *)
      fail "Instalacao nativa automatica suportada para Ubuntu/Debian."
      ;;
  esac
}

ensure_python() {
  if has_command python3.12; then
    PYTHON_BIN="python3.12"
    return
  fi

  if apt_candidate_exists python3.12 \
    && apt_candidate_exists python3.12-dev \
    && apt_candidate_exists python3.12-venv; then
    info "Instalando Python 3.12 pelo repositorio disponivel..."
    as_root apt-get install -y python3.12 python3.12-dev python3.12-venv
    PYTHON_BIN="python3.12"
    return
  fi

  if [ "$OS_ID" = "ubuntu" ]; then
    warn "Python 3.12 nao encontrado. Configurando repositorio deadsnakes..."
    as_root apt-get install -y software-properties-common

    if ! configure_deadsnakes_repository; then
      fail "Nao foi possivel configurar o repositorio do Python 3.12. Verifique DNS/internet do servidor e rode novamente."
    fi

    as_root apt-get update
    as_root apt-get install -y python3.12 python3.12-dev python3.12-venv
    PYTHON_BIN="python3.12"
    return
  fi

  PYTHON_BIN="python3"
  PYTHON_MAJOR_MINOR="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  case "$PYTHON_MAJOR_MINOR" in
    3.10|3.11|3.12|3.13)
      warn "Python 3.12 nao encontrado. Usando $PYTHON_BIN $PYTHON_MAJOR_MINOR."
      ;;
    *)
      fail "Python 3.10+ e necessario. Instale Python 3.12 e rode novamente."
      ;;
  esac
}

apt_candidate_exists() {
  CANDIDATE="$(
    apt-cache policy "$1" | awk -v package_name="$1" '
      $0 == package_name ":" { found = 1; next }
      found && /Candidate:/ { print $2; exit }
    '
  )"
  [ -n "$CANDIDATE" ] && [ "$CANDIDATE" != "(none)" ]
}

configure_deadsnakes_repository() {
  [ -n "$OS_CODENAME" ] || OS_CODENAME="$(lsb_release -cs 2>/dev/null || true)"
  [ -n "$OS_CODENAME" ] || return 1

  as_root install -m 0755 -d /etc/apt/keyrings

  if curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF23C5A6CF475977595C89F51BA6932366A755776" \
    | gpg --dearmor \
    | as_root tee /etc/apt/keyrings/deadsnakes.gpg >/dev/null; then
    printf 'deb [signed-by=/etc/apt/keyrings/deadsnakes.gpg] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu %s main\n' \
      "$OS_CODENAME" | as_root tee /etc/apt/sources.list.d/deadsnakes.list >/dev/null
    return 0
  fi

  warn "Nao consegui baixar a chave GPG do deadsnakes. Usando fallback trusted para concluir a instalacao."
  printf 'deb [trusted=yes] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu %s main\n' \
    "$OS_CODENAME" | as_root tee /etc/apt/sources.list.d/deadsnakes.list >/dev/null
  return 0
}

prepare_repository() {
  info "Preparando diretorio em $APP_DIR..."
  as_root mkdir -p "$APP_DIR"
  as_root chown "$(id -u):$(id -g)" "$APP_DIR"

  if [ -d "$APP_DIR/src/.git" ]; then
    info "Atualizando codigo existente..."
    git -C "$APP_DIR/src" fetch --all --prune
    git -C "$APP_DIR/src" pull --ff-only
  else
    info "Baixando codigo do repositorio..."
    git clone "$REPO_URL" "$APP_DIR/src"
  fi
}

configure_env() {
  PROJECT_DIR="$APP_DIR/src/$APP_SUBDIR"
  [ -d "$PROJECT_DIR" ] || fail "Diretorio do projeto nao encontrado: $PROJECT_DIR"

  cd "$PROJECT_DIR"

  if [ ! -f .env ]; then
    info "Criando .env a partir do .env.example..."
    cp .env.example .env
  fi

  if grep -q '^SECRET_KEY=change-this-secret-key$' .env; then
    SECRET_VALUE="$(openssl rand -hex 32)"
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_VALUE/" .env
  fi

  sed -i 's/^POSTGRES_HOST=.*/POSTGRES_HOST=localhost/' .env
}

env_value() {
  awk -v key="$1" '
    BEGIN { FS = "=" }
    $1 == key {
      sub(/^[^=]*=/, "")
      gsub(/^"/, "")
      gsub(/"$/, "")
      print
      exit
    }
  ' "$PROJECT_DIR/.env"
}

sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

validate_identifier() {
  case "$1" in
    ""|*[!A-Za-z0-9_]*)
      fail "Identificador invalido no .env: $1"
      ;;
  esac
}

postgres_exec() {
  if has_command sudo; then
    sudo -u postgres psql "$@"
  elif has_command runuser; then
    runuser -u postgres -- psql "$@"
  else
    fail "Nao encontrei sudo nem runuser para administrar o PostgreSQL."
  fi
}

setup_postgres() {
  POSTGRES_USER_VALUE="$(env_value POSTGRES_USER)"
  POSTGRES_PASSWORD_VALUE="$(env_value POSTGRES_PASSWORD)"
  POSTGRES_DB_VALUE="$(env_value POSTGRES_DB)"

  validate_identifier "$POSTGRES_USER_VALUE"
  validate_identifier "$POSTGRES_DB_VALUE"

  info "Configurando PostgreSQL local..."
  as_root systemctl enable postgresql
  as_root systemctl start postgresql

  PASSWORD_SQL="$(sql_literal "$POSTGRES_PASSWORD_VALUE")"
  USER_EXISTS="$(postgres_exec -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$POSTGRES_USER_VALUE';" | tr -d '[:space:]')"
  if [ "$USER_EXISTS" != "1" ]; then
    postgres_exec -c "CREATE USER \"$POSTGRES_USER_VALUE\" WITH PASSWORD '$PASSWORD_SQL';"
  else
    postgres_exec -c "ALTER USER \"$POSTGRES_USER_VALUE\" WITH PASSWORD '$PASSWORD_SQL';"
  fi

  DB_EXISTS="$(postgres_exec -tAc "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB_VALUE';" | tr -d '[:space:]')"
  if [ "$DB_EXISTS" != "1" ]; then
    postgres_exec -c "CREATE DATABASE \"$POSTGRES_DB_VALUE\" OWNER \"$POSTGRES_USER_VALUE\";"
  fi
}

setup_python_app() {
  cd "$PROJECT_DIR"
  info "Criando ambiente Python..."
  "$PYTHON_BIN" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt

  mkdir -p logs backups
  .venv/bin/alembic upgrade head
}

setup_service_user() {
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    as_root useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  fi

  as_root chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
}

setup_systemd() {
  SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

  info "Criando servico systemd..."
  as_root tee "$SERVICE_FILE" >/dev/null <<SERVICE
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
}

open_firewall() {
  if has_command ufw && as_root ufw status | grep -q "Status: active"; then
    info "Liberando porta 8000 no UFW..."
    as_root ufw allow 8000/tcp
  fi
}

main() {
  if [ "$(uname -s)" != "Linux" ]; then
    fail "Este instalador deve ser executado em um servidor Linux."
  fi

  if ! has_command sudo && [ "$(id -u)" -ne 0 ]; then
    fail "Instale sudo ou execute este comando como root."
  fi

  install_packages
  ensure_python
  prepare_repository
  configure_env
  setup_postgres
  setup_python_app
  setup_service_user
  setup_systemd
  open_firewall

  info "Instalacao nativa concluida."
  printf '\nAcesse: http://SEU_IP:8000/\n'
  printf 'Login padrao: admin / admin\n'
  printf 'Arquivo de configuracao: %s/.env\n' "$PROJECT_DIR"
  printf 'Logs do servico: journalctl -u %s -f\n\n' "$SERVICE_NAME"
  warn "Altere ADMIN_PASSWORD e configure SNMP/Telegram/Asterisk no .env quando necessario."
}

main "$@"
