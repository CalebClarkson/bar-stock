# Bar Stock

A stock system for a UK events bar, built on [Open Source Barware](https://github.com/RichardBJamison/open-source-barware).
It runs on one Windows PC behind the bar and replaces paid stock tools.

## Why I built this

We were paying around £150 a month for stock software, and it still didn't track comps, staff drinks or batched
cocktails properly. I took an open-source bar inventory app and adapted it to how our bar actually works: Square for
sales, one cellar and one bar, end-of-night imports, and a work PC with no admin access.

## What it does

- **One stock figure per product.** Bar and Cellar are counted separately at a stocktake, but sales, wastage, batches
  and deliveries all come off one overall figure.
- **Append-only ledger.** Stock on hand is the last stocktake plus every movement since, so nothing is overwritten and
  any import can be undone.
- **Square sales import.** Reads Square's item sales detail export (UTF-16, tab-separated). Re-importing the same day
  is safe. Full comps and 100% discounts are flagged for a reason: wastage, overpour, training or staff drinks.
- **Mappings and recipes.** Each Square item points at a recipe, a product and serve size, or "no stock". Cocktails and
  pre-mix batches take their ingredients off stock, and costs flow through to GP after VAT.
- **Deliveries.** Invoices go in as drafts and only change stock once approved.
- **Reports.** Usage by reason, and variance between the last two stocktakes.
- **Security.** PIN login on every route, admin/manager/staff roles, scrypt PIN hashing with lockout, same-origin
  checks on writes, and the server bound to `127.0.0.1` by default.
- **Windows installers.** One PowerShell line installs Python, the app and the data, with a version that needs no
  admin rights.

## Run it

Linux or macOS:

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python manage.py create-admin "Your Name" yourlogin
    .venv/bin/python server.py

Then open http://localhost:5052/stock.

Windows: see [windows/SETUP-GUIDE.md](windows/SETUP-GUIDE.md).

Tests:

    .venv/bin/pip install pytest && .venv/bin/python -m pytest -q tests

## Commands

    python manage.py create-admin "Name" login
    python manage.py import-baseline stocktake.xlsx
    python manage.py import-catalogue square-catalogue.csv
    python manage.py backup [folder]
    python manage.py export-data bundle.txt      (password in OSB_BUNDLE_PASSWORD)
    python manage.py import-data bundle.txt      (password in OSB_BUNDLE_PASSWORD)

## Settings

Copy `venue.env.example` to `venue.env`. `OSB_BIND` defaults to `127.0.0.1`. To serve staff devices, bind to the LAN
and use HTTPS (for example `tailscale serve 5052` with `OSB_HTTPS=1`), since plain HTTP over Wi-Fi exposes PINs.
Square API sync is off until `SQUARE_ACCESS_TOKEN` and `SQUARE_LOCATION_ID` are set.

Stock data lives in `data/` and is never committed.

## Credits and licence

Based on [Open Source Barware](https://github.com/RichardBJamison/open-source-barware) by Richard B. Jamison. The first
commit in this repository is his `program/` folder, unchanged. The original setup screens (`/home`, `/setup`) are still
there for admins.

GPL-3.0-or-later. See `LICENSE.txt`, and `NOTICE.md` for the list of changes.
