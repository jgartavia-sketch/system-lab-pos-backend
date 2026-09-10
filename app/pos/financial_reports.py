"""Operating result and cash flow are distinct, auditable views of the same period."""
from datetime import datetime, timezone, timedelta, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .models import Order, Movement, FinancialEntry

TZ = ZoneInfo('America/Costa_Rica')
D = Decimal

def money(value): return D(str(value)).quantize(D('.01'), rounding=ROUND_HALF_UP)
def local_day(value):
    if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ).date().isoformat()

def build_report(db, bid, start, end, serialize):
    lo=datetime.combine(start,time.min,TZ).astimezone(timezone.utc)
    hi=datetime.combine(end+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
    orders=db.scalars(select(Order).where(Order.business_id==bid,Order.status=='paid',Order.paid_at>=lo,Order.paid_at<hi)).all()
    payments={key:D(0) for key in ('cash','card','sinpe','transfer')}
    fields=('sales','tax','discount','cost','cash_expenses','operating_expenses','inventory_purchases','other_income','capital_in','withdrawals','manual_cash_income','service_total','packaging_total')
    daily={}
    for offset in range((end-start).days+1):
        key=(start+timedelta(days=offset)).isoformat()
        daily[key]={'date':key,**{field:D(0) for field in fields},'tickets':0,'missing_cost_lines':0}
    top={}
    for order in orders:
        day=daily[local_day(order.paid_at)]
        for field in ('tax','discount','service_total','packaging_total'): day[field]+=getattr(order,field) or 0
        day['sales']+=order.total; day['tickets']+=1
        payments[order.payment_method]+=order.total
        for item in order.items:
            quantity=D(item['quantity'])
            day['cost']+=D(item['cost'])*quantity
            if item.get('cost_known') is False: day['missing_cost_lines']+=1
            top[item['name']]=top.get(item['name'],D(0))+quantity
    entries=db.scalars(select(FinancialEntry).where(FinancialEntry.business_id==bid)).all()
    # Both the original drawer movement and an eventual reversal belong to the ledger.
    linked={ident for entry in entries for ident in (entry.cash_movement_id,entry.void_movement_id) if ident}
    for movement in db.scalars(select(Movement).where(Movement.business_id==bid,Movement.kind.in_(['income','expense']),Movement.created_at>=lo,Movement.created_at<hi)):
        if movement.id in linked: continue
        day=daily[local_day(movement.created_at)]
        if movement.kind=='expense':
            day['cash_expenses']-=movement.amount
            day['operating_expenses']-=movement.amount
        else: day['manual_cash_income']+=movement.amount
    mapping={'expense':'operating_expenses','purchase':'inventory_purchases','other_income':'other_income','capital_in':'capital_in','withdrawal':'withdrawals'}
    categories={}
    for entry in entries:
        key=local_day(entry.occurred_at)
        if entry.voided_at or key not in daily: continue
        day=daily[key]; day[mapping[entry.kind]]+=entry.amount
        if entry.cash_movement_id and entry.kind=='expense': day['cash_expenses']+=entry.amount
        if entry.kind in ('expense','purchase'):
            category=(entry.kind,entry.category)
            categories[category]=categories.get(category,D(0))+entry.amount
    for day in daily.values():
        day['net_sales']=day['sales']-day['tax']
        # Service collected for the staff is displayed separately, not claimed as business profit.
        day['operating_sales']=day['net_sales']-day['service_total']
        day['gross_profit']=day['operating_sales']-day['cost']
        day['income']=day['operating_sales']+day['other_income']
        day['outflows']=day['cost']+day['operating_expenses']
        day['profit']=day['income']-day['outflows']
        day['estimated_margin']=day['profit']
        day['money_in']=day['sales']+day['other_income']+day['capital_in']+day['manual_cash_income']
        day['money_out']=day['operating_expenses']+day['inventory_purchases']+day['withdrawals']
        day['cash_flow']=day['money_in']-day['money_out']
    totals={field:money(sum((day[field] for day in daily.values()),D(0))) for field in next(iter(daily.values())) if field not in ('date','tickets','missing_cost_lines')}
    tickets=len(orders)
    channels={key:{'channel':key,'orders':0,'paid':0,'paid_total':D(0)} for key in ('pos','website','whatsapp')}
    received=db.scalars(select(Order).where(Order.business_id==bid,Order.created_at>=lo,Order.created_at<hi)).all()
    for order in received:
        item=channels[order.source_channel or 'pos']; item['orders']+=1
        if order.status=='paid': item['paid']+=1; item['paid_total']+=order.total
    return {**totals,'tickets':tickets,'average':money(totals['sales']/tickets) if tickets else D(0),
            'missing_cost_lines':sum(day['missing_cost_lines'] for day in daily.values()),
            'payments':payments,'top_products':sorted([{'name':key,'quantity':value} for key,value in top.items()],key=lambda item:item['quantity'],reverse=True),
            'orders':[serialize(order) for order in orders],'daily':list(daily.values()),'timezone':str(TZ),
            'expense_categories':[{'kind':key[0],'category':key[1],'amount':value} for key,value in sorted(categories.items(),key=lambda item:item[1],reverse=True)],
            'channels':list(channels.values())}
