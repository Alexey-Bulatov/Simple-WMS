from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter()


def navigation(active: str) -> str:
    links = (
        ("work", "/work", "Рабочее место"),
        ("terminal", "/terminal", "ТСД"),
        ("cards", "/cards", "Поиск"),
        ("demo", "/demo", "Демо"),
        ("api", "/docs", "API"),
    )
    return "".join(
        f'<a class="{"active" if key == active else ""}" href="{url}">{label}</a>'
        for key, url, label in links
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
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/static/universal.css"></head><body class="{body_class}">{body}<div id="toast" class="toast" hidden></div><script src="{script}" defer></script></body></html>"""


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
