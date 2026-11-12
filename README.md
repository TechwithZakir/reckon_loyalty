# Retail Loyalty (`reckon_loyalty`)

Retail CRM, membership and loyalty for ERPNext and Frappe CRM, with a POS integration API.
Built as a separate Frappe app so it installs beside ERPNext without changing it.

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the demo walkthrough and
[docs/POS_API.md](docs/POS_API.md) for the integration API.

## Install

```bash
bench get-app reckon_loyalty <repo-url>
bench --site <site> install-app reckon_loyalty
bench build --app reckon_loyalty
bench --site <site> execute reckon_loyalty.demo.seed.run   # optional Sailor demo data
```

Requires Frappe and ERPNext 15 or 16. Frappe CRM is optional.
