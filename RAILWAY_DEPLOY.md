# Railway deployment checklist

The Docker container runs FastAPI, Python, Chromium and Selenium. Existing accounts, subscriptions, promotional prices, and payment evidence are in a SQLite database and require persistent storage.

1. Railway service source: private GitHub repository TRomeoPrince/BetPawa_Virtual_Predictor, branch main after production merge. Dockerfile builder.
2. Create and attach a Railway Volume to this service, mounted at /var/data. Do not manually define Railway system variable RAILWAY_VOLUME_MOUNT_PATH; Railway supplies it after a real volume is attached.
3. In Railway Variables add PREDICTOR_ADMIN_PASSWORD with a new strong secret, 12+ characters. Dockerfile already sets PREDICTOR_DB_PATH=/var/data/predictor.db and PREDICTOR_HEADLESS_ONLY=1.
4. Start service, then generate a Railway public HTTPS domain and open /api/status. Set PREDICTOR_PUBLIC_BASE_URL to that actual HTTPS base URL.
5. On Railway, public signup and purchase requests deliberately default to disabled. After existing local accounts are safely migrated and verified, set PREDICTOR_SIGNUP_ENABLED=true and PREDICTOR_PURCHASE_ENABLED=true.
6. Enable Railway volume backups. Use a single service replica with the SQLite database.
7. Check that the remote Selenium-driven live betPawa prediction engine can reach the feed, and that a Free release, subscriptions, manual payment approval, promotions, and referral links work as intended.

If you have client records on your Windows PC, the cloud begins with a new empty database unless you migrate the local database using a consistent SQLite backup. Do not simply upload a running SQLite file while write-ahead logs are active. Do not accept customer payments until you have verified user data persistence, admin access, and accurate payment destinations. A successful Railway build does not prove all the app features work.

The Railway preflight blocks startup if the attached volume or private admin password is absent. This is intentional and keeps account/payment data from being written to ephemeral disk.
