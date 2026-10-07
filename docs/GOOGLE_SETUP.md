# Connecting Google (Gmail, Calendar, Drive)

Veluntra can read your Gmail, Google Calendar and Google Drive, **read-only**: it can look, but never send,
create, change or delete anything in Google. This needs a Google "OAuth client" that you create once (about
10 minutes, free). Until you do, the Connections page says Google isn't set up, and everything else works normally.

## 1. Create a Google Cloud project

1. Go to <https://console.cloud.google.com/> and sign in with the Google account you want to connect.
2. Click the project picker (top bar) → **New project** → name it `Veluntra` → **Create**, then select it.

## 2. Turn on the three APIs

Open **APIs & Services → Library** and enable each of:

- **Gmail API**
- **Google Calendar API**
- **Google Drive API**

## 3. Configure the consent screen

1. **APIs & Services → OAuth consent screen** (may appear as *Google Auth Platform*).
2. User type: **External** → **Create**.
3. App name `Veluntra`, your email as support and developer contact → save.
4. **Data access / Scopes** → **Add or remove scopes**, and add these read-only scopes:
   - `.../auth/gmail.readonly`
   - `.../auth/calendar.readonly`
   - `.../auth/drive.readonly`
   - `openid` and `.../auth/userinfo.email`
5. **Test users** → **Add users** → add **your own Google address** (and anyone else who will connect).

> While the app is in **Testing** mode only the test users you list can connect, and Google expires the
> connection after 7 days (you simply press *Reconnect*). That is fine for personal use. Publishing the app
> for other people requires Google's verification review, because Gmail and Drive are "restricted" scopes.

## 4. Create the OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Web application**, name `Veluntra`.
3. **Authorized redirect URIs** → add exactly:

   ```
   http://localhost:8000/api/v1/integrations/google/callback
   ```

   (If the API is reachable at another address, use `<that address>/api/v1/integrations/google/callback`
   and set `PUBLIC_BACKEND_URL` to match.)
4. **Create**, then copy the **Client ID** and **Client secret**.

## 5. Tell Veluntra

Add to your `.env` (project root, never committed):

```
GOOGLE_CLIENT_ID=<the client ID>
GOOGLE_CLIENT_SECRET=<the client secret>
```

Optional:

```
PUBLIC_BACKEND_URL=http://localhost:8000     # must match the redirect URI above
FRONTEND_URL=http://localhost:3000           # where you land after connecting
INTEGRATION_ENCRYPTION_KEY=                  # see below
```

Then restart the backend so it picks up the new settings:

```
docker compose up -d backend
```

## 6. Connect

Open Veluntra → **Connections** → **Connect Google**. Google shows what Veluntra asks for; keep the
permissions ticked, approve, and you're brought back. The page then shows your next 7 days, an email search
and a Drive search, and the assistant can answer things like *"What's on my calendar this week?"* and
*"Search my email for the invoice from Ram"*.

## Security notes

- **Read-only.** Only `*.readonly` scopes are requested.
- **Tokens are encrypted** in the database (Fernet). By default the key is derived from `SECRET_KEY`; set
  `INTEGRATION_ENCRYPTION_KEY` to use a dedicated one:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
  If you change `SECRET_KEY` (or the key) later, saved connections can't be read and show *Reconnect*.
- **Disconnecting** revokes the access at Google and deletes the stored tokens. You can also remove Veluntra at
  <https://myaccount.google.com/permissions>.
- **Email, events and files are written by other people.** The assistant is told never to follow instructions
  found inside them, and it only reads them when you ask a question that needs them.
- The connection belongs to **you** personally: other members of a workspace cannot use it.
