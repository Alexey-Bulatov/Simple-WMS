from enum import StrEnum


class MeasurementDimension(StrEnum):
    QUANTITY = "quantity"
    MASS = "mass"
    VOLUME = "volume"
    LENGTH = "length"
    AREA = "area"


class EquipmentKind(StrEnum):
    PRINTER = "printer"
    SCANNER = "scanner"
    TERMINAL = "terminal"
    SCALE = "scale"
    OTHER = "other"


class EquipmentConnection(StrEnum):
    PDF = "pdf"
    SYSTEM_QUEUE = "system_queue"
    RAW_TCP = "raw_tcp"
    KEYBOARD = "keyboard"
    CAMERA = "camera"
    WEB = "web"
    SERIAL = "serial"
    USB = "usb"


class LogisticUnitStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    AVAILABLE = "available"
    RESERVED = "reserved"
    PICKING = "picking"
    EXPEDITION = "expedition"
    LOADED = "loaded"
    IN_TRANSIT = "in_transit"
    QUARANTINE = "quarantine"
    BLOCKED = "blocked"
    DISASSEMBLED = "disassembled"
    WRITTEN_OFF = "written_off"
    SHIPPED = "shipped"


class StockDocumentStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"
    CANCELLED = "cancelled"


class InboundReceiptKind(StrEnum):
    EXPECTED = "expected"
    UNPLANNED = "unplanned"


class InboundReceiptStatus(StrEnum):
    DRAFT = "draft"
    RECEIVING = "receiving"
    POSTED = "posted"
    CANCELLED = "cancelled"


class StockReservationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    CONSUMED = "consumed"


class StockReservationKind(StrEnum):
    QUANTITY = "quantity"
    LOGISTIC_UNIT = "logistic_unit"


class StockReservationResult(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class StockRecipientKind(StrEnum):
    EMPLOYEE = "employee"
    DEPARTMENT = "department"
    WORKPLACE = "workplace"


class AuthenticationMethod(StrEnum):
    PASSWORD = "password"
    ACCESS_PASS = "access_pass"


class AuthenticationEventType(StrEnum):
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    SESSIONS_REVOKED = "sessions_revoked"
    ACCESS_PASS_ISSUED = "access_pass_issued"
    ACCESS_PASS_REVOKED = "access_pass_revoked"
    USER_UPDATED = "user_updated"
    WORKSTATION_UPDATED = "workstation_updated"
    PRIVILEGED_ACTION_CONFIRMED = "privileged_action_confirmed"


class UserRole(StrEnum):
    PRODUCTION_OPERATOR = "production_operator"
    RECEIVING_CLERK = "receiving_clerk"
    WAREHOUSE_CLERK = "warehouse_clerk"
    SHIPPING_OPERATOR = "shipping_operator"
    SENIOR_CLERK = "senior_clerk"
    WAREHOUSE_MANAGER = "warehouse_manager"
    ADMIN = "admin"
    AUDITOR = "auditor"
    INTEGRATION = "integration"


class WarehousePermission(StrEnum):
    LOGISTIC_UNIT_CREATE = "logistic_unit.create"
    LOGISTIC_UNIT_RECEIVE = "logistic_unit.receive"
    LOGISTIC_UNIT_PACK = "logistic_unit.pack"
    LOGISTIC_UNIT_MOVE = "logistic_unit.move"
    LOGISTIC_UNIT_HOLD = "logistic_unit.hold"
    LOGISTIC_UNIT_RELEASE = "logistic_unit.release"
    LOGISTIC_UNIT_DISASSEMBLE = "logistic_unit.disassemble"
    SHIPMENT_OPERATE = "shipment.operate"
    TRANSFER_OPERATE = "transfer.operate"
    INVENTORY_COUNT = "inventory.count"
    INVENTORY_RESOLVE = "inventory.resolve"
    TASK_EXECUTE = "task.execute"
    TASK_DISPATCH = "task.dispatch"
    STOCK_RESERVE = "stock.reserve"
    STOCK_RELEASE_RESERVATION = "stock.release_reservation"
    STOCK_CONSUME = "stock.consume"
    STOCK_CORRECT = "stock.correct"
    LABEL_PRINT = "label.print"
    CATALOG_MANAGE = "catalog.manage"
    WAREHOUSE_STRUCTURE_MANAGE = "warehouse_structure.manage"
    SYSTEM_ADMINISTER = "system.administer"
    DEMO_MANAGE = "demo.manage"


class ShipmentStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    EXPEDITION = "expedition"
    LOADING = "loading"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TransferStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    EXPEDITION = "expedition"
    LOADING = "loading"
    IN_TRANSIT = "in_transit"
    RECEIVING = "receiving"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TransferKind(StrEnum):
    LOCAL = "local"
    TRANSPORT = "transport"


class InventoryStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"


class InventoryLineStatus(StrEnum):
    EXPECTED = "expected"
    SCANNED = "scanned"
    MISSING = "missing"
    EXTRA = "extra"
    WRONG_LOCATION = "wrong_location"


class InventoryLocationStatus(StrEnum):
    UNCHECKED = "unchecked"
    CHECKED = "checked"
    PROBLEM = "problem"


class TaskType(StrEnum):
    BUILD = "build"
    PLACE = "place"
    MOVE = "move"
    SHIP = "ship"
    INVENTORY = "inventory"
    TRANSFER = "transfer"


class TaskStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class LocationKind(StrEnum):
    RECEIVING = "receiving"
    STORAGE = "storage"
    QUARANTINE = "quarantine"
    DISCREPANCY = "discrepancy"
    EXPEDITION = "expedition"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    SCRAP = "scrap"
