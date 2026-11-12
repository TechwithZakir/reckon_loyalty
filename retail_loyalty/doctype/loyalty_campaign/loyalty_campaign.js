frappe.ui.form.on("Loyalty Campaign", {
	refresh(frm) {
		if (frm.is_new()) return;
		const manager = frappe.user.has_role(["Loyalty Manager", "System Manager"]);
		const base = "reckon_loyalty.services.campaigns.";

		frm.add_custom_button(__("Preview Message"), () => {
			frappe.call(base + "preview_message", { campaign: frm.doc.name }).then((r) => {
				const m = r.message;
				const esc = frappe.utils.escape_html;
				frappe.msgprint({
					title: __("Preview for {0}", [m.member]),
					message: `
						${m.sms ? `<h6>${__("SMS")} <span class="text-muted">(${m.sms.length} ${__("characters")})</span></h6><div class="rl-sms">${esc(m.sms)}</div>` : ""}
						${m.email_subject ? `<h6 class="mt-3">${__("Email")}: ${esc(m.email_subject)}</h6><div class="rl-email">${m.email_message}</div>` : ""}`,
					wide: true,
				});
			});
		});

		if (manager && ["Draft", "Scheduled"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Send Now"), () => {
				frappe.confirm(__("Send this campaign to segment {0} now?", [frm.doc.segment.bold()]), () => {
					frappe.call({ method: base + "send_now", args: { campaign: frm.doc.name }, freeze: true }).then((r) => {
						const m = r.message || {};
						frappe.msgprint(
							m.queued
								? __("Queued for {0} members.", [m.targeted])
								: __("{0} members targeted: {1} SMS, {2} emails, {3} skipped or failed.{4}", [
										m.targeted,
										m.sms,
										m.email,
										m.failed,
										m.demo_mode ? " " + __("Demo mode is on, so messages were logged and not sent.") : "",
								  ])
						);
						frm.reload_doc();
					});
				});
			}).addClass("btn-primary");
		}
		if (manager && frm.doc.status === "Draft") {
			frm.add_custom_button(__("Schedule"), () => {
				frappe.call(base + "schedule", { campaign: frm.doc.name }).then(() => frm.reload_doc());
			});
		}
		if (manager && frm.doc.status === "Scheduled") {
			frm.add_custom_button(__("Cancel Schedule"), () => {
				frappe.call(base + "cancel_schedule", { campaign: frm.doc.name }).then(() => frm.reload_doc());
			});
		}
		if (frm.doc.status === "Sent") {
			frm.add_custom_button(__("Refresh Results"), () => {
				frappe.call(base + "refresh_results", { campaign: frm.doc.name }).then(() => frm.reload_doc());
			});
			frm.add_custom_button(__("Message Log"), () => {
				frappe.set_route("List", "Loyalty Message Log", { campaign: frm.doc.name });
			});
		}
	},
});
