from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.payment_method import PaymentMethod


def seed_roles(db: Session):
    roles = [
        {
            "name": "SuperAdmin",
            "description": "Administrador global de System Lab POS",
        },
        {
            "name": "Administrador",
            "description": "Administrador del negocio",
        },
        {
            "name": "Supervisor",
            "description": "Supervisor operativo",
        },
        {
            "name": "Cajero",
            "description": "Usuario de caja",
        },
    ]

    for role_data in roles:
        exists = (
            db.query(Role)
            .filter(Role.name == role_data["name"])
            .first()
        )

        if not exists:
            db.add(Role(**role_data))

    db.commit()


def seed_payment_methods(db: Session):
    methods = [
        {
            "name": "Efectivo",
            "description": "Pago en efectivo",
        },
        {
            "name": "SINPE Móvil",
            "description": "Pago mediante SINPE Móvil",
        },
        {
            "name": "Tarjeta",
            "description": "Pago con tarjeta",
        },
        {
            "name": "Transferencia Bancaria",
            "description": "Pago mediante transferencia bancaria",
        },
        {
            "name": "Crédito",
            "description": "Venta a crédito",
        },
    ]

    for method_data in methods:
        exists = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.name == method_data["name"])
            .first()
        )

        if not exists:
            db.add(PaymentMethod(**method_data))

    db.commit()


def seed_initial_data(db: Session):
    seed_roles(db)
    seed_payment_methods(db)

    print("✅ Datos iniciales cargados correctamente.")