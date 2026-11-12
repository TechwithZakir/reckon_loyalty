# Sailor CRM and Loyalty Demo Guide

A demo of the proposed retail CRM for Sailor (Epyllion Group) on Frappe and ERPNext.
It is delivered as a separate app, `reckon_loyalty`, that installs beside ERPNext and
Frappe CRM without modifying either.

## How the pieces fit

| Layer | Product | Role in the solution |
|---|---|---|
| System of record | ERPNext | Customer, Item, Sales Invoice, accounts, and the **Loyalty Program** and **Loyalty Point Entry** ledger (tiers, earn rate, point value, expiry) |
| Loyalty platform | `reckon_loyalty` (this app) | Members, digital card and QR, stores, rewards, segments, campaigns, POS API, dashboard |
| Relationship work | Frappe CRM | Leads created from web and app sign-ups and from segments, for clienteling and call-centre follow-up |
| Point of sale | Sailor's existing POS | Calls the POS API. The **POS Simulator** page stands in for it during the demo |

Points are not a parallel ledger. A sale earns and redeems through ERPNext's standard
Sales Invoice loyalty fields, so finance sees the redemption expense and the outstanding
liability in the books they already use.

## Requirement coverage

| # | Sailor's requirement | Where it is in the demo |
|---|---|---|
| 1 | Customer registration and digital membership card | `/loyalty-join` (self sign-up), POS Simulator > New member, Loyalty Member form. Card at `/card/<token>` |
| 2 | QR code based identification | QR on the digital card and on the member form. POS Simulator > Scan QR, or `lookup_member` |
| 3 | Customer profile and purchase history | Loyalty Member form: summary, Purchase History tab, points ledger. Same data on the digital card |
| 4 | Loyalty points, rewards and tier management | ERPNext Loyalty Program "Sailor Club" (Blue, Silver, Gold, Platinum), Loyalty Reward, Loyalty Reward Redemption, welcome and birthday bonus in Loyalty Settings |
| 5 | Segmentation and targeted campaigns | Loyalty Segment (profile, behaviour, category and consent rules with live preview), Create Campaign from a segment |
| 6 | POS API integration and real-time sync | `reckon_loyalty.api.pos.*` (see POS_API.md), Loyalty POS Sync Log, POS Simulator "API traffic" panel |
| 7 | SMS, email and promotional campaigns | Loyalty Campaign: personalised SMS and email, bonus points, schedule, Loyalty Message Log |
| 8 | Customer analytics and management dashboard | Loyalty Dashboard page |
| 9 | Mobile application and digital card integration | Mobile-first card page that can be added to the home screen, and the JSON API behind it (`api.member.get_card`, `api.member.join`) for a native app |

## Demo data

Seeded by `bench --site <site> execute reckon_loyalty.demo.seed.run` under its own company
**Sailor (Demo)**, so it does not mix with other companies on the site.

- 38 products in five categories with the names and list prices shown on sailor.clothing
  (November 2026), and 8 real outlets from the store locator.
- 60 **fictional** members (invented names, placeholder mobile numbers, example.com emails)
  with about six months of purchases posted through the POS API.
- Sailor Club tiers: Blue from Tk 0 (1 point per Tk 100), Silver from Tk 20,000 (per Tk 80),
  Gold from Tk 50,000 (per Tk 60), Platinum from Tk 100,000 (per Tk 50). 1 point = Tk 1,
  valid 365 days. These numbers are placeholders to be replaced with Sailor's own rules.
- 5 rewards, 7 segments, 3 campaigns (one sent, one draft with bonus points, one draft).

**Demo Mode** is on in Loyalty Settings: SMS and email are written to Loyalty Message Log
with status *Simulated* and nothing is sent. Turn it off only after an SMS gateway is set in
SMS Settings and real, consented contacts are loaded.

## Walkthrough (about 25 minutes)

1. **Dashboard** (`/app/loyalty-dashboard`), 3 min. Members, active rate, member sales,
   points issued and redeemed, outstanding liability, tier mix, sales by store and category,
   behaviour segments, campaign results. Filter by store.
2. **Join as a customer** (`/loyalty-join` on a phone), 3 min. Register, land on the digital
   card with the QR code and 100 welcome points. Show the simulated welcome SMS in Loyalty
   Message Log, and the lead that appeared in Frappe CRM (`/crm`).
3. **Sale at the till** (`/app/loyalty-pos-simulator`), 6 min. Scan the QR from the phone.
   Add items, complete the sale, read the response: invoice number, points earned, new
   balance, distance to the next tier. Open the invoice in ERPNext. Refresh the card on the phone.
4. **Redeem points**, 2 min. Pick an existing member with a balance (search by mobile),
   add items, press Max, complete. Show the redemption in the points ledger.
5. **API view**, 2 min. The "API traffic" panel shows the exact request and response.
   Open Loyalty POS Sync Log for the audit trail. Explain the idempotency key.
6. **Member 360** (Loyalty Member form), 2 min. Card, QR, purchase history, points ledger,
   Adjust Points, Redeem a Reward (issues a voucher code).
7. **Segments**, 3 min. Open "Lapsed 60 Days", preview members. Build a new one live, for
   example Gold tier + bought Footwear in 90 days. Send to Frappe CRM for clienteling.
8. **Campaign**, 3 min. Open "We Miss You: 200 Bonus Points", Preview Message, Send Now.
   Show the message log and the bonus points on a member. Open "Winter Collection Preview"
   for results: reach, orders and revenue inside the offer window.
9. **Programme rules**, 1 min. ERPNext Loyalty Program "Sailor Club" and Loyalty Settings.

## What is demo-grade and what a project would add

- **POS connector.** The API is real; the connector inside Sailor's POS has to be built with
  the POS vendor. Offline tills are supported by `posting_date` and the idempotency key.
- **SMS gateway.** Uses Frappe's SMS Settings. A Bangladeshi gateway (and masking ID) must be configured.
- **Native mobile app.** The card is a mobile web page backed by a JSON API. A native app or
  Apple/Google Wallet pass would consume the same API. OTP verification of the mobile number
  at sign-up is not in the demo and should be added before go-live.
- **One programme per site.** Loyalty Settings holds a single company and programme.
- **Partial returns** go through ERPNext's own return screen; the API posts full returns.
- **Volumes.** Segments read statistics cached on the member, so they scale; the nightly
  refresh should move to batched background jobs at Sailor's member count.
- **Tax.** Prices are treated as VAT-inclusive with no tax rows. Sailor's VAT setup would be applied in ERPNext.
