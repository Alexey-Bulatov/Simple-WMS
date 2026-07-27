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


class UserRole(StrEnum):
    PRODUCTION_OPERATOR = "production_operator"
    RECEIVING_CLERK = "receiving_clerk"
    WAREHOUSE_CLERK = "warehouse_clerk"
    SHIPPING_OPERATOR = "shipping_operator"
    SENIOR_CLERK = "senior_clerk"
    WAREHOUSE_MANAGER = "warehouse_manager"
    ADMIN = "admin"


class BoxStatus(StrEnum):
    LABEL_CREATED = "label_created"
    ACCEPTED_FROM_PRODUCTION = "accepted_from_production"
    IN_OPEN_PALLET = "in_open_pallet"
    IN_CLOSED_PALLET = "in_closed_pallet"
    BLOCKED = "blocked"
    QUARANTINE = "quarantine"
    DAMAGED = "damaged"
    WRITTEN_OFF = "written_off"
    SHIPPED = "shipped"


class PalletStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    WAITING_PLACEMENT = "waiting_placement"
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
