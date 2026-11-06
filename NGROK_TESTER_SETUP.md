# Supervised client onboarding + ngrok tester setup

This is a **local test deployment**, not a cloud-hosted website. Your Windows PC must stay on, connected to the internet, and keep both `run.bat` and `start-ngrok.bat` running. The public HTTPS URL is provided by ngrok and may change when restarted, depending on your ngrok plan/domain configuration.

## 1. Update the test branch on your Windows PC

From PowerShell:

```powershell
Set-Location "C:\Users\USER\Desktop\Bots\Personal_AI\BetPawa Predictor"
git fetch origin
git switch feature/client-ready-site
git pull --ff-only origin feature/client-ready-site
```

If you have local changes, Git may ask you to commit/stash them first. Never force-reset the branch or delete your `data/predictor.db` file.

## 2. Start the predictor

Double-click `run.bat`, or run `.\run.bat` in PowerShell.

It starts at `http://127.0.0.1:8010`. Keep the window open. Existing admin accounts remain in the local SQLite database. If it is a fresh database, the initial admin password appears **once** in the server terminal or comes from `PREDICTOR_ADMIN_PASSWORD`; it cannot be retrieved later. The first login must change it.

## 3. Configure ngrok once

1. Register at https://dashboard.ngrok.com/signup and download ngrok for Windows from https://ngrok.com/download/windows.
2. Add `ngrok.exe` to PATH, or use ngrok from the folder where it is installed.
3. Copy your ngrok authtoken from https://dashboard.ngrok.com/get-started/your-authtoken.
4. In **your own** PowerShell (never in a public screenshot or chat), run:

   ```powershell
   ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
   ```

   Replace the placeholder locally. Do not put the real token in GitHub, `.bat` files, or client messages.

5. Double-click `start-ngrok.bat` in the project folder, or run `ngrok http 8010`.
6. Copy the HTTPS forwarding URL displayed by ngrok, such as `https://YOUR-ASSIGNED-DOMAIN.ngrok-free.app`. This is an example only, not a deployed URL.

**Your computer and both terminal windows must remain running.** The URL opens a public login page; ngrok does not automatically enforce invitations or a second authentication layer. Do not share the ngrok authtoken or admin credentials.

## 4. Invite testers

1. Open `http://127.0.0.1:8010/admin` on the host PC, or use your HTTPS ngrok address plus `/admin`.
2. Open **Clients & Invitations** (the default admin tab).
3. Enter the client's username and display name.
4. Choose an optional test plan (e.g., Weekly). An account with **No plan** can log in but cannot open subscription-gated markets.
5. Click **Generate temporary password**.
6. The one-time password appears in a prominent panel. Click **Copy full invitation** and send it privately to the client. The invitation uses the current website origin, so create invitations while using the ngrok address if you want the link in the message to be public.
7. The client opens the HTTPS login link, signs in with their username and temporary password, confirms the 25+ policy and creates a new password (12–128 characters).
8. The client is signed out and signs back in with their personal password. Their subscription controls access.

The admin cannot read the personal password, and the temporary password cannot be retrieved after closing the invitation panel.

## 5. Forgotten passwords

Open **Admin → Clients & Invitations → Manage clients → Reset password** beside the correct client.

- Confirm the reset.
- A **new** one-time temporary password is generated and shown once.
- The old password immediately stops working and all of that client's sessions are invalidated.
- Copy the replacement invitation and send it privately.
- The client must repeat the first-login password setup.

A password reset **does not** cancel or extend their subscription.

## 6. Before inviting testers

- Test admin first-login password setup and reset flows locally.
- Use a strong, unique administrator password. Do not give testers admin credentials.
- Limit invitations to a small, trusted group of adults aged 25+. The checkbox is an **attestation**, not independent age/identity verification; confirm applicable Ugandan gaming licensing and age-verification requirements before public sale or broader release.
- Disable public payment collection: there is no configured Flutterwave merchant or live gateway.
- Keep `data/predictor.db` private and backed up. The SQLite database is local to your PC.
- Use HTTPS ngrok URLs only. Never share `127.0.0.1` with remote testers.
- Be aware the ngrok address is internet-reachable. Use it only for controlled testing; production needs rate limiting, monitoring, stable storage, security review, and appropriate legal compliance.
- Stop `start-ngrok.bat` to disconnect the public link when testing is over.

## Technical notes

The backend redirects all first-login users to `/password-setup` and blocks protected API endpoints until setup is complete. Only `/api/auth/me`, `/api/auth/logout`, and `/api/auth/change-password` remain available for a signed-in user with a temporary password. New passwords and temporary passwords are stored as salted PBKDF2 hashes, not plaintext. Admin resets and password changes revoke all existing sessions and record an audit event. One-time credentials are returned only in the authorized admin create/reset response.

**Never merge to main without approval.** This work is on `feature/client-ready-site` after review.
