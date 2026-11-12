# Private admin analytics and administrator recovery

## Analytics definitions
- **Online now:** distinct authenticated active client accounts that made a request or sent a visible-tab heartbeat in the last 5 minutes. This is NOT an anonymous-site-visitor counter or a count of open TCP connections.
- **Active 24h / 7d:** distinct authenticated active client accounts with a recent last-seen record.
- **Signups:** registered client accounts by created timestamp, with today and this-month windows using EAT (UTC+3), and a rolling 7-day window.
- **VIP:** active client subscriptions with a future expiry, or active Lifetime memberships. Free members excludes inactive accounts and current VIP.
- **Verified external sales:** total *gross* approved payment request amounts (UGX); only externally verified approved requests, not wallet funds. This is not net revenue, and refunds must be handled separately.
- **VIP wallet redemptions:** sum of previously earned commissions spent on VIP; never counted as fresh external revenue.
- **Referrals:** referral-attributed signups and first VIP conversion records. Link visits are a separate sum and can include repeat visits.
- **Trends:** last 14 EAT calendar dates; new signups and distinct authenticated member activity. Historical activity begins when this feature was deployed, so previous inactive days are not inferred.
- **Privacy:** response is admin-only; no email addresses, identities, access tokens, passwords or individual user activity records are sent to the UI. Daily activity rows retained for 90 days. Refresh while admin analytics is visible, about once per minute.

## One-time admin password recovery
The Railway PREDICTOR_ADMIN_PASSWORD variable is a bootstrap secret: it is NOT normally reapplied after first admin creation. When admin login fails because the password was changed or forgotten, an operator with Railway access may set a unique, non-secret PREDICTOR_ADMIN_RECOVERY_ONCE marker (12–128 characters) to trigger a one-time reset of only the active account with username admin to the existing PREDICTOR_ADMIN_PASSWORD. The marker digest and an audit entry are stored in the same attached SQLite database, and existing admin sessions are revoked.

A repeated deployment using the same marker cannot reset the admin password again, including after the admin changes their password. The admin must then sign in with the existing Railway bootstrap password and complete the password-change screen. No secret may be logged or sent to chat. After recovery is confirmed, remove the PREDICTOR_ADMIN_RECOVERY_ONCE environment variable so it cannot trigger again. Do not delete the volume, overwrite the database or recreate admin accounts.

## Production
Develop/test on a feature branch; require passing GitHub Actions before merging to main. Railway deploys main into the service with the existing persistent SQLite volume at /var/data. Keep signup, purchase and referral withdrawal settings unchanged. Never publish private analytics publicly.
