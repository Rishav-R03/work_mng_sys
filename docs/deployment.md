# Deployment on Render

This guide deploys the Work Tracker app to Render for real users, including
GitHub login/registration, a production database, and the checks to run after
launch.

## What You Need

- A GitHub repository containing this app.
- A Render account connected to GitHub.
- A GitHub OAuth App for production login.
- A Render PostgreSQL database.

Render deploys web apps as Web Services and runs the build/start commands you
provide. For FastAPI, the service must listen on Render's assigned `$PORT`.

## 1. Create the Database

1. In Render, choose **New +** -> **Postgres**.
2. Pick the same region you plan to use for the web service.
3. Create the database.
4. Copy the **Internal Database URL** if the web service will also run on Render.

Use the internal URL for the app's `DATABASE_URL`. It is faster and private
inside Render.

## 2. Create the Web Service

1. In Render, choose **New +** -> **Web Service**.
2. Connect the GitHub repository.
3. Choose the branch you deploy from, usually `main`.
4. Set the runtime to Python if Render does not detect it automatically.
5. Use these commands:

```bash
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

If the app uses Alembic migrations, use this start command instead:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

If the repository has `requirements-dev.txt`, do not install it in production.
Keep production dependencies in `requirements.txt`.

## 3. Set Environment Variables

In the Render Web Service, open **Environment** and add these variables.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Render Postgres internal database URL |
| `SECRET_KEY` | Long random production secret |
| `SESSION_SECRET_KEY` | Long random production session secret |
| `GITHUB_CLIENT_ID` | Production GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | Production GitHub OAuth App client secret |
| `APP_BASE_URL` | `https://YOUR-SERVICE.onrender.com` or custom domain |
| `FRONTEND_URL` | Same as `APP_BASE_URL`, unless frontend is separate |
| `ENVIRONMENT` | `production` |

Generate secrets locally with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Use different values for `SECRET_KEY` and `SESSION_SECRET_KEY`.

If your app uses different names for base URL or frontend origin, use the names
already expected by the code. The OAuth-related names above match the test and
auth setup in this repository.

## 4. Configure GitHub OAuth

Create a production GitHub OAuth App:

1. Go to **GitHub** -> **Settings** -> **Developer settings** -> **OAuth Apps**.
2. Choose **New OAuth App**.
3. Set **Homepage URL** to:

```text
https://YOUR-SERVICE.onrender.com
```

4. Set **Authorization callback URL** to:

```text
https://YOUR-SERVICE.onrender.com/auth/github/callback
```

5. Copy the generated **Client ID** and **Client Secret** into Render as
   `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.

The callback URL must exactly match the route used by the app. If you later add
a custom domain, update the GitHub OAuth App callback URL to the custom-domain
version:

```text
https://YOUR-DOMAIN.com/auth/github/callback
```

GitHub OAuth Apps support a configured authorization callback URL, and GitHub
returns users to that URL after authorization.

## 5. Deploy

1. Click **Create Web Service** or **Manual Deploy**.
2. Watch the Render logs.
3. Confirm the service starts without import or database errors.
4. Open:

```text
https://YOUR-SERVICE.onrender.com/docs
```

If API docs are disabled in production, open the home page or a health endpoint
instead.

## 6. Verify Real User Registration

Run this checklist after the first deploy:

- Open the deployed app in a private/incognito browser window.
- Start GitHub login.
- Approve the GitHub OAuth App.
- Confirm the browser returns to the Render URL, not localhost.
- Confirm a user record is created in the production database.
- Log out and log back in with the same GitHub account.
- Try a second GitHub account to confirm new-user registration works.
- Check Render logs for OAuth warnings or database errors.

If login fails with a state mismatch, the most likely causes are:

- The user opened the callback URL directly instead of starting login from the
  app.
- The browser blocked or dropped the session cookie.
- The callback URL in GitHub does not exactly match the deployed app URL.
- The app is mixing `http://` and `https://` URLs.
- Multiple instances are using different session secrets.

## 7. Production Safety Checklist

Before inviting real users:

- Use HTTPS-only public URLs.
- Do not use localhost callback URLs in the production GitHub OAuth App.
- Keep `GITHUB_CLIENT_SECRET`, `SECRET_KEY`, and `SESSION_SECRET_KEY` only in
  Render environment variables.
- Use Render Postgres for production data, not SQLite.
- Back up the database before risky migrations.
- Confirm CI passes before deploying.
- Review Render logs after each deploy.

## 8. Optional Custom Domain

After the Render service is working:

1. Add the custom domain in the Render service settings.
2. Configure DNS as Render instructs.
3. Wait for the certificate to become active.
4. Update `APP_BASE_URL` and `FRONTEND_URL` in Render.
5. Update the GitHub OAuth App callback URL to:

```text
https://YOUR-DOMAIN.com/auth/github/callback
```

6. Redeploy the service.
7. Test GitHub login again.

## 9. Troubleshooting

### Render says no open port was detected

Make sure the start command binds to `$PORT`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### ModuleNotFoundError on deploy

Make sure every production package is listed in `requirements.txt`, including:

- `fastapi`
- `uvicorn`
- `authlib`
- `httpx`
- database driver, such as `psycopg2-binary` or `asyncpg`

### OAuth redirects to localhost

Update the GitHub OAuth App callback URL and any Render base URL environment
variables so they use the deployed HTTPS URL.

### OAuth state mismatch

Confirm all deployed instances use the same `SESSION_SECRET_KEY`, then start the
login flow again from the app. Do not reuse old callback URLs from browser
history.

### Database connection fails

Use Render's internal database URL for services running on Render. Confirm the
variable is named exactly what the app expects, usually `DATABASE_URL`.

## References

- [Render Web Services](https://render.com/docs/web-services)
- [Render environment variables](https://render.com/docs/configure-environment-variables)
- [Create and connect to Render Postgres](https://render.com/docs/postgresql-creating-connecting)
- [GitHub: Creating an OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)
