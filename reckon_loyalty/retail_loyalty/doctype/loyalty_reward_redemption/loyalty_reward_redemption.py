import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, today

from reckon_loyalty.services.utils import tier_rank


class LoyaltyRewardRedemption(Document):
    def before_insert(self):
        reward = frappe.get_doc("Loyalty Reward", self.reward)
        member = frappe.get_doc("Loyalty Member", self.member)
        if not reward.is_active:
            frappe.throw(_("Reward {0} is not active.").format(reward.name))
        if member.status != "Active":
            frappe.throw(_("Member {0} is {1}.").format(member.member_name, member.status))
        if reward.minimum_tier and tier_rank(member.loyalty_program, member.tier) < tier_rank(
            member.loyalty_program, reward.minimum_tier
        ):
            frappe.throw(_("{0} is available from the {1} tier.").format(reward.name, reward.minimum_tier))

        self.points = cint(reward.points_required)
        self.company = member.company
        self.status = "Issued"
        self.issued_on = today()
        self.valid_till = add_days(today(), cint(reward.valid_days) or 30)
        self.voucher_code = "V" + frappe.generate_hash(length=9).upper()

    def after_insert(self):
        from reckon_loyalty.services import members, points

        # Throws when the balance is short, which rolls the voucher back with it.
        points.redeem_points(self.member, self.points, f"Reward: {self.reward} ({self.voucher_code})")
        members.refresh_member_stats(self.member)

    def on_trash(self):
        if self.status == "Issued":
            frappe.throw(_("Cancel the voucher instead of deleting it, so the points are returned."))
