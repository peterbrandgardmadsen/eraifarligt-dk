"""Løbende høst af artikler til en pulje pr. måned.

RSS-feeds er en strøm, ikke et arkiv. De fleste af projektets feeds rummer kun
de sidste 10-20 poster, altså typisk 1-2 uger. Hvis vurderingen for juli først
hentede feeds den 1. august, ville halvdelen af juli allerede være rullet ud af
feedet — og materialet ville systematisk overrepræsentere månedens sidste uger.
Præcis den fejl gjorde 2025-udgaven, hvor "antal kilder" derfor endte på 7.

Derfor kører høsten dagligt og lægger nye artikler i
``data/raw/YYYY-MM.jsonl``. Månedsvurderingen læser fra puljen, ikke fra feeds.
Høsten kalder ingen model og kræver ingen API-nøgle.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .collect import Article, FeedStatus, Collection, hent_alle, maaned_for, udvaelg
from .config import Config, ROOT

log = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"


@dataclass
class HarvestResultat:
    nye: int
    set_i_alt: int
    maaneder: dict[str, int]
    status: list[FeedStatus]

    @property
    def fejlede(self) -> list[FeedStatus]:
        return [s for s in self.status if not s.ok]


def pulje_sti(maaned: str, raw_dir: Path | None = None) -> Path:
    return (raw_dir or RAW_DIR) / f"{maaned}.jsonl"


def _eksisterende_ider(sti: Path) -> set[str]:
    if not sti.exists():
        return set()
    ider = set()
    with sti.open("r", encoding="utf-8") as f:
        for linje in f:
            linje = linje.strip()
            if not linje:
                continue
            try:
                ider.add(json.loads(linje)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ider


def harvest(cfg: Config, raw_dir: Path | None = None, i_dag: date | None = None) -> HarvestResultat:
    """Hent alle feeds og læg nye artikler i puljen for deres respektive måned."""
    raw_dir = raw_dir or RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    i_dag = i_dag or datetime.now(timezone.utc).date()

    artikler, status = hent_alle(cfg)

    # Grupper efter måned. Artikler uden dato henføres til i dag, hvilket er
    # rimeligt når høsten kører dagligt.
    efter_maaned: dict[str, list[Article]] = {}
    for a in artikler:
        d = date.fromisoformat(a.dato) if a.dato else i_dag
        # Artikler mere end 60 dage gamle er arkivstøj fra store feeds.
        if (i_dag - d).days > 60 or d > i_dag:
            continue
        efter_maaned.setdefault(maaned_for(d), []).append(a)

    nye_i_alt = 0
    nye_pr_maaned: dict[str, int] = {}

    for maaned, poster in sorted(efter_maaned.items()):
        sti = pulje_sti(maaned, raw_dir)
        kendte = _eksisterende_ider(sti)
        nye: list[Article] = []
        for a in poster:
            if a.id in kendte:
                continue
            kendte.add(a.id)
            nye.append(a)
        if not nye:
            continue
        with sti.open("a", encoding="utf-8") as f:
            for a in nye:
                post = a.to_dict()
                post["hoestet"] = i_dag.isoformat()
                f.write(json.dumps(post, ensure_ascii=False) + "\n")
        nye_i_alt += len(nye)
        nye_pr_maaned[maaned] = len(nye)
        log.info("%s: +%d nye artikler (pulje nu %d)", maaned, len(nye), len(kendte))

    return HarvestResultat(
        nye=nye_i_alt, set_i_alt=len(artikler), maaneder=nye_pr_maaned, status=status
    )


def laes_pulje(maaned: str, raw_dir: Path | None = None) -> list[Article]:
    sti = pulje_sti(maaned, raw_dir)
    if not sti.exists():
        return []
    artikler = []
    with sti.open("r", encoding="utf-8") as f:
        for linje in f:
            linje = linje.strip()
            if not linje:
                continue
            try:
                artikler.append(Article.from_dict(json.loads(linje)))
            except (json.JSONDecodeError, KeyError) as exc:
                log.warning("Sprang ugyldig linje over i %s: %s", sti, exc)
    return artikler


def pulje_status(cfg: Config, artikler: list[Article]) -> list[FeedStatus]:
    """Rekonstruér en kildestatus ud fra hvad puljen faktisk indeholder.

    En kilde uden en eneste artikel i puljen har enten intet udgivet eller været
    utilgængelig hele måneden. Begge dele er værd at vise på sitet.
    """
    tal: dict[str, int] = {}
    for a in artikler:
        tal[a.kilde] = tal.get(a.kilde, 0) + 1
    return [
        FeedStatus(
            navn=k.navn,
            url=k.url,
            ok=tal.get(k.navn, 0) > 0,
            antal_hentet=tal.get(k.navn, 0),
            fejl=None if tal.get(k.navn, 0) else "ingen artikler i puljen denne måned",
        )
        for k in cfg.kilder
    ]


def samling_fra_pulje(cfg: Config, maaned: str, raw_dir: Path | None = None) -> Collection:
    """Byg månedens udvalg ud fra den løbende høst."""
    artikler = laes_pulje(maaned, raw_dir)
    log.info("Pulje for %s: %d artikler", maaned, len(artikler))
    return udvaelg(cfg, artikler, maaned, pulje_status(cfg, artikler), kilde_type="pulje")
