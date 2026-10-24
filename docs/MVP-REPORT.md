# wzSearch – MVP report

23 October 2026 · for the project owner. Details for continuing the work: [HANDOFF.md](HANDOFF.md); open decisions
and known issues: [../BACKLOG.md](../BACKLOG.md).

The MVP is finished and tested on the real data. It's a static site plus a Python script that rebuilds the data, and
it runs on your laptop or on GitHub Pages without changes.

## What it shows

- **Planning records (578):** 474 from the district's monthly Excel files, nothing dropped, plus 104 Praga-Południe
  rows from the city architecture bureau's lists (the district page itself points there).
- **Building permits (2,591, switch on in the filters):** from GUNB's national open register, so 2,365 permits and
  226 notifications, hidden by default.
- **Source link on every record:** the page, the Excel file (the original link plus our archived copy), the sheet
  and row, and the cells exactly as published.

## How you can use it

- Search by address, decision number, applicant or parcel, with Polish word endings handled.
- Filter by type, period, neighbourhood, street, investment type and outcome.
- See records on a map with parcel outlines, or near your location.
- Follow related records over time, such as a WZ decision followed by a building permit on the same parcel.
- Export to CSV, subscribe to an Atom feed, and share a link that reopens your exact filters.
- The site works on phones, has a dark mode, and works with a keyboard.

## How it was checked

- **Data:** an independent re-read of every source cell found everything present (the one missing cell is a
  deliberately removed personal name). It found no personal names leaking, and every map point placed by parcel
  sits on its own parcel.
- **Site:** independent reviews covered accessibility, Safari's engine, the code and GitHub Pages hosting. Each
  finding was re-checked by a second reviewer before anything was fixed; 73 held up, 70 are fixed and the other 3
  are in the backlog.
- **Tests:** all automated suites pass, including 162 browser checks on the real data. Rebuilding from the saved
  data produces identical output.

## To run it locally

```sh
make install && make data && make serve
```

Then open http://127.0.0.1:8000. `make data-offline` rebuilds in seconds without the network.

## To publish it (needs you)

1. Create a GitHub repo and push. I haven't run `git init` or committed anything.
2. In Settings → Pages, set Source to "GitHub Actions", and allow Actions to push commits.
3. Fill in `REPO_URL` and `ISSUES_URL` in `site/js/config.js`. This turns on the "Zgłoś błąd" (report an error)
   buttons.

The included workflow then refreshes the data on a schedule and deploys automatically. README.md has the details.

## Please review: decisions I made without you

Section 1 of `BACKLOG.md`, marked 🔴. The main ones:

- **Building permits:** your source page has none, so I added them from the GUNB register, hidden until switched on.
- **City bureau lists:** included as a second source of the same kinds of decisions.
- **Privacy:**
  - Private individuals' names are removed.
  - Company names are kept.
  - Building designers' names are left out of the site, but stay in the archived copy of the register so it matches
    GUNB byte for byte.
- **Map and location rules:**
  - Neighbourhoods are the six official ones.
  - Where a source's parcel district number contradicts its address, the record is placed by the address and shows
    a warning.
- **Not chosen yet:** a code licence, and a base-map provider if traffic grows. The free OpenStreetMap tiles are fine
  for low traffic.

`BACKLOG.md` also lists errors in the source data worth reporting to the offices, for example the missing August
2022 page and 43 decision numbers that never appear in any list. It also lists the known limitations.
