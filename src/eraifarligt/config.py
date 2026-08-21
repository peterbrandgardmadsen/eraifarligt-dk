"""Indlæsning af konfiguration fra config/*.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data" / "verdicts"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "site"


@dataclass(frozen=True)
class Source:
    navn: str
    url: str
    tier: str
    maks: int


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    weight: float
    beskrivelse: str


@dataclass(frozen=True)
class Baand:
    """Et interval på faresindekset der oversættes til en bedømmelse."""

    id: str
    label: str
    min: int
    tone: str


@dataclass(frozen=True)
class Config:
    kilder: list[Source]
    tier_beskrivelser: dict[str, str]
    dimensioner: list[Dimension]
    baand: list[Baand]
    maks_artikler_i_alt: int = 140
    naade_dage: int = 3
    timeout: int = 20
    user_agent: str = "eraifarligt.dk-bot/2.0"

    _by_id: dict[str, Dimension] = field(default_factory=dict, compare=False)

    def dimension(self, dim_id: str) -> Dimension | None:
        return next((d for d in self.dimensioner if d.id == dim_id), None)

    def bedoem(self, indeks: float) -> Baand:
        """Oversæt et faresindeks til en bedømmelse. Rent deterministisk."""
        for baand in sorted(self.baand, key=lambda b: b.min, reverse=True):
            if indeks >= baand.min:
                return baand
        return self.baand[-1]


def load_config(config_dir: Path | None = None) -> Config:
    config_dir = config_dir or CONFIG_DIR
    sources_raw = yaml.safe_load((config_dir / "sources.yaml").read_text(encoding="utf-8"))
    dims_raw = yaml.safe_load((config_dir / "dimensions.yaml").read_text(encoding="utf-8"))

    ind = sources_raw.get("indstillinger", {})

    return Config(
        kilder=[
            Source(navn=k["navn"], url=k["url"], tier=k["tier"], maks=int(k.get("maks", 10)))
            for k in sources_raw["kilder"]
        ],
        tier_beskrivelser=dict(sources_raw.get("tier_beskrivelser", {})),
        dimensioner=[
            Dimension(
                id=d["id"],
                label=d["label"],
                weight=float(d["weight"]),
                beskrivelse=" ".join(d["beskrivelse"].split()),
            )
            for d in dims_raw["dimensioner"]
        ],
        baand=[
            Baand(id=b["id"], label=b["label"], min=int(b["min"]), tone=b["tone"])
            for b in dims_raw["baand"]
        ],
        maks_artikler_i_alt=int(ind.get("maks_artikler_i_alt", 140)),
        naade_dage=int(ind.get("naade_dage", 3)),
        timeout=int(ind.get("timeout", 20)),
        user_agent=ind.get("user_agent", "eraifarligt.dk-bot/2.0"),
    )
