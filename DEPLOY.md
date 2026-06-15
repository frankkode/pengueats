# PenguEats — Screenshots, GitHub CI & Railway Deployment

This guide has three parts:

1. Taking the screenshots for the README
2. Pushing to GitHub (so the CI tests run automatically)
3. Deploying to Railway

---

## 1. Taking the screenshots

All README screenshots live in **one folder**:

```
pengueats/docs/screenshots/
```

Run the app locally first:

```bash
python manage.py runserver      # then open http://127.0.0.1:8000
```

Take each shot and save it with the **exact filename** below (PNG or JPG both work).
The README already references these names, so the images appear automatically once
the files exist.

| Save as | What to capture | Where |
|---------|-----------------|-------|
| `00-erd.png` | The database ERD diagram | Render `ERD.md` at https://mermaid.live, or screenshot your DB tool |
| `01-home.png` | Home page (hero + featured dish) | `/` |
| `02-recipes-search.png` | Recipes page — type a word in the navbar search first | `/recipes/?q=salmon` |
| `03-recipe-detail.png` | A single recipe page | click any recipe |
| `04-menu.png` | The printable price menu | `/menu/` |
| `05-cart-checkout.png` | Cart with an item + the checkout button | `/cart/` |
| `06-contact.png` | The contact page | `/contact/` |
| `07-login.png` | Owner login screen | `/login/` |
| `08-dashboard.png` | Owner dashboard (inventory, orders, finance) | `/dashboard/` after login |
| `09-recipe-form.png` | The Add / Edit recipe form | dashboard → "Add a Recipe" |
| `10-mobile.png` | A page in a narrow window (mobile view) | resize browser or use device toolbar |
| `11-tests.png` | Terminal showing all 7 tests pass | run `python manage.py test` |

**How to screenshot**

- **macOS:** `Cmd + Shift + 4`, then drag the area. The file lands on your Desktop —
  rename and move it into `docs/screenshots/`.
- **Windows:** `Win + Shift + S` (Snipping Tool), paste into Paint, save into the folder.
- **Mobile view in Chrome:** press `F12` → click the device-toolbar icon (phone/tablet)
  → pick "iPhone" → screenshot. Good for `10-mobile.png`.

---

## 2. Push to GitHub (CI runs the tests)

The repo includes a GitHub Actions workflow at **`.github/workflows/ci.yml`**. On every
push and pull request to `main`, GitHub spins up a clean Ubuntu machine, installs the
dependencies, runs `manage.py check`, and runs the **7 unit tests**. A green check next to
your commit means the build is healthy; a red X means a test failed.

First-time setup (run from inside the `pengueats/` folder — the one with `manage.py`):

```bash
git init
git add .
git commit -m "PenguEats: initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/pengueats.git
git push -u origin main
```

Then open your repo on GitHub and click the **Actions** tab — you'll see the `CI`
workflow running. After it finishes you can add a status badge to the README:

```markdown
![CI](https://github.com/<your-username>/pengueats/actions/workflows/ci.yml/badge.svg)
```

---

## 3. Deploy to Railway

The project is already deployment-ready. These files do the work:

- **`Procfile`** — `release:` runs migrations + `collectstatic`; `web:` starts Gunicorn.
- **`runtime.txt`** — pins Python 3.13.5.
- **`requirements.txt`** — includes `gunicorn`, `whitenoise`, `dj-database-url`, `psycopg2-binary`.
- **`settings.py`** — reads `DATABASE_URL`, `RAILWAY_PUBLIC_DOMAIN`, and the secret/host
  env vars automatically. WhiteNoise serves the static files, so no S3 is needed.

### Steps

1. **Sign in** at https://railway.app with your GitHub account.
2. Click **New Project → Deploy from GitHub repo**, and pick your `pengueats` repo.
   Railway auto-detects Python and builds it.
3. **Add a database:** in the project, click **New → Database → Add PostgreSQL**.
   Railway creates a `DATABASE_URL` and shares it with your app automatically.
4. **Set environment variables** on the web service (the **Variables** tab):

   | Variable | Value |
   |----------|-------|
   | `DJANGO_SECRET_KEY` | a long random string (e.g. from `python -c "import secrets;print(secrets.token_urlsafe(50))"`) |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | leave blank — Railway's domain is trusted automatically |
   | `STRIPE_SECRET_KEY` | *(optional)* your `sk_test_...` key; omit to use simulated checkout |
   | `STRIPE_PUBLISHABLE_KEY` | *(optional)* your `pk_test_...` key |

   > `DATABASE_URL` and `RAILWAY_PUBLIC_DOMAIN` are injected by Railway — you don't set
   > these yourself. `settings.py` already reads them.

5. **Generate a domain:** Settings tab → **Networking → Generate Domain**. Railway gives
   you a `*.up.railway.app` URL.
6. Railway runs the `release` command (migrate + collectstatic) and then starts Gunicorn.
   Open the domain — the site is live.
7. **Create your owner login** on the live site. In the service's shell (or locally
   pointed at the same `DATABASE_URL`):

   ```bash
   python manage.py createsuperuser
   python manage.py seed_data     # optional: load the demo fish & recipes
   ```

### One caveat to know (and to mention in your exam)

Railway's filesystem is **ephemeral** — it resets on each redeploy. The SQLite file and
any uploaded recipe photos (`media/`) would be wiped, which is exactly why the deploy
uses **PostgreSQL** for data. Seeded recipes use bundled *static* images (kept by
WhiteNoise), so they always show. For persistent **user uploads** you would add a Railway
**Volume** mounted at `media/`, or switch `Recipe.photo` storage to an object store like S3.
