"""Hentning og normalisering af artikler fra RSS/Atom-feeds.

Til forskel fra 2025-udgaven:
  - feeds slås sammen som en flad liste, ikke parvist pr. position,
  - artikler dedupliceres på URL og på næsten-ens overskrifter,
  - hver kilde har et loft, så en arkivfeed med 1000 poster ikke drukner resten,
  - en fejlende feed stopper ikke kørslen, men registreres og vises på sitet.

Bemærk: RSS er en strøm, ikke et arkiv. De fleste feeds rummer kun de sidste
1-2 uger. Derfor høster harvest.py løbende ind i en pulje pr. måned, og selve
vurderingen læser fra puljen. Se harvest.py.
"""

from __future__ import annotations

import calendar
import hashlib
import logging
import re
import socket
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

import feedparser

from .config import Config, Source

log = logging.getLogger(__name__)

_WS = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z0-9æøå]+")

# Overskrifter der deler mindst denne andel af deres ord regnes som samme historie.
_DUP_TAERSKEL = 0.8

# Rækkefølge for beskæring: de mindst troværdige kilder ryger først.
TIER_PRIORITET = {
    "haendelser": 0,
    "regulering": 1,
    "analyse": 2,
    "presse": 3,
    "dansk": 4,
    "forskning": 5,
    "leverandoer": 6,
    "kommentar": 7,
    "community": 8,
}


@dataclass
class Article:
    id: str
    titel: str
    resume: str
    link: str
    kilde: str
    tier: str
    dato: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(
            id=d["id"],
            titel=d["titel"],
            resume=d.get("resume", ""),
            link=d.get("link", ""),
            kilde=d["kilde"],
            tier=d.get("tier", "presse"),
            dato=d.get("dato"),
        )


@dataclass
class FeedStatus:
    navn: str
    url: str
    ok: bool
    antal_hentet: int = 0
    antal_i_perioden: int = 0
    fejl: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Collection:
    """Det udvalg af artikler der faktisk sendes til modellen."""

    artikler: list[Article]
    status: list[FeedStatus]
    periode_start: date
    periode_slut: date
    kilde_type: str = "live"  # "pulje" når materialet kommer fra den løbende høst

    @property
    def antal_artikler(self) -> int:
        return len(self.artikler)

    @property
    def antal_kilder(self) -> int:
        return len({a.kilde for a in self.artikler})


# --- Hjælpefunktioner --------------------------------------------------------


def month_window(maaned: str, naade_dage: int = 0) -> tuple[date, date]:
    """(start, slut) for 'YYYY-MM', med valgfrie nådedage før månedens første."""
    aar, md = (int(x) for x in maaned.split("-"))
    sidste = calendar.monthrange(aar, md)[1]
    return date(aar, md, 1) - timedelta(days=naade_dage), date(aar, md, sidste)


def maaned_for(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _rens(tekst: str | None, maks: int = 600) -> str:
    if not tekst:
        return ""
    ren = _WS.sub(" ", _TAGS.sub(" ", tekst)).strip()
    if len(ren) <= maks:
        return ren
    return ren[:maks].rsplit(" ", 1)[0] + "…"


def _entry_dato(entry) -> date | None:
    for felt in ("published_parsed", "updated_parsed", "created_parsed"):
        v = entry.get(felt)
        if not v:
            continue
        try:
            return datetime(*v[:6], tzinfo=timezone.utc).date()
        except (TypeError, ValueError):
            continue
    return None


def _entry_resume(entry) -> str:
    """Find den bedste tilgængelige brødtekst i en feed-post."""
    indhold = entry.get("content")
    if indhold:
        for blok in indhold:
            vaerdi = blok.get("value") if hasattr(blok, "get") else None
            if vaerdi:
                return _rens(vaerdi)
    return _rens(entry.get("summary") or entry.get("description"))


def _article_id(link: str, titel: str) -> str:
    return hashlib.sha1((link or titel).strip().lower().encode("utf-8")).hexdigest()[:10]


def titel_ord(titel: str) -> frozenset[str]:
    return frozenset(_WORD.findall(titel.lower()))


def er_dublet(ord_ny: frozenset[str], sete: list[frozenset[str]]) -> bool:
    """Sand hvis overskriften i praksis er den samme historie som en allerede set."""
    if len(ord_ny) < 3:
        return False
    for ord_gl in sete:
        if not ord_gl:
            continue
        mindste = min(len(ord_ny), len(ord_gl))
        if mindste and len(ord_ny & ord_gl) / mindste >= _DUP_TAERSKEL:
            return True
    return False


# --- Hentning ----------------------------------------------------------------


def hent_feed(kilde: Source, cfg: Config) -> tuple[list[Article], FeedStatus]:
    """Hent én feed og normalisér alle dens poster. Ingen datofiltrering her."""
    socket.setdefaulttimeout(cfg.timeout)
    try:
        parsed = feedparser.parse(
            kilde.url,
            agent=cfg.user_agent,
            request_headers={"Accept": "application/rss+xml, application/atom+xml, */*"},
        )
    except Exception as exc:  # feedparser er robust, men netværket er ikke
        return [], FeedStatus(kilde.navn, kilde.url, ok=False, fejl=f"{type(exc).__name__}: {exc}")

    status_kode = getattr(parsed, "status", None)
    if status_kode and status_kode >= 400:
        return [], FeedStatus(kilde.navn, kilde.url, ok=False, fejl=f"HTTP {status_kode}")

    poster = list(parsed.entries)
    if not poster:
        grund = getattr(parsed, "bozo_exception", None)
        return [], FeedStatus(
            kilde.navn,
            kilde.url,
            ok=False,
            fejl=f"ingen poster ({grund})" if grund else "ingen poster",
        )

    artikler: list[Article] = []
    for entry in poster:
        titel = _rens(entry.get("title"), maks=300)
        if not titel:
            continue
        link = (entry.get("link") or "").strip()
        d = _entry_dato(entry)
        artikler.append(
            Article(
                id=_article_id(link, titel),
                titel=titel,
                resume=_entry_resume(entry),
                link=link,
                kilde=kilde.navn,
                tier=kilde.tier,
                dato=d.isoformat() if d else None,
            )
        )

    return artikler, FeedStatus(kilde.navn, kilde.url, ok=True, antal_hentet=len(artikler))


def hent_alle(cfg: Config) -> tuple[list[Article], list[FeedStatus]]:
    """Hent samtlige feeds. Fejl på én feed stopper ikke de øvrige."""
    alle: list[Article] = []
    status: list[FeedStatus] = []
    for kilde in cfg.kilder:
        artikler, s = hent_feed(kilde, cfg)
        if not s.ok:
            log.warning("Feed fejlede: %s (%s)", kilde.navn, s.fejl)
        else:
            log.info("%-28s %4d poster", kilde.navn, len(artikler))
        alle.extend(artikler)
        status.append(s)
    return alle, status


# --- Udvælgelse --------------------------------------------------------------


def udvaelg(
    cfg: Config,
    artikler: list[Article],
    maaned: str,
    status: list[FeedStatus],
    kilde_type: str = "live",
) -> Collection:
    """Filtrér til måneden, fjern dubletter, håndhæv lofter pr. kilde og i alt."""
    start, slut = month_window(maaned, cfg.naade_dage)
    lofter = {k.navn: k.maks for k in cfg.kilder}
    brugt: dict[str, int] = {}
    sete_ids: set[str] = set()
    sete_titler: list[frozenset[str]] = []
    valgt: list[Article] = []

    # De mest troværdige kilder får først lov at fylde deres kvote.
    ordnet = sorted(
        artikler,
        key=lambda a: (TIER_PRIORITET.get(a.tier, 9), a.dato or "9999", a.titel),
    )

    for a in ordnet:
        if a.dato is not None:
            d = date.fromisoformat(a.dato)
            if not (start <= d <= slut):
                continue
        if a.id in sete_ids:
            continue
        if brugt.get(a.kilde, 0) >= lofter.get(a.kilde, 10):
            continue
        ord_ny = titel_ord(a.titel)
        if er_dublet(ord_ny, sete_titler):
            continue

        sete_ids.add(a.id)
        sete_titler.append(ord_ny)
        brugt[a.kilde] = brugt.get(a.kilde, 0) + 1
        valgt.append(a)

    if len(valgt) > cfg.maks_artikler_i_alt:
        log.info("Beskærer %d artikler til %d", len(valgt), cfg.maks_artikler_i_alt)
        valgt = valgt[: cfg.maks_artikler_i_alt]

    for s in status:
        s.antal_i_perioden = brugt.get(s.navn, 0)

    # Nyeste først, så modellen læser materialet i en genkendelig orden.
    valgt.sort(key=lambda a: (a.dato or "0000-00-00"), reverse=True)

    return Collection(
        artikler=valgt,
        status=status,
        periode_start=start,
        periode_slut=slut,
        kilde_type=kilde_type,
    )


def collect(cfg: Config, maaned: str) -> Collection:
    """Hent alle feeds live og udvælg månedens artikler.

    Bruges til enkeltstående kørsler og som nødløsning. Til den planlagte
    månedsvurdering bør puljen fra harvest.py bruges i stedet, fordi feeds
    kun rummer de sidste par uger.
    """
    log.info("Live-indsamling for %s", maaned)
    artikler, status = hent_alle(cfg)
    return udvaelg(cfg, artikler, maaned, status, kilde_type="live")
