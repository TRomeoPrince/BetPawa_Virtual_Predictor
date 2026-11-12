# Referral commissions and wallet — internal policy

## Rates and eligibility
A referrer gets 20% on every manually verified and approved VIP payment by their referred customer in the first 30 elapsed days after that customer's first approved VIP payment. On and after the 30-day boundary, each verified paid purchase or renewal earns 15%.

Commission is calculated from the ACTUAL locked UGX amount on the verified purchase request, after any promotional pricing, rounded half up to a whole UGX shilling.

Examples:
- Weekly UGX 5,000 promotional payment during first 30 days: UGX 1,000 credit
- Weekly UGX 20,000 renewal during first 30 days: UGX 4,000 credit
- Weekly UGX 20,000 renewal after 30 days: UGX 3,000 credit

Only original referral attribution captured during free signup qualifies. Manually gifted subscriptions, unpaid requests, legacy requests without independently approved payment amounts and non-referred guests do not produce credits. Duplicate approvals cannot duplicate commissions because the ledger and VIP approval commit in one SQLite transaction, with a unique purchase source.

Past verified purchases before this feature are not automatically credited retroactively. Historical approved purchase timestamps still determine the correct subsequent rate for new renewals.

## Wallet
The ledger and VIP wallet purchase receipts are append-only financial records. Wallet balance = credited commissions - reversal adjustments - confirmed paid withdrawals - wallet-funded VIP spending; available to spend/withdraw = max(0, balance - pending withdrawal reservations). Paid withdrawals remain on the audit trail. Refunds and chargebacks insert negative adjustments, not edits or silent deletion. A chargeback after a payout can produce a negative carried balance until future commissions offset it, while withdrawable never drops below zero.

Requests are DISABLED by default through PREDICTOR_REFERRAL_WITHDRAWALS_ENABLED=false. The member can see their wallet and available funds, but the request form is unavailable until payout operations are ready. Once enabled, withdrawal requests only reserve funds, and an administrator marks them paid ONLY after independently sending money and recording a unique transfer reference; there is no automated MTN or crypto transfer. The minimum payout PREDICTOR_REFERRAL_MIN_WITHDRAWAL_UGX defaults to UGX 1,000 as requested. Configure it explicitly on Railway to enforce that limit consistently. Limit to one pending withdrawal per account.

Financial audit entries are retained in anonymized form when accounts are deleted. Deleting an account with an unsettled wallet balance is blocked until settled or adjusted.

## Wallet-funded VIP purchases
Authenticated members may pay for an entire Daily, Weekly, Monthly, Yearly or Lifetime VIP plan from their available referral balance. Promo codes and automatic promotional prices are honored by server-side quotes. Wallet purchases activate or extend VIP in a single SQLite transaction along with an immutable debit receipt; no external transfer proof or manual settlement approval is required because these are previously earned commission funds. A confirmation prompt and exact expected UGX price protect against accidental purchases or stale quotes.

Funds reserved for pending withdrawal requests cannot also be spent on VIP. Insufficient funds cannot be split with MTN or crypto in this release; the customer can use the existing external payment flow separately. Wallet purchases are not treated as new external revenue, never generate referral commissions, and use one-use idempotency keys to prevent a browser retry from double-charging or extending access twice. A currently active Lifetime account cannot pay for further plans.

## Release tracing
This document, Git commit SHAs, pull request descriptions and Railway deployment history are the authoritative private code version trail. Do not expose website version numbers, commit hashes or internal release identifiers on customer-facing pages.

## Deployment
Keep existing Railway SQLite volume mounted at /var/data, single service replica and scheduled backups. Deploy through a feature branch and CI, then merge to main; Railway auto-deploys main. Don't wipe the existing database. Keep the existing registration/purchase flags unchanged and withdrawals disabled until an agreed payout policy exists.
