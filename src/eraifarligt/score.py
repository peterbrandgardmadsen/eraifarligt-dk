"""Ét struktureret Claude-kald der scorer månedens artikler pr. dimension.

Modellen scorer KUN dimensionerne og skriver begrundelser. Den beregner ikke
faresindekset, vælger ikke bedømmelsesordet og tæller ikke kilder - alt det
sker deterministisk i verdict.py, så resultatet kan efterprøves.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel, Field

from .collect import Article, Collection
from .config import Config

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 16000


class DimensionVurdering(BaseModel):
    """Modellens vurdering af én dimension."""

    dimension_id: str = Field(description="Dimensionens id, præcis som opgivet i opgaven.")
    score: int = Field(ge=0, le=100, description="0-100 hvor højere betyder mere farligt.")
    begrundelse: str = Field(
        description="2-4 sætninger på dansk der begrunder scoren med henvisning til konkrete artikler."
    )
    artikel_ider: list[str] = Field(
        description="Id'er på de artikler der bærer vurderingen. Mindst 1, højst 6."
    )


class Haendelse(BaseModel):
    """En enkeltbegivenhed der prægede måneden."""

    overskrift: str = Field(description="Kort dansk overskrift, højst 90 tegn.")
    artikel_id: str = Field(description="Id på den artikel begivenheden stammer fra.")
    betydning: str = Field(description="Én sætning på dansk om hvorfor den betyder noget.")


class Vurdering(BaseModel):
    """Hele modellens output for en måned."""

    dimensioner: list[DimensionVurdering]
    sammenfatning: str = Field(
        description="400-700 tegn sammenhængende dansk prosa der forklarer månedens samlede billede."
    )
    vigtigste_haendelser: list[Haendelse] = Field(
        description="3-5 begivenheder der prægede måneden mest."
    )
    modvaegt: str = Field(
        description="1-3 sætninger på dansk om det stærkeste argument IMOD månedens samlede vurdering."
    )


@dataclass
class ScoreResultat:
    vurdering: Vurdering
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    advarsler: list[str]


SYSTEM = """Du er analytiker med speciale i teknologirisiko, og du skriver til et dansk offentligt publikum på eraifarligt.dk.

Din opgave er at score en given måned på en række faste risikodimensioner ud fra de artikler du får forelagt. Du skal:

1. Kun bruge de forelagte artikler. Du må ikke trække på begivenheder der ikke fremgår af materialet, og du må ikke opfinde kilder.
2. Score hver dimension fra 0 til 100, hvor 0 betyder "ingen tegn på fare i denne måned" og 100 betyder "akut, udbredt og dokumenteret fare". En helt almindelig måned uden dramatiske begivenheder ligger typisk mellem 30 og 55. Brug hele skalaen: hvis materialet er kedeligt, så giv lave tal.
3. Vægte kilderne efter deres troværdighed. Materiale fra AI-virksomhedernes egne blogs er markedsføring. Forumopslag er stemning, ikke bevis. En dokumenteret hændelse vejer tungere end en bekymret kommentar.
4. Begrunde hver score med henvisning til konkrete artikel-id'er fra materialet. Et id du ikke har fået udleveret er en fejl.
5. Skrive alt på klart, korrekt dansk uden engelske vendinger.

Vær nøgtern. Undgå både teknologioptimisme og undergangsretorik. Du beregner ikke selv noget samlet indeks og vælger ikke en samlet bedømmelse - det gør systemet bagefter ud fra dine scorer."""


def _dimension_afsnit(cfg: Config) -> str:
    linjer = []
    for d in cfg.dimensioner:
        linjer.append(f'- id "{d.id}" — {d.label} (vægt {d.weight})\n  {d.beskrivelse}')
    return "\n".join(linjer)


def _kilde_afsnit(cfg: Config, artikler: list[Article]) -> str:
    brugte = {a.tier for a in artikler}
    return "\n".join(
        f"- {tier}: {beskrivelse}"
        for tier, beskrivelse in cfg.tier_beskrivelser.items()
        if tier in brugte
    )


def _artikel_afsnit(artikler: list[Article]) -> str:
    blokke = []
    for a in artikler:
        dato = a.dato or "ukendt dato"
        resume = a.resume or "(intet resumé)"
        blokke.append(f"[{a.id}] {a.titel}\n  kilde: {a.kilde} ({a.tier}) · {dato}\n  {resume}")
    return "\n\n".join(blokke)


def _historik_afsnit(historik: list[dict]) -> str:
    if not historik:
        return "Ingen tidligere målinger. Dette er den første måned i den nye serie."
    linjer = [f"- {h['maaned']}: indeks {h['indeks']} ({h['bedoemmelse']})" for h in historik[-12:]]
    return (
        "Tidligere måneder, udelukkende til kalibrering af niveauet. "
        "Lad dem ikke trække dagens vurdering mod midten:\n" + "\n".join(linjer)
    )


def build_prompt(cfg: Config, samling: Collection, maaned: str, historik: list[dict]) -> str:
    return f"""Måned der skal vurderes: {maaned}
Artikler indsamlet i perioden {samling.periode_start} til {samling.periode_slut}.
Antal artikler: {samling.antal_artikler} fra {samling.antal_kilder} forskellige kilder.

## Dimensioner du skal score

{_dimension_afsnit(cfg)}

## Sådan skal du vægte kilderne

{_kilde_afsnit(cfg, samling.artikler)}

## Kalibrering

{_historik_afsnit(historik)}

## Materiale

{_artikel_afsnit(samling.artikler)}

## Opgave

Score hver af de {len(cfg.dimensioner)} dimensioner ovenfor. Brug præcis de id'er der er opgivet, én vurdering pr. dimension, hverken flere eller færre. Henvis kun til artikel-id'er der optræder i materialet. Skriv derefter en sammenfatning, de vigtigste begivenheder og den stærkeste modvægt mod din egen samlede vurdering."""


def _valider(vurdering: Vurdering, cfg: Config, artikler: list[Article]) -> list[str]:
    """Fjern ugyldige henvisninger og manglende dimensioner. Returnér advarsler."""
    advarsler: list[str] = []
    gyldige_ider = {a.id for a in artikler}
    forventede = {d.id for d in cfg.dimensioner}

    for dv in vurdering.dimensioner:
        ukendte = [i for i in dv.artikel_ider if i not in gyldige_ider]
        if ukendte:
            advarsler.append(
                f"Dimension '{dv.dimension_id}' henviste til {len(ukendte)} ukendt(e) "
                f"artikel-id: {', '.join(ukendte)}"
            )
            dv.artikel_ider = [i for i in dv.artikel_ider if i in gyldige_ider]
        if not dv.artikel_ider:
            advarsler.append(f"Dimension '{dv.dimension_id}' har ingen gyldige kildehenvisninger")

    faktiske = {dv.dimension_id for dv in vurdering.dimensioner}
    for manglende in sorted(forventede - faktiske):
        advarsler.append(f"Dimension '{manglende}' mangler helt i modellens svar")
    for ukendt in sorted(faktiske - forventede):
        advarsler.append(f"Modellen returnerede ukendt dimension '{ukendt}' - ignoreret")
    vurdering.dimensioner = [dv for dv in vurdering.dimensioner if dv.dimension_id in forventede]

    vurdering.vigtigste_haendelser = [
        h for h in vurdering.vigtigste_haendelser if h.artikel_id in gyldige_ider
    ]
    return advarsler


def score(
    cfg: Config,
    samling: Collection,
    maaned: str,
    historik: list[dict],
    client: anthropic.Anthropic | None = None,
) -> ScoreResultat:
    if not samling.artikler:
        raise RuntimeError("Ingen artikler indsamlet - vurdering afbrudt. Tjek kildestatus i loggen.")

    client = client or anthropic.Anthropic()
    prompt = build_prompt(cfg, samling, maaned, historik)
    prompt_hash = hashlib.sha256((SYSTEM + prompt).encode("utf-8")).hexdigest()[:16]

    log.info(
        "Kalder %s med %d artikler (prompt %d tegn, hash %s)",
        MODEL,
        samling.antal_artikler,
        len(prompt),
        prompt_hash,
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Vurdering,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Modellen afviste at svare: {response.stop_details}")

    vurdering = response.parsed_output
    if vurdering is None:
        raise RuntimeError("Modellen returnerede intet gyldigt struktureret svar")

    advarsler = _valider(vurdering, cfg, samling.artikler)
    for a in advarsler:
        log.warning("Validering: %s", a)

    return ScoreResultat(
        vurdering=vurdering,
        model=MODEL,
        prompt_hash=prompt_hash,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        advarsler=advarsler,
    )
