# SF Apartments — Setup Guide

## What you're deploying

A website that scrapes Craigslist, Apartments.com, Zillow, and Padmapper every 4 hours,
shows you all SF studio/1BR listings up to $3,500, and sends you a daily email + SMS
digest at 8am PT with new listings.

---

## Step 1 — Get a Gmail App Password

Your regular Gmail password won't work for sending email programmatically. You need an App Password.

1. Go to **myaccount.google.com**
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google", click **2-Step Verification** (enable it if not already on)
4. Scroll to the bottom and click **App passwords**
5. Name it "SF Apartments" and click **Create**
6. Copy the 16-character password shown — you'll need it in Step 3

---

## Step 2 — Set up Twilio for SMS

1. Go to **twilio.com** and click **Sign up for free**
2. Verify your phone number (732-668-3269) during signup
3. From the Twilio Console dashboard, copy your:
   - **Account SID** (starts with "AC...")
   - **Auth Token**
4. Click **Get a phone number** to get a free Twilio number (e.g. +1-415-xxx-xxxx)
5. Copy that number — it's your `TWILIO_FROM_NUMBER`

> Free trial note: You can only send SMS to verified numbers on the free trial.
> Your number (732-668-3269) is already verified since you used it at signup.

---

## Step 3 — Deploy to Railway

Railway runs your app 24/7 for free (up to 500 hours/month on the free tier).

### 3a. Push your code to GitHub

1. Go to **github.com** and create a new repository called "sf-apartments"
2. In your terminal, from the `sf-apartments` folder, run:
   ```
   git init
   git add .
   git commit -m "initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/sf-apartments.git
   git push -u origin main
   ```

### 3b. Deploy on Railway

1. Go to **railway.app** and sign up with your GitHub account
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `sf-apartments` repo
4. Railway will detect the `railway.toml` and start building automatically

### 3c. Add a PostgreSQL database

1. In your Railway project, click **+ New** → **Database** → **PostgreSQL**
2. Railway automatically sets `DATABASE_URL` in your app's environment — nothing else needed

### 3d. Set environment variables

1. Click on your app service in Railway
2. Go to the **Variables** tab
3. Add each of these (copy from your `.env.example`):

   | Variable | Value |
   |---|---|
   | `GMAIL_ADDRESS` | `musicalvivian@gmail.com` |
   | `GMAIL_APP_PASSWORD` | *(the 16-char password from Step 1)* |
   | `ALERT_EMAIL` | `musicalvivian@gmail.com` |
   | `ALERT_PHONE` | `7326683269` |
   | `TWILIO_ACCOUNT_SID` | *(from Twilio Console)* |
   | `TWILIO_AUTH_TOKEN` | *(from Twilio Console)* |
   | `TWILIO_FROM_NUMBER` | *(your Twilio number, e.g. `+14155551234`)* |

4. After saving, click on your app's **Settings** tab and copy the public URL
5. Add one more variable: `APP_URL` = your Railway URL (e.g. `https://sf-apartments.up.railway.app`)

---

## Step 4 — You're live!

- Your site will be at the Railway URL (e.g. `https://sf-apartments.up.railway.app`)
- Listings are scraped every 4 hours automatically
- Daily digest email + SMS arrives at 8am PT
- Use the "Refresh listings" button on the site to trigger a manual scrape anytime

---

## Filters on the website

| Filter | What it does |
|---|---|
| Studio / 1 Bedroom | Filter by bedroom count |
| AC | Only show listings with air conditioning |
| W/D | Only show listings with in-unit washer/dryer |
| Max Price | Filter by max monthly rent |
| Source | Filter by Craigslist, Zillow, Apartments.com, or Padmapper |

---

## Notes

- **Zillow** has aggressive bot protection and may occasionally return no results — this is normal
- **Padmapper** aggregates some Craigslist listings, so you may see some duplicates — they're stored separately and the UI shows the source
- AC and W/D fields may show as unknown for some listings if the source doesn't clearly list them
