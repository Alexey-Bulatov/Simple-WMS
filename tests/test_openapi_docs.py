from copy import deepcopy

from app.main import app
from app.openapi_docs import append_russian_summaries, russian_summary


def test_russian_summary_for_logistic_transfers():
    assert russian_summary("/api/logistic-transfers", "get") == (
        "Список универсальных межскладских передач"
    )
    assert russian_summary("/api/logistic-units/{uid}/accept", "post") == (
        "Логистическая единица: принять"
    )


def test_openapi_adds_display_text_without_changing_operation_id():
    source = {
        "paths": {
            "/api/logistic-transfers": {
                "get": {
                    "summary": "Api List Logistic Transfers",
                    "operationId": "api_list_logistic_transfers_api_logistic_transfers_get",
                }
            }
        }
    }
    result = append_russian_summaries(deepcopy(source))
    operation = result["paths"]["/api/logistic-transfers"]["get"]

    assert operation["summary"] == (
        "Api List Logistic Transfers (Список универсальных межскладских передач)"
    )
    assert operation["operationId"] == (
        "api_list_logistic_transfers_api_logistic_transfers_get"
    )


def test_application_openapi_has_russian_display_summary_for_every_operation():
    schema = app.openapi()
    operations = [
        operation
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]

    assert operations
    assert all(operation.get("x-russian-summary") for operation in operations)
    assert schema["paths"]["/api/logistic-transfers"]["get"]["summary"] == (
        "Api List Logistic Transfers (Список универсальных межскладских передач)"
    )
