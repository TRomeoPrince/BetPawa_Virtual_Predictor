# Verified subscription payments — integration checklist

This feature branch is based on `feature/client-ready-site` and **does not deploy or charge customers** on its own. It adds a verified payment ledger and the first working payment-provider adapter. Do not merge or enable live checkout until approved and tested.

## Payment methods

- **MTN MoMo** and **Airtel Money**: routed to Flutterwave's Uganda mobile-money checkout (`mobilemoneyuganda`). The hosted checkout may show both networks; selecting the button does not force a network.
- **Flutterwave**: hosted checkout for UGX card or Uganda mobile money.
- **Cryptocurrency**: listed as *coming soon* until a wallet/payment processor with verifiable transaction callbacks is configured.
- **Binance Pay**: listed as *coming soon* until a Binance Pay merchant account, authenticated create-order API and signed settlement notifications are integrated. A Binance Pay ID or transfer screenshot alone is **not** proof of payment.

Flutterwave supports UGX mobile money and cards, subject to merchant eligibility, account approval and payment-provider policy. Obtain explicit approval from the payment processor for this product's business category before taking live payments.

## Configuration (server environment variables; never commit secrets)

- `PREDICTOR_PUBLIC_BASE_URL`: externally reachable HTTPS origin, e.g. `https://predictor.example.com`. No trailing path.
- `FLW_SECRET_KEY`: Flutterwave **server-side** secret key for the correct test/live environment.
- `FLW_WEBHOOK_HASH`: random Flutterwave v3 webhook secret hash; must match Flutterwave Dashboard > Webhooks.
- `PREDICTOR_PRICE_DAILY_UGX`, `PREDICTOR_PRICE_WEEKLY_UGX`, `PREDICTOR_PRICE_MONTHLY_UGX`, `PREDICTOR_PRICE_QUARTERLY_UGX`, `PREDICTOR_PRICE_HALF_YEAR_UGX`, `PREDICTOR_PRICE_ANNUAL_UGX`: positive integer UGX prices, configured only after pricing approval.

**No live prices are hardcoded.** A plan without a configured price cannot start checkout. The current manual access-request/approval path remains available. Receipt email is required at checkout by Flutterwave; username/password remains the app login method.

Set Flutterwave's **v3** webhook URL to:

`https://YOUR_PUBLIC_DOMAIN/api/payments/flutterwave/webhook`

Flutterwave must send its `verif-hash` header, matching `FLW_WEBHOOK_HASH`. If the merchant account uses v4 signature-based webhooks instead, update the integration for v4 rather than bypassing signature validation.

## Activation logic

1. Client signs in, chooses a priced plan and payment method, supplies a receipt email and confirms they are 25+.
2. Server records a unique order and creates a Flutterwave-hosted checkout.
3. Flutterwave redirects the user back and/or sends a signed webhook.
4. Server queries Flutterwave **server-to-server** using the exact merchant transaction reference.
5. Only a successful transaction with the correct reference, UGX currency, sufficient amount and unique provider transaction ID activates the subscription.
6. Order settlement and subscription extension happen in **one SQLite transaction**; repeated callbacks do not extend twice.
7. Clients can use **Check payment** if a webhook was missed; admin can review orders under **Payments**.

A redirect query string, webhook payload alone, screenshot or client-supplied reference never grants access. Unavailable methods are visibly disabled, not presented as active checkout options.

## Before public launch

- Confirm plan prices, provider merchant account approval, legal requirements and an appropriate **25+ age verification** process. The current checkbox is an attestation, not identity/age verification.
- Use a stable HTTPS deployment, durable SQLite storage, reliable off-site backups and secure secret management. A temporary Cloudflare Tunnel may work for sandbox testing, but changing its URL requires updating `PREDICTOR_PUBLIC_BASE_URL`.
- Test Flutterwave sandbox payments, webhook signature rejection, repeated notifications, wrong amounts/currencies, retries, expired subscriptions, simultaneous callbacks, and mobile-money settlement delays.
- Add operational monitoring, refund/dispute handling, transaction reconciliation, customer support and rate limiting before production.
- Keep private API credentials out of GitHub, logs, chat messages and frontend code.
- No recurring automatic charge is implemented; this is **automatic access activation after each successful one-time payment**, not subscription auto-renewal.

## Official provider references

- Flutterwave Standard: https://developer.flutterwave.com/docs/flutterwave-standard-1
- Flutterwave payment methods: https://developer.flutterwave.com/docs/payment-methods
- Flutterwave v3 webhooks: https://developer.flutterwave.com/docs/webhooks
- Flutterwave transaction verification: https://developer.flutterwave.com/docs/transaction-verification
- Binance Pay Merchant: https://developers.binance.com/en/docs/products/binance-pay-merchant/api-common
