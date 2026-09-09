from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from test_pos import env, good, order, req, setup_sale
from test_pos_roles import call, staff
from app.pos.models import Business, Membership, Movement, Order, Product


def test_ceo_adds_local_without_removing_existing_access(env):
    client, headers, Session = env
    owner_headers = headers(2)
    saved = good(client.post('/pos-api/admin/accounts/2/businesses', headers=headers(), json={
        'name': 'Segundo restaurante', 'mode': 'restaurante', 'tables': 8,
    }))
    me = good(client.get('/pos-api/auth/me', headers=owner_headers))
    assert {b['id'] for b in me['businesses']} == {2, saved['id']}
    assert all(b['role'] == 'owner' for b in me['businesses'])
    assert client.get(f"/pos-api/business/{saved['id']}/state", headers=owner_headers).status_code == 200
    assert client.get('/pos-api/business/1/state', headers=owner_headers).status_code == 403
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Membership).where(Membership.account_id == 2)) == 2


def test_client_cannot_create_accounts_or_assign_local_by_api(env):
    client, headers, Session = env
    owner_headers = headers(2)
    business = {'name': 'Sin autorización', 'mode': 'restaurante'}
    assert client.post('/pos-api/admin/accounts/2/businesses', headers=owner_headers, json=business).status_code == 403
    assert client.post('/pos-api/admin/businesses', headers=owner_headers, json=business).status_code == 403
    assert client.put('/pos-api/admin/accounts/2', headers=owner_headers, json={'active': True, 'business_ids': [1, 2]}).status_code == 403
    assert client.post('/pos-api/admin/accounts', headers=owner_headers, json={'name': 'Otro dueño', 'email': 'new@example.com', 'password': 'password-123', 'business_ids': [2]}).status_code == 403
    assert client.post('/pos-api/admin/accounts/2/businesses', json=business).status_code == 401
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Business)) == 2
        assert list(db.scalars(select(Membership.business_id).where(Membership.account_id == 2))) == [2]


def test_new_local_unknown_owner_or_invalid_payload_leaves_no_orphan(env):
    client, headers, Session = env
    assert client.post('/pos-api/admin/accounts/999/businesses', headers=headers(), json={'name': 'Local', 'mode': 'restaurante'}).status_code == 404
    assert client.post('/pos-api/admin/accounts/2/businesses', headers=headers(), json={'name': 'Local', 'mode': 'restaurante', 'tables': -1}).status_code == 422
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Business)) == 2


def test_daily_report_timezone_cost_snapshot_refunds_and_expense_only_day(env):
    _, _, Session = env
    product = setup_sale(env)
    orders = [order(env, product) for _ in range(5)]
    for item in [orders[0], orders[1], orders[3], orders[4]]:
        good(req(env, f"/orders/{item['id']}/pay", 'post', {'method': 'card'}))
    good(req(env, f"/orders/{orders[3]['id']}/refund", 'post', {'reason': 'Devolución completa'}))
    good(req(env, '/cash', 'post', {'kind': 'expense', 'amount': 50, 'reason': 'Gasto operativo'}))
    good(req(env, '/cash', 'post', {'kind': 'income', 'amount': 700, 'reason': 'Aporte del dueño'}))
    with Session.begin() as db:
        db.get(Order, orders[0]['id']).paid_at = datetime(2026, 9, 9, 5, 59, 59, tzinfo=timezone.utc)
        db.get(Order, orders[1]['id']).paid_at = datetime(2026, 9, 9, 6, 0, 0, tzinfo=timezone.utc)
        db.get(Order, orders[3]['id']).paid_at = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
        # Midnight after the selected final day is excluded.
        db.get(Order, orders[4]['id']).paid_at = datetime(2026, 9, 11, 6, 0, 0, tzinfo=timezone.utc)
        for movement in db.scalars(select(Movement).where(Movement.kind.in_(['expense', 'income']))):
            movement.created_at = datetime(2026, 9, 10, 18, 0, 0, tzinfo=timezone.utc)
        db.get(Product, product['id']).cost = 999
    report = good(req(env, '/reports?start=2026-09-08&end=2026-09-10'))
    assert report['tickets'] == 2
    assert Decimal(str(report['sales'])) == Decimal('452')
    assert Decimal(str(report['cost'])) == Decimal('120')
    assert Decimal(str(report['gross_profit'])) == Decimal('280')
    assert Decimal(str(report['net_sales'])) == Decimal('400')
    assert Decimal(str(report['estimated_margin'])) == Decimal('230')
    assert [row['date'] for row in report['daily']] == ['2026-09-08', '2026-09-09', '2026-09-10']
    assert [row['tickets'] for row in report['daily']] == [1, 1, 0]
    assert [Decimal(str(row['estimated_margin'])) for row in report['daily']] == [Decimal('140'), Decimal('140'), Decimal('-50')]
    assert {row['id'] for row in report['orders']} == {orders[0]['id'], orders[1]['id']}


def test_daily_report_discount_once_and_empty_range(env):
    _, _, Session = env
    product = setup_sale(env)
    saved = order(env, product, discount=15, adjustment_reason='Descuento comercial')
    good(req(env, f"/orders/{saved['id']}/pay", 'post', {'method': 'sinpe'}))
    with Session.begin() as db:
        db.get(Order, saved['id']).paid_at = datetime(2026, 9, 9, 18, 0, 0, tzinfo=timezone.utc)
    report = good(req(env, '/reports?start=2026-09-09&end=2026-09-09'))
    assert Decimal(str(report['gross_profit'])) == Decimal('125')
    assert Decimal(str(report['daily'][0]['gross_profit'])) == Decimal('125')
    assert Decimal(str(report['sales'])) == Decimal('209.05')
    assert report['daily'][0]['tickets'] == 1
    empty = good(req(env, '/reports?start=2026-09-12&end=2026-09-13'))
    assert empty['tickets'] == 0 and len(empty['daily']) == 2
    assert all(Decimal(str(row['gross_profit'])) == 0 for row in empty['daily'])


def test_reports_stay_isolated_and_restricted_to_managers(env):
    setup_sale(env)
    _, waiter = staff(env)
    _, admin = staff(env, role='admin', email='admin@example.com')
    path = '/reports?start=2026-09-01&end=2026-09-30'
    assert call(env, waiter, path, method='get').status_code == 403
    assert call(env, admin, path, method='get').status_code == 200
    assert call(env, admin, path, method='get', bid=2).status_code == 403
    assert req(env, path, who=2, bid=1).status_code == 403
    assert req(env, '/reports?start=2026-09-10&end=2026-09-09').status_code == 400


def test_staff_password_minimum_is_enforced_on_server(env):
    body = {'name': 'Empleado', 'email': 'short@example.com', 'password': '1234567', 'role': 'waiter'}
    assert req(env, '/team', 'post', body).status_code == 422
    body['password'] = '12345678'
    assert req(env, '/team', 'post', body).status_code == 200
