"""Deterministisk beregning af faresindeks og bedømmelse, samt lagring på disk.

Intet i denne fil kalder en model. Givet de samme dimensionsscorer og den samme
konfiguration falder resultatet altid ud på samme måde, og en læser kan regne
efter i hånden.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .collect import Collection
from .config import Config, DATA_DIR
from .score import ScoreResultat

log = logging.getLogger(__name__)

SKEMA_VERSION = 2


def beregn_indeks(cfg: Config, scorer: dict[str, int]) -> float:
    """Vægtet gennemsnit af dimensionsscorerne. Manglende dimensioner udelades."""
    taeller = 0.0
    naevner = 0.0
    for dim in cfg.dimensioner:
        if dim.id not in scorer:
            continue
        taeller += dim.weight * scorer[dim.id]
        naevner += dim.weight
    if naevner == 0:
        raise RuntimeError("Ingen gyldige dimensionsscorer at beregne indeks ud fra")
    return round(taeller / naevner, 1)


def byg_maaned(
    cfg: Config,
    maaned: str,
    samling: Collection,
    resultat: ScoreResultat,
    historik: list[dict],
) -> dict:
    """Saml alt om én måned i den JSON-struktur der lagres og renderes."""
    vurdering = resultat.vurdering
    scorer = {dv.dimension_id: dv.score for dv in vurdering.dimensioner}
    indeks = beregn_indeks(cfg, scorer)
    baand = cfg.bedoem(indeks)

    forrige = historik[-1] if historik else None
    aendring = round(indeks - forrige["indeks"], 1) if forrige else None

    artikler_efter_id = {a.id: a for a in samling.artikler}

    dimensioner = []
    for dim in cfg.dimensioner:
        dv = next((d for d in vurdering.dimensioner if d.dimension_id == dim.id), None)
        if dv is None:
            continue
        dimensioner.append(
            {
                "id": dim.id,
                "label": dim.label,
                "vaegt": dim.weight,
                "score": dv.score,
                "tone": cfg.bedoem(dv.score).tone,
                "begrundelse": dv.begrundelse,
                "ubegrundet": not dv.artikel_ider,
                "kilder": [
                    {
                        "id": aid,
                        "titel": artikler_efter_id[aid].titel,
                        "link": artikler_efter_id[aid].link,
                        "kilde": artikler_efter_id[aid].kilde,
                    }
                    for aid in dv.artikel_ider
                    if aid in artikler_efter_id
                ],
            }
        )

    haendelser = []
    for h in vurdering.vigtigste_haendelser:
        art = artikler_efter_id.get(h.artikel_id)
        if art is None:
            continue
        haendelser.append(
            {
                "overskrift": h.overskrift,
                "betydning": h.betydning,
                "link": art.link,
                "kilde": art.kilde,
            }
        )

    return {
        "skema_version": SKEMA_VERSION,
        "maaned": maaned,
        "genereret": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "indeks": indeks,
        "bedoemmelse": baand.label,
        "baand_id": baand.id,
        "tone": baand.tone,
        "aendring": aendring,
        "sammenfatning": vurdering.sammenfatning,
        "modvaegt": vurdering.modvaegt,
        "dimensioner": dimensioner,
        "vigtigste_haendelser": haendelser,
        "grundlag": {
            "antal_artikler": samling.antal_artikler,
            "antal_kilder": samling.antal_kilder,
            "periode_start": samling.periode_start.isoformat(),
            "periode_slut": samling.periode_slut.isoformat(),
            "artikel_ider": [a.id for a in samling.artikler],
        },
        "kildestatus": [s.to_dict() for s in samling.status],
        "koersel": {
            "model": resultat.model,
            "prompt_hash": resultat.prompt_hash,
            "input_tokens": resultat.input_tokens,
            "output_tokens": resultat.output_tokens,
            "advarsler": resultat.advarsler,
        },
    }


# --- Lagring -----------------------------------------------------------------


def sti_for(maaned: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / f"{maaned}.json"


def gem(maaned_data: dict, data_dir: Path | None = None) -> Path:
    sti = sti_for(maaned_data["maaned"], data_dir)
    sti.parent.mkdir(parents=True, exist_ok=True)
    sti.write_text(
        json.dumps(maaned_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("Gemte %s", sti)
    return sti


def indlaes_alle(data_dir: Path | None = None) -> list[dict]:
    """Alle gemte måneder, sorteret kronologisk."""
    mappe = data_dir or DATA_DIR
    if not mappe.exists():
        return []
    maaneder = []
    for sti in sorted(mappe.glob("*.json")):
        try:
            maaneder.append(json.loads(sti.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            log.error("Kunne ikke læse %s: %s", sti, exc)
    return sorted(maaneder, key=lambda m: m["maaned"])


def historik_foer(maaned: str, data_dir: Path | None = None) -> list[dict]:
    """Kompakt historik til kalibrering af prompten. Kun måneder før den angivne."""
    return [
        {"maaned": m["maaned"], "indeks": m["indeks"], "bedoemmelse": m["bedoemmelse"]}
        for m in indlaes_alle(data_dir)
        if m["maaned"] < maaned
    ]
