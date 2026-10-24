# Deploy BetPawa Predictor on Render

This repository includes a Render Blueprint in `render.yaml` and a Docker image that installs Chromium for the BetPawa public-feed reader.

## Important: persistent hosting costs

The Blueprint selects a **paid Starter web service** and a **1 GB persistent disk**. This is intentional: the app stores administrator/client accounts, subscriptions, sessions, prediction history, and cached rounds in SQLite. Render's free web services lose local files when they restart or spin down and cannot attach a persistent disk, so a free deployment is only suitable for a disposable demo.

Do not create the service unless you accept the plan and storage charges shown by Render. A prepaid card may or may not be accepted by the provider; check the payment method during setup before confirming any paid resource.

## Deploy

1. Sign in to Render and choose **New → Blueprint**.
2. Connect GitHub if prompted, then select the private repository `TRomeoPrince/BetPawa_Virtual_Predictor` and branch `main`.
3. Review the Blueprint. Confirm it shows the paid Starter web service and 1 GB disk before creating anything billable.
4. When asked for `PREDICTOR_ADMIN_PASSWORD`, enter a strong, unique password of at least 8 characters. Save it privately; the app does not print this configured secret to logs.
5. Create the Blueprint and wait for the deploy to finish.
6. Open the service's public URL followed by `/login`, then sign in with username `admin` and the password you configured.
7. Change the initial password from **Admin → Security** after the first login.

The app's health check is `/api/status`. The first market check can take longer because the service has to start Chromium and load the public virtual-football data.

## Troubleshooting

- **Build fails installing Chromium:** open the Render deploy logs and inspect the Docker build error.
- **Login fails:** confirm `PREDICTOR_ADMIN_PASSWORD` was set before the first database initialization. If an admin account already exists in the persistent database, changing the environment variable does not reset that account's password.
- **Market check fails:** open the service logs and inspect the prediction-service error. The UI now sends POST to the backend's `/api/predict/{category}` route.
- **Service is healthy but predictions fail:** the public BetPawa feed or browser-assisted request may be temporarily unavailable; the app returns a temporary-unavailable response rather than inventing predictions.

The deployment has not been provisioned by this repository change. It must still be created from the Render dashboard.
