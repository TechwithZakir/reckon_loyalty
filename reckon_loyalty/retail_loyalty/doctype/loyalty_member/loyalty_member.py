import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, today

from reckon_loyalty.services.utils import get_settings, normalize_mobile


class LoyaltyMember(Document):
    def autoname(self):
        prefix = (get_settings().card_prefix or "RL").upper()
        self.card_number = make_autoname(f"{prefix}.YY.######")
        self.name = self.card_number

    def before_insert(self):
        settings = get_settings()
        # Always the programme's company: Frappe pre-fills Link fields named "company" with
        # the user's default, which may be a different company on a shared site.
        self.company = settings.company
        self.loyalty_program = settings.loyalty_program
        self.enrollment_date = self.enrollment_date or today()
        self.qr_token = frappe.generate_hash(length=24)
        if not self.company or not self.loyalty_program:
            frappe.throw(_("Set the Company and Loyalty Program in Loyalty Settings first."))

    def validate(self):
        self.member_name = (self.member_name or "").strip()
        self.mobile_no = normalize_mobile(self.mobile_no)
        if self.email:
            self.email = self.email.strip().lower()
        duplicate = frappe.db.get_value(
            "Loyalty Member", {"mobile_no": self.mobile_no, "name": ["!=", self.name or ""]}, "card_number"
        )
        if duplicate:
            frappe.throw(_("Mobile {0} is already registered with card {1}.").format(self.mobile_no, duplicate))
        if self.is_new() and not self.customer:
            self.customer = self.create_customer()

    def after_insert(self):
        settings = get_settings()
        frappe.db.set_value(
            "Customer",
            self.customer,
            {"loyalty_member": self.name, "loyalty_program": self.loyalty_program},
            update_modified=False,
        )

        from reckon_loyalty.services import campaigns, crm_sync, members, points

        if cint(settings.welcome_bonus_points) and not self.flags.skip_welcome:
            points.add_points(self, settings.welcome_bonus_points, "Welcome bonus", posting_date=self.enrollment_date)
        members.refresh_member_stats(self.name)
        if not self.flags.skip_welcome:
            campaigns.send_welcome(self)
        if (
            cint(settings.create_crm_lead)
            and self.enrollment_channel in ("Web", "Mobile App")
            and not self.flags.skip_crm_lead
        ):
            crm_sync.create_lead_for_member(self.name)

    def on_trash(self):
        if self.customer and frappe.db.get_value("Customer", self.customer, "loyalty_member") == self.name:
            frappe.db.set_value("Customer", self.customer, "loyalty_member", None, update_modified=False)

    def create_customer(self):
        settings = get_settings()
        customer = frappe.new_doc("Customer")
        customer.update(
            {
                "customer_name": self.member_name,
                "customer_type": "Individual",
                "customer_group": settings.customer_group
                or frappe.db.get_single_value("Selling Settings", "customer_group"),
                "territory": settings.territory or frappe.db.get_single_value("Selling Settings", "territory"),
                "mobile_no": self.mobile_no,
                "email_id": self.email,
                "gender": self.gender if self.gender and frappe.db.exists("Gender", self.gender) else None,
                "loyalty_program": self.loyalty_program,
            }
        )
        # Sites running the Reckon SaaS apps scope customers to a company through this field.
        if customer.meta.has_field("rd_company"):
            customer.rd_company = self.company
        customer.flags.ignore_permissions = True
        customer.insert()
        return customer.name
