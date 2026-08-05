from app.db.database import SessionLocal
from app.seeders.initial_data import seed_initial_data


def initialize_database():
    db = SessionLocal()

    try:
        seed_initial_data(db)
        print("✅ Base de datos inicializada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    initialize_database()