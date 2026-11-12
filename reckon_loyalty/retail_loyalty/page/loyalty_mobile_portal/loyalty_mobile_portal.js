frappe.pages["loyalty-mobile-portal"].on_page_load = function (wrapper) {
	const title = __("Mobile Application / Digital Customer Card Integration");
	const page = frappe.ui.make_app_page({ parent: wrapper, title, single_column: true });
	const join_url = `${window.location.origin}/loyalty-join`;
	const $body = $('<div class="rl-mobile-portal"></div>').appendTo(page.main);

	page.set_primary_action(
		__("Open Customer Registration"),
		() => window.open(join_url, "_blank", "noopener"),
		"external-link"
	);
	page.add_inner_button(__("Loyalty Members"), () => frappe.set_route("List", "Loyalty Member"));

	$body.html(`
		<div class="rl-panel">
			<h4>${title}</h4>
			<p>${__("Share this public registration page with customers. It creates the ERPNext customer and loyalty membership, then opens their mobile digital card.")}</p>
			<p><a href="${frappe.utils.escape_html(join_url)}" target="_blank" rel="noopener">${frappe.utils.escape_html(join_url)}</a></p>
		</div>
		<div class="rl-panel">
			<h5>${__("Existing member cards")}</h5>
			<p>${__("Open a Loyalty Member record and choose Open Digital Card to view that member's QR code, points, vouchers and purchase history.")}</p>
			<p>${__("Customers can save their card page to a phone home screen. The QR token and card API also support a future native mobile application.")}</p>
		</div>
	`);
};
