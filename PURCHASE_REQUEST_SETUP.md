# Customer purchase requests — manual verification

This implementation is intentionally **not a payment gateway**. A receipt or transfer hash is only an untrusted payment claim. A client account is created only when an administrator checks the actual received funds and explicitly approves.

## Before accepting purchases

Purchase requests are **open by default**. The page accepts payment claims as soon as the updated server restarts. To temporarily close submissions, set `PREDICTOR_PURCHASE_ENABLED=false` on the server before launch. Setting it to `true` explicitly also enables submissions. This is manual review only: receiving a claim does not grant VIP access.

Before approval, enter the current HTTPS ngrok origin under Admin → Payment Requests → Current HTTPS website URL. This provides a private activation-link fallback when SMTP is unavailable.

## Public customer flow

- Open /purchase. Select an approved plan: Daily UGX 5,000, Weekly UGX 20,000, Monthly UGX 60,000, Yearly UGX 500,000, or Lifetime UGX 1,000,000. All plans include three sessions of five matchdays each per day (15 matchdays daily).
- Select **Airtel Money — 0753208363 — Norah Nagawa** or the exact coin/network, then transfer payment. Wallet addresses and the Airtel Money number come from the owner's supplied instructions. The former MTN receiving account is no longer a valid destination for new purchases.
- Enter email and username, then submit the transaction reference or an attached PNG/JPG/WebP/PDF receipt (2 MB limit). Customers can send either form of evidence, or both. Both blank is rejected. Matching transaction references and identical receipt files are blocked from reuse.
- The request remains pending until manual verification. No automatic proof acceptance or subscription grant happens.

## Admin flow

- Open /admin > Payment Requests. Review the submitted reference and/or download the proof when attached; cross-check the Airtel Money receiving statement or blockchain explorer. Confirm correct amount, coin, chain, recipient, settlement/finality, and that it hasn't already been used.
- Select Approve verified only after settlement is confirmed. The system creates one account and a one-use 24-hour activation link.
- If SMTP is configured and working, the activation link is emailed. Otherwise the system reports **email not sent** and shows an admin-only copyable HTTPS link. The admin may click Retry activation email, which rotates the link.
- Reject unconfirmed or mismatched payments. Approval is not idempotently repeatable: a reviewed request cannot be approved again.

## Configure pricing

These exact prices are built in. The server environment variables below optionally override them (positive whole UGX amounts). Lifetime grants access without a calendar expiry while the service/account remains active; it is still subject to admin revocation and service availability.

PREDICTOR_PRICE_DAILY_UGX=5000
PREDICTOR_PRICE_WEEKLY_UGX=20000
PREDICTOR_PRICE_MONTHLY_UGX=60000
PREDICTOR_PRICE_ANNUAL_UGX=500000
PREDICTOR_PRICE_LIFETIME_UGX=1000000

No conversion between UGX and crypto is currently automated. The displayed UGX plan price is not a fixed token amount. Ensure customers agree the crypto amount before transfer.

## Configure email delivery (server-side only)

PREDICTOR_PUBLIC_BASE_URL=https://YOUR-ACTUAL-HTTPS-DOMAIN
PREDICTOR_SMTP_HOST=
PREDICTOR_SMTP_PORT=587
PREDICTOR_SMTP_FROM=
PREDICTOR_SMTP_USER=
PREDICTOR_SMTP_PASSWORD=

Port 587 uses STARTTLS; port 465 uses implicit TLS. Do not commit credentials into Git. Sender authorization may be required by your SMTP provider. Without SMTP, approvals work but you must privately send the admin-generated link.

## Safety before open public use

- A temporary ngrok tunnel can change after restart; set PREDICTOR_PUBLIC_BASE_URL to the current HTTPS origin.
- Add rate-limiting at the edge, abuse prevention, backups, monitoring, a customer-support/refund process and a legal/compliance review before handling real customer payments.
- The 25+ checkbox is not identity verification.
- Proof files and payment details contain personal information: database files, backups and admin account access must be protected; determine a retention/deletion policy.
- Crypto network variations and wrapped assets must be verified with the receiving wallet/provider; do not assume a matching address means that all assets are supported.
- A transfer reference or screenshot on its own is not evidence of settlement. Operators must verify the full amount, correct destination and network using independent provider records.
- No automated Stripe/Flutterwave, MTN or crypto transaction confirmation is claimed. No email is claimed sent unless SMTP returns success.
