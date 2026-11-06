# Overhead

**The planes flying over your house right now, each one painted from a photograph of that exact aircraft, on an e-paper frame on your wall.**

![Eight aircraft over Melbourne Airport, painted and arranged on one page](screenshots/arrangement.png)

Overhead is a set of four widgets for [Tesserae](https://github.com/dmellok/tesserae), a self-hosted server that draws dashboards for e-paper panels. Each time the panel refreshes, it asks a public ADS-B feed (or your own receiver) what is in the air near you, looks up a photograph of each airframe by its registration, and has an image model paint it, once, in the style you pick. The paintings are cut out and packed onto the page with each aircraft's callsign, type and height.

A painting costs about four US cents and is kept for good, so an aircraft that passes every day is only ever painted once. Photographs alone cost nothing.

## What it draws

| | |
|---|---|
| ![An arrangement on a portrait panel](screenshots/arrangement-portrait.png) | ![A livery chart](screenshots/livery-chart.png) |
| **Arrangement** on a portrait panel: each aircraft in a livelier view (flying towards you, the front quarter, the side, now and then one banking), packed close and staggered edge to edge | **Livery chart**: every aircraft side-on, all facing the same way, its particulars beside it |
| ![Postage stamps](screenshots/extra-7.png) | ![A plate](screenshots/extra-8.png) |
| **Packed cluster** in the postage-stamp style | **Plate**: one aircraft in a ruled frame, its particulars beside it |
| ![A scene at sunset](screenshots/extra-6.png) | ![The photo widget](screenshots/extra-3.png) |
| **Scene**: one painting across the page, on a sky of its own, or the sky as it is now at your place | **Photo**: no AI at all, the nearest airframe's own photograph and the next few along a strip |
| ![The arrangement on a colour of your own](screenshots/own-colour.png) | ![A packed cluster](screenshots/lg.png) |
| Any **paper colour** you like | The **packed cluster**, sized by wingspan |

The four widgets are **Overhead: Photo**, **Overhead: Plate**, **Overhead: Cluster** (packed, arrangement or livery chart) and **Overhead: Scene**.

## Twenty styles

The same Qantas 737 in each of them. There is also **Build my own** (medium, period, palette, line, texture and mood, plus your own words) and **Your own prompt**.

| | | | |
|---|---|---|---|
| <img src="overhead_core/static/styles/large/poster.jpg" width="200" alt="Vintage airline poster"> | <img src="overhead_core/static/styles/large/engraving.jpg" width="200" alt="Black-ink engraving"> | <img src="overhead_core/static/styles/large/technical.jpg" width="200" alt="Technical ink drawing"> | <img src="overhead_core/static/styles/large/watercolour.jpg" width="200" alt="Loose watercolour"> |
| **Vintage airline poster** | **Black-ink engraving** | **Technical ink drawing** | **Loose watercolour** |
| <img src="overhead_core/static/styles/large/linocut.jpg" width="200" alt="Linocut"> | <img src="overhead_core/static/styles/large/deco.jpg" width="200" alt="Art Deco travel poster"> | <img src="overhead_core/static/styles/large/blueprint.jpg" width="200" alt="Blueprint"> | <img src="overhead_core/static/styles/large/cutaway.jpg" width="200" alt="Magazine cutaway"> |
| **Linocut** | **Art Deco travel poster** | **Blueprint** | **Magazine cutaway** |
| <img src="overhead_core/static/styles/large/stamp.jpg" width="200" alt="Postage stamp"> | <img src="overhead_core/static/styles/large/tattoo.jpg" width="200" alt="Tattoo flash"> | <img src="overhead_core/static/styles/large/riso.jpg" width="200" alt="Risograph"> | <img src="overhead_core/static/styles/large/pixel.jpg" width="200" alt="Pixel art"> |
| **Postage stamp** | **Tattoo flash** | **Risograph** | **Pixel art** |
| <img src="overhead_core/static/styles/large/lowpoly.jpg" width="200" alt="Low-poly render"> | <img src="overhead_core/static/styles/large/toybrick.jpg" width="200" alt="Toy bricks"> | <img src="overhead_core/static/styles/large/charcoal.jpg" width="200" alt="Charcoal"> | <img src="overhead_core/static/styles/large/stained_glass.jpg" width="200" alt="Stained glass"> |
| **Low-poly render** | **Toy bricks** | **Charcoal** | **Stained glass** |
| <img src="overhead_core/static/styles/large/gilt.jpg" width="200" alt="Illuminated manuscript"> | <img src="overhead_core/static/styles/large/pulp.jpg" width="200" alt="Pulp cover"> | <img src="overhead_core/static/styles/large/synthwave.jpg" width="200" alt="Synthwave"> | <img src="overhead_core/static/styles/large/chalk.jpg" width="200" alt="Chalkboard"> |
| **Illuminated manuscript** | **Pulp cover** | **Synthwave** | **Chalkboard** |

<sub>Painted by Nano Banana from "Qantas 737-800 landing runway 03" by Jordan Vuong (CC BY 2.0). The Qantas livery and marks belong to Qantas.</sub>

## How it works

1. **Where the aircraft are.** adsb.lol, a community ADS-B aggregator that needs no key, with adsb.fi as a fallback; or your own readsb, dump1090 or tar1090 receiver. Optionally, everything that passed since the last render rather than one moment of it.
2. **What each one is.** Type and wingspan from the ICAO type code, operator from the callsign, route from adsbdb, and a photograph of the very airframe from planespotters.net, credited to its photographer on the page.
3. **The painting.** The photograph goes to an image model on fal.ai (Nano Banana by default) with the style, the view and the rule that the livery, titles and registration are kept exactly. An aircraft with no photograph is painted from the Wikipedia picture of its type.
4. **The cut-out.** The painting is made on white paper and cut out by flooding the paper in from the edges, which keeps a white fuselage white. Paper trapped inside the outline, between a strut and a wing, is found by a background-removal model (BiRefNet, about two cents, once per painting).
5. **The page.** The cut-outs are packed by their actual outlines, not their boxes, so wings nest into each other's gaps; captions are measured and never cover an aircraft. Two of the packers come from [Fugleramme](https://github.com/arnegiacomo/fugleramme).

Everything is kept on your server: photographs, paintings, cut-outs and a ledger of what passed, so the paintings page can tell you how much of your sky is already painted.

## What it costs

- **Photographs**: free.
- **A painting**: about US$0.04 on Nano Banana, once per aircraft and style. Set **One painting for** to *each type in each airline's livery* and a busy place needs a few dozen paintings rather than thousands.
- **Finding the gaps in a cut-out**: about US$0.02, once per painting.
- **A daily budget** for each (US$4 and US$2 by default) stops it there, and the page carries on with what it has.

## Install

You need [Tesserae](https://github.com/dmellok/tesserae) 0.463 or later.

1. Install the **Overhead** bundle from the Tesserae catalog, or copy the five folders (`overhead_core`, `overhead_photo`, `overhead_plate`, `overhead_cluster`, `overhead_scene`) into your plugins folder together.
2. In **Settings › Plugins › Overhead Core**, give a contact (an email or a web page) for planespotters.net, whose API asks every application for one. For paintings, add a [fal.ai key](https://fal.ai/dashboard/keys).
3. Put an Overhead widget on a dashboard and pick a place and a radius. Without a fal.ai key it shows photographs.

The paintings page is under **Widgets › Overhead Core**: what was painted today, every painting with the photograph it came from, repaint, delete, earlier versions and **Paint a plane** by registration.

Every option, at length: [docs/REFERENCE.md](docs/REFERENCE.md).

## Development

```sh
# the tests import Tesserae's app.artwork: a checkout beside this repo is found on its own
PYTHONPATH=../tesserae python -m pytest overhead_core/tests -q     # offline, the network faked
python3 overhead_core/tools/manifests.py                           # the four plugin.json from one description
FAL_KEY=... python3 overhead_core/tools/preview.py --widget cluster layout=bouquet --w 1200 --h 1600
python3 overhead_core/tools/preview.py --data saved.json packing=voids   # draw a saved page again, no fetch
```

## Credits and licence

Positions from adsb.lol and adsb.fi, routes from adsbdb, photographs from planespotters.net (each credited to its photographer), type pictures and visitors' references from Wikimedia Commons and NASA. Airline marks, when turned on, are fetched at render time and belong to the airlines; keep logos off on anything you publish. Details in [ATTRIBUTION.md](ATTRIBUTION.md).

AGPL-3.0-or-later, apart from the Spiral and Voids packing in `overhead_core/static/pack.js`, adapted from Fugleramme (MIT, Arne Giacomo Munthe-Kaas).
