from app.db.session import SessionLocal
from app.internal_issues import process_due_accountability_writeoffs


def main() -> None:
    with SessionLocal() as db:
        documents = process_due_accountability_writeoffs(db)
    uids = ", ".join(document.uid for document in documents) or "none"
    print(f"Accountability writeoffs processed: {len(documents)}; documents: {uids}")


if __name__ == "__main__":
    main()
