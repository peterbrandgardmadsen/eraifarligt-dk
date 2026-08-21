"""Generering af det statiske site ud fra de gemte månedsfiler."""

from __future__ import annotations

import logging
import shutil
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config, SITE_DIR, STATIC_DIR, TEMPLATE_DIR

log = logging.getLogger(__name__)

MAANEDSNAVNE = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def dansk_maaned(maaned: str) -> str:
    """'2026-08' -> 'august 2026'."""
    aar, md = (int(x) for x in maaned.split("-"))
    return f"{MAANEDSNAVNE[md - 1]} {aar}"


def dansk_dato(iso: str) -> str:
    """ISO-tidsstempel eller -dato -> '21. august 2026'."""
    tekst = iso.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(tekst).date()
    except ValueError:
        d = date.fromisoformat(tekst[:10])
    return f"{d.day}. {MAANEDSNAVNE[d.month - 1]} {d.year}"


def naeste_maaned(maaned: str) -> str:
    aar, md = (int(x) for x in maaned.split("-"))
    return f"{aar + 1}-01" if md == 12 else f"{aar}-{md + 1:02d}"


def naeste_vurdering(maaned: str) -> str:
    """Hvornår den efterfølgende vurdering udgives, som '1. september 2026'.

    Vurderingen for en måned udgives den 1. i måneden efter. Den næste
    vurdering falder derfor to måneder efter den måned der vises.
    """
    aar, md = (int(x) for x in naeste_maaned(maaned).split("-"))
    md += 1
    if md > 12:
        md, aar = 1, aar + 1
    return f"1. {MAANEDSNAVNE[md - 1]} {aar}"


def _trend_svg(maaneder: list[dict], bredde: int = 720, hoejde: int = 220) -> str:
    """Inline SVG-graf over faresindekset. Ingen JavaScript, ingen eksterne kald."""
    if not maaneder:
        return ""

    pad_v, pad_h, pad_b = 16, 44, 34
    plot_b = bredde - pad_h - pad_v
    plot_h = hoejde - pad_v - pad_b

    punkter = maaneder[-24:]
    n = len(punkter)

    def x(i: int) -> float:
        if n == 1:
            return pad_h + plot_b / 2
        return pad_h + plot_b * i / (n - 1)

    def y(vaerdi: float) -> float:
        return pad_v + plot_h * (1 - vaerdi / 100)

    dele: list[str] = [
        f'<svg viewBox="0 0 {bredde} {hoejde}" role="img" '
        f'aria-label="Faresindeks over tid" class="trend">'
    ]

    # Båndene som vandrette zoner, så man kan se hvor Ja/Måske/Nej ligger.
    for fra, til, klasse in ((65, 100, "zone-hoej"), (35, 65, "zone-mellem"), (0, 35, "zone-lav")):
        top = y(til)
        dele.append(
            f'<rect x="{pad_h}" y="{top:.1f}" width="{plot_b}" '
            f'height="{y(fra) - top:.1f}" class="{klasse}"/>'
        )

    for vaerdi in (0, 35, 65, 100):
        yv = y(vaerdi)
        dele.append(
            f'<line x1="{pad_h}" y1="{yv:.1f}" x2="{bredde - pad_v}" y2="{yv:.1f}" class="gitter"/>'
            f'<text x="{pad_h - 8}" y="{yv + 4:.1f}" class="akse" text-anchor="end">{vaerdi}</text>'
        )

    bane = " ".join(
        f"{'M' if i == 0 else 'L'}{x(i):.1f} {y(m['indeks']):.1f}" for i, m in enumerate(punkter)
    )
    dele.append(f'<path d="{bane}" class="linje"/>')

    for i, m in enumerate(punkter):
        dele.append(
            f'<circle cx="{x(i):.1f}" cy="{y(m["indeks"]):.1f}" r="4" '
            f'class="punkt tone-{m["tone"]}"><title>{dansk_maaned(m["maaned"])}: '
            f'{m["indeks"]} ({m["bedoemmelse"]})</title></circle>'
        )

    # Kun første og sidste etiket, ellers overlapper de. Ankrene vender indad,
    # så teksten ikke løber ud over grafens kant.
    etiketter = {0: "start"} if n == 1 else {0: "start", n - 1: "end"}
    for i, anker in etiketter.items():
        dele.append(
            f'<text x="{x(i):.1f}" y="{hoejde - 10}" class="akse" text-anchor="{anker}">'
            f'{dansk_maaned(punkter[i]["maaned"])}</text>'
        )

    dele.append("</svg>")
    return "".join(dele)


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["dansk_maaned"] = dansk_maaned
    env.filters["dansk_dato"] = dansk_dato
    env.filters["naeste_vurdering"] = naeste_vurdering
    return env


def render(cfg: Config, maaneder: list[dict], site_dir: Path | None = None) -> Path:
    """Byg hele sitet. maaneder skal være sorteret kronologisk."""
    if not maaneder:
        raise RuntimeError("Ingen månedsdata at rendere")

    ud = site_dir or SITE_DIR
    if ud.exists():
        shutil.rmtree(ud)
    (ud / "maaned").mkdir(parents=True, exist_ok=True)

    env = _env()
    nyeste = maaneder[-1]
    trend = _trend_svg(maaneder)
    faelles = {
        "alle_maaneder": maaneder,
        "nyeste": nyeste,
        "trend_svg": trend,
        "dimensioner": cfg.dimensioner,
        "baand": sorted(cfg.baand, key=lambda b: b.min, reverse=True),
        "bygget": date.today().isoformat(),
    }

    (ud / "index.html").write_text(
        env.get_template("maaned.html.j2").render(
            m=nyeste, er_forside=True, rod="", naeste=naeste_maaned(nyeste["maaned"]), **faelles
        ),
        encoding="utf-8",
    )

    for m in maaneder:
        (ud / "maaned" / f"{m['maaned']}.html").write_text(
            env.get_template("maaned.html.j2").render(
                m=m, er_forside=False, rod="../", naeste=naeste_maaned(m["maaned"]), **faelles
            ),
            encoding="utf-8",
        )

    (ud / "arkiv.html").write_text(
        env.get_template("arkiv.html.j2").render(rod="", **faelles), encoding="utf-8"
    )
    (ud / "om.html").write_text(
        env.get_template("om.html.j2").render(rod="", **faelles), encoding="utf-8"
    )

    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, ud / "static")

    (ud / ".nojekyll").write_text("", encoding="utf-8")
    (ud / "CNAME").write_text("eraifarligt.dk\n", encoding="utf-8")

    log.info("Byggede site i %s (%d måneder)", ud, len(maaneder))
    return ud
