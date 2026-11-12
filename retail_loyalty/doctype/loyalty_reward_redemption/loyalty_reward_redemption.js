frappe.ui.form.on("Loyalty Reward Redemption", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Issued") return;
		if (frappe.user.has_role(["Loyalty Manager", "System Manager"])) {
			frm.add_custom_button(__("Cancel and Refund Points"), () => {
				frappe.confirm(__("Cancel voucher {0} and return {1} points?", [frm.doc.voucher_code, frm.doc.points]), () => {
					frappe
						.call("reckon_loyalty.services.rewards.cancel_redemption", { redemption: frm.doc.name })
						.then(() => frm.reload_doc());
				});
			});
		}
		frm.add_custom_button(__("Mark as Used"), () => {
			frappe
				.call("reckon_loyalty.services.rewards.mark_used", { voucher_code: frm.doc.voucher_code })
				.then(() => frm.reload_doc());
		});
	},
});
