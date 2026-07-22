# Debian 13 Deployment Notes

Минимальная схема для пилота:

- код проекта: `/opt/wms-pilot`;
- виртуальное окружение: `/opt/wms-pilot/.venv`;
- пользователь systemd-сервиса: `codex-audit` или отдельный `wms`;
- база данных: PostgreSQL;
- внешний доступ: сначала порт `8000`, позже `nginx` reverse proxy.

## Пример установки

```bash
sudo mkdir -p /opt/wms-pilot
sudo chown -R codex-audit:codex-audit /opt/wms-pilot
cd /opt/wms-pilot

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## PostgreSQL

```bash
sudo -u postgres createuser wms
sudo -u postgres createdb -O wms wms
sudo -u postgres psql -c "ALTER USER wms WITH PASSWORD 'change-me';"
```

В `.env`:

```bash
DATABASE_URL=postgresql+psycopg://wms:change-me@127.0.0.1:5432/wms
```

## systemd

`/etc/systemd/system/wms-pilot.service`:

```ini
[Unit]
Description=WMS Pilot Backend
After=network.target postgresql.service

[Service]
User=codex-audit
WorkingDirectory=/opt/wms-pilot
EnvironmentFile=/opt/wms-pilot/.env
ExecStart=/opt/wms-pilot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wms-pilot
sudo systemctl status wms-pilot
```
