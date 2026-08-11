# Развёртывание Simple WMS на Debian 13

Минимальная схема для тестового или небольшого рабочего контура:

- код проекта: `/opt/simple-wms`;
- виртуальное окружение: `/opt/simple-wms/.venv`;
- пользователь systemd-сервиса: `codex-audit` или отдельный `wms`;
- база данных: PostgreSQL;
- внешний доступ: сначала порт `8000`, позже `nginx` reverse proxy.

## Пример установки

```bash
sudo useradd --system --create-home --home-dir /opt/simple-wms --shell /usr/sbin/nologin wms
sudo mkdir -p /opt/simple-wms
sudo chown -R wms:wms /opt/simple-wms
cd /opt/simple-wms

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
AUTH_ENFORCEMENT_ENABLED=false
AUTH_COOKIE_SECURE=false
```

Для внешнего HTTPS-контура установите `AUTH_COOKIE_SECURE=true`.

## systemd

`/etc/systemd/system/simple-wms.service`:

```ini
[Unit]
Description=Simple WMS
After=network.target postgresql.service

[Service]
User=wms
WorkingDirectory=/opt/simple-wms
EnvironmentFile=/opt/simple-wms/.env
ExecStart=/opt/simple-wms/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now simple-wms
sudo systemctl status simple-wms
```

## Первоначальный администратор

После миграции сначала оставьте `AUTH_ENFORCEMENT_ENABLED=false` и один раз
создайте администратора локальным запросом с самого сервера:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","full_name":"Администратор WMS","password":"replace-with-a-long-password"}'
```

Без `AUTH_BOOTSTRAP_TOKEN` такой запрос принимается только с loopback-интерфейса.
После успешного ответа включите обязательный режим и перезапустите приложение:

```bash
sed -i 's/^AUTH_ENFORCEMENT_ENABLED=.*/AUTH_ENFORCEMENT_ENABLED=true/' .env
sudo systemctl restart simple-wms
```

Проверьте вход на `/login`, затем создайте рабочие места и назначьте
пользователям склады через `/docs`. В контуре без TLS оставляйте cookie без
флага `Secure` только внутри доверенной локальной сети.
