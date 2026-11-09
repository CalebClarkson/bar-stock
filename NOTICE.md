# Open Source Barware Notice

Copyright (C) 2026 Open Source Barware contributors.

Open Source Barware is distributed under the GNU General Public License version 3 or later. This distribution includes the public website source, spreadsheet templates, AI inventory prompt, legacy local app, and the in-progress Chrome-side inventory program scaffold.

There is no warranty for this free software. Modified versions should keep the GPL license text, preserve existing notices, and mark meaningful changes with a relevant date in the project README, package README, changelog, or source headers.

## Modifications

Modified 2026-10-31: login enforced on all routes with admin/manager/staff roles, scrypt PIN
hashing and lockout, CORS removed, bind host configurable, Waitress server. Added a stock ledger with Bar and Cellar stocktakes
(`venue_*.py`), Square CSV and API import (`square_api.py`), recipes, batches, deliveries, variance
reports and the `/stock` screens. See `README.md`.

Modified 2026-11-03: this repository holds only the upstream `program/` folder, at its root. The public website,
browser test scripts, demo test kit and cloud deployment files were removed. Windows installers were added under
`windows/`.

Modified 2026-11-09: the `/stock` screens were rebuilt as a read-only dashboard with a Settings mode, a drink and
special editor, product editing and archiving, and new analytics (`venue_db.dashboard`).
Also 2026-11-09: custom wastage reasons, price history with cost captured per movement, batch preview with actual
yield, and venue branding stored in the data folder.
