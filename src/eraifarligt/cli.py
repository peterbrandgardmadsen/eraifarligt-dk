"""Kommandolinje til eraifarligt.dk.

    python -m eraifarligt harvest            # daglig høst af feeds til puljen
    python -m eraifarligt run                # månedsvurdering af forrige måned
    python -m eraifarligt run --maaned 2026-07
    python -m eraifarligt status             # hvad ligger der i puljen
    python -m eraifarligt build              # byg kun sitet af eksisterende data
    python -m eraifarligt demo --ud tmp/data # opdigtet måned, til at se designet
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from .collect import collect
from .config import DATA_DIR, load_config
from .harvest import RAW_DIR, harvest, laes_pulje, pulje_sti, samling_fra_pulje
from .render import dansk_maaned, render
from .verdict import byg_maaned, gem, historik_foer, indlaes_alle

log = logging.getLogger("eraifarligt")

# Under så mange artikler i puljen er materialet for tyndt til en troværdig
# månedsvurdering. Så falder kørslen tilbage til en live-hentning og siger det.
MIN_ARTIKLER = 40


def forrige_maaned(i_dag: date | None = None) -> str:
    i_dag = i_dag or date.today()
    return f"{i_dag.year - 1}-12" if i_dag.month == 1 else f"{i_dag.year}-{i_dag.month - 1:02d}"


def _opsaet_log(niveau: str) -> None:
    logging.basicConfig(
        level=getattr(logging, niveau.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def kommando_harvest(args: argparse.Namespace) -> int:
    cfg = load_config()
    res = harvest(cfg, Path(args.raw) if args.raw else None)

    print(f"Hentede {res.set_i_alt} poster fra {len(res.status)} feeds")
    print(f"Nye artikler i puljen: {res.nye}")
    for maaned, antal in sorted(res.maaneder.items()):
        print(f"  {maaned}: +{antal}")
    if res.fejlede:
        print(f"\n{len(res.fejlede)} feed(s) fejlede:")
        for s in res.fejlede:
            print(f"  {s.navn}: {s.fejl}")

    # En enkelt død feed må ikke vælte den daglige høst, men hvis alle fejler
    # er der noget grundlæggende galt, og så skal kørslen være rød.
    if len(res.fejlede) == len(res.status):
        log.error("Samtlige feeds fejlede")
        return 1
    return 0


def kommando_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    raw = Path(args.raw) if args.raw else RAW_DIR
    if not raw.exists():
        print(f"Ingen pulje endnu ({raw})")
        return 0

    print(f"Pulje i {raw}:\n")
    for sti in sorted(raw.glob("*.jsonl")):
        maaned = sti.stem
        artikler = laes_pulje(maaned, raw)
        kilder = len({a.kilde for a in artikler})
        udvalg = samling_fra_pulje(cfg, maaned, raw)
        vurderet = "vurderet" if (DATA_DIR / f"{maaned}.json").exists() else "ikke vurderet"
        print(
            f"  {maaned}  {len(artikler):4d} høstet · {kilder:2d} kilder"
            f" · {udvalg.antal_artikler:3d} udvalgt · {vurderet}"
        )
    return 0


def kommando_run(args: argparse.Namespace) -> int:
    from .score import score  # importeres sent, så resten virker uden API-nøgle

    cfg = load_config()
    maaned = args.maaned or forrige_maaned()
    raw = Path(args.raw) if args.raw else None

    sti = DATA_DIR / f"{maaned}.json"
    if sti.exists() and not args.overskriv:
        log.error("%s findes allerede. Brug --overskriv for at køre måneden om.", sti)
        return 1

    samling = samling_fra_pulje(cfg, maaned, raw)
    if samling.antal_artikler < MIN_ARTIKLER:
        log.warning(
            "Kun %d artikler i puljen for %s (mindst %d ønsket, %s). Falder tilbage til live-hentning.",
            samling.antal_artikler,
            maaned,
            MIN_ARTIKLER,
            pulje_sti(maaned, raw),
        )
        samling = collect(cfg, maaned)

    if samling.antal_artikler == 0:
        log.error("Intet materiale for %s - afbryder uden at kalde modellen", maaned)
        return 1
    if samling.kilde_type == "live":
        log.warning(
            "Vurderingen bygger på en live-hentning og dækker derfor mest månedens "
            "sidste uger. Kør 'harvest' dagligt for fuld dækning."
        )

    historik = historik_foer(maaned)
    resultat = score(cfg, samling, maaned, historik)
    maaned_data = byg_maaned(cfg, maaned, samling, resultat, historik)
    gem(maaned_data)

    log.info(
        "%s: %s (indeks %s) · %d artikler · %d/%d tokens",
        maaned,
        maaned_data["bedoemmelse"],
        maaned_data["indeks"],
        samling.antal_artikler,
        resultat.input_tokens,
        resultat.output_tokens,
    )

    if not args.spring_build_over:
        render(cfg, indlaes_alle())
    return 0


def kommando_collect(args: argparse.Namespace) -> int:
    """Live-hentning uden modelkald. Til fejlsøgning og til at se prompten."""
    cfg = load_config()
    maaned = args.maaned or forrige_maaned()
    raw = Path(args.raw) if args.raw else None

    samling = samling_fra_pulje(cfg, maaned, raw) if args.pulje else collect(cfg, maaned)
    fejlede = [s for s in samling.status if not s.ok]

    print(f"\nMåned:    {maaned} ({dansk_maaned(maaned)})")
    print(f"Kilde:    {samling.kilde_type}")
    print(f"Vindue:   {samling.periode_start} .. {samling.periode_slut}")
    print(f"Artikler: {samling.antal_artikler} fra {samling.antal_kilder} kilder")
    print(f"Feeds:    {len(samling.status) - len(fejlede)} ok, {len(fejlede)} uden bidrag")
    for s in fejlede:
        print(f"  {s.navn}: {s.fejl}")

    if args.udskriv_prompt:
        from .score import SYSTEM, build_prompt

        prompt = build_prompt(cfg, samling, maaned, historik_foer(maaned))
        print("\n" + "=" * 70 + "\n" + SYSTEM + "\n" + "=" * 70)
        print(prompt)
        print("=" * 70)
        print(f"Promptlængde: {len(prompt)} tegn (~{len(prompt) // 4} tokens)")

    return 0 if samling.artikler else 1


def kommando_build(args: argparse.Namespace) -> int:
    cfg = load_config()
    maaneder = indlaes_alle()
    if not maaneder:
        log.error("Ingen månedsdata i %s", DATA_DIR)
        return 1
    ud = render(cfg, maaneder)
    print(f"Byggede {len(maaneder)} måned(er) til {ud}")
    return 0


def kommando_demo(args: argparse.Namespace) -> int:
    """Skriv en opdigtet måned, så designet kan ses uden at bruge API-kvote."""
    cfg = load_config()
    maaned = args.maaned or forrige_maaned()
    mappe = Path(args.ud) if args.ud else DATA_DIR
    gem(_demo_data(cfg, maaned), mappe)
    render(cfg, indlaes_alle(mappe))
    print(f"Demo-måned {maaned} skrevet til {mappe} og site bygget.")
    print("BEMÆRK: indholdet er opdigtet og må ikke udgives.")
    return 0


def _demo_data(cfg, maaned: str) -> dict:
    from .verdict import beregn_indeks

    demoscorer = {
        "skader": 58, "misinformation": 61, "arbejdsmarked": 47,
        "kapabilitet": 66, "regulering": 52, "koncentration": 71,
    }
    scorer = {d.id: demoscorer.get(d.id, 50) for d in cfg.dimensioner}
    indeks = beregn_indeks(cfg, scorer)
    baand = cfg.bedoem(indeks)
    return {
        "skema_version": 2,
        "maaned": maaned,
        "genereret": f"{date.today().isoformat()}T08:00:00+00:00",
        "indeks": indeks,
        "bedoemmelse": baand.label,
        "baand_id": baand.id,
        "tone": baand.tone,
        "aendring": None,
        "sammenfatning": (
            "DEMODATA. Denne tekst er opdigtet og beskriver ikke en virkelig måned. "
            "Den findes udelukkende for at vise hvordan siden ser ud, før den første "
            "rigtige kørsel har fundet sted."
        ),
        "modvaegt": "DEMODATA. Her ville det stærkeste modargument stå.",
        "dimensioner": [
            {
                "id": d.id,
                "label": d.label,
                "vaegt": d.weight,
                "score": scorer[d.id],
                "tone": cfg.bedoem(scorer[d.id]).tone,
                "begrundelse": "DEMODATA. Her ville begrundelsen stå, med henvisning til artikler.",
                "ubegrundet": False,
                "kilder": [
                    {"id": "0" * 10, "titel": "Eksempelartikel", "link": "#", "kilde": "Demokilde"}
                ],
            }
            for d in cfg.dimensioner
        ],
        "vigtigste_haendelser": [
            {
                "overskrift": "DEMODATA: en begivenhed",
                "betydning": "Her ville betydningen stå.",
                "link": "#",
                "kilde": "Demokilde",
            }
        ],
        "grundlag": {
            "antal_artikler": 0,
            "antal_kilder": 0,
            "periode_start": f"{maaned}-01",
            "periode_slut": f"{maaned}-28",
            "artikel_ider": [],
        },
        "kildestatus": [
            {"navn": k.navn, "url": k.url, "ok": True, "antal_hentet": 0,
             "antal_i_perioden": 0, "fejl": None}
            for k in cfg.kilder
        ],
        "koersel": {
            "model": "demo", "prompt_hash": "demo", "input_tokens": 0, "output_tokens": 0,
            "advarsler": ["Dette er demodata, ikke en rigtig vurdering."],
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eraifarligt", description="Månedlig AI-risikovurdering")
    p.add_argument("--log", default="info", choices=["debug", "info", "warning", "error"])
    p.add_argument("--raw", help="Anden puljemappe end data/raw")
    sub = p.add_subparsers(dest="kommando", required=True)

    h = sub.add_parser("harvest", help="Daglig høst af feeds til puljen")
    h.set_defaults(func=kommando_harvest)

    s = sub.add_parser("status", help="Vis hvad puljen indeholder")
    s.set_defaults(func=kommando_status)

    r = sub.add_parser("run", help="Månedsvurdering: udvælg, vurdér, gem, byg")
    r.add_argument("--maaned", help="YYYY-MM (standard: forrige måned)")
    r.add_argument("--overskriv", action="store_true", help="Kør en måned om der allerede findes")
    r.add_argument("--spring-build-over", action="store_true", help="Gem data uden at bygge sitet")
    r.set_defaults(func=kommando_run)

    c = sub.add_parser("collect", help="Hent materiale uden at kalde modellen")
    c.add_argument("--maaned", help="YYYY-MM (standard: forrige måned)")
    c.add_argument("--pulje", action="store_true", help="Læs fra puljen i stedet for at hente live")
    c.add_argument("--udskriv-prompt", action="store_true", help="Vis prompten der ville blive sendt")
    c.set_defaults(func=kommando_collect)

    b = sub.add_parser("build", help="Byg sitet ud fra eksisterende månedsfiler")
    b.set_defaults(func=kommando_build)

    d = sub.add_parser("demo", help="Skriv en opdigtet måned og byg sitet")
    d.add_argument("--maaned", help="YYYY-MM")
    d.add_argument("--ud", help="Anden datamappe, så rigtige data ikke blandes")
    d.set_defaults(func=kommando_demo)

    args = p.parse_args(argv)
    _opsaet_log(args.log)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
