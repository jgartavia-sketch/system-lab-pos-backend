from app.db.database import SessionLocal
from app.seeders.initial_data import seed_initial_data


def run():
    db = SessionLocal()

    try:
        seed_initial_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()