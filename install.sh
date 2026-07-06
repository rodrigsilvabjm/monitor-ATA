#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/rodrigsilvabjm/monitor-ATA.git}"
APP_DIR="${APP_DIR:-/opt/gateway-monitor}"
APP_SUBDIR="${APP_SUBDIR:-gateway-monitor}"

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

install_base_packages() {
  detect_os

  case "$OS_ID" in
    ubuntu|debian)
      info "Instalando pacotes basicos..."
      as_root apt-get update
      as_root apt-get install -y ca-certificates curl git openssl
      ;;
    *)
      fail "Instalacao automatica suportada para Ubuntu/Debian. Instale Docker, Compose, Git e rode novamente."
      ;;
  esac
}

install_docker() {
  if has_command docker && docker compose version >/dev/null 2>&1; then
    info "Docker e Docker Compose ja estao instalados."
    return
  fi

  install_base_packages
  info "Instalando Docker..."

  case "$OS_ID" in
    ubuntu|debian)
      if [ -z "$OS_CODENAME" ] && has_command lsb_release; then
        OS_CODENAME="$(lsb_release -cs)"
      fi

      [ -n "$OS_CODENAME" ] || fail "Nao foi possivel detectar a versao do Ubuntu/Debian."

      ARCH="$(dpkg --print-architecture)"
      as_root install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" | as_root tee /etc/apt/keyrings/docker.asc >/dev/null
      as_root chmod a+r /etc/apt/keyrings/docker.asc

      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "$ARCH" "$OS_ID" "$OS_CODENAME" | as_root tee /etc/apt/sources.list.d/docker.list >/dev/null

      as_root apt-get update
      if ! as_root apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin; then
        warn "docker-buildx-plugin indisponivel. Tentando instalar Docker sem Buildx..."
        as_root apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      fi
      ;;
    *)
      fail "Instalacao automatica do Docker suportada para Ubuntu/Debian."
      ;;
  esac

  docker_compose version >/dev/null 2>&1 || fail "Docker Compose nao ficou disponivel apos a instalacao."
}

docker_compose() {
  if docker ps >/dev/null 2>&1; then
    docker compose "$@"
  else
    as_root docker compose "$@"
  fi
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

  sed -i 's/^POSTGRES_HOST=.*/POSTGRES_HOST=db/' .env
}

start_application() {
  cd "$APP_DIR/src/$APP_SUBDIR"
  info "Subindo containers..."
  COMPOSE_BAKE=false COMPOSE_DOCKER_CLI_BUILD=0 DOCKER_BUILDKIT=0 docker_compose up -d --build
}

main() {
  if [ "$(uname -s)" != "Linux" ]; then
    fail "Este instalador deve ser executado em um servidor Linux."
  fi

  if ! has_command sudo && [ "$(id -u)" -ne 0 ]; then
    fail "Instale sudo ou execute este comando como root."
  fi

  install_docker
  prepare_repository
  configure_env
  start_application

  info "Instalacao concluida."
  printf '\nAcesse: http://SEU_IP:8000/\n'
  printf 'Login padrao: admin / admin\n'
  printf 'Arquivo de configuracao: %s/src/%s/.env\n\n' "$APP_DIR" "$APP_SUBDIR"
  warn "Altere a senha ADMIN_PASSWORD e configure SNMP/Telegram/Asterisk no .env quando necessario."
}

main "$@"
