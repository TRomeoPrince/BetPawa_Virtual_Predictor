# Client Website Launch Checklist

This branch prepares a client-facing **invitation-only** BetPawa Predictor site. It is **not deployed** merely by merging the code.

## What works

- Public landing page at /, login at /login
- Admin-created client accounts and temporary passwords
- Account password changes
- Client subscription requests with pending/approved status
- Admin approval, extension and revocation of subscriptions
- Subscription-gated Overs, Unders, BTTS and Wins pages
- Next-matchday fixtures, qualifying predictions, My Combo and personal results
- Private strategy metadata stored server-side; client API responses are sanitized
- Historical timing estimates explicitly labeled as approximate

## Not yet included

- Public self-registration or email verification
- Automatic checkout, payment collection or refunds
- Automated password recovery by email
- A customer support address/contact method
- Verified public uptime or real-world Selenium scraping from Render

Do not advertise these as available until implemented and tested.

## Local review

On a clean working tree:

~~~cmd
cd /d "C:\Users\USER\Desktop\Bots\Personal_AI\BetPawa Predictor"
git fetch origin
git switch feature/client-ready-site
run.bat
~~~

Check / (public homepage), /login, /client, and each market page on both desktop and mobile. Sign in with an admin account and use **Client view**; create a test client, request a plan, approve it, then verify the market pages unlock.

## Before public deployment

1. Review and merge the PR only after local UI testing.
2. Decide prices, payment method and how clients contact the administrator.
3. Decide whether to keep invitation-only accounts or add secure self-registration.
4. Confirm and approve Render Starter + persistent disk charges before provisioning.
5. Set PREDICTOR_ADMIN_PASSWORD securely on the first deployment; changing it later does **not** reset an existing admin password.
6. Establish regular off-service backups of /var/data/predictor.db (and any WAL files) with tested restore procedures.
7. Verify HTTPS, authentication, rate limiting, privacy/security policy and production logs.
8. Test live fixture fetching, predictions, result grading, My Combo, subscriptions and restarts on the hosted service.

Predictions are not guaranteed outcomes. This service is independent of betPawa and is intended for adults.
