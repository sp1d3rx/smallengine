"""Accounting & Financial Reporting Domain Contexts."""
import collections
import datetime
from decimal import Decimal
from ..gantrika.context import BaseContext


class AccountingContext(BaseContext):
    """Domain service for shop revenue recognition, cash-basis accounting, and financial reporting."""

    def get_paid_in_full_date(self, invoice_id):
        """Find the latest payment date for an invoice with fallback to modified/created date."""
        db = self.db
        latest_payment = db(db.payment.invoice_id == invoice_id).select(
            db.payment.received_on, orderby=~db.payment.received_on
        ).first()
        if latest_payment and latest_payment.received_on:
            return latest_payment.received_on

        invoice = db.invoice[invoice_id]
        if invoice:
            ref_datetime = invoice.modified_on or invoice.created_on
            if ref_datetime:
                return ref_datetime.date() if hasattr(ref_datetime, "date") else ref_datetime
        return None

    def calculate_revenue_summary(self, max_months=6):
        """Calculate cash-basis revenue, COGS, gross profit, and margins across recent months."""
        db = self.db
        months_data = collections.defaultdict(lambda: {
            "labor": 0.0,
            "parts": 0.0,
            "equipment": 0.0,
            "parts_cost": 0.0,
            "equipment_cost": 0.0,
        })

        # 1. Closed & paid work orders
        wos = db((db.work_order.status == "closed") & (db.invoice.status == "paid")).select(
            db.work_order.id, db.work_order.work_type, db.invoice.id,
            left=db.invoice.on(db.invoice.work_order_id == db.work_order.id)
        )
        for r in wos:
            invoice_id = r.invoice.id if r.invoice else None
            if not invoice_id:
                continue

            ref_date = self.get_paid_in_full_date(invoice_id)
            m_key = str(ref_date)[:7] if ref_date else "unknown"

            # Labor revenue
            labor_sum = db(db.work_order_labor.work_order_id == r.work_order.id).select(
                db.work_order_labor.total.sum()
            ).first()[db.work_order_labor.total.sum()] or 0.0
            months_data[m_key]["labor"] += float(labor_sum)

            # Parts revenue & cost
            p_parts = db((db.work_order_part.work_order_id == r.work_order.id) & (db.work_order_part.is_warranty == False)).select()
            for line in p_parts:
                months_data[m_key]["parts"] += float(line.total or 0.0)
                months_data[m_key]["parts_cost"] += float(line.unit_cost or 0.0) * int(line.quantity or 0)

        # 2. Paid retail parts sales
        retail_sales = db((db.sale.status == "paid") & (db.sale.equipment_id == None)).select(
            db.sale.id, db.sale.sale_date
        )
        for s in retail_sales:
            m_key = str(s.sale_date)[:7] if s.sale_date else "unknown"
            lines = db(db.sale_line.sale_id == s.id).select()
            for line in lines:
                months_data[m_key]["parts"] += float(line.total or 0.0)
                months_data[m_key]["parts_cost"] += float(line.unit_cost or 0.0) * int(line.quantity or 0)

        # 3. Paid equipment sales
        equip_sales = db((db.sale.status == "paid") & (db.sale.equipment_id != None)).select(
            db.sale.id, db.sale.sale_price, db.sale.trade_in_value, db.sale.sale_date, db.sale.equipment_id
        )
        for s in equip_sales:
            m_key = str(s.sale_date)[:7] if s.sale_date else "unknown"
            val = float(s.sale_price or 0.0) - float(s.trade_in_value or 0.0)
            months_data[m_key]["equipment"] += val
            equip = db.equipment[s.equipment_id]
            if equip:
                months_data[m_key]["equipment_cost"] += float(equip.acquisition_cost or 0.0)

        # Sort and project
        sorted_months = sorted([k for k in months_data.keys() if k != "unknown"], reverse=True)[:max_months]
        result = []
        for m in sorted_months:
            d = months_data[m]
            total_rev = d["labor"] + d["parts"] + d["equipment"]
            total_cogs = d["parts_cost"] + d["equipment_cost"]
            gp = total_rev - total_cogs
            margin_pct = (gp / total_rev * 100.0) if total_rev > 0 else 0.0
            result.append({
                "month": m,
                "labor": float(d["labor"]),
                "parts": float(d["parts"]),
                "equipment": float(d["equipment"]),
                "total_revenue": float(total_rev),
                "cogs": float(total_cogs),
                "gross_profit": float(gp),
                "gross_margin": float(margin_pct),
            })
        return result
