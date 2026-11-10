# Free + VIP, promotions and referrals

- **Public signup**: /signup; each adult 25+ selects a permanent password and receives a Free membership. Set PREDICTOR_SIGNUP_ENABLED=false to suspend new registrations.
- **Free access**: five estimated 5-minute evening matchdays in the 22:00–22:25 Africa/Kampala window; EPL/English and Dutch virtual leagues only. The same live prediction engine serves VIP. Free members cannot fetch VIP history or save My Combo picks.
- **VIP access**: existing 15 matchdays/day and original prices (daily 5,000; weekly 20,000; monthly 60,000; annual 500,000; lifetime 1,000,000 UGX).
- **Upgrade/renewal**: signed-in members use /purchase, enter payment details and proof. An administrator independently verifies receipt and approves the request; the **existing account** gains VIP, without creating duplicate credentials. Rejected requests leave Free intact.
- **Admin promotions**: Admin > Promotions; create a plan-specific discounted UGX price such as 5,000 for Weekly. Optional code (otherwise automatic), optional start/end dates, enabled/disabled toggle. Standard price is never overwritten. Checkout stores the quoted UGX at submission.
- **Referrals**: member dashboard > Invite friends. /r/BP... link records visits, signup attribution and first manually approved VIP conversion. No rewards or automatic payouts.
- **Live payments**: PREDICTOR_PURCHASE_ENABLED defaults false; enable only when ready to receive and independently verify actual transfers. Screenshots do not establish payment settlement.
- **Public URL**: Set PREDICTOR_PUBLIC_BASE_URL to a stable HTTPS origin so referral and activation links don't point to localhost.
- **Important limitations**: Free-round clock uses existing *estimated* virtual-football 5-minute timing; monitor actual alignment. SQLite is not cloud-persistent by default. Public signup still needs email verification, anti-spam/rate limiting, CSRF review, and browser compatibility testing before a large public launch. This release is not a fully hardened production deployment.
