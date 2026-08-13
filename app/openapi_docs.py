from collections.abc import Callable
from typing import Any

from fastapi import FastAPI


# Display-only labels. Paths, operationId values and schemas stay untouched.
ENTITY_TERMS = {
    "maps": ("Карта склада", "карт складов", "карту склада"),
    "users": ("Пользователь", "пользователей", "пользователя"),
    "equipment-profiles": ("Профиль оборудования", "профилей оборудования", "профиль оборудования"),
    "units-of-measure": ("Единица измерения", "единиц измерения", "единицу измерения"),
    "logistic-unit-types": ("Тип логистической единицы", "типов логистических единиц", "тип логистической единицы"),
    "logistic-units": ("Логистическая единица", "логистических единиц", "логистическую единицу"),
    "logistic-shipments": ("Универсальная отгрузка", "универсальных отгрузок", "универсальную отгрузку"),
    "logistic-transfers": ("Универсальная межскладская передача", "универсальных межскладских передач", "универсальную межскладскую передачу"),
    "logistic-inventories": ("Универсальная инвентаризация", "универсальных инвентаризаций", "универсальную инвентаризацию"),
    "logistic-tasks": ("Универсальное складское задание", "универсальных складских заданий", "универсальное складское задание"),
    "products": ("Номенклатура", "позиций номенклатуры", "позицию номенклатуры"),
    "product-packagings": ("Товарная упаковка", "товарных упаковок", "товарную упаковку"),
    "stock-owners": ("Владелец запаса", "владельцев запаса", "владельца запаса"),
    "stock-recipients": ("Получатель запаса", "получателей запаса", "получателя запаса"),
    "stock-positions": ("Позиция остатка", "позиций остатка", "позицию остатка"),
    "stock-reservations": ("Резерв запаса", "резервов запаса", "резерв запаса"),
    "stock-reservation-requests": ("Заявка на резерв", "заявок на резерв", "заявку на резерв"),
    "stock-documents": ("Документ учёта", "документов учёта", "документ учёта"),
    "stock-movements": ("Движение запаса", "движений запаса", "движение запаса"),
    "internal-issues": ("Внутренняя выдача", "внутренних выдач", "внутреннюю выдачу"),
    "batches": ("Партия", "партий", "партию"),
    "warehouses": ("Склад", "складов", "склад"),
    "zones": ("Зона", "зон", "зону"),
    "aisles": ("Проход", "проходов", "проход"),
    "racks": ("Стеллаж", "стеллажей", "стеллаж"),
    "rack-sections": ("Секция стеллажа", "секций стеллажей", "секцию стеллажа"),
    "rack-levels": ("Ярус стеллажа", "ярусов стеллажей", "ярус стеллажа"),
    "locations": ("Ячейка", "ячеек", "ячейку"),
    "inventory-locations": ("Инвентаризируемая ячейка", "инвентаризируемых ячеек", "инвентаризируемую ячейку"),
    "boxes": ("Коробка пилота", "коробок пилота", "коробку пилота"),
    "pallets": ("Палета пилота", "палет пилота", "палету пилота"),
    "shipments": ("Отгрузка пилота", "отгрузок пилота", "отгрузку пилота"),
    "transfers": ("Межскладская передача пилота", "межскладских передач пилота", "межскладскую передачу пилота"),
    "tasks": ("Складское задание пилота", "складских заданий пилота", "складское задание пилота"),
    "inventories": ("Инвентаризация пилота", "инвентаризаций пилота", "инвентаризацию пилота"),
    "events": ("Событие", "событий", "событие"),
    "auth": ("Авторизация", "операций авторизации", "операцию авторизации"),
}

ACTION_LABELS = {
    "setup": "подготовить демонстрационные карты",
    "rows": "работа со стеллажами на карте",
    "locations": "работа с ячейками на карте",
    "labels": "работа с подписями на карте",
    "items": "изменить элемент карты",
    "delete": "удалить",
    "reset": "вернуть демонстрационное состояние",
    "accept": "принять",
    "contents": "товарное содержимое",
    "remove": "удалить вложенный объект",
    "children": "вложенные логистические единицы",
    "close": "закрыть",
    "reopen": "переоткрыть",
    "block": "заблокировать",
    "quarantine": "поместить в карантин",
    "release": "освободить из блокировки или карантина",
    "place": "разместить",
    "move": "переместить",
    "disassemble": "разукомплектовать",
    "units": "логистические единицы документа",
    "expedition": "переместить в экспедицию",
    "load": "подтвердить погрузку",
    "dispatch": "отправить в путь",
    "receive": "принять на складе назначения",
    "scan-location": "сканировать ячейку",
    "scan-unit": "сканировать логистическую единицу",
    "confirm-location": "подтвердить проверку ячейки",
    "empty": "подтвердить пустую ячейку",
    "complete": "завершить",
    "events": "история операций",
    "discrepancies": "расхождения",
    "confirm-missing": "подтвердить недостачу",
    "place-found": "разместить найденную единицу",
    "move-to-actual": "переместить по фактическому адресу",
    "sync": "синхронизировать и создать задания",
    "start": "начать выполнение",
    "assign": "назначить исполнителя",
    "cancel": "отменить",
    "label.pdf": "получить PDF-этикетку",
    "label.print": "напечатать этикетку",
    "generate": "сформировать",
    "trace": "прослеживаемость",
    "boxes": "коробки",
    "pallets": "палеты",
    "lines": "строки документа",
    "progress": "ход выполнения",
    "scan": "сканировать",
    "preview": "предпросмотр импорта",
    "apply": "применить импорт",
    "resolve": "распознать код объекта",
    "reverse": "создать компенсирующий документ",
    "quantity": "распределить количество",
    "logistic-unit": "зарезервировать логистическую единицу целиком",
    "bootstrap": "создать первого администратора",
    "password": "войти по логину и паролю",
    "pass": "войти по QR или штрихкоду",
    "me": "получить текущий профиль",
    "logout": "завершить сессию",
    "issue": "выпустить новый пропуск",
    "revoke-all": "отозвать все сессии",
    "workstations": "рабочие места",
}

METHOD_ACTION_LABELS = {
    ("get", "contents"): "получить товарное содержимое",
    ("post", "contents"): "добавить товарное содержимое",
    ("get", "children"): "получить вложенные единицы",
    ("post", "children"): "добавить вложенную единицу",
    ("get", "units"): "получить единицы документа",
    ("post", "units"): "добавить единицу в документ",
    ("get", "boxes"): "получить коробки",
    ("post", "boxes"): "добавить коробку",
    ("get", "pallets"): "получить палеты",
    ("post", "pallets"): "добавить палету",
}


def russian_summary(path: str, method: str) -> str:
    if path == "/health":
        return "Проверка состояния приложения"
    if path == "/api/meta/constants":
        return "Системные константы API"
    if path == "/api/stock-reconciliation":
        return "Сверить текущие позиции с журналом движений"
    if path == "/api/stock-search":
        return "Найти номенклатуру и расшифровать фактический остаток"

    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) < 2 or segments[0] != "api":
        return "Служебный маршрут"
    root = segments[1]

    if root == "demo":
        action = next((segment for segment in reversed(segments[2:]) if not segment.startswith("{")), "data")
        return f"Демонстрационные данные: {ACTION_LABELS.get(action, 'сформировать')}"
    if root == "import":
        action = next((segment for segment in segments[2:] if not segment.startswith("{")), "preview")
        return f"Импорт справочников: {ACTION_LABELS.get(action, action)}"
    if root == "cards":
        action = next((segment for segment in segments[2:] if not segment.startswith("{")), "resolve")
        return f"Карточки объектов: {ACTION_LABELS.get(action, 'получить карточку')}"
    if root == "labels":
        return "Пакетное формирование этикеток"

    terms = ENTITY_TERMS.get(root)
    if terms is None:
        return "Операция API"
    entity_label, plural_genitive, singular_accusative = terms
    tail = segments[2:]
    static_tail = [segment for segment in tail if not segment.startswith("{")]
    if not static_tail:
        if not tail and method == "get":
            return f"Список {plural_genitive}"
        if not tail and method == "post":
            return f"Создать {singular_accusative}"
        if not tail and method == "put":
            return f"Изменить {singular_accusative}"
        if method == "get":
            return f"Карточка: {entity_label}"
        if method == "put":
            return f"Изменить: {entity_label}"
        return f"Операция: {entity_label}"

    action = static_tail[-1]
    if root == "stock-reservations" and action == "release":
        return f"{entity_label}: снять резерв"
    if root == "stock-reservations" and action == "consume":
        return f"{entity_label}: погасить фактическим отбором"
    action_label = METHOD_ACTION_LABELS.get(
        (method, action),
        ACTION_LABELS.get(action, action.replace("-", " ")),
    )
    return f"{entity_label}: {action_label}"


def append_russian_summaries(schema: dict[str, Any]) -> dict[str, Any]:
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict) or operation.get("x-russian-summary"):
                continue
            translated = russian_summary(path, method.lower())
            english = operation.get("summary") or operation.get("operationId") or "API operation"
            operation["summary"] = f"{english} ({translated})"
            operation["x-russian-summary"] = translated
    return schema


def install_bilingual_openapi(app: FastAPI) -> None:
    original_openapi: Callable[[], dict[str, Any]] = app.openapi

    def bilingual_openapi() -> dict[str, Any]:
        return append_russian_summaries(original_openapi())

    app.openapi = bilingual_openapi
