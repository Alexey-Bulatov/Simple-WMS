from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter()


def navigation(active: str) -> str:
    links = (
        ("work", "/work", "Рабочее место", False),
        ("terminal", "/terminal", "ТСД", False),
        ("stock", "/stock", "Номенклатура", False),
        ("cards", "/cards", "Объекты", False),
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
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/static/universal.css?v=20260813-2"></head><body class="{body_class}">{body}<div id="toast" class="toast" hidden></div><script src="{script}?v=20260814-2" defer></script><script src="/static/universal-auth-shell.js?v=20260814-1" defer></script></body></html>"""


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


@router.get("/stock", response_class=HTMLResponse, include_in_schema=False)
def stock_page() -> str:
    body = f"""
    <header class="product-header"><a class="brand" href="/work">Simple WMS</a><nav>{navigation("stock")}</nav></header>
    <main class="stock-page-main">
      <section class="stock-search-panel">
        <div class="panel-head"><div><span class="eyebrow">SCN-02</span><h1>Номенклатура и остатки</h1></div><button id="newProduct" class="secondary" type="button" hidden>Новая позиция</button></div>
        <form id="stockSearchForm" class="stock-search-form">
          <label><span>Склад</span><select id="stockWarehouse"><option value="">Все доступные склады</option></select></label>
          <label><span>Название, артикул или штрихкод</span><input id="stockQuery" class="scan-input" autocomplete="off" autofocus placeholder="Например, перчатки"></label>
          <button class="primary" type="submit">Найти</button>
        </form>
        <div id="stockSearchMessage" class="message">Введите название, код или отсканируйте упаковку.</div>
        <div id="stockSearchResults" class="stock-search-results"></div>
      </section>
      <section id="stockDetail" class="stock-detail-panel">
        <div class="empty-operation"><div class="empty-symbol">i</div><h2>Номенклатура не выбрана</h2><p>Здесь появятся общий и доступный остаток, ячейки, логистические единицы и партии.</p></div>
      </section>
      <section id="issuePanel" class="issue-panel" hidden>
        <div class="panel-head"><div><span class="eyebrow">SCN-08</span><h2>Внутренняя выдача</h2></div><button id="closeIssue" class="icon-button" type="button" title="Закрыть" aria-label="Закрыть">×</button></div>
        <div class="rail"><div class="rail-step done"><span>1</span><b>Источник</b></div><div class="rail-step active"><span>2</span><b>Получатель</b></div><div class="rail-step"><span>3</span><b>Проведение</b></div></div>
        <div id="issueFacts" class="facts"></div>
        <form id="issueForm" class="issue-form">
          <label><span>Получатель</span><select id="issueRecipient" required></select></label>
          <label><span>Вид выдачи</span><select id="issueKind" required><option value="permanent">Без возврата</option><option value="accountable:return_required">Под ответственность · вернуть</option><option value="accountable:normative_writeoff">Под ответственность · списать по нормативу</option></select></label>
          <label><span>Количество</span><input id="issueQuantity" type="number" min="0.000001" step="0.000001" required></label>
          <label><span>Единица</span><select id="issueUom" required></select></label>
          <label id="plannedCloseField" hidden><span id="plannedCloseLabel">Плановая дата</span><input id="issuePlannedCloseDate" type="date"></label>
          <label id="autoWriteoffField" class="check-row issue-check" hidden><input id="issueAutoWriteoff" type="checkbox" checked><span>Списать автоматически по нормативу</span></label>
          <label><span>Номер заявки</span><input id="issueRequestReference" maxlength="120" placeholder="Необязательно"></label>
          <div id="existingIssueWarning" class="message warn issue-span" hidden></div>
          <label class="issue-span"><span>Основание выдачи</span><textarea id="issueReason" maxlength="500" required placeholder="Для чего и на каком основании выдаётся"></textarea></label>
          <label><span>Скан источника</span><input id="issueSourceScan" class="mono" autocomplete="off" required></label>
          <label><span>Скан товара или упаковки</span><input id="issueItemScan" class="mono" autocomplete="off" required></label>
          <button class="primary issue-span" type="submit">Подтвердить выдачу</button>
        </form>
        <div id="issueMessage" class="message">Скан источника и товара защищает от выдачи не из той ячейки.</div>
      </section>
      <section class="recent-issues-panel">
        <div class="panel-head"><div><span class="eyebrow">Последние операции</span><h2>Выдачи и ответственность</h2></div><button id="refreshIssues" class="icon-button" type="button" title="Обновить" aria-label="Обновить">↻</button></div>
        <div id="recentIssues" class="data-list"></div>
      </section>
    </main>
    <dialog id="productDialog" class="catalog-dialog">
      <form id="productForm">
        <div class="dialog-head"><div><span class="eyebrow">Справочник</span><h2>Новая номенклатура</h2></div><button class="icon-button" data-close-dialog="productDialog" type="button" title="Закрыть" aria-label="Закрыть">×</button></div>
        <div class="catalog-form-grid">
          <label><span>Код</span><input id="productCode" class="mono" maxlength="64" autocomplete="off" required></label>
          <label><span>Название</span><input id="productName" maxlength="240" autocomplete="off" required></label>
          <label><span>Базовая единица</span><select id="productUom" required></select></label>
          <label><span>Срок годности, дней</span><input id="productShelfLife" type="number" min="1" step="1" placeholder="Необязательно"></label>
          <label class="catalog-span"><span>Норматив ответственной выдачи, дней</span><input id="productAccountabilityPeriod" type="number" min="1" step="1" placeholder="Необязательно"></label>
        </div>
        <div id="productMessage" class="message">Код будет приведён к верхнему регистру.</div>
        <div class="dialog-actions"><button class="secondary" data-close-dialog="productDialog" type="button">Отмена</button><button class="primary" type="submit">Создать позицию</button></div>
      </form>
    </dialog>
    <dialog id="packagingDialog" class="catalog-dialog">
      <form id="packagingForm">
        <div class="dialog-head"><div><span class="eyebrow">Упаковка и код</span><h2 id="packagingTitle">Новая упаковка</h2></div><button class="icon-button" data-close-dialog="packagingDialog" type="button" title="Закрыть" aria-label="Закрыть">×</button></div>
        <div id="packagingFacts" class="facts"></div>
        <div class="catalog-form-grid">
          <label><span>Код упаковки</span><input id="packagingCode" class="mono" maxlength="64" autocomplete="off" required></label>
          <label><span>Название</span><input id="packagingName" maxlength="160" autocomplete="off" required></label>
          <label><span>Количество</span><input id="packagingQuantity" type="number" min="0.000001" step="0.000001" required></label>
          <label><span>Единица</span><select id="packagingUom" required></select></label>
          <label class="catalog-span"><span>Штрихкод или QR-код</span><input id="packagingBarcode" class="mono" maxlength="120" autocomplete="off" placeholder="Необязательно"></label>
        </div>
        <div id="packagingMessage" class="message">Количество будет пересчитано в базовую единицу товара.</div>
        <div class="dialog-actions"><button class="secondary" data-close-dialog="packagingDialog" type="button">Отмена</button><button class="primary" type="submit">Добавить упаковку</button></div>
      </form>
    </dialog>
    <dialog id="returnDialog" class="catalog-dialog">
      <form id="returnForm">
        <div class="dialog-head"><div><span class="eyebrow">SCN-08</span><h2 id="returnTitle">Возврат по выдаче</h2></div><button class="icon-button" data-close-dialog="returnDialog" type="button" title="Закрыть" aria-label="Закрыть">×</button></div>
        <div id="returnFacts" class="facts"></div>
        <div class="catalog-form-grid">
          <label class="catalog-span"><span>Позиция исходной выдачи</span><select id="returnMovement" required></select></label>
          <label><span>Количество</span><input id="returnQuantity" type="number" min="0.000001" step="0.000001" required></label>
          <label><span>Единица</span><select id="returnUom" required></select></label>
          <label><span>Состояние</span><select id="returnQuality"><option value="released">Годно к хранению</option><option value="quarantine">Карантин / требуется проверка</option></select></label>
          <label><span>Скан места возврата</span><input id="returnDestinationScan" class="mono" autocomplete="off" required></label>
          <label class="catalog-span"><span>Скан товара или упаковки</span><input id="returnItemScan" class="mono" autocomplete="off" required></label>
          <label class="catalog-span"><span>Основание возврата</span><textarea id="returnReason" maxlength="500" required placeholder="Например, увольнение или окончание работ"></textarea></label>
        </div>
        <div id="returnMessage" class="message">Количество сверяется с невозвращённым остатком исходной выдачи.</div>
        <div class="dialog-actions"><button class="secondary" data-close-dialog="returnDialog" type="button">Отмена</button><button class="primary" type="submit">Подтвердить возврат</button></div>
      </form>
    </dialog>
    """
    return document(
        "Номенклатура Simple WMS",
        "stock-page",
        body,
        "/static/universal-stock.js?v=20260813-3",
    )


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
        <button data-settings-tab="recipients" type="button">Получатели</button>
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

      <section class="settings-view" data-settings-view="recipients" hidden>
        <form id="recipientForm" class="settings-form-panel">
          <div class="panel-head"><div><span class="eyebrow">Внутренняя выдача</span><h2 id="recipientFormTitle">Новый получатель</h2></div></div>
          <div class="settings-form-body">
            <input id="recipientId" type="hidden">
            <label><span>Код</span><input id="recipientCode" class="mono" maxlength="64" required></label>
            <label><span>Название или ФИО</span><input id="recipientName" maxlength="200" required></label>
            <label><span>Тип</span><select id="recipientKind" required><option value="employee">Сотрудник</option><option value="department">Подразделение</option><option value="workplace">Рабочее место</option></select></label>
            <label class="check-row"><input id="recipientActive" type="checkbox" checked><span>Получатель активен</span></label>
            <div class="form-actions"><button class="primary" type="submit">Сохранить</button><button id="recipientReset" type="button">Очистить</button></div>
          </div>
        </form>
        <section class="settings-list-panel"><div class="panel-head"><div><span class="eyebrow">Справочник</span><h2>Получатели</h2></div></div><div id="recipientList" class="settings-list"></div></section>
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
