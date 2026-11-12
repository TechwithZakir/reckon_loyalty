import frappe
from frappe import _
from frappe.utils import today

from reckon_loyalty.services import members as member_service
from reckon_loyalty.services import points as points_service
from reckon_loyalty.services.utils import require_role, tier_rank


def available_rewards(member=None):
    """Active rewards, flagged with whether this member can afford and unlock them."""
    rewards = frappe.get_all(
        "Loyalty Reward",
        filters={"is_active": 1},
        fields=[
            "name",
            "reward_name",
            "reward_type",
            "points_required",
            "voucher_value",
            "discount_percent",
            "item",
            "minimum_tier",
            "valid_days",
            "description",
        ],
        order_by="points_required asc",
    )
    if member:
        if isinstance(member, str):
            member = frappe.get_doc("Loyalty Member", member)
        balance = points_service.get_balance(member.customer, member.loyalty_program, member.company)
        rank = tier_rank(member.loyalty_program, member.tier)
        for reward in rewards:
            unlocked = (
                not reward.minimum_tier or rank >= tier_rank(member.loyalty_program, reward.minimum_tier)
            )
            reward["unlocked"] = unlocked
            reward["can_redeem"] = unlocked and balance >= reward.points_required
            reward["points_short"] = max(0, reward.points_required - balance)
    return rewards


@frappe.whitelist()
def redeem_reward(member, reward, store=None):
    """Swap points for a reward voucher. Returns the voucher."""
    require_role()
    doc = frappe.get_doc(
        {"doctype": "Loyalty Reward Redemption", "member": member_service.get_member(member).name, "reward": reward, "store": store}
    )
    doc.flags.ignore_permissions = True
    doc.insert()
    return {
        "redemption": doc.name,
        "voucher_code": doc.voucher_code,
        "valid_till": doc.valid_till,
        "points": doc.points,
        "reward": doc.reward,
    }


@frappe.whitelist()
def cancel_redemption(redemption):
    """Cancel an unused voucher and give the points back."""
    require_role(("Loyalty Manager", "System Manager"))
    doc = frappe.get_doc("Loyalty Reward Redemption", redemption)
    if doc.status != "Issued":
        frappe.throw(_("Only an Issued voucher can be cancelled."))
    points_service.add_points(doc.member, doc.points, f"Refund of cancelled voucher {doc.voucher_code}")
    doc.db_set("status", "Cancelled")
    member_service.refresh_member_stats(doc.member)


@frappe.whitelist()
def mark_used(voucher_code, store=None):
    """Called by the till when the voucher is accepted."""
    require_role()
    name = frappe.db.get_value("Loyalty Reward Redemption", {"voucher_code": (voucher_code or "").strip().upper()})
    if not name:
        frappe.throw(_("Voucher {0} was not found.").format(voucher_code), frappe.DoesNotExistError)
    doc = frappe.get_doc("Loyalty Reward Redemption", name)
    if doc.status != "Issued":
        frappe.throw(_("Voucher {0} is {1}.").format(doc.voucher_code, doc.status))
    if doc.valid_till and str(doc.valid_till) < today():
        frappe.throw(_("Voucher {0} expired on {1}.").format(doc.voucher_code, doc.valid_till))
    doc.db_set({"status": "Used", "store": store or doc.store})
    return {"voucher_code": doc.voucher_code, "reward": doc.reward, "status": "Used"}


def expire_vouchers():
    frappe.db.sql(
        "update `tabLoyalty Reward Redemption` set status = 'Expired' where status = 'Issued' and valid_till < %s",
        today(),
    )
