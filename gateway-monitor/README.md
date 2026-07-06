# Gateway Monitor

Gateway Monitor e uma aplicacao FastAPI preparada para monitoramento de gateway.
Esta entrega cobre infraestrutura, leitura SNMP, atualizacao em tempo real,
gravacao de mudancas de estado, historico em PostgreSQL, alertas Telegram,
integracao Asterisk AMI e uma base de plataforma profissional.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL
- Docker e Docker Compose
- Jinja2
- Bootstrap 5
- WebSocket para atualizacao das linhas do gateway
- PySNMP
- Telegram Bot API para alertas de congestionamento
- Asterisk AMI para chamadas em tempo real
- Login por sessao assinada
- Relatorios PDF e Excel
- Prometheus metrics
- Base multi-gateway

## Estrutura

```text
gateway-monitor/
  app/
    routers/
    services/
    models/
    schemas/
    templates/
    static/
    main.py
    config.py
    database.py
  alembic/
  logs/
  tests/
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
```

## Instalacao em um comando no Linux

Em um servidor Ubuntu/Debian limpo, execute:

```bash
curl -fsSL https://raw.githubusercontent.com/rodrigsilvabjm/monitor-ATA/main/install.sh | bash
```

O instalador cria a aplicacao em `/opt/gateway-monitor`, instala Docker quando
necessario, gera uma `SECRET_KEY`, cria o `.env` inicial e sobe os containers.

Para usar outro diretorio:

```bash
APP_DIR=/srv/gateway-monitor curl -fsSL https://raw.githubusercontent.com/rodrigsilvabjm/monitor-ATA/main/install.sh | bash
```

Depois da instalacao, edite:

```text
/opt/gateway-monitor/src/gateway-monitor/.env
```

Altere principalmente `ADMIN_PASSWORD`, `SNMP_HOST`, Telegram e Asterisk.

## Instalacao local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Para executar localmente sem Docker, ajuste `POSTGRES_HOST` no `.env` para
`localhost` e tenha um PostgreSQL disponivel.

## Execucao com Docker

```bash
cp .env.example .env
docker compose up -d --build
```

A aplicacao ficara disponivel em:

- Pagina inicial: http://localhost:8000/
- Health check: http://localhost:8000/health
- API status: http://localhost:8000/api/status
- API linhas: http://localhost:8000/api/lines
- API historico: http://localhost:8000/api/events
- WebSocket linhas: ws://localhost:8000/ws/gateway-lines
- Dashboard TV: http://localhost:8000/tv
- Prometheus: http://localhost:8000/metrics

## Migracoes

As migrations rodam automaticamente quando o container da aplicacao sobe.

Para executar manualmente:

```bash
docker compose exec app alembic upgrade head
```

Para criar uma nova migration no futuro:

```bash
docker compose exec app alembic revision --autogenerate -m "descricao"
```

## Banco de dados

Tabela inicial:

```text
gateway_events
  id
  created_at
  busy_lines
  idle_lines
  event_type
  duration
  message
```

## Logs

Os logs da aplicacao ficam em:

```text
logs/application.log
```

A rotacao automatica mantem ate 5 arquivos de 5 MB.

## SNMP

A leitura SNMP consulta o gateway a cada 1 segundo e atualiza a tela em tempo
real via WebSocket.

A MIB Synway foi adicionada em:

```text
app/mibs/SYNWAY-GW-MIB.txt
```

Configure o `.env`:

```env
SNMP_ENABLED=true
SNMP_HOST=192.168.0.1
SNMP_PORT=161
SNMP_COMMUNITY=public
SNMP_VERSION=2c
SNMP_TIMEOUT=1
SNMP_RETRIES=0
SNMP_POLL_INTERVAL=1
SNMP_MIB_DIR=app/mibs
SNMP_MIB_NAME=SYNWAY-GW-MIB
GATEWAY_MONITORED_LINES=1,2,3,4
SNMP_LINE_1_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.1
SNMP_LINE_2_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.2
SNMP_LINE_3_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.3
SNMP_LINE_4_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.4
SNMP_LINE_5_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.5
SNMP_LINE_6_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.6
SNMP_LINE_7_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.7
SNMP_LINE_8_OID=.1.3.6.1.4.1.39871.1.2.1.1.9.8
```

O campo usado e `chUsingNum` da tabela `pstnStatusTable`. Valor `0` indica
linha livre; valor maior que `0` indica linha ocupada.

O alerta de congestionamento considera somente as linhas em
`GATEWAY_MONITORED_LINES`. Nesta instalacao, as linhas 5 a 8 estao desativadas.

## Historico

A Sprint 3 grava eventos na tabela `gateway_events`:

- `state_change`: uma ou mais linhas mudaram de estado.
- `congestion_start`: todas as linhas monitoradas ficaram ocupadas.
- `congestion_end`: ao menos uma linha voltou a ficar livre, com duracao em segundos.

Consultar historico:

```bash
curl http://localhost:8000/api/events
```

## Telegram

A Sprint 4 envia alertas somente quando o estado de congestionamento muda:

- Todas as linhas monitoradas ficam ocupadas: envia alerta de inicio.
- O congestionamento termina: envia alerta com duracao.

Configure no `.env`:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=000000000:token_do_bot
TELEGRAM_CHAT_ID=123456789
TELEGRAM_TIMEOUT=5
```

Mensagem de inicio:

```text
🚨 Gateway Monitor

Todas as linhas estão ocupadas.

Data:
06/07/2026

Hora:
09:32:41
```

Mensagem de fim:

```text
✅ Congestionamento encerrado

Duração

3 minutos e 12 segundos
```

## Asterisk AMI

A Sprint 6 adiciona conexao com o Asterisk AMI para exibir chamadas em tempo
real no dashboard.

Configure no `.env`:

```env
ASTERISK_AMI_ENABLED=true
ASTERISK_AMI_HOST=127.0.0.1
ASTERISK_AMI_PORT=5038
ASTERISK_AMI_USERNAME=usuario_ami
ASTERISK_AMI_PASSWORD=senha_ami
ASTERISK_AMI_TIMEOUT=5
ASTERISK_AMI_RECONNECT_DELAY=5
```

Dados exibidos:

- numero de origem;
- numero de destino;
- ramal que atendeu;
- duracao da chamada;
- linha FXO utilizada;
- chamadas simultaneas;
- tempo medio;
- chamadas perdidas.

Endpoints:

```text
GET /api/asterisk
WS  /ws/asterisk
```

## Backup

Criar backup do PostgreSQL:

```bash
docker compose exec db pg_dump -U gateway_user gateway_monitor > backup.sql
```

Restaurar backup:

```bash
docker compose exec -T db psql -U gateway_user gateway_monitor < backup.sql
```

Se voce alterar usuario, senha ou nome do banco no `.env`, ajuste os comandos.

## Atualizacao

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose exec app alembic upgrade head
```

## Testes

```bash
pytest
```

## Login

Configure no `.env`:

```env
SECRET_KEY=troque-esta-chave
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
SESSION_DURATION_MINUTES=480
```

O dashboard principal `/` exige login. O dashboard para TV fica em `/tv`.

## Plataforma

Relatorios:

```text
GET /api/reports/pdf
GET /api/reports/excel
```

Multi-gateway:

```text
GET  /api/gateways
POST /api/gateways
```

Prometheus:

```text
GET /metrics
GET /api/metrics
```

Backup automatico de eventos:

```env
BACKUP_ENABLED=true
BACKUP_INTERVAL_MINUTES=60
BACKUP_DIR=backups
```

## Variaveis de ambiente

Todas as configuracoes sao carregadas pelo `.env` usando Pydantic Settings.
Use `.env.example` como referencia.
