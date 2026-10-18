# Overhead

Four Tesserae widgets for the aircraft overhead right now, installed together as one bundle:

| widget | the page |
|---|---|
| **Overhead: Photo** | the nearest aircraft as a full-bleed photograph of the very airframe, the next few along a strip |
| **Overhead: Plate** | one aircraft painted from its photograph, in a ruled frame, its particulars beside it |
| **Overhead: Cluster** | everything in the air near you on one page, each painted and cut out, sized by wingspan; or a spotter's log of photograph cards |
| **Overhead: Scene** | one whole painting across the page: the aircraft on a painted sky, clouds, sunset, night, storm or an ornate plate |

**Positions** come from adsb.lol (no key, the community feed), with adsb.fi asked instead when adsb.lol is slow or down, or a receiver of your own (readsb, dump1090 or tar1090: the widget reads `/data/aircraft.json`). Each aircraft gets its type and wingspan from its ICAO code, its operator from its callsign, its route from adsbdb, and a photograph of the actual registration from planespotters.net, credited to the photographer.

**Since the last render** is a setting on every page beside the order: instead of what is within reach at the moment the page is drawn, everything that passed since the page was last drawn for a panel, each aircraft at its closest approach with the time, so a page drawn every hour is the hour's traffic rather than one moment of it. The widget keeps a watch on the place between renders (the community feeds asked every minute, a receiver every thirty seconds) and remembers each aircraft with the moment it came closest, for two days; the windows chain, so nothing falls between two pages, and the warm-ahead, the settle and the send of one page share a window. The editor's previews show the same window without moving it on. The watch stops three hours after a page last asked, and a first render shows the last hour. A label line, **When it was within reach**, says when it was first seen and, once it has passed, when last.

**Pictures** are the photographs, or AI paintings: each airframe painted once from its own photograph through fal.ai, in a style, on white paper so it cuts out cleanly, at about US$0.04 a painting. Twenty-six styles, from a vintage airline poster, engravings, watercolour, woodblock, linocut, Art Deco and mid-century flat to a magazine cutaway, a postage stamp, tattoo flash, risograph, pixel art, a low-poly render, paper craft, toy bricks, charcoal, stained glass, an illuminated manuscript, a pulp cover, synthwave and a chalkboard, **Build my own** (medium, period, palette, line, texture, mood and your own words) and **Your own prompt** with examples to start from. The Plate and the Scene take a **backdrop**: none, a clear sky, above the clouds, sunset, night, storm light or an ornate framed plate. Four views, a pure side-on livery profile among them. Every aircraft is painted with a fine contour line so the cut-out keeps a white fuselage.

**The cluster** packs the cut-outs the way the Specimen Sheet does: each aircraft's footprint on a lattice from the middle out, as large as the page allows, with a Scale slider for more paper round the arrangement. The cut-out reads the paper as what reaches the page's edge, so a white fuselage inside its contour stays white, and a frame or vignette the model draws round the page is stepped inside.

**The sky as it is now** is a backdrop for the Plate and the Scene: the time of day (dawn, morning, midday, afternoon, dusk, night, from the sun times) and the weather (Open-Meteo: clear, cloud, overcast, fog, rain, snow, storm) at the place, painted behind the aircraft and keyed by condition, so a changing sky is a new painting.

**Type** is a picker: IM Fell English (the old plate), Archivo Narrow, Georgia, or the dashboard's own font.

**Chance of a UFO** is a slider on the painted pages. Each hour the page rolls it, and on a hit an unidentified contact joins: from the craft you tick: classic UFOs of plainly alien make (a saucer, a black triangle, a cigar, an orb, a tic-tac, an Adamski bell), famous craft from film and television (described to the painter by shape, never named), and real spacecraft (the Shuttle, Apollo, Sputnik, Starship, Voyager, the station, a Zeppelin); painted in the page's style from an openly licensed reference picture where one exists (Wikimedia Commons and NASA, credited on the page), from a picture of your own given in the Overhead Core settings (one a line, craft = URL or path), or from words alone otherwise, the smallest thing on the page, captioned with no transponder and a made-up height and bearing. The preview and the panel roll the same within the hour.

**Airline logos** are off by default. On, the widget fetches the airline's mark by its IATA code from a logo service chosen in the settings (Daisycon wordmarks or Kiwi.com square icons) at render time and keeps it on your server; nothing ships with the widget, and the marks are the airlines'. Keep it off on anything you publish; the airline's name shows instead.

**Settings** live on Overhead Core (Settings › Plugins): the fal.ai key, a contact for planespotters.net (their API refuses requests without one), the daily painting limit, how many paintings start per preview and run at once, and the logo service. The paintings page is under Widgets › Overhead Core: what was painted to-day, each painting with a link to the photograph it was painted from, Render now (paints what the panels' pages are missing, and nothing more), the paintings grouped by dashboard with a tab per style, repaint, delete, earlier versions and Purge everything.

While a dashboard is being edited nothing is painted: the editor's previews hold their paintings and the job tray offers Paint now; a preview left alone for twenty seconds paints; a panel's own render paints what its page needs within the daily limit. Changing the style while editing drops what was held or queued for the old one.

**How full the catalogue is**: the widgets count every pass of every aircraft they see, across all your cells (the same one again within half an hour is one pass), in one ledger under the core's data folder. The paintings page shows the chance the next one past is already painted, what share of passes were of a painted one, how many seen are painted, and an estimate of how many pass your places in all (Chao1, from how many were seen once and twice), with the ones seen most.

## Install

Needs Tesserae 0.463 or later: the paintings are kept, queued, budgeted and
listed by the server's own Artwork support (`app.artwork`), and the paintings
page is the one Tesserae renders at Plugins › Overhead.


From the Tesserae catalog as the Overhead bundle, or by hand: copy the five folders (`overhead_core`, `overhead_photo`, `overhead_plate`, `overhead_cluster`, `overhead_scene`) into your plugins folder together (the tests and tools live inside `overhead_core`, so the tarball's top level holds nothing but plugin folders); the four widgets load their shared code from `overhead_core` by path.

## Development

The tests and the tools import Tesserae's `app.artwork`; a checkout of the
server beside this repo is found on its own, or point `TESSERAE_REPO` at one:

```sh
PYTHONPATH=../tesserae python -m pytest overhead_core/tests -q
```


```
python3 -m pytest overhead_core/tests -q          # offline: every call on the network is faked
python3 overhead_core/tools/manifests.py          # rewrites the four plugin.json from one description
python3 overhead_core/tools/preview.py --widget cluster pictures=photos   # a live render to overhead_core/tools/out/
```
