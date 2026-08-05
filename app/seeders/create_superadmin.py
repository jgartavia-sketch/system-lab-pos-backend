from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.models.role import Role
from app.models.user import User


def create_superadmin():
    db: Session = SessionLocal()

    try:
        role = (
            db.query(Role)
            .filter(Role.name == "SuperAdmin")
            .first()
        )

        if not role:
            print("❌ No existe el rol SuperAdmin.")
            return

        existing_user = (
            db.query(User)
            .filter(
                User.email == "admin@systemlabpos.com"
            )
            .first()
        )

        if existing_user:
            print("⚠️ El SuperAdmin ya existe.")
            return

        user = User(
            role_id=role.id,
            first_name="System",
            last_name="Administrator",
            email="admin@systemlabpos.com",
            password_hash=get_password_hash("Admin123*"),
            is_active=True,
        )

        db.add(user)
        db.commit()

        print("✅ SuperAdmin creado correctamente.")
        print("Email: admin@systemlabpos.com")
        print("Password: Admin123*")

    finally:
        db.close()


if __name__ == "__main__":
    create_superadmin()