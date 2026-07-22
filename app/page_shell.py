from collections.abc import Callable
from functools import wraps
from typing import ParamSpec


P = ParamSpec("P")


HEADER_CSS = """
    .app-header {
      height: 54px;
      min-height: 54px;
      padding: 8px 18px;
      display: flex;
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      color: #fff;
      background: var(--dark, #111820);
    }
    .app-header h1 {
      flex: 0 0 174px;
      margin: 0;
      color: #fff;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
      white-space: nowrap;
    }
    .app-nav {
      min-width: 0;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 13px;
      overflow: visible;
      font-size: 15px;
      white-space: nowrap;
    }
    .app-nav > a,
    .app-nav summary,
    .app-nav-more-menu a {
      color: #d8fbf6;
      font-weight: 750;
      line-height: 1.25;
      text-decoration: none;
    }
    .app-nav > a.active,
    .app-nav-more.active > summary {
      color: #fff;
      text-decoration: underline;
      text-decoration-thickness: 2px;
      text-underline-offset: 5px;
    }
    .app-nav-more { position: relative; }
    .app-nav-more summary {
      cursor: pointer;
      list-style: none;
    }
    .app-nav-more summary::-webkit-details-marker { display: none; }
    .app-nav-more-menu {
      position: absolute;
      right: 0;
      top: 29px;
      z-index: 100;
      min-width: 190px;
      padding: 7px;
      display: grid;
      gap: 2px;
      border: 1px solid #34424d;
      border-radius: 6px;
      background: #1b2630;
      box-shadow: 0 10px 26px rgba(0, 0, 0, .24);
    }
    .app-nav-more-menu a {
      padding: 7px 9px;
      border-radius: 4px;
    }
    .app-nav-more-menu a:hover,
    .app-nav-more-menu a.active { color: #fff; background: #273641; }
    @media (max-width: 820px) {
      .app-header { padding-inline: 12px; gap: 10px; }
      .app-header h1 { display: none; }
      .app-nav {
        width: 100%;
        justify-content: flex-start;
        overflow-x: auto;
        overflow-y: hidden;
        padding: 8px 0;
      }
      .app-nav-more { position: static; }
      .app-nav-more-menu { position: fixed; top: 50px; right: 8px; }
    }
"""


PRIMARY_LINKS = (
    ("scan", "/scan", "Склад"),
    ("terminal", "/terminal", "ТСД"),
    ("map", "/map", "Карта"),
    ("transfers", "/transfers", "Перемещения"),
    ("shipments", "/shipments", "Отгрузки"),
    ("inventory", "/inventory", "Инвентаризация"),
)

MORE_LINKS = (
    ("catalog", "/catalog", "Справочники"),
    ("cards", "/cards", "Карточки"),
    ("docs", "/docs", "Документация API"),
)


def _link(key: str, href: str, label: str, active: str) -> str:
    class_name = ' class="active"' if key == active else ""
    return f'      <a{class_name} href="{href}">{label}</a>'


def render_header(active: str, desktop_only: bool = False) -> str:
    primary = "\n".join(_link(*link, active) for link in PRIMARY_LINKS)
    secondary = "\n".join(_link(*link, active) for link in MORE_LINKS)
    more_active = " active" if active in {link[0] for link in MORE_LINKS} else ""
    desktop_class = " desktop-header" if desktop_only else ""
    return f"""  <header class="app-header{desktop_class}" data-page="{active}">
    <h1>Складской пилот</h1>
    <nav class="app-nav" aria-label="Основные разделы">
{primary}
      <details class="app-nav-more{more_active}">
        <summary>Ещё</summary>
        <div class="app-nav-more-menu">
{secondary}
        </div>
      </details>
    </nav>
  </header>"""


def standard_page(active: str, *, desktop_only: bool = False) -> Callable:
    def decorator(page_function: Callable[P, str]) -> Callable[P, str]:
        @wraps(page_function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> str:
            html = page_function(*args, **kwargs)
            html = html.replace("  </style>", f"{HEADER_CSS}  </style>", 1)

            header_start = html.find("<header")
            header_end = html.find("</header>", header_start)
            if header_start == -1 or header_end == -1:
                raise ValueError(f"Page {page_function.__name__} has no header")
            header_end += len("</header>")
            return html[:header_start] + render_header(active, desktop_only) + html[header_end:]

        return wrapped

    return decorator
