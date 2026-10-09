"""Accounting & Financial Reporting Domain Contexts."""

import collections
import datetime
from ..gantrika.context import BaseContext


class AccountingContext(BaseContext):
    """Domain service for shop revenue recognition, cash-basis accounting, and financial reporting."""

    def get_paid_in_full_date(self, invoice_id):
        """Find the latest payment date for an invoice with fallback to modified/created date."""
        db = self.db
        latest_payment = (
            db(db.payment.invoice_id == invoice_id)
            .select(db.payment.received_on, orderby=~db.payment.received_on)
            .first()
        )
        if latest_payment and latest_payment.received_on:
            return latest_payment.received_on

        invoice = db.invoice[invoice_id]
        if invoice:
            ref_datetime = invoice.modified_on or invoice.created_on
            if ref_datetime:
                return (
                    ref_datetime.date()
                    if hasattr(ref_datetime, "date")
                    else ref_datetime
                )
        return None

    def calculate_revenue_summary(self, max_months=6):
        """Calculate cash-basis revenue, COGS, gross profit, and margins across recent months."""
        db = self.db

        # Window start: first day of the month, max_months months back.
        # Bounding the initial queries here keeps this from scanning the full history.
        today = datetime.date.today()
        win_year, win_month = today.year, today.month
        for _ in range(max_months):
            win_month -= 1
            if win_month == 0:
                win_month = 12
                win_year -= 1
        window_start = datetime.date(win_year, win_month, 1)

        months_data = collections.defaultdict(
            lambda: {
                "labor": 0.0,
                "parts": 0.0,
                "equipment": 0.0,
                "parts_cost": 0.0,
                "equipment_cost": 0.0,
            }
        )

        # 1. Closed & paid work orders with a payment (or invoice touch) in the window
        has_recent_payment = db(db.payment.received_on >= window_start).select(
            db.payment.invoice_id
        )
        wos = db(
            (db.work_order.status == "closed")
            & (db.invoice.status == "paid")
            & (
                db.invoice.id.belongs(has_recent_payment)
                | (db.invoice.modified_on >= window_start)
            )
        ).select(
            db.work_order.id,
            db.work_order.work_type,
            db.invoice.id,
            db.invoice.modified_on,
            db.invoice.created_on,
            left=db.invoice.on(db.invoice.work_order_id == db.work_order.id),
        )
        wo_ids = [r.work_order.id for r in wos]

        # Bulk: latest payment date per invoice (one query instead of one per WO)
        latest_pay = {}
        inv_ids = [r.invoice.id for r in wos if r.invoice]
        if inv_ids:
            for r in (
                db(db.payment.invoice_id.belongs(inv_ids))
                .select(db.payment.invoice_id, db.payment.received_on.max())
                .groupby(db.payment.invoice_id)
            ):
                latest_pay[r.payment.invoice_id] = r.payment[
                    db.payment.received_on.max()
                ]

        # Bulk: labor revenue per work order
        labor_by_wo = {}
        if wo_ids:
            for r in (
                db(db.work_order_labor.work_order_id.belongs(wo_ids))
                .select(
                    db.work_order_labor.work_order_id, db.work_order_labor.total.sum()
                )
                .groupby(db.work_order_labor.work_order_id)
            ):
                labor_by_wo[r.work_order_labor.work_order_id] = float(
                    r.work_order_labor[db.work_order_labor.total.sum()] or 0.0
                )

        # Bulk: parts revenue + cost per work order
        parts_by_wo = {}
        if wo_ids:
            for r in (
                db(
                    (db.work_order_part.work_order_id.belongs(wo_ids))
                    & (db.work_order_part.is_warranty == False)
                )
                .select(
                    db.work_order_part.work_order_id,
                    db.work_order_part.total.sum(),
                    (db.work_order_part.unit_cost * db.work_order_part.quantity).sum(),
                )
                .groupby(db.work_order_part.work_order_id)
            ):
                parts_by_wo[r.work_order_part.work_order_id] = (
                    float(r.work_order_part[db.work_order_part.total.sum()] or 0.0),
                    float(
                        r.work_order_part[
                            (
                                db.work_order_part.unit_cost
                                * db.work_order_part.quantity
                            ).sum()
                        ]
                        or 0.0
                    ),
                )

        for r in wos:
            invoice_id = r.invoice.id if r.invoice else None
            if not invoice_id:
                continue

            # Paid-in-full date: latest payment, else invoice modified/created (matches get_paid_in_full_date)
            ref_date = latest_pay.get(invoice_id)
            if not ref_date and r.invoice:
                ref_dt = r.invoice.modified_on or r.invoice.created_on
                ref_date = ref_dt.date() if hasattr(ref_dt, "date") else ref_dt
            m_key = str(ref_date)[:7] if ref_date else "unknown"

            months_data[m_key]["labor"] += labor_by_wo.get(r.work_order.id, 0.0)
            p_total, p_cost = parts_by_wo.get(r.work_order.id, (0.0, 0.0))
            months_data[m_key]["parts"] += p_total
            months_data[m_key]["parts_cost"] += p_cost

        # 2. Paid retail parts sales in the window
        retail_sales = db(
            (db.sale.status == "paid")
            & (db.sale.equipment_id == None)
            & (db.sale.sale_date >= window_start)
        ).select(db.sale.id, db.sale.sale_date)
        retail_ids = [s.sale.id for s in retail_sales]
        lines_by_sale = {}
        if retail_ids:
            for r in (
                db(db.sale_line.sale_id.belongs(retail_ids))
                .select(
                    db.sale_line.sale_id,
                    db.sale_line.total.sum(),
                    (db.sale_line.unit_cost * db.sale_line.quantity).sum(),
                )
                .groupby(db.sale_line.sale_id)
            ):
                lines_by_sale[r.sale_line.sale_id] = (
                    float(r.sale_line[db.sale_line.total.sum()] or 0.0),
                    float(
                        r.sale_line[
                            (db.sale_line.unit_cost * db.sale_line.quantity).sum()
                        ]
                        or 0.0
                    ),
                )
        for s in retail_sales:
            m_key = str(s.sale_date)[:7] if s.sale_date else "unknown"
            p_total, p_cost = lines_by_sale.get(s.sale.id, (0.0, 0.0))
            months_data[m_key]["parts"] += p_total
            months_data[m_key]["parts_cost"] += p_cost

        # 3. Paid equipment sales in the window
        equip_sales = db(
            (db.sale.status == "paid")
            & (db.sale.equipment_id != None)
            & (db.sale.sale_date >= window_start)
        ).select(
            db.sale.id,
            db.sale.sale_price,
            db.sale.trade_in_value,
            db.sale.sale_date,
            db.sale.equipment_id,
        )
        for s in equip_sales:
            m_key = str(s.sale_date)[:7] if s.sale_date else "unknown"
            val = float(s.sale_price or 0.0) - float(s.trade_in_value or 0.0)
            months_data[m_key]["equipment"] += val
            equip = db.equipment[s.equipment_id]
            if equip:
                months_data[m_key]["equipment_cost"] += float(
                    equip.acquisition_cost or 0.0
                )

        # Sort and project
        sorted_months = sorted(
            [k for k in months_data.keys() if k != "unknown"], reverse=True
        )[:max_months]
        result = []
        for m in sorted_months:
            d = months_data[m]
            total_rev = d["labor"] + d["parts"] + d["equipment"]
            total_cogs = d["parts_cost"] + d["equipment_cost"]
            gp = total_rev - total_cogs
            margin_pct = (gp / total_rev * 100.0) if total_rev > 0 else 0.0
            result.append(
                {
                    "month": m,
                    "labor": float(d["labor"]),
                    "parts": float(d["parts"]),
                    "equipment": float(d["equipment"]),
                    "total_revenue": float(total_rev),
                    "cogs": float(total_cogs),
                    "gross_profit": float(gp),
                    "gross_margin": float(margin_pct),
                }
            )
        return result
