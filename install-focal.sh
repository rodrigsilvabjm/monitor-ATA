#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/rodrigsilvabjm/monitor-ATA.git}"
APP_DIR="${APP_DIR:-/opt/gateway-monitor}"
APP_SUBDIR="${APP_SUBDIR:-gateway-monitor}"
SERVICE_NAME="${SERVICE_NAME:-gateway-monitor}"
SERVICE_USER="${SERVICE_USER:-gateway-monitor}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
PYTHON_PATCH_VERSION="${PYTHON_PATCH_VERSION:-3.11.9}"
PYTHON_PREFIX="${PYTHON_PREFIX:-/opt/python-$PYTHON_VERSION}"

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

install_packages() {
  info "Instalando pacotes base..."
  as_root apt-get update
  as_root apt-get install -y \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnupg \
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libpq-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    libxml2-dev \
    libxmlsec1-dev \
    openssl \
    postgresql \
    postgresql-contrib \
    software-properties-common \
    tk-dev \
    uuid-dev \
    wget \
    xz-utils \
    zlib1g-dev
}

configure_deadsnakes() {
  info "Configurando repositorio deadsnakes para Python $PYTHON_VERSION..."
  as_root add-apt-repository -y ppa:deadsnakes/ppa || true
  as_root apt-get update
}

install_python() {
  if has_command "python$PYTHON_VERSION"; then
    PYTHON_BIN="python$PYTHON_VERSION"
    return
  fi

  if [ -x "$PYTHON_PREFIX/bin/python$PYTHON_VERSION" ]; then
    PYTHON_BIN="$PYTHON_PREFIX/bin/python$PYTHON_VERSION"
    return
  fi

  configure_deadsnakes

  info "Instalando Python $PYTHON_VERSION..."
  if as_root apt-get install -y \
    "python$PYTHON_VERSION" \
    "python$PYTHON_VERSION-dev" \
    "python$PYTHON_VERSION-venv"; then
    PYTHON_BIN="python$PYTHON_VERSION"
    return
  fi

  warn "Python $PYTHON_VERSION nao esta disponivel no APT. Compilando Python $PYTHON_PATCH_VERSION..."
  build_python_from_source
  PYTHON_BIN="$PYTHON_PREFIX/bin/python$PYTHON_VERSION"
}

build_python_from_source() {
  BUILD_DIR="/tmp/Python-$PYTHON_PATCH_VERSION"
  TARBALL="/tmp/Python-$PYTHON_PATCH_VERSION.tgz"

  if [ ! -x "$PYTHON_PREFIX/bin/python$PYTHON_VERSION" ]; then
    curl -fsSL "https://www.python.org/ftp/python/$PYTHON_PATCH_VERSION/Python-$PYTHON_PATCH_VERSION.tgz" -o "$TARBALL"
    rm -rf "$BUILD_DIR"
    tar -xzf "$TARBALL" -C /tmp

    cd "$BUILD_DIR"
    ./configure --prefix="$PYTHON_PREFIX" --with-ensurepip=install
    make -j"$(nproc)"
    as_root make altinstall
  fi

  "$PYTHON_PREFIX/bin/python$PYTHON_VERSION" -m ensurepip --upgrade
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

  warn "Instalador focal: usando Python $PYTHON_VERSION para evitar pacote quebrado python3.12 neste Ubuntu."
  install_packages
  install_python
  prepare_repository
  configure_env
  setup_postgres
  setup_python_app
  setup_service_user
  setup_systemd
  open_firewall

  info "Instalacao concluida."
  printf '\nAcesse: http://SEU_IP:8000/\n'
  printf 'Login padrao: admin / admin\n'
  printf 'Arquivo de configuracao: %s/.env\n' "$PROJECT_DIR"
  printf 'Logs do servico: journalctl -u %s -f\n\n' "$SERVICE_NAME"
  warn "Altere ADMIN_PASSWORD e configure SNMP/Telegram/Asterisk no .env quando necessario."
}

main "$@"
