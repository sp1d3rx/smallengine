"""Sales and Retail POS domain contexts."""
from datetime import date
from decimal import Decimal
from ..gantrika.context import BaseContext, NotFoundError, BusinessRuleError
from ..roles.base import cast
from ..roles.customer_roles import BillableRole
from ..roles.equipment_roles import SellableRole, TradeInRole
from ..roles.sales_roles import CashRegisterSaleRole
from ..settings import SALES_TAX_RATE


class CreateRetailSaleContext(BaseContext):
    """Start a new open retail checkout session."""

    def execute(self, employee_id: int = None) -> dict:
        with self.transaction():
            sale_id = self.db.sale.insert(
                status="open",
                sale_date=date.today(),
                employee_id=employee_id,
                subtotal=0.0,
                tax_amount=0.0,
                total=0.0,
            )
            return {"id": sale_id}


class GetRetailSaleContext(BaseContext):
    """Retrieve full retail sale details including lines and customer profile."""

    def execute(self, sale_id: int) -> dict:
        sale = self.db.sale[sale_id]
        if not sale:
            raise NotFoundError(f"Sale {sale_id} not found")
        lines = self.db(self.db.sale_line.sale_id == sale_id).select(
            orderby=self.db.sale_line.created_on
        )
        customer = self.db.customer[sale.customer_id] if sale.customer_id else None
        return {
            "sale": sale.as_dict(),
            "lines": [r.as_dict() for r in lines],
            "customer": customer.as_dict() if customer else None,
        }


class AddRetailLineContext(BaseContext):
    """Add or increment a catalog part line in an open retail sale."""

    def execute(self, sale_id: int, part_id: int, quantity: int = 1) -> dict:
        with self.transaction():
            sale_row = self.db.sale[sale_id]
            if not sale_row:
                raise NotFoundError(f"Sale {sale_id} not found")
            part_row = self.db.part[part_id]
            if not part_row:
                raise NotFoundError(f"Part {part_id} not found")

            register = cast(sale_row, CashRegisterSaleRole, table_name="sale")
            try:
                register.add_item(self.db, part_row, quantity)
            except ValueError as e:
                raise BusinessRuleError(str(e))

            return GetRetailSaleContext(self.db).execute(sale_id)


class RemoveRetailLineContext(BaseContext):
    """Remove a line item from an open retail sale."""

    def execute(self, sale_id: int, line_id: int) -> dict:
        with self.transaction():
            sale_row = self.db.sale[sale_id]
            if not sale_row:
                raise NotFoundError(f"Sale {sale_id} not found")

            register = cast(sale_row, CashRegisterSaleRole, table_name="sale")
            try:
                register.remove_item(self.db, line_id)
            except ValueError as e:
                raise BusinessRuleError(str(e))

            return GetRetailSaleContext(self.db).execute(sale_id)


class PayRetailSaleContext(BaseContext):
    """Finalize an open retail sale with payment, decrement stock, and create invoice."""

    def execute(self, sale_id: int, payment_method: str = "cash",
                customer_id: int = None, cash_customer_name: str = None,
                payment_reference: str = None) -> dict:
        with self.transaction():
            sale_row = self.db.sale[sale_id]
            if not sale_row:
                raise NotFoundError(f"Sale {sale_id} not found")

            register = cast(sale_row, CashRegisterSaleRole, table_name="sale")
            try:
                inv_id = register.finalize_payment(
                    self.db,
                    payment_method=payment_method,
                    customer_id=customer_id,
                    cash_customer_name=cash_customer_name,
                    payment_reference=payment_reference,
                )
            except ValueError as e:
                raise BusinessRuleError(str(e))

            return {"ok": True, "sale_id": sale_id, "invoice_id": inv_id}


class VoidRetailSaleContext(BaseContext):
    """Void a retail sale and restock parts if previously paid."""

    def execute(self, sale_id: int) -> dict:
        with self.transaction():
            sale_row = self.db.sale[sale_id]
            if not sale_row:
                raise NotFoundError(f"Sale {sale_id} not found")

            register = cast(sale_row, CashRegisterSaleRole, table_name="sale")
            register.void(self.db)
            return {"ok": True}


class ReturnRetailSaleContext(BaseContext):
    """Process partial or full returns on a paid sale and restock returned items."""

    def execute(self, sale_id: int, return_items: list) -> dict:
        with self.transaction():
            sale_row = self.db.sale[sale_id]
            if not sale_row:
                raise NotFoundError(f"Sale {sale_id} not found")

            register = cast(sale_row, CashRegisterSaleRole, table_name="sale")
            try:
                register.process_return(self.db, return_items)
            except ValueError as e:
                raise BusinessRuleError(str(e))

            return {"ok": True}


class SellEquipmentContext(BaseContext):
    """Sell a piece of shop inventory (new or renewed) to a customer with optional trade-in."""

    def __init__(self, db, customer_row, equipment_row):
        super().__init__(db)
        self.customer = cast(customer_row, BillableRole, table_name="customer")
        self.equipment = cast(equipment_row, SellableRole, table_name="equipment")

    def execute(self, sale_price: Decimal, employee_id: int = None,
                payment_method: str = "card",
                trade_in_row=None, trade_in_value: Decimal = Decimal("0"),
                trade_in_disposition: str = "renewed") -> dict:
        with self.transaction():
            if not self.equipment.is_available():
                raise BusinessRuleError(
                    f"Equipment condition '{self.equipment.condition}' is not available for sale"
                )

            tax_rate = Decimal(str(SALES_TAX_RATE))
            tax_amount = sale_price * tax_rate
            total = (sale_price + tax_amount) - trade_in_value

            trade_in_id = None
            if trade_in_row:
                trade_in_id = trade_in_row.id
                trade_in = cast(trade_in_row, TradeInRole, table_name="equipment")
                if trade_in_disposition == "renewed":
                    trade_in.assign_to_renewed_inventory(self.db, trade_in_value)
                else:
                    trade_in.assign_to_scrap(self.db)

            sale_id = self.db.sale.insert(
                customer_id=self.customer.id,
                equipment_id=self.equipment.id,
                employee_id=employee_id,
                sale_price=float(sale_price),
                trade_in_equipment_id=trade_in_id,
                trade_in_value=float(trade_in_value),
                tax_rate=float(tax_rate),
                tax_amount=float(tax_amount),
                total=float(total),
                payment_method=payment_method,
                sale_date=date.today(),
            )

            # Transfer equipment ownership to customer
            self.db(self.db.equipment.id == self.equipment.id).update(
                customer_id=self.customer.id,
                condition="customer_owned",
            )

            invoice_id = self.db.invoice.insert(
                sale_id=sale_id,
                customer_id=self.customer.id,
                subtotal=float(sale_price),
                tax_amount=float(tax_amount),
                total=float(total),
                status="draft",
            )

            return {
                "sale_id": sale_id,
                "invoice_id": invoice_id,
                "sale_price": float(sale_price),
                "tax_amount": float(tax_amount),
                "trade_in_value": float(trade_in_value),
                "total": float(total),
            }
