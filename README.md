# README.md

## Propósito

Scripts Python para descargar y consolidar datos de reembolsos de salud desde dos fuentes:
- **Isapre (Nueva Más Vida)**: scraping con Selenium del portal web, extrae estado de reembolsos y exporta a Excel por estado.
- **Seguro complementario (MetLife)**: descarga de claims y PDFs vía API REST (requiere JWT obtenido manualmente desde DevTools).

## Ejecución

### Isapre

```bash
cd isapre/
python isapre.py
```

Requiere: `selenium`, `pandas`, `openpyxl`, chromedriver en PATH.
Credenciales via env vars `ISAPRE_RUT` e `ISAPRE_PASSWORD` (fallback hardcodeado en el script).
Output: `autorizadas.xlsx`, `devueltas.xlsx`, `ingresadas.xlsx`, `en_tramite.xlsx`.

### Seguro complementario (MetLife)

```bash
cd seguro_complementario/
python seguro_complementario.py          # incremental
python seguro_complementario.py --force  # redescarga todo
```

Requiere: `requests`.
Antes de cada ejecución, pegar un cURL fresco en `metlife_curl.txt` (JWT expira en ~1h).
Output: `metlife_data/claims_metlife.csv` + carpetas `<claimNumber>_<claimId>/` con PDFs.

## Arquitectura

```
reembolsos_salud/
├── isapre/
│   ├── isapre.py              # script monolítico: login → scraping → pivot → export xlsx
│   ├── archivados/            # exports anteriores para referencia
│   └── *.xlsx                 # output actual
└── seguro_complementario/
    ├── seguro_complementario.py  # API client: fetch claims → descarga PDFs incremental
    ├── metlife_curl.txt          # cURL pegado manualmente (headers de sesión)
    └── metlife_data/             # output: CSV + state + PDFs por claim
```

## Detalles técnicos relevantes

- `isapre.py` maneja overlays fancybox que interceptan clicks (usa JS click como fallback).
- El estado "EN TRÁMITE" viene con encoding roto del portal (falta la Á); la normalización en `normalizar_estado_robusto()` maneja esa variante.
- `seguro_complementario.py` usa estado incremental (`metlife_state.json`) para no redescargar claims sin cambios.
- MetLife usa dos versiones de API: v2 para summary/liquidación, v1 para files/download.
