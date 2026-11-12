import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ("Loyalty Manager", "Loyalty User", "Loyalty POS")

CUSTOM_FIELDS = {
    "Customer": [
        {
            "fieldname": "loyalty_member",
            "label": "Loyalty Member",
            "fieldtype": "Link",
            "options": "Loyalty Member",
            "insert_after": "loyalty_program_tier",
            "read_only": 1,
            "no_copy": 1,
        }
    ],
    "Sales Invoice": [
        {
            "fieldname": "loyalty_member",
            "label": "Loyalty Member",
            "fieldtype": "Link",
            "options": "Loyalty Member",
            "insert_after": "loyalty_program",
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
        },
        {
            "fieldname": "loyalty_store",
            "label": "Loyalty Store",
            "fieldtype": "Link",
            "options": "Loyalty Store",
            "insert_after": "loyalty_member",
            "no_copy": 1,
        },
        {
            "fieldname": "pos_external_id",
            "label": "POS Transaction ID",
            "fieldtype": "Data",
            "insert_after": "loyalty_store",
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
        },
    ],
}


def after_install():
    setup()


def after_migrate():
    setup()


def create_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def setup():
    create_roles()
    create_custom_fields(CUSTOM_FIELDS, update=True)


def can_see_app():
    if frappe.session.user == "Administrator":
        return True
    return bool({"Loyalty Manager", "Loyalty User", "System Manager"} & set(frappe.get_roles()))
