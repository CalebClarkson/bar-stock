# Bar Stock

A self-hosted stock system for bars that sell through Square, built on
[Open Source Barware](https://github.com/RichardBJamison/open-source-barware). It runs on one Windows PC behind the bar,
keeps all data on that PC, and replaces paid stock tools.

## Why I built this

Paid stock software is expensive for a small bar and often doesn't track comps, staff drinks or batched cocktails
properly. I adapted an open-source bar inventory app suited to my own setup (Square for sales, bar and a
cellar counted separately, no admin rights on the office PC) but it can be easily adapted for different setups. I tried
to make everything as customisable as possible within the UI so users can make any changes they want for it to suit them.

## What it does

- **One-button nightly upload.** The front page is read-only: figures, tables and a single "Upload Square sales"
  button (or drag the CSV onto it). Anyone signed in can upload; everything that changes setup sits behind a
  Settings mode for managers.
- **Manager dashboard.** Takings, drinks sold, GP and losses for last night, 7 or 30 days or a custom range, compared
  with the period before. Sortable, searchable tables (with CSV download) for best sellers, takings by category,
  stock used, stock levels, an order list with "nights left" at the recent pace, losses, slow-moving stock, the
  stocktake check and GP per Square price. Sales before 5am count towards the night before, and amounts read as
  people say them (11 L, 10.6 bottles), not 11000ml.
- **Drinks, specials and batches.** A drink editor with an ingredient picker, quick ml buttons and live cost and GP.
  A Square button named exactly like a drink links itself, so a new special needs no mapping step. Drinks can be
  duplicated, archived when they come off the menu, or deleted if nothing uses them yet.
- **One stock figure per product.** Bar and Cellar are counted separately at a stocktake, but sales, wastage, batches
  and deliveries all come off one overall figure.
- **Append-only ledger.** Stock on hand is the last stocktake plus every movement since, so nothing is overwritten and
  any import can be undone.
- **Square sales import.** Reads Square's item sales detail export (UTF-16, tab-separated). Re-importing the same day
  is safe. Full comps and 100% discounts are flagged for a reason: wastage, overpour, training or staff drinks.
- **Mappings and recipes.** Each Square item points at a recipe, a product and serve size, or "no stock". Cocktails and
  pre-mix batches take their ingredients off stock, and costs flow through to GP after VAT.
- **Deliveries.** Invoices go in as drafts and only change stock once approved.
- **Changing prices.** Every change to what you pay (typed in, or from an approved delivery) and to what you charge
  (from a fresh Square catalogue upload) is logged with the old and new price. Each stock movement keeps the cost it
  had at the time, so past GP does not shift when a supplier puts prices up. Drinks use Square's current price.
- **Your own wastage reasons.** Besides wastage, overpour, training and staff drinks, staff can type a reason such as
  "Breakage"; it is remembered and reported like the others.
- **Look & feel.** Ready-made looks, plus light or dark mode, main colour, font, text size, corners, spacing, header
  and banner style, all applied instantly. Fonts are ones Windows already has, so nothing is fetched online.
- **Branding without committing it.** An admin uploads the venue's logo, name and main colour once in Settings. They
  are kept in `data/` beside the stock database (never in git), survive updates and travel with backups. Logos must
  be PNG, JPEG or WebP, checked by content; SVG is refused because it can carry script. The page trims empty space
  around the logo, picks its main colour, and uses a dark header when the logo has light lettering.
- **Who can change what.** Only admins change anything (drinks, products, prices, people, branding). Managers see
  every figure; staff see stock figures. Everyone can upload the night's sales, and an admin can switch on
  stocktakes, wastage or batches for each person.
- **Stocktake on a phone.** A small offline page (`docs/`, served by GitHub Pages) that staff add to their home
  screen. The product list arrives in the part of a link after `#`, which browsers never send to the website, so
  the page holds no venue data. Counts, including new items, go back to the PC as a file and fill in the stocktake.
- **Charts.** Takings through the night (or night by night), takings by category and losses by reason, each with a
  hover tooltip and the same numbers as a table.
- **Security.** PIN login on every route, admin/manager/staff roles, scrypt PIN hashing with lockout, same-origin
  checks on writes, and the server bound to `127.0.0.1` by default.
- **Windows installers.** One PowerShell line installs Python, the app and the data, with a version that needs no
  admin rights.

## Your venue's details stay local

Nothing about a particular venue is in this repository. Everything venue-specific lives in `data/`, which git ignores:
the stock database, logins, logo and colours, and `venue-rules.json` (stocktake spellings, which Square buttons match
which products, post-mix items). Copy `venue-rules.example.json` there to start your own; without it, items are simply
matched by hand in the app.

## Run it

Linux or macOS:

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python manage.py create-admin "Your Name" yourlogin
    .venv/bin/python server.py

Then open http://localhost:5052/stock.

Windows (one line, no Git needed): see [windows/SETUP-GUIDE.md](windows/SETUP-GUIDE.md).

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

## Disclaimer

As you can probably tell by the structure, this project was heavily reliant on the development capabilities of Claude
Code (Opus 5.5), although the process has taught me a lot, and proved to be a no-brainer fix to a real issue we were
facing in my workplace. I encourage anybody who stumbles upon this repo to build on this, and see what you think!

## Credits and licence

Based on [Open Source Barware](https://github.com/RichardBJamison/open-source-barware) by Richard B. Jamison. The first
commit in this repository is his `program/` folder, unchanged. The original setup screens (`/home`, `/setup`) are still
there for admins.

GPL-3.0-or-later. See `LICENSE.txt`, and `NOTICE.md` for the list of changes.
