# Резервное копирование WMS Pilot

## Автоматические копии

Таймер `wms-pilot-backup.timer` ежедневно запускает `pg_dump` в custom-формате.
Готовый архив появляется в `/var/backups/wms-pilot` только после успешной проверки
командой `pg_restore --list`. Автоматические файлы хранятся 14 дней.

Проверка состояния:

```bash
systemctl status wms-pilot-backup.timer
systemctl list-timers wms-pilot-backup.timer
journalctl -u wms-pilot-backup.service
ls -lh /var/backups/wms-pilot
```

Ручной запуск:

```bash
sudo systemctl start wms-pilot-backup.service
```

## Проверка восстановления

Восстановление следует сначала проверять в отдельной базе, не поверх рабочего контура:

```bash
sudo install -o postgres -g postgres -m 600 \
  /var/backups/wms-pilot/wms-pilot-YYYYMMDDTHHMMSSZ.dump \
  /var/lib/postgresql/wms-pilot-restore.dump
sudo -u postgres createdb -O wms_pilot wms_pilot_restore_test
sudo -u postgres pg_restore \
  --dbname=wms_pilot_restore_test \
  --no-owner \
  --role=wms_pilot \
  /var/lib/postgresql/wms-pilot-restore.dump
sudo -u postgres psql -d wms_pilot_restore_test -c '\dt'
```

После проверки тестовую базу можно удалить:

```bash
sudo -u postgres dropdb wms_pilot_restore_test
sudo unlink /var/lib/postgresql/wms-pilot-restore.dump
```

Перед восстановлением рабочего контура необходимо остановить `wms-pilot.service`,
создать отдельную страховочную копию текущего состояния и только затем переключать базу.
