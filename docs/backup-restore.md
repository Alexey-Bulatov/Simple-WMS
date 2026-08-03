# Резервное копирование Simple WMS

## Автоматические копии

Таймер `simple-wms-backup.timer` ежедневно запускает `pg_dump` в custom-формате.
Готовый архив появляется в `/var/backups/simple-wms` только после успешной проверки
командой `pg_restore --list`. Автоматические файлы хранятся 14 дней.

Проверка состояния:

```bash
systemctl status simple-wms-backup.timer
systemctl list-timers simple-wms-backup.timer
journalctl -u simple-wms-backup.service
ls -lh /var/backups/simple-wms
```

Ручной запуск:

```bash
sudo systemctl start simple-wms-backup.service
```

## Проверка восстановления

Восстановление следует сначала проверять в отдельной базе, не поверх рабочего контура:

```bash
sudo install -o postgres -g postgres -m 600 \
  /var/backups/simple-wms/simple-wms-YYYYMMDDTHHMMSSZ.dump \
  /var/lib/postgresql/simple-wms-restore.dump
sudo -u postgres createdb -O wms wms_restore_test
sudo -u postgres pg_restore \
  --dbname=wms_restore_test \
  --no-owner \
  --role=wms \
  /var/lib/postgresql/simple-wms-restore.dump
sudo -u postgres psql -d wms_restore_test -c '\dt'
```

После проверки тестовую базу можно удалить:

```bash
sudo -u postgres dropdb wms_restore_test
sudo unlink /var/lib/postgresql/simple-wms-restore.dump
```

Перед восстановлением рабочего контура необходимо остановить `simple-wms.service`,
создать отдельную страховочную копию текущего состояния и только затем переключать базу.
