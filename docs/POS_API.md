# POS Integration API

All endpoints are standard Frappe REST methods.

```
POST https://<site>/api/method/reckon_loyalty.api.pos.<method>
Authorization: token <api_key>:<api_secret>
Content-Type: application/json
```

Create one integration user per POS vendor or per store, give it the **Loyalty POS** role and
generate its API key from the User form (Settings > API Access). Responses are wrapped by
Frappe as `{"message": ...}`. Errors return a non-2xx status with the reason in `_server_messages`.

## Flow at the till

| Step | Call | When |
|---|---|---|
| 1 | `lookup_member` | Cashier scans the QR code on the digital card, or types the card or mobile number |
| 1b | `register_member` | New customer: enrol on the spot, card link goes out by SMS |
| 2 | `sync_transaction` | Sale is tendered. Posts the invoice, redeems and earns points in one call |
| 3 | `sync_return` | A sale is returned in full |
| opt. | `get_rewards`, `redeem_reward`, `use_voucher` | Reward catalogue and vouchers |
| opt. | `get_items`, `get_stores` | If the POS pulls its catalogue and store list from ERPNext |

## `lookup_member`

Request: `{"identifier": "RL1:4f0c...e2"}`. The identifier may be the QR payload, the card
link, the card number (`SLR26000012`) or the mobile number (`017XXXXXXXX`).

Response (abridged):

```json
{
  "member_name": "Nusrat Rahman", "card_number": "SLR26000012", "mobile_no": "01700555011",
  "status": "Active", "tier": "Gold", "next_tier": "Platinum", "spend_to_next_tier": 18240.0,
  "points_balance": 742, "points_value": 742.0, "point_value": 1.0,
  "earn_rule": "1 point for every 60 spent", "lifetime_spend": 81760.0,
  "qr_payload": "RL1:4f0c...e2", "rewards": [ ... rewards the member can redeem now ... ]
}
```

`points_balance * point_value` is the most the cashier may offer as a points discount.

## `register_member`

```json
{"member_name": "Arif Hossain", "mobile_no": "01712345678", "email": "", "gender": "Male",
 "date_of_birth": "1992-04-18", "store": "BSH"}
```

Returns the same profile as `lookup_member`, plus `already_registered`. A mobile number that
is already a member returns the existing card rather than an error, so the cashier can continue.

## `sync_transaction`

```json
{
  "external_id": "BSH-T01-000184",
  "member": "RL1:4f0c...e2",
  "store": "BSH",
  "terminal": "T01",
  "items": [
    {"item_code": "SLR-M-113", "qty": 1, "rate": 2990},
    {"item_code": "SLR-A-503", "qty": 1}
  ],
  "redeem_points": 300,
  "payments": [{"mode_of_payment": "Cash", "amount": 5080}],
  "posting_date": "2026-11-12"
}
```

- `external_id` is the POS receipt number and the **idempotency key**. Sending the same id again
  returns the first result with `"duplicate": true` and posts nothing, so the POS can retry
  safely after a timeout.
- `rate` is optional; without it the retail price list rate is used.
- `payments` is optional; without it one payment for the amount due is recorded in the default mode.
  When given, it must add up to the bill minus the points discount.
- `posting_date` is optional, for tills that were offline and sync later.

Response:

```json
{
  "external_id": "BSH-T01-000184", "invoice": "ACC-SINV-2026-00412",
  "grand_total": 5380.0, "points_redeemed": 300, "redeemed_amount": 300.0, "amount_paid": 5080.0,
  "points_earned": 84, "points_balance": 526, "points_value": 526.0,
  "tier": "Gold", "next_tier": "Platinum", "spend_to_next_tier": 12860.0, "duplicate": false
}
```

What happens in ERPNext, inside one database transaction:

1. A submitted **Sales Invoice** (POS type, paid) for the member's Customer, tagged with the store
   and the POS receipt number.
2. Redeemed points are deducted oldest-first and booked to the loyalty expense account.
3. Earned points are written to the **Loyalty Point Entry** ledger at the member's tier rate, with
   their expiry date.
4. The member's tier, balance and purchase statistics are refreshed.

If any step fails nothing is posted, and the request and error are kept in **Loyalty POS Sync Log**.

## `sync_return`

```json
{"external_id": "BSH-T01-R00012", "original_external_id": "BSH-T01-000184"}
```

Posts a full credit note against the original sale. ERPNext removes the points earned on that
sale and gives back the points that were redeemed on it. A sale whose earned points were already
redeemed on a later sale cannot be returned until that later redemption is reversed (standard
ERPNext rule).

## Rewards

- `get_rewards` `{"identifier": "..."}`: the catalogue, each reward flagged `can_redeem`.
- `redeem_reward` `{"identifier": "...", "reward": "Tk 500 Shopping Voucher", "store": "BSH"}`:
  deducts the points and returns `voucher_code` and `valid_till`.
- `use_voucher` `{"voucher_code": "V8K2M4QXA1", "store": "BSH"}`: marks the voucher used.
  Fails when the voucher is unknown, already used, cancelled or expired.

## Customer-facing endpoints (no login)

For the digital card page and a mobile app. The card is addressed by its secret token, never
by mobile number. Both are rate limited per IP address.

- `GET /api/method/reckon_loyalty.api.member.get_card?token=<token>`: profile, QR code (SVG),
  tier ladder, recent purchases, points activity, rewards and vouchers.
- `POST /api/method/reckon_loyalty.api.member.join`: self-registration. For a number that is
  already a member it does not reveal the card; it re-sends the card link by SMS.

## curl example

```bash
curl -X POST "https://<site>/api/method/reckon_loyalty.api.pos.lookup_member" -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"identifier": "01700555011"}'
```
