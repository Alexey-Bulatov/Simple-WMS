from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter()


def navigation(active: str) -> str:
    links = (
        ("work", "/work", "Рабочее место", False),
        ("terminal", "/terminal", "ТСД", False),
        ("cards", "/cards", "Поиск", False),
        ("demo", "/demo", "Демо", False),
        ("api", "/docs", "API", False),
        ("settings", "/settings", "Настройки", True),
        ("profile", "/profile", "Вход", False),
    )
    return "".join(
        f'<a class="{"active" if key == active else ""}" href="{url}"'
        f'{" data-admin-link hidden" if admin_only else ""}>{label}</a>'
        for key, url, label, admin_only in links
    )


def console_markup() -> str:
    return """
      <section class="queue-panel">
        <div class="panel-head">
          <div><span class="eyebrow">Автоматическая очередь</span><h1>Задания склада</h1></div>
          <button id="refreshTasks" class="icon-button" type="button" title="Обновить" aria-label="Обновить">↻</button>
        </div>
        <div class="queue-summary">
          <div><b id="newCount">0</b><span>Новых</span></div>
          <div><b id="progressCount">0</b><span>В работе</span></div>
          <div><b id="highCount">0</b><span>Срочных</span></div>
        </div>
        <div id="taskList" class="task-list"></div>
      </section>
      <section class="operation-panel">
        <div id="emptyOperation" class="empty-operation">
          <div class="empty-symbol">→</div><h2>Выберите задание</h2>
          <p>Система покажет следующий шаг и примет сканер как клавиатуру.</p>
        </div>
        <div id="activeOperation" hidden>
          <div class="operation-head">
            <div><span id="taskTypeLabel" class="eyebrow">Операция</span><h2 id="taskTitle">—</h2><div id="taskCode" class="mono muted">—</div></div>
            <div class="badge-row"><span id="taskPriority" class="badge">Обычный</span><span id="taskStatus" class="badge">Новое</span></div>
          </div>
          <div class="rail">
            <div class="rail-step done"><span>1</span><b>Задание</b></div>
            <div id="railWork" class="rail-step"><span>2</span><b>Операция</b></div>
            <div id="railDone" class="rail-step"><span>3</span><b>Готово</b></div>
          </div>
          <div id="message" class="message">Нажмите «Начать».</div>
          <div id="objectFacts" class="facts"></div>
          <div id="scanBlock" class="scan-block" hidden>
            <label for="scanInput">Сканер</label>
            <input id="scanInput" class="scan-input mono" autocomplete="off" placeholder="Отсканируйте код">
            <div id="scanHint" class="scan-hint">Ожидается код объекта</div>
          </div>
          <div id="actionBar" class="action-bar"></div>
          <div class="operation-links"><a id="objectCardLink" href="/cards">Открыть карточку</a><button id="releaseTask" class="link-button" type="button">Вернуться в очередь</button></div>
        </div>
      </section>
    """


def document(title: str, body_class: str, body: str, script: str) -> str:
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/static/universal.css"></head><body class="{body_class}">{body}<div id="toast" class="toast" hidden></div><script src="{script}" defer></script><script src="/static/universal-auth-shell.js" defer></script></body></html>"""


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/work")


@router.get("/tasks", include_in_schema=False)
def tasks() -> RedirectResponse:
    return RedirectResponse(url="/work")


@router.get("/work", response_class=HTMLResponse, include_in_schema=False)
def work_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><div class="work-context"><label><span>Склад</span><select id="warehouseSelect"></select></label><label><span>Оператор</span><input id="actorInput" value="Кладовщик" autocomplete="off"></label></div><nav>{navigation("work")}</nav></header>
    <main class="work-console" data-console="work">{console_markup()}</main>
    """
    return document("Рабочее место Simple WMS", "work-page", body, "/static/universal-console.js")


@router.get("/terminal", response_class=HTMLResponse, include_in_schema=False)
def terminal_page() -> str:
    body = f"""
    <header class="product-header desktop-only"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("terminal")}</nav></header>
    <main class="terminal-stage" data-console="terminal"><section class="terminal-device"><div class="device-status"><span id="deviceClock">--:--</span><span>WMS · Wi-Fi · 87%</span></div><div class="terminal-context"><label><span>Склад</span><select id="warehouseSelect"></select></label><label><span>Оператор</span><input id="actorInput" value="tsd-demo" autocomplete="off"></label></div><div class="terminal-console">{console_markup()}</div></section></main>
    """
    return document("Эмулятор ТСД Simple WMS", "terminal-page", body, "/static/universal-console.js")


@router.get("/cards", response_class=HTMLResponse, include_in_schema=False)
def cards_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("cards")}</nav></header>
    <main class="cards-page-main"><aside class="search-panel"><span class="eyebrow">Прослеживаемость</span><h1>Поиск объекта</h1><div id="cardMessage" class="message">Отсканируйте единицу или ячейку.</div><label for="cardCode">Код</label><input id="cardCode" class="scan-input mono" autocomplete="off" autofocus placeholder="PLT-... / WH01-..."><div class="segmented"><button class="active" data-card-kind="auto" type="button">Авто</button><button data-card-kind="unit" type="button">Единица</button><button data-card-kind="location" type="button">Ячейка</button></div><button id="openCard" class="primary" type="button">Открыть</button><div class="quick-head"><b>Быстрый список</b><select id="cardWarehouse"></select></div><div class="segmented"><button id="listUnits" class="active" type="button">Единицы</button><button id="listLocations" type="button">Ячейки</button></div><div id="quickList" class="quick-list"></div></aside><section id="cardView" class="card-view"><div class="empty-operation"><div class="empty-symbol">i</div><h2>Карточка не выбрана</h2><p>Здесь будут состав, местонахождение, задания и история.</p></div></section></main>
    """
    return document("Карточки Simple WMS", "cards-page", body, "/static/universal-cards.js")


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("demo")}</nav></header>
    <main class="demo-page-main">
      <section class="demo-form-panel">
        <div class="panel-head"><div><span class="eyebrow">Подготовка контура</span><h1>Демонстрационный склад</h1></div></div>
        <form id="demoForm" class="demo-form">
          <div class="form-grid">
            <label><span>Код склада</span><input id="demoWarehouseCode" class="mono" value="WH01" maxlength="32" required></label>
            <label><span>Название склада</span><input id="demoWarehouseName" value="Основной демонстрационный склад" maxlength="160" required></label>
            <label><span>Ячеек хранения</span><input id="demoStorageLocations" type="number" value="10" min="1" max="80" required></label>
            <label><span>Внешних единиц</span><input id="demoQuantity" type="number" value="5" min="1" max="50" required></label>
            <label><span>Внешняя единица</span><select id="demoParentType" required></select></label>
            <label><span>Вложенная тара</span><select id="demoChildType"></select></label>
            <label><span>Вложенных единиц</span><input id="demoChildren" type="number" value="4" min="1" max="40" required></label>
            <label><span>Единица содержимого</span><select id="demoContentUom" required></select></label>
            <label><span>Количество в единице</span><input id="demoContentQuantity" type="number" value="24" min="0.000001" step="0.000001" required></label>
            <label><span>Автор операции</span><input id="demoActor" value="demo-generator" maxlength="80" required></label>
          </div>
          <label class="check-row"><input id="demoPlace" type="checkbox" checked><span>Разместить в свободные ячейки</span></label>
          <button id="generateDemo" class="primary" type="submit">Сформировать данные</button>
        </form>
      </section>
      <section class="demo-result-panel">
        <div class="panel-head"><div><span class="eyebrow">Результат запуска</span><h2>Состояние генератора</h2></div></div>
        <div id="demoMessage" class="message">Данные ещё не формировались.</div>
        <div id="demoFacts" class="facts demo-facts"></div>
        <div class="demo-result-list"><h3>Созданные логистические единицы</h3><div id="demoUnits" class="data-list"><div class="data-row">Список появится после запуска.</div></div></div>
      </section>
    </main>
    """
    return document("Демо-данные Simple WMS", "demo-page", body, "/static/universal-demo.js")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page() -> str:
    body = """
    <main class="auth-stage">
      <section class="auth-panel">
        <a class="brand auth-brand" href="/work">Simple WMS</a>
        <div class="auth-heading"><span class="eyebrow">Рабочая сессия</span><h1>Вход</h1></div>
        <div class="segmented auth-tabs"><button class="active" data-auth-tab="password" type="button">Логин и пароль</button><button data-auth-tab="pass" type="button">QR / штрихкод</button></div>
        <form id="passwordLogin" class="auth-form">
          <label><span>Логин</span><input id="loginUsername" autocomplete="username" required autofocus></label>
          <label><span>Пароль</span><input id="loginPassword" type="password" autocomplete="current-password" required></label>
          <label><span>Рабочее место</span><input id="loginWorkstation" class="mono" autocomplete="off" placeholder="Необязательно"></label>
          <button class="primary" type="submit">Войти</button>
        </form>
        <form id="passLogin" class="auth-form" hidden>
          <label><span>Код пропуска</span><input id="loginAccessCode" class="scan-input mono" autocomplete="off" required></label>
          <label><span>Рабочее место</span><input id="passWorkstation" class="mono" autocomplete="off" required></label>
          <button class="primary" type="submit">Войти по коду</button>
        </form>
        <div id="authMessage" class="message">Введите учётные данные.</div>
      </section>
    </main>
    """
    return document("Вход в Simple WMS", "auth-page", body, "/static/universal-auth.js")


@router.get("/profile", response_class=HTMLResponse, include_in_schema=False)
def profile_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("profile")}</nav></header>
    <main class="profile-main">
      <section class="profile-panel">
        <div class="panel-head"><div><span class="eyebrow">Текущая сессия</span><h1 id="profileName">Пользователь</h1><div id="profileLogin" class="mono muted"></div></div><button id="logoutButton" type="button">Выйти</button></div>
        <div id="profileFacts" class="facts"></div>
      </section>
      <section class="profile-panel">
        <div class="panel-head"><div><span class="eyebrow">Персональный код</span><h2>Пропуск для рабочего места</h2></div></div>
        <form id="issuePassForm" class="auth-form compact-auth-form">
          <label><span>Рабочее место</span><select id="profileWorkstation" required></select></label>
          <label><span>Подтвердите пароль</span><input id="profilePassword" type="password" autocomplete="current-password" required></label>
          <button class="primary" type="submit">Выпустить новый код</button>
        </form>
        <div id="issuedPass" class="issued-pass" hidden><span>Новый код</span><strong id="issuedPassCode" class="mono"></strong></div>
        <div id="profileMessage" class="message">Действующий код повторно не показывается.</div>
      </section>
      <section class="profile-panel profile-panel-wide">
        <div class="panel-head"><div><span class="eyebrow">Безопасность</span><h2>Сменить пароль</h2></div></div>
        <form id="passwordChangeForm" class="auth-form compact-auth-form">
          <label><span>Текущий пароль</span><input id="currentPassword" type="password" autocomplete="current-password" required></label>
          <label><span>Новый пароль</span><input id="newPassword" type="password" autocomplete="new-password" minlength="10" required></label>
          <label><span>Повторите новый пароль</span><input id="repeatPassword" type="password" autocomplete="new-password" minlength="10" required></label>
          <button class="primary" type="submit">Сменить пароль</button>
        </form>
        <div id="passwordMessage" class="message">После сброса администратором пароль необходимо сменить до складских операций.</div>
      </section>
    </main>
    """
    return document("Профиль Simple WMS", "profile-page", body, "/static/universal-auth.js")


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("settings")}</nav></header>
    <main class="settings-main">
      <div class="settings-title"><div><span class="eyebrow">Администрирование</span><h1>Настройки системы</h1></div><div id="settingsMessage" class="message">Загрузка данных...</div></div>
      <div class="settings-tabs" role="tablist">
        <button class="active" data-settings-tab="warehouses" type="button">Склады</button>
        <button data-settings-tab="users" type="button">Пользователи</button>
        <button data-settings-tab="workstations" type="button">Рабочие места</button>
        <button data-settings-tab="equipment" type="button">Оборудование</button>
      </div>

      <section class="settings-view" data-settings-view="warehouses">
        <form id="warehouseForm" class="settings-form-panel">
          <div class="panel-head"><div><span class="eyebrow">Справочник</span><h2 id="warehouseFormTitle">Новый склад</h2></div></div>
          <div class="settings-form-body">
            <input id="warehouseId" type="hidden">
            <label><span>Код</span><input id="warehouseCode" class="mono" value="WH01" maxlength="32" required></label>
            <label><span>Название</span><input id="warehouseName" value="Основной склад" maxlength="160" required></label>
            <label><span>Город</span><input id="warehouseCity" maxlength="120"></label>
            <label><span>Часовой пояс</span><input id="warehouseTimezone" value="Europe/Moscow" maxlength="80" required></label>
            <div class="form-actions"><button class="primary" type="submit">Сохранить</button><button id="warehouseReset" type="button">Очистить</button></div>
          </div>
        </form>
        <section class="settings-list-panel"><div class="panel-head"><div><span class="eyebrow">Доступные склады</span><h2>Склады</h2></div></div><div id="warehouseList" class="settings-list"></div></section>
      </section>

      <section class="settings-view" data-settings-view="users" hidden>
        <form id="userForm" class="settings-form-panel">
          <div class="panel-head"><div><span class="eyebrow">Учётная запись</span><h2 id="userFormTitle">Новый пользователь</h2></div></div>
          <div class="settings-form-body">
            <input id="userId" type="hidden">
            <label><span>Логин</span><input id="userUsername" autocomplete="off" maxlength="80" required></label>
            <label><span>ФИО</span><input id="userFullName" maxlength="160" required></label>
            <label><span>Роль</span><select id="userRole" required>
              <option value="warehouse_clerk">Кладовщик</option><option value="receiving_clerk">Оператор приёмки</option><option value="shipping_operator">Оператор отгрузки</option><option value="production_operator">Оператор производства</option><option value="senior_clerk">Старший кладовщик</option><option value="warehouse_manager">Руководитель склада</option><option value="auditor">Аудитор</option><option value="integration">Интеграция</option><option value="admin">Администратор</option>
            </select></label>
            <fieldset class="settings-fieldset"><legend>Полномочия роли</legend><div id="userPermissions" class="permission-list"></div></fieldset>
            <label id="userPasswordLabel"><span>Временный пароль</span><input id="userPassword" type="password" minlength="10" autocomplete="new-password"></label>
            <fieldset class="settings-fieldset"><legend>Доступные склады</legend><div id="userWarehouses" class="check-grid"></div></fieldset>
            <label id="userDefaultWarehouseLabel"><span>Склад по умолчанию</span><select id="userDefaultWarehouse"><option value="">Не выбран</option></select></label>
            <label class="check-row"><input id="userActive" type="checkbox" checked><span>Пользователь активен</span></label>
            <div class="form-actions"><button class="primary" type="submit">Сохранить</button><button id="userReset" type="button">Очистить</button></div>
          </div>
        </form>
        <section class="settings-list-panel"><div class="panel-head"><div><span class="eyebrow">Безопасность</span><h2>Пользователи</h2></div></div><div id="userList" class="settings-list"></div></section>
      </section>

      <section class="settings-view" data-settings-view="workstations" hidden>
        <form id="workstationForm" class="settings-form-panel">
          <div class="panel-head"><div><span class="eyebrow">Точка входа</span><h2 id="workstationFormTitle">Новое рабочее место</h2></div></div>
          <div class="settings-form-body">
            <input id="workstationId" type="hidden">
            <label><span>Код</span><input id="workstationCode" class="mono" maxlength="64" required></label>
            <label><span>Название</span><input id="workstationName" maxlength="160" required></label>
            <label><span>Склад</span><select id="workstationWarehouse" required></select></label>
            <label class="check-row"><input id="workstationPass" type="checkbox" checked><span>Разрешить вход по QR/штрихкоду</span></label>
            <label class="check-row"><input id="workstationActive" type="checkbox" checked><span>Рабочее место активно</span></label>
            <div class="form-actions"><button class="primary" type="submit">Сохранить</button><button id="workstationReset" type="button">Очистить</button></div>
          </div>
        </form>
        <section class="settings-list-panel"><div class="panel-head"><div><span class="eyebrow">Авторизация</span><h2>Рабочие места</h2></div></div><div id="workstationList" class="settings-list"></div></section>
      </section>

      <section class="settings-view" data-settings-view="equipment" hidden>
        <form id="equipmentForm" class="settings-form-panel settings-form-wide">
          <div class="panel-head"><div><span class="eyebrow">Подключение</span><h2 id="equipmentFormTitle">Новый профиль оборудования</h2></div></div>
          <div class="settings-form-body settings-form-grid">
            <input id="equipmentId" type="hidden">
            <label><span>Код</span><input id="equipmentCode" class="mono" maxlength="48" required></label>
            <label><span>Название</span><input id="equipmentName" maxlength="160" required></label>
            <label><span>Тип</span><select id="equipmentKind"><option value="printer">Принтер</option><option value="scanner">Сканер</option><option value="terminal">ТСД</option><option value="scale">Весы</option><option value="other">Другое</option></select></label>
            <label><span>Подключение</span><select id="equipmentConnection"><option value="raw_tcp">RAW TCP</option><option value="pdf">PDF</option><option value="system_queue">Системная очередь</option><option value="keyboard">Клавиатура</option><option value="camera">Камера</option><option value="web">Веб</option><option value="serial">COM / Serial</option><option value="usb">USB</option></select></label>
            <label><span>Производитель</span><input id="equipmentManufacturer" maxlength="120"></label>
            <label><span>Модель</span><input id="equipmentModel" maxlength="120"></label>
            <label><span>Склад</span><select id="equipmentWarehouse"><option value="">Общий профиль</option></select></label>
            <label><span>Драйвер</span><input id="equipmentDriver" class="mono" maxlength="80"></label>
            <label data-connection-field="network"><span>IP / имя хоста</span><input id="equipmentHost" maxlength="255"></label>
            <label data-connection-field="network"><span>Порт</span><input id="equipmentPort" type="number" min="1" max="65535"></label>
            <label data-connection-field="queue"><span>Очередь печати</span><input id="equipmentQueue" maxlength="120"></label>
            <label data-connection-field="serial"><span>Устройство</span><input id="equipmentSerial" class="mono" maxlength="160" placeholder="/dev/ttyUSB0"></label>
            <label class="settings-span"><span>Дополнительные параметры JSON</span><textarea id="equipmentParameters" rows="3">{{}}</textarea></label>
            <label class="check-row"><input id="equipmentDefault" type="checkbox"><span>Использовать по умолчанию</span></label>
            <label class="check-row"><input id="equipmentActive" type="checkbox" checked><span>Профиль активен</span></label>
            <div class="form-actions settings-span"><button class="primary" type="submit">Сохранить</button><button id="equipmentReset" type="button">Очистить</button></div>
          </div>
        </form>
        <section class="settings-list-panel"><div class="panel-head"><div><span class="eyebrow">Устройства</span><h2>Профили оборудования</h2></div></div><div id="equipmentList" class="settings-list"></div></section>
      </section>
    </main>
    """
    return document("Настройки Simple WMS", "settings-page", body, "/static/universal-settings.js")
