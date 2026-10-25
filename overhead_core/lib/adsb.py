"""What is in the air: aircraft near a place from adsb.lol or a receiver of
your own (readsb, dump1090, tar1090: their aircraft.json), each with its
type, operator, route (adsbdb), a photograph of the very airframe
(planespotters.net) and its airline's mark (fetched from the web, never
shipped). Loaded by path."""

from __future__ import annotations

import base64
import contextlib
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import html
import importlib.util
import io
import json
import math
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _sibling(name: str) -> Any:
    full = f"_tesserae_plugins.overhead_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


N = _sibling("net")

ADSB_LOL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
ADSB_FI = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}"
# the community feeds, in order of preference; the same readsb answer from each
FEEDS = (("adsb.lol", ADSB_LOL), ("adsb.fi", ADSB_FI))
FEED_WAIT_S = 2.0  # how long the first feed gets before the next is asked too
FEED_BUDGET_S = 3.5  # how long the position lookup may take in all
FEED_DOWN_S = 600  # a feed that failed is passed over for this long
ADSBDB = "https://api.adsbdb.com/v0/callsign/{cs}"
ADSBDB_AIRCRAFT = "https://api.adsbdb.com/v0/aircraft/{key}"
PLANESPOTTERS = "https://api.planespotters.net/pub/photos/reg/{reg}"
# a photograph of the type, for an airframe planespotters.net has none of: the lead picture of the type's
# Wikipedia article, with its author and licence from Commons
WIKIPEDIA = "https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages&piprop=name&{q}"
COMMONS_FILE = (
    "https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|extmetadata"
    "&iiurlwidth=1024&iiextmetadatafilter=Artist|LicenseShortName&titles={title}"
)
# the type's article where a search on its name finds the wrong one (or one without a picture)
TYPE_ARTICLES = {
    "C208": "Cessna 208 Caravan",
    "P28A": "Piper PA-28 Cherokee",
    "GLF4": "Gulfstream IV",
    "GLF5": "Gulfstream V",
    "AT72": "ATR 72",
    "AT76": "ATR 72",
    "C150": "Cessna 152",  # the 150's article has no lead picture; the 152 is the same airframe
}
# codes that name a kind of craft rather than a type: painted from words, never looked up
KIND_CODES = frozenset({"GLID", "ULAC", "BALL"})
TYPE_PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp")  # a drawing (svg) is no photograph
LOGO_SOURCES = {
    "daisycon": "https://www.daisycon.io/images/airline/?width=400&height=200&color=ffffff&iata={iata}",
    "kiwi": "https://images.kiwi.com/airlines/128/{iata}.png",
}
LIVE_S = 15  # the live feed is asked at most this often
WEATHER_S = 15 * 60
OPEN_METEO = "https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lon:.3f}&current=weather_code,cloud_cover,is_day&daily=sunrise,sunset&timezone=auto&forecast_days=1"
ROUTE_S = 7 * 86400
PHOTO_S = 30 * 86400
NM_KM = 1.852


def user_agent(contact: str) -> str:
    c = " ".join(str(contact or "").split())
    return f"tesserae-overhead/0.1 (+https://github.com/dmellok/tesserae-widget-overhead{'; ' + c if c else ''})"


# ----------------------------------------------------------------------
# Types: ICAO designator to a name and a class for the fallback silhouette
# ----------------------------------------------------------------------
TYPES: dict[str, tuple[str, str, float]] = {
    # code: (name, class, wingspan m)
    "A318": ("Airbus A318", "jet", 34.1), "A319": ("Airbus A319", "jet", 35.8), "A320": ("Airbus A320", "jet", 35.8),
    "A20N": ("Airbus A320neo", "jet", 35.8), "A321": ("Airbus A321", "jet", 35.8), "A21N": ("Airbus A321neo", "jet", 35.8),
    "A332": ("Airbus A330-200", "wide", 60.3), "A333": ("Airbus A330-300", "wide", 60.3), "A339": ("Airbus A330-900neo", "wide", 64.0),
    "A342": ("Airbus A340-200", "wide", 60.3), "A343": ("Airbus A340-300", "wide", 60.3), "A346": ("Airbus A340-600", "wide", 63.5),
    "A359": ("Airbus A350-900", "wide", 64.8), "A35K": ("Airbus A350-1000", "wide", 64.8), "A388": ("Airbus A380", "wide", 79.8),
    "A306": ("Airbus A300-600", "wide", 44.8), "A310": ("Airbus A310", "wide", 43.9),
    "B712": ("Boeing 717", "jet", 28.4), "B732": ("Boeing 737-200", "jet", 28.4), "B733": ("Boeing 737-300", "jet", 28.9),
    "B734": ("Boeing 737-400", "jet", 28.9), "B735": ("Boeing 737-500", "jet", 28.9), "B736": ("Boeing 737-600", "jet", 34.3),
    "B737": ("Boeing 737-700", "jet", 34.3), "B738": ("Boeing 737-800", "jet", 35.8), "B739": ("Boeing 737-900", "jet", 35.8),
    "B37M": ("Boeing 737 MAX 7", "jet", 35.9), "B38M": ("Boeing 737 MAX 8", "jet", 35.9), "B39M": ("Boeing 737 MAX 9", "jet", 35.9),
    "B3XM": ("Boeing 737 MAX 10", "jet", 35.9), "B744": ("Boeing 747-400", "wide", 64.4), "B748": ("Boeing 747-8", "wide", 68.4),
    "B752": ("Boeing 757-200", "jet", 38.0), "B753": ("Boeing 757-300", "jet", 38.0), "B762": ("Boeing 767-200", "wide", 47.6),
    "B763": ("Boeing 767-300", "wide", 47.6), "B764": ("Boeing 767-400", "wide", 51.9), "B772": ("Boeing 777-200", "wide", 60.9),
    "B77L": ("Boeing 777-200LR", "wide", 64.8), "B773": ("Boeing 777-300", "wide", 60.9), "B77W": ("Boeing 777-300ER", "wide", 64.8),
    "B778": ("Boeing 777-8", "wide", 71.8), "B779": ("Boeing 777-9", "wide", 71.8), "B788": ("Boeing 787-8", "wide", 60.1),
    "B789": ("Boeing 787-9", "wide", 60.1), "B78X": ("Boeing 787-10", "wide", 60.1),
    "E170": ("Embraer E170", "jet", 26.0), "E175": ("Embraer E175", "jet", 26.0), "E190": ("Embraer E190", "jet", 28.7),
    "E195": ("Embraer E195", "jet", 28.7), "E290": ("Embraer E190-E2", "jet", 33.7), "E295": ("Embraer E195-E2", "jet", 35.1),
    "E135": ("Embraer ERJ 135", "jet", 20.0), "E145": ("Embraer ERJ 145", "jet", 20.0),
    "CRJ2": ("Bombardier CRJ200", "jet", 21.2), "CRJ7": ("Bombardier CRJ700", "jet", 23.2), "CRJ9": ("Bombardier CRJ900", "jet", 24.9),
    "CRJX": ("Bombardier CRJ1000", "jet", 26.2), "BCS1": ("Airbus A220-100", "jet", 35.1), "BCS3": ("Airbus A220-300", "jet", 35.1),
    "F100": ("Fokker 100", "jet", 28.1), "F70": ("Fokker 70", "jet", 28.1), "MD82": ("McDonnell Douglas MD-82", "jet", 32.9),
    "MD83": ("McDonnell Douglas MD-83", "jet", 32.9), "MD11": ("McDonnell Douglas MD-11", "wide", 51.7), "RJ85": ("Avro RJ85", "jet", 26.3),
    "RJ1H": ("Avro RJ100", "jet", 26.3), "SU95": ("Sukhoi Superjet 100", "jet", 27.8), "C919": ("Comac C919", "jet", 35.8),
    "DH8A": ("Dash 8-100", "prop", 25.9), "DH8B": ("Dash 8-200", "prop", 25.9), "DH8C": ("Dash 8-300", "prop", 27.4),
    "DH8D": ("Dash 8 Q400", "prop", 28.4), "AT43": ("ATR 42-300", "prop", 24.6), "AT45": ("ATR 42-500", "prop", 24.6),
    "AT46": ("ATR 42-600", "prop", 24.6), "AT72": ("ATR 72-200", "prop", 27.0), "AT75": ("ATR 72-500", "prop", 27.0),
    "AT76": ("ATR 72-600", "prop", 27.0), "SF34": ("Saab 340", "prop", 21.4), "SB20": ("Saab 2000", "prop", 24.8),
    "E120": ("Embraer Brasilia", "prop", 19.8), "JS41": ("BAe Jetstream 41", "prop", 18.4), "D328": ("Dornier 328", "prop", 21.0),
    "F50": ("Fokker 50", "prop", 29.0), "B350": ("King Air 350", "prop", 17.7), "BE20": ("King Air 200", "prop", 16.6),
    "BE9L": ("King Air 90", "prop", 15.3), "PC12": ("Pilatus PC-12", "prop", 16.3), "C208": ("Cessna Caravan", "prop", 15.9),
    "DHC6": ("Twin Otter", "prop", 19.8), "C402": ("Cessna 402", "prop", 13.5), "F406": ("Reims-Cessna F406", "prop", 15.1),
    "PA31": ("Piper Navajo", "prop", 12.4), "P68": ("Partenavia P68", "prop", 12.0), "BE58": ("Beechcraft Baron", "prop", 11.5),
    "C172": ("Cessna 172", "light", 11.0), "C182": ("Cessna 182", "light", 11.0), "C152": ("Cessna 152", "light", 10.2),
    "C150": ("Cessna 150", "light", 10.2), "C206": ("Cessna 206", "light", 11.0), "C210": ("Cessna 210", "light", 11.2),
    "P28A": ("Piper Cherokee", "light", 10.7), "P28R": ("Piper Arrow", "light", 10.8), "PA44": ("Piper Seminole", "light", 11.8),
    "DA40": ("Diamond DA40", "light", 11.9), "DA42": ("Diamond DA42", "light", 13.4), "DA20": ("Diamond DA20", "light", 10.9),
    "SR20": ("Cirrus SR20", "light", 11.7), "SR22": ("Cirrus SR22", "light", 11.7), "BE36": ("Beechcraft Bonanza", "light", 10.2),
    "M20P": ("Mooney M20", "light", 11.0), "C77R": ("Cessna Cardinal", "light", 10.8), "SLG2": ("Slingsby T67", "light", 10.6),
    "TBM9": ("TBM 900", "prop", 12.8), "TBM7": ("TBM 700", "prop", 12.7), "PC24": ("Pilatus PC-24", "biz", 17.0),
    "C25A": ("Cessna CitationJet CJ2", "biz", 15.2), "C25B": ("Cessna Citation CJ3", "biz", 16.3), "C25C": ("Cessna Citation CJ4", "biz", 15.5),
    "C56X": ("Cessna Citation XLS", "biz", 17.2), "C680": ("Cessna Citation Sovereign", "biz", 19.2), "C68A": ("Cessna Citation Latitude", "biz", 22.0),
    "C700": ("Cessna Citation Longitude", "biz", 21.0), "C750": ("Cessna Citation X", "biz", 19.4), "CL30": ("Bombardier Challenger 300", "biz", 19.5),
    "CL35": ("Bombardier Challenger 350", "biz", 21.0), "CL60": ("Bombardier Challenger 600", "biz", 19.6), "GLF4": ("Gulfstream IV", "biz", 23.7),
    "GLF5": ("Gulfstream V", "biz", 28.5), "GLF6": ("Gulfstream G650", "biz", 30.4), "GL5T": ("Bombardier Global 5000", "biz", 28.7),
    "GLEX": ("Bombardier Global Express", "biz", 28.7), "F2TH": ("Dassault Falcon 2000", "biz", 21.4), "FA7X": ("Dassault Falcon 7X", "biz", 26.2),
    "LJ35": ("Learjet 35", "biz", 12.0), "LJ45": ("Learjet 45", "biz", 14.6), "E55P": ("Embraer Phenom 300", "biz", 16.2),
    "E50P": ("Embraer Phenom 100", "biz", 12.3), "H25B": ("Hawker 800", "biz", 15.7), "PRM1": ("Beechcraft Premier", "biz", 13.6),
    "R44": ("Robinson R44", "heli", 10.1), "R22": ("Robinson R22", "heli", 7.7), "R66": ("Robinson R66", "heli", 10.1),
    "AW139": ("AgustaWestland AW139", "heli", 13.8), "A139": ("AgustaWestland AW139", "heli", 13.8), "A109": ("AgustaWestland AW109", "heli", 11.0),
    "EC35": ("Airbus H135", "heli", 10.2), "EC45": ("Airbus H145", "heli", 11.0), "EC30": ("Airbus H130", "heli", 10.7),
    "AS50": ("Airbus H125", "heli", 10.7), "AS55": ("Eurocopter AS355", "heli", 10.7), "B06": ("Bell 206", "heli", 10.2),
    "B407": ("Bell 407", "heli", 10.7), "B412": ("Bell 412", "heli", 14.0), "B429": ("Bell 429", "heli", 11.0),
    "S76": ("Sikorsky S-76", "heli", 13.4), "S92": ("Sikorsky S-92", "heli", 17.2), "H60": ("Sikorsky Black Hawk", "heli", 16.4),
    "C130": ("Lockheed C-130 Hercules", "prop", 40.4), "C17": ("Boeing C-17 Globemaster", "wide", 51.7), "K35R": ("Boeing KC-135", "jet", 39.9),
    "P8": ("Boeing P-8 Poseidon", "jet", 37.6), "E7": ("Boeing E-7 Wedgetail", "jet", 34.3), "A400": ("Airbus A400M", "prop", 42.4),
    "C30J": ("Lockheed C-130J", "prop", 40.4), "F18": ("F/A-18 Hornet", "jet", 12.3), "F35": ("F-35 Lightning II", "jet", 10.7),
    "HAWK": ("BAE Hawk", "jet", 9.9), "PC21": ("Pilatus PC-21", "prop", 9.1), "PC9": ("Pilatus PC-9", "prop", 10.1),
    "GLID": ("Glider", "light", 15.0), "ULAC": ("Ultralight", "light", 9.0), "BALL": ("Balloon", "light", 0.0),
}
CLASS_SPAN = {"wide": 60.0, "jet": 35.0, "biz": 18.0, "prop": 24.0, "light": 11.0, "heli": 11.0}


def type_of(code: str, desc: str = "", category: str = "") -> tuple[str, str, float]:
    """(name, class, wingspan m) for an ICAO type code."""
    code = (code or "").strip().upper()
    if code in TYPES:
        return TYPES[code]
    words = " ".join(str(desc or "").split())
    name = words.title().replace("Airbus Industrie", "Airbus") if words else (code or "Aircraft")
    cls = "jet"
    cat = (category or "").upper()
    if cat in ("A7",) or "HELI" in words.upper() or code.startswith(("R4", "R2", "EC", "AS", "B4", "A10", "A13")):
        cls = "heli"
    elif cat in ("A1",) or code.startswith(("C1", "P2", "DA", "SR")):
        cls = "light"
    elif cat in ("A5",):
        cls = "wide"
    elif cat in ("A2",):
        cls = "prop"
    return (name, cls, CLASS_SPAN[cls])


# ----------------------------------------------------------------------
# Airlines: ICAO callsign prefix to (IATA code, name). Enough for most of
# what passes over a city; adsbdb fills the rest in from the route lookup.
# ----------------------------------------------------------------------
AIRLINES: dict[str, tuple[str, str]] = {
    "QFA": ("QF", "Qantas"), "QLK": ("QF", "QantasLink"), "JST": ("JQ", "Jetstar"), "VOZ": ("VA", "Virgin Australia"),
    "RXA": ("ZL", "Rex"), "UTY": ("QF", "QantasLink"), "NWK": ("QF", "QantasLink"), "QJE": ("QF", "Qantas Freight"),
    "BNZ": ("BZ", "Bonza"), "ANZ": ("NZ", "Air New Zealand"), "UAE": ("EK", "Emirates"), "ETD": ("EY", "Etihad"),
    "QTR": ("QR", "Qatar Airways"), "SIA": ("SQ", "Singapore Airlines"), "SLK": ("MI", "SilkAir"), "TGW": ("TR", "Scoot"),
    "CPA": ("CX", "Cathay Pacific"), "CRK": ("HX", "Hong Kong Airlines"), "MAS": ("MH", "Malaysia Airlines"), "AXM": ("AK", "AirAsia"),
    "XAX": ("D7", "AirAsia X"), "THA": ("TG", "Thai Airways"), "GIA": ("GA", "Garuda Indonesia"), "PAL": ("PR", "Philippine Airlines"),
    "CEB": ("5J", "Cebu Pacific"), "VJC": ("VJ", "VietJet"), "HVN": ("VN", "Vietnam Airlines"), "CES": ("MU", "China Eastern"),
    "CSN": ("CZ", "China Southern"), "CCA": ("CA", "Air China"), "CXA": ("MF", "Xiamen Airlines"), "CSZ": ("ZH", "Shenzhen Airlines"),
    "CHH": ("HU", "Hainan Airlines"), "CSC": ("3U", "Sichuan Airlines"), "JAL": ("JL", "Japan Airlines"), "ANA": ("NH", "All Nippon Airways"),
    "KAL": ("KE", "Korean Air"), "AAR": ("OZ", "Asiana"), "CAL": ("CI", "China Airlines"), "EVA": ("BR", "EVA Air"),
    "AIC": ("AI", "Air India"), "SVA": ("SV", "Saudia"), "THY": ("TK", "Turkish Airlines"), "BAW": ("BA", "British Airways"),
    "VIR": ("VS", "Virgin Atlantic"), "DLH": ("LH", "Lufthansa"), "AFR": ("AF", "Air France"), "KLM": ("KL", "KLM"),
    "SWR": ("LX", "Swiss"), "AUA": ("OS", "Austrian"), "IBE": ("IB", "Iberia"), "TAP": ("TP", "TAP Air Portugal"),
    "AZA": ("AZ", "ITA Airways"), "ITY": ("AZ", "ITA Airways"), "SAS": ("SK", "SAS"), "FIN": ("AY", "Finnair"),
    "EIN": ("EI", "Aer Lingus"), "RYR": ("FR", "Ryanair"), "EZY": ("U2", "easyJet"), "EJU": ("EC", "easyJet Europe"),
    "WZZ": ("W6", "Wizz Air"), "VLG": ("VY", "Vueling"), "TRA": ("HV", "Transavia"), "NAX": ("DY", "Norwegian"),
    "LOT": ("LO", "LOT Polish Airlines"), "AFL": ("SU", "Aeroflot"), "ELY": ("LY", "El Al"), "MSR": ("MS", "EgyptAir"),
    "ETH": ("ET", "Ethiopian Airlines"), "KQA": ("KQ", "Kenya Airways"), "SAA": ("SA", "South African Airways"), "RAM": ("AT", "Royal Air Maroc"),
    "AAL": ("AA", "American Airlines"), "DAL": ("DL", "Delta"), "UAL": ("UA", "United"), "SWA": ("WN", "Southwest"),
    "JBU": ("B6", "JetBlue"), "ASA": ("AS", "Alaska Airlines"), "NKS": ("NK", "Spirit"), "FFT": ("F9", "Frontier"),
    "HAL": ("HA", "Hawaiian Airlines"), "ACA": ("AC", "Air Canada"), "WJA": ("WS", "WestJet"), "AMX": ("AM", "Aeroméxico"),
    "VOI": ("Y4", "Volaris"), "LAN": ("LA", "LATAM"), "TAM": ("JJ", "LATAM Brasil"), "GLO": ("G3", "Gol"), "AZU": ("AD", "Azul"),
    "ARG": ("AR", "Aerolíneas Argentinas"), "AVA": ("AV", "Avianca"), "CMP": ("CM", "Copa Airlines"), "FDX": ("FX", "FedEx"),
    "UPS": ("5X", "UPS"), "GTI": ("5Y", "Atlas Air"), "CLX": ("CV", "Cargolux"), "BOX": ("3S", "AeroLogic"),
    "FJI": ("FJ", "Fiji Airways"), "ANG": ("PX", "Air Niugini"), "LDA": ("LD", "Air Hong Kong"), "ABY": ("G9", "Air Arabia"),
    "FDB": ("FZ", "flydubai"), "OMA": ("WY", "Oman Air"), "GFA": ("GF", "Gulf Air"), "KAC": ("KU", "Kuwait Airways"),
    "RJA": ("RJ", "Royal Jordanian"), "PIA": ("PK", "PIA"), "UBD": ("UB", "Myanmar National"), "BBC": ("BG", "Biman"),
    "ALK": ("UL", "SriLankan"), "IGO": ("6E", "IndiGo"), "VTI": ("UK", "Vistara"), "AXB": ("IX", "Air India Express"),
    "NCA": ("KZ", "Nippon Cargo"), "APJ": ("MM", "Peach"), "JJP": ("GK", "Jetstar Japan"), "TAX": ("TZ", "Scoot"),
    "AWQ": ("QZ", "Indonesia AirAsia"), "LNI": ("JT", "Lion Air"), "BTK": ("ID", "Batik Air"), "MXD": ("OD", "Batik Air Malaysia"),
    "POL": ("", "Police"), "RSCU": ("", "Air Ambulance"), "ASY": ("", "Royal Australian Air Force"), "RFDS": ("", "Royal Flying Doctor Service"),
    "AME": ("", "Spanish Air Force"), "RRR": ("", "Royal Air Force"), "RCH": ("", "US Air Force"), "GAF": ("", "German Air Force"),
}


# Prefixes more than one operator flies under (every Australian state's police
# helicopters call themselves POL): the table's word is the neutral one, and the
# airframe's registered owner, when it is known, says whose it is.
SHARED_PREFIXES = frozenset({"POL"})


def shared_prefix(callsign: str) -> bool:
    """Whether the callsign's prefix is one several operators share."""
    cs = (callsign or "").strip().upper()
    return any(cs[:n] in SHARED_PREFIXES and len(cs) > n and cs[n:].isalnum() for n in (4, 3))


def airline_of(callsign: str, reg: str, route_airline: str = "", owner: str = "") -> tuple[str, str]:
    """(IATA code or '', operator name) from the callsign's prefix; for a
    prefix several operators share, the airframe's registered owner instead
    when it is known (from the feed or adsbdb), else the table's neutral word."""
    cs = (callsign or "").strip().upper()
    for n in (4, 3):
        if cs[:n] in AIRLINES and (len(cs) > n and (cs[n:].isdigit() or cs[n:].isalnum())):
            if cs[:n] in SHARED_PREFIXES and owner.strip():
                return ("", " ".join(owner.split()))
            return AIRLINES[cs[:n]]
    if route_airline:
        return ("", route_airline)
    if cs and reg and cs.replace("-", "") == reg.replace("-", "").upper():
        return ("", "private")
    return ("", "")


# ----------------------------------------------------------------------
# The aircraft near a place
# ----------------------------------------------------------------------
def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """(km, degrees) from the first point to the second."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 6371.0 * 2 * math.asin(math.sqrt(a))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return km, (math.degrees(math.atan2(y, x)) + 360) % 360


def _rows(ac: list[dict[str, Any]], lat: float, lon: float, radius_km: float) -> list[dict[str, Any]]:
    out = []
    for a in ac:
        if not isinstance(a, dict):
            continue
        alat, alon = a.get("lat"), a.get("lon")
        if not isinstance(alat, (int, float)) or not isinstance(alon, (int, float)):
            continue
        km, deg = _bearing(lat, lon, float(alat), float(alon))
        if km > radius_km:
            continue
        alt = a.get("alt_baro", a.get("altitude"))
        try:
            alt_ft = 0 if alt == "ground" else max(0, int(round(float(alt))))  # a barometric reading below sea level reads as 0
        except (TypeError, ValueError):
            alt_ft = 0
        # on the ground: said so, or so low it is rolling on a runway or a taxiway
        ground = alt == "ground" or alt_ft <= 25
        try:
            rate = int(round(float(a.get("baro_rate", a.get("geom_rate", a.get("vert_rate", 0))) or 0)))
        except (TypeError, ValueError):
            rate = 0
        cs = str(a.get("flight") or "").strip().upper()
        reg = str(a.get("r") or a.get("registration") or "").strip().upper()
        code = str(a.get("t") or a.get("type") or "").strip().upper()
        name, cls, span = type_of(code, str(a.get("desc") or ""), str(a.get("category") or ""))
        out.append(
            {
                "hex": str(a.get("hex") or ""), "cs": cs or reg or str(a.get("hex") or "").upper(), "reg": reg, "code": code,
                "typ": name, "cls": cls, "span": span, "alt": alt_ft, "ground": ground, "rate": rate,
                "gs": int(round(float(a.get("gs") or 0))) if isinstance(a.get("gs"), (int, float)) else 0,
                "trk": int(round(float(a.get("track") or 0))) if isinstance(a.get("track"), (int, float)) else 0,
                "km": round(km, 1), "dir": int(round(deg)), "lat": float(alat), "lon": float(alon),
                "owner": " ".join(str(a.get("ownOp") or "").split()),
                "squawk": str(a.get("squawk") or ""), "military": bool(a.get("dbFlags", 0) & 1) if isinstance(a.get("dbFlags"), int) else False,
            }
        )
    return out


def _down_marker(data_dir: Path, name: str) -> Path:
    return data_dir / "live" / f"{N.slug(name)}.down"


def _mark_down(data_dir: Path, name: str) -> None:
    with contextlib.suppress(OSError):
        marker = _down_marker(data_dir, name)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()


def _ask_feeds(feeds: list[tuple[str, str]], data_dir: Path, ua: str) -> tuple[Any | None, str | None, str]:
    """The first feed's answer, or the next's when it is slow or down: the first
    gets FEED_WAIT_S alone, then the others are asked beside it, and the whole
    lookup stops at FEED_BUDGET_S. A feed that failed is passed over for
    FEED_DOWN_S so the next refresh does not wait on it again."""
    now = time.time()
    order = [f for f in feeds if not _fresh(_down_marker(data_dir, f[0]), now)] or list(feeds)
    deadline = now + FEED_BUDGET_S
    pool = ThreadPoolExecutor(max_workers=len(order), thread_name_prefix="overhead-feed")
    pending: dict[Any, str] = {}
    waiting = list(order)
    last_err: str | None = None
    try:
        while True:
            if waiting and (not pending or time.time() - now >= FEED_WAIT_S):
                name, url = waiting.pop(0)
                pending[pool.submit(N.get_json, url, ua=ua, timeout=FEED_BUDGET_S)] = name
            left = deadline - time.time()
            if left <= 0 or not pending:
                break
            step = min(left, FEED_WAIT_S - (time.time() - now) if waiting else left)
            done, _rest = wait(list(pending), timeout=max(0.05, step), return_when=FIRST_COMPLETED)
            for f in done:
                name = pending.pop(f)
                data, err = f.result()
                if data is not None:
                    for slow in pending.values():  # asked earlier and still silent: passed over for a while
                        _mark_down(data_dir, slow)
                    return data, None, name
                last_err = err or last_err
                _mark_down(data_dir, name)
        for name in pending.values():  # too slow to count as up
            _mark_down(data_dir, name)
        return None, last_err or "unreachable", ""
    finally:
        pool.shutdown(wait=False)


def _fresh(path: Path, now: float) -> bool:
    try:
        return now - path.stat().st_mtime < FEED_DOWN_S
    except OSError:
        return False


def nearby(source: str, receiver_url: str, lat: float, lon: float, radius_km: float, data_dir: Path, ua: str) -> tuple[list[dict[str, Any]], str | None, str]:
    """(rows, error, feed): the aircraft within ``radius_km`` of a point, nearest
    first, with the name of the feed that answered; the live answer is kept
    LIVE_S so the editor's refreshes share one."""
    nm = max(1, min(250, int(math.ceil(radius_km / NM_KM))))
    if source == "receiver":
        base = str(receiver_url or "").strip().rstrip("/")
        if not base:
            return [], "Give the receiver's address (for readsb or dump1090, http://host:8080).", ""
        if not base.startswith("http"):
            base = "http://" + base
        url = base + ("" if base.endswith("aircraft.json") else "/data/aircraft.json")
        feeds = [("The receiver", url)]
    else:
        feeds = [(name, u.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}", nm=nm)) for name, u in FEEDS]
    cache = data_dir / "live" / (N.slug(feeds[0][1]) + ".json")
    got = N.read_json(cache, None)
    feed = str(got.get("feed") or feeds[0][0]) if isinstance(got, dict) else feeds[0][0]
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < LIVE_S:
        data = got.get("data")
    else:
        data, err, answered = _ask_feeds(feeds, data_dir, ua)
        if data is None:
            if isinstance(got, dict):
                data = got.get("data")  # the last answer, rather than nothing
            else:
                why = {"unreachable": "could not be reached", "auth": "refused the request"}.get(err or "", err or "gave no answer")
                who = feeds[0][0] if len(feeds) == 1 else "The live feeds (" + ", ".join(n for n, _u in feeds) + ")"
                return [], f"{who} {why}.", ""
        else:
            feed = answered
            N.write(cache, json.dumps({"at": time.time(), "data": data, "feed": feed}).encode())
    ac = data.get("ac") if isinstance(data, dict) else None
    if ac is None and isinstance(data, dict):
        ac = data.get("aircraft")
    rows = _rows(ac if isinstance(ac, list) else [], lat, lon, radius_km)
    rows.sort(key=lambda r: r["km"])
    return rows, None, feed


# ----------------------------------------------------------------------
# Routes, photographs, marks
# ----------------------------------------------------------------------
def route_of(cs: str, data_dir: Path, ua: str) -> dict[str, str]:
    """{origin, origin_city, dest, dest_city, airline} from adsbdb, kept a week."""
    cs = (cs or "").strip().upper()
    if not cs or not cs[:3].isalpha() or not any(c.isdigit() for c in cs):
        return {}
    cache = data_dir / "routes" / f"{N.slug(cs)}.json"
    got = N.read_json(cache, None)
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < ROUTE_S:
        return got.get("route") or {}
    data, _err = N.get_json(ADSBDB.format(cs=urllib.parse.quote(cs)), ua=ua, timeout=4)
    route: dict[str, str] = {}
    try:
        fr = data["response"]["flightroute"]
        route = {
            "origin": str(fr["origin"].get("iata_code") or ""), "origin_city": str(fr["origin"].get("municipality") or ""),
            "dest": str(fr["destination"].get("iata_code") or ""), "dest_city": str(fr["destination"].get("municipality") or ""),
            "airline": str((fr.get("airline") or {}).get("name") or ""),
        }
    except (KeyError, TypeError, AttributeError):
        route = {}
    if data is not None or _err not in ("unreachable", None):
        N.write(cache, json.dumps({"at": time.time(), "route": route}).encode())
    return route


def owner_of(hexid: str, reg: str, data_dir: Path, ua: str) -> str:
    """The airframe's registered owner from adsbdb (by its ICAO 24-bit address,
    else its registration), kept a month; '' when it is not known."""
    key = (hexid or "").strip().lower() or (reg or "").strip().upper()
    if not key or key.startswith("~"):
        return ""
    cache = data_dir / "owners" / f"{N.slug(key)}.json"
    got = N.read_json(cache, None)
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < PHOTO_S:
        return str(got.get("owner") or "")
    data, err = N.get_json(ADSBDB_AIRCRAFT.format(key=urllib.parse.quote(key)), ua=ua, timeout=4)
    try:
        owner = " ".join(str(data["response"]["aircraft"].get("registered_owner") or "").split())
    except (KeyError, TypeError, AttributeError):
        owner = ""
    if data is not None or err not in ("unreachable", None):
        N.write(cache, json.dumps({"at": time.time(), "owner": owner}).encode())
    return owner


def photo_of(reg: str, data_dir: Path, ua: str) -> dict[str, str]:
    """{src, thumb, by, link, w, h} for the airframe's photograph on
    planespotters.net, kept a month; {} when it has none."""
    reg = (reg or "").strip().upper()
    if not reg:
        return {}
    cache = data_dir / "photos" / f"{N.slug(reg)}.json"
    got = N.read_json(cache, None)
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < PHOTO_S:
        return got.get("photo") or {}
    data, err = N.get_json(PLANESPOTTERS.format(reg=urllib.parse.quote(reg)), ua=ua, timeout=4)
    photo: dict[str, str] = {}
    try:
        p = data["photos"][0]
        photo = {
            "src": str(p["thumbnail_large"]["src"]), "thumb": str(p["thumbnail"]["src"]), "by": str(p.get("photographer") or ""),
            "link": str(p.get("link") or ""), "w": str(p["thumbnail_large"]["size"]["width"]), "h": str(p["thumbnail_large"]["size"]["height"]),
        }
    except (KeyError, TypeError, IndexError):
        photo = {}
    if data is not None:
        N.write(cache, json.dumps({"at": time.time(), "photo": photo}).encode())
    elif err == "auth":
        N.write(cache, json.dumps({"at": time.time() - PHOTO_S + 3600, "photo": {}, "why": "auth"}).encode())
    return photo


def type_photo(code: str, name: str, data_dir: Path, ua: str) -> dict[str, str]:
    """{src, by, lic, link, article} for a photograph of the type, any airframe of it: the
    lead picture of the type's Wikipedia article, credited from Commons, kept a month;
    {} when there is none. For an airframe planespotters.net has no photograph of."""
    code = (code or "").strip().upper()
    name = " ".join(str(name or "").split())
    if code in KIND_CODES or not (code or name) or name.lower() in ("", "aircraft"):
        return {}
    cache = data_dir / "types" / f"{N.slug(code or name)}.json"
    got = N.read_json(cache, None)
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < PHOTO_S:
        return got.get("photo") or {}
    article = TYPE_ARTICLES.get(code, "")
    q = (
        urllib.parse.urlencode({"titles": article})
        if article
        else urllib.parse.urlencode({"generator": "search", "gsrsearch": f"{name or code} aircraft", "gsrlimit": 1})
    )
    data, err = N.get_json(WIKIPEDIA.format(q=q), ua=ua, timeout=4)
    if data is None:
        if err != "unreachable":  # an answer that was not one: asked again in a day
            N.write(cache, json.dumps({"at": time.time() - PHOTO_S + 86400, "photo": {}}).encode())
        return {}
    pages = list(((data.get("query") or {}).get("pages") or {}).values()) if isinstance(data, dict) else []
    page = pages[0] if pages else {}
    file = str(page.get("pageimage") or "")
    photo: dict[str, str] = {}
    if file and file.lower().endswith(TYPE_PHOTO_EXT):
        info, err = N.get_json(COMMONS_FILE.format(title=urllib.parse.quote("File:" + file)), ua=ua, timeout=4)
        if info is None:
            return {}  # asked again next time
        try:
            ii = next(iter(info["query"]["pages"].values()))["imageinfo"][0]
            meta = ii.get("extmetadata") or {}
            by = re.sub(r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value") or ""))
            photo = {
                "src": str(ii.get("thumburl") or ii["url"]),
                # the author as Commons gives it, up to an address, a link or the camera notes
                "by": re.split(r"\s*(?:\[at\]|\S+@|https?://|;|\()", " ".join(html.unescape(by).split()))[0][:80].rstrip(" ,-")
                or "a Commons contributor",
                "lic": str((meta.get("LicenseShortName") or {}).get("value") or "open licence"),
                "link": str(ii.get("descriptionurl") or ""),
                "article": str(page.get("title") or ""),
            }
        except (KeyError, TypeError, IndexError, StopIteration, AttributeError):
            photo = {}
    N.write(cache, json.dumps({"at": time.time(), "photo": photo}).encode())
    return photo


def photo_src(photo: dict[str, str], data_dir: Path, ua: str, px: int, levels: str) -> str:
    """The photograph as a data URI, fetched once and resized for the page."""
    url = photo.get("src") or ""
    if not url:
        return ""
    raw = N.cached_get(data_dir, url, ua=ua)
    if not raw:
        return ""
    import hashlib

    cache = data_dir / "img" / (hashlib.sha1(url.encode()).hexdigest()[:20] + f"_{px}.jpg")
    return N.render(raw, px, None, cache, levels)


def logo_ref(iata: str, source: str, data_dir: Path) -> str:
    """The airline's mark as a data URI for the painter's second reference,
    composited on white so the model sees the mark as it is printed."""
    iata = (iata or "").strip().upper()
    if not iata or source not in LOGO_SOURCES:
        return ""
    raw = logo_bytes(iata, source, data_dir)
    if not raw:
        return ""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        out = io.BytesIO()
        bg.convert("RGB").save(out, "PNG")
        return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return ""


def logo_bytes(iata: str, source: str, data_dir: Path) -> bytes:
    """The mark as the service serves it, or b"" when it is missing or is the
    service's stock picture for an airline it does not know (what it serves
    for a code that is no airline's)."""
    iata = (iata or "").strip().upper()
    if not iata or source not in LOGO_SOURCES:
        return b""
    raw = N.cached_get(data_dir, LOGO_SOURCES[source].format(iata=iata))
    if not raw or len(raw) < 200:
        return b""
    import hashlib

    stamp = data_dir / "img" / f"{source}_placeholder.txt"
    known = stamp.read_text(encoding="utf-8").strip() if stamp.exists() else ""
    if not known:
        blank = N.cached_get(data_dir, LOGO_SOURCES[source].format(iata="ZZ")) or b""
        known = hashlib.sha1(blank).hexdigest() if blank else "-"
        N.write(stamp, known.encode())
    return b"" if hashlib.sha1(raw).hexdigest() == known else raw


def brand_of(iata: str, source: str, data_dir: Path) -> dict[str, str]:
    """The airline's colours, read off its mark: the most used saturated colour
    as the main one, the next distinct colour as the second, and the ink that
    reads on the main one. {} when the mark is missing or has no colour."""
    iata = (iata or "").strip().upper()
    if not iata or source not in LOGO_SOURCES:
        return {}
    url = LOGO_SOURCES[source].format(iata=iata)
    import hashlib

    cache = data_dir / "img" / (hashlib.sha1(url.encode()).hexdigest()[:20] + "_brand3.json")
    got = N.read_json(cache, None)
    if isinstance(got, dict):
        return {k: str(v) for k, v in got.items()}
    raw = logo_bytes(iata, source, data_dir)
    if not raw:
        return {}
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return {}
    im.thumbnail((240, 240))
    # a coarse histogram of the solid pixels: no edge blending, no near-white, no faint alpha
    bins: dict[tuple[int, int, int], list[int]] = {}
    for r, g, b, a in im.getdata():
        if a < 200 or (max(r, g, b) > 225 and max(r, g, b) - min(r, g, b) < 50):
            continue
        k = (r >> 4, g >> 4, b >> 4)
        acc = bins.setdefault(k, [0, 0, 0, 0])
        acc[0] += 1
        acc[1] += r
        acc[2] += g
        acc[3] += b
    if sum(v[0] for v in bins.values()) < 20:
        return {}
    def sat(c: tuple[int, int, int]) -> int:
        return max(c) - min(c)

    def far(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    # the bins gathered into tones: an anti-aliased edge spreads one colour over several bins
    tones: list[list[int]] = []
    for v in sorted(bins.values(), key=lambda v: -v[0]):
        c = (v[1] // v[0], v[2] // v[0], v[3] // v[0])
        for tone in tones:
            if far(c, (tone[1] // tone[0], tone[2] // tone[0], tone[3] // tone[0])) < 72:
                for i in range(4):
                    tone[i] += v[i]
                break
        else:
            tones.append(list(v))
    cols = [((v[1] // v[0], v[2] // v[0], v[3] // v[0]), v[0]) for v in tones]
    cols.sort(key=lambda cn: -cn[1])
    most = cols[0][1]
    coloured = [(c, n) for c, n in cols if sat(c) > 40 and n >= most * 0.12]
    primary = max(coloured, key=lambda cn: cn[1] * (1 + sat(cn[0]) / 128) * (1.6 - max(cn[0]) / 255))[0] if coloured else cols[0][0]
    rest = [c for c, n in cols if far(c, primary) > 90 and n >= most * 0.08]
    secondary = rest[0] if rest else tuple(max(0, v - 70) for v in primary)
    third = next((c for c in rest[1:] if far(c, secondary) > 90), None)

    def hexed(c: tuple[int, ...]) -> str:
        return "#%02x%02x%02x" % tuple(int(v) for v in c)

    def mix(c: tuple[int, int, int], to: int, k: float) -> tuple[int, ...]:
        return tuple(round(v + (to - v) * k) for v in c)

    def lum_of(c: tuple[int, ...]) -> float:
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    out = {
        "primary": hexed(primary), "secondary": hexed(secondary), "ink": "#000000" if lum_of(primary) > 150 else "#ffffff",
        "ink2": "#000000" if lum_of(secondary) > 150 else "#ffffff",
        "tint": hexed(mix(primary, 255, 0.86)), "shade": hexed(mix(primary, 0, 0.45)),
    }
    if third:
        out["third"] = hexed(third)
    N.write(cache, json.dumps(out).encode())
    return out


def logo_src(iata: str, source: str, data_dir: Path, levels: str) -> str:
    """The airline's mark as a data URI, fetched from the chosen service and
    kept; composited on white and thresholded for a panel without greys."""
    iata = (iata or "").strip().upper()
    if not iata or source not in LOGO_SOURCES:
        return ""
    url = LOGO_SOURCES[source].format(iata=iata)
    raw = logo_bytes(iata, source, data_dir)
    if not raw:
        return ""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return ""
    import hashlib

    cache = data_dir / "img" / (hashlib.sha1(url.encode()).hexdigest()[:20] + f"_logo_{levels}.png")
    if cache.exists():
        return "data:image/png;base64," + base64.b64encode(cache.read_bytes()).decode()
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return ""
    bbox = im.split()[3].point(lambda p: 255 if p > 24 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    if im.getbbox() is None:
        return ""
    im.thumbnail((360, 160), Image.Resampling.LANCZOS)
    if levels != "colour":
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        grey = bg.convert("L")
        if levels == "mono":
            grey = grey.point(lambda p: 255 if p > 150 else 0)
        alpha = grey.point(lambda p: 255 - p)
        im = Image.merge("LA", (Image.new("L", im.size, 0), alpha))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    N.write(cache, out.getvalue())
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


# ----------------------------------------------------------------------
# The sky as it is: a time of day and a weather, for a painted backdrop
# ----------------------------------------------------------------------
TIMES = {
    "night": "a night sky, dark and starry, the aircraft's navigation lights on and its cabin windows glowing",
    "dawn": "the sky at dawn, the first light low on the horizon and the aircraft lit from the side",
    "morning": "a bright morning sky, the light clean and from the side",
    "midday": "a high midday sky, the light from above",
    "afternoon": "a warm afternoon sky, the light long and from the side",
    "dusk": "a dusk sky just after sunset, the last light on the aircraft",
}
WEATHERS = {
    "clear": "clear",
    "partly": "with scattered fair-weather cumulus",
    "overcast": "flat and grey with overcast cloud",
    "fog": "soft and pale with fog",
    "rain": "grey with rain clouds and rain in the air",
    "snow": "pale with snow falling",
    "storm": "brooding with storm clouds and lightning far off",
}


def weather_bucket(code: int, cloud: float) -> str:
    if code in (95, 96, 99):
        return "storm"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (45, 48):
        return "fog"
    if code == 3 or cloud >= 80:
        return "overcast"
    if code in (1, 2) or cloud >= 25:
        return "partly"
    return "clear"


def time_bucket(mins: int, rise: int | None, set_: int | None) -> str:
    if rise is None or set_ is None:
        return "night" if mins < 6 * 60 or mins > 19 * 60 else "midday"
    if abs(mins - rise) <= 45:
        return "dawn"
    if abs(mins - set_) <= 45:
        return "dusk"
    if mins < rise or mins > set_:
        return "night"
    if mins < 11 * 60:
        return "morning"
    if mins < 14 * 60:
        return "midday"
    return "afternoon"


def _hhmm(text: str) -> int | None:
    t = str(text or "")[-5:]
    if len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit():
        return int(t[:2]) * 60 + int(t[3:])
    return None


def sky_now(lat: float, lon: float, mins: int, data_dir: Path, ua: str) -> tuple[str, str]:
    """(time bucket, weather bucket) at the place now, Open-Meteo kept WEATHER_S;
    clear midday or night when it cannot be reached."""
    cache = data_dir / "weather" / f"{lat:.2f}_{lon:.2f}.json"
    got = N.read_json(cache, None)
    if not (isinstance(got, dict) and time.time() - float(got.get("at") or 0) < WEATHER_S):
        data, _err = N.get_json(OPEN_METEO.format(lat=lat, lon=lon), ua=ua, timeout=4)
        if isinstance(data, dict):
            got = {"at": time.time(), "data": data}
            N.write(cache, json.dumps(got).encode())
    data = (got or {}).get("data") if isinstance(got, dict) else None
    rise = set_ = None
    code, cloud = 0, 0.0
    if isinstance(data, dict):
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        with contextlib.suppress(TypeError, ValueError, IndexError):
            code = int(cur.get("weather_code") or 0)
            cloud = float(cur.get("cloud_cover") or 0)
            rise = _hhmm((daily.get("sunrise") or [""])[0])
            set_ = _hhmm((daily.get("sunset") or [""])[0])
    return time_bucket(mins, rise, set_), weather_bucket(code, cloud)


def sky_words(tod: str, wx: str) -> str:
    return f"{TIMES.get(tod, TIMES['midday'])}, {WEATHERS.get(wx, 'clear')}, in the same style"
