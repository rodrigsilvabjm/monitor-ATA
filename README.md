# Monitor ATA - Gateway Monitor

Aplicacao FastAPI para monitoramento de gateway ATA/FXO com PostgreSQL,
SNMP, alertas, dashboard em tempo real e base para integracao Asterisk.

## Instalacao rapida em servidor Linux

Em Ubuntu/Debian, execute:

```bash
curl -fsSL https://raw.githubusercontent.com/rodrigsilvabjm/monitor-ATA/main/install.sh | bash
```

O instalador baixa o projeto em `/opt/gateway-monitor`, instala Docker quando
necessario, cria o `.env` inicial e sobe os containers.

Depois da instalacao, ajuste as configuracoes:

```bash
nano /opt/gateway-monitor/src/gateway-monitor/.env
cd /opt/gateway-monitor/src/gateway-monitor
docker compose up -d --build
```

Documentacao completa: [gateway-monitor/README.md](gateway-monitor/README.md)

## Instalacao sem Docker

Se o servidor for VPS/LXC/OpenVZ e negar montagem de `/proc` para containers,
use a instalacao nativa com PostgreSQL local e systemd:

```bash
curl -fsSL https://raw.githubusercontent.com/rodrigsilvabjm/monitor-ATA/main/install-native.sh | bash
```

Para Ubuntu 20.04 `focal` com problemas nos pacotes `python3.12`, use:

```bash
curl -fsSL https://raw.githubusercontent.com/rodrigsilvabjm/monitor-ATA/main/install-focal.sh | bash
```
