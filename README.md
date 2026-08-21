# eraifarligt.dk

Automatisk månedlig vurdering af, om kunstig intelligens er farlig — bygget på et
vægtet faresindeks over offentlige nyhedskilder.

Sitet svarer på ét spørgsmål: **Er AI farligt i denne måned?** Svaret er
`Ja`, `Måske` eller `Nej`, og det udledes deterministisk af et 0–100-indeks,
som igen er et vægtet gennemsnit af seks dimensionsscorer sat af en sprogmodel.

## Sådan hænger det sammen

```
data/raw/YYYY-MM.jsonl        daglig høst fra 23 RSS-feeds (ingen API-nøgle)
        │
        ▼  udvælgelse: månedsfilter, dublet­fjernelse, loft pr. kilde
   ét kald til claude-opus-5  scorer 6 dimensioner 0–100 med kildehenvisninger
        │
        ▼  verdict.py: vægtet gennemsnit → indeks → fast grænseværdi → ord
data/verdicts/YYYY-MM.json    månedens facit, versionsstyret
        │
        ▼  render.py: Jinja2 + inline SVG
site/                         index.html, arkiv.html, om.html, maaned/*.html
```

### Hvorfor to jobs og ikke ét

RSS er en strøm, ikke et arkiv. De fleste feeds rummer kun de sidste 10–20
poster, altså typisk 1–2 uger. Hvis vurderingen for juli først hentede feeds den
1. august, ville månedens første halvdel allerede være rullet ud af feedet.
Derfor høster `harvest` dagligt ind i en pulje, og `run` vurderer ud fra puljen.

## Kom i gang

```bash
pip install -r requirements.txt
export PYTHONPATH=src            # eller: pip install -e .
```

| Kommando | Hvad den gør | Kræver API-nøgle |
|---|---|---|
| `python -m eraifarligt harvest` | Henter alle feeds og lægger nye artikler i puljen | nej |
| `python -m eraifarligt status` | Viser hvad puljen indeholder pr. måned | nej |
| `python -m eraifarligt collect --pulje --maaned 2026-07 --udskriv-prompt` | Viser det udvalgte materiale og hele prompten | nej |
| `python -m eraifarligt run --maaned 2026-07` | Månedsvurdering: udvælg, kald model, gem, byg site | **ja** |
| `python -m eraifarligt build` | Bygger sitet ud fra `data/verdicts/` | nej |
| `python -m eraifarligt demo --ud .demo` | Opdigtet måned, så designet kan ses uden at bruge kvote | nej |

Nøglen læses fra `ANTHROPIC_API_KEY`.

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."      # PowerShell, kun denne session
```

## Automatik

| Workflow | Kadence | Hvad |
|---|---|---|
| `.github/workflows/harvest.yml` | dagligt 05:17 UTC | høster feeds, committer `data/raw` |
| `.github/workflows/verdict.yml` | den 1. kl. 06:00 UTC | vurderer forrige måned, committer, udgiver |
| `.github/workflows/deploy.yml` | ved push til `main` | bygger og udgiver sitet igen |

`verdict.yml` kan også startes manuelt med en valgfri måned og `overskriv`.

### Opsætning i GitHub

1. Læg repoet på GitHub og slå **Pages** til med kilden **GitHub Actions**.
2. Tilføj hemmeligheden `ANTHROPIC_API_KEY` under
   *Settings → Secrets and variables → Actions*.
3. Peg `eraifarligt.dk` på GitHub Pages. `CNAME` skrives automatisk ved build.

## Konfiguration

Alt der styrer resultatet ligger i `config/` og er versionsstyret:

- `config/sources.yaml` — feeds, deres troværdighedsgruppe (`tier`), loft pr.
  kilde, samlet artikelloft, nådedage og timeout.
- `config/dimensions.yaml` — de seks dimensioner, deres vægte og de
  grænseværdier der oversætter indeks til `Ja` / `Måske` / `Nej`.

Ændrer man vægte eller grænser, ændrer man alle fremtidige svar. Gamle
månedsfiler bevarer det indeks de blev udregnet med — de omskrives ikke.

## Hvad modellen ikke bestemmer

Bevidst holdt uden for sprogmodellen, så resultatet kan efterprøves:

- antal artikler og antal kilder — tælles i koden
- faresindekset — vægtet gennemsnit i `verdict.py`
- ordet `Ja` / `Måske` / `Nej` — fast grænseværdi i `dimensions.yaml`
- gyldigheden af kildehenvisninger — valideres mod det faktiske materiale

Hver månedsfil gemmer model-id, prompt-hash, tokenforbrug, kildestatus og
listen over de artikel-id'er der indgik.

## Historik

Projektet kørte fra sommeren 2025 som en n8n-arbejdsgang og gik i stå i august
2025 uden at nogen kunne se det. `docs/WORKLOG.md` beskriver den gamle
opbygning, hvad der konkret var galt med den, og hvorfor 2026-udgaven ser ud
som den gør. Samme sammenligning står i kort form på sitets `om.html`.
