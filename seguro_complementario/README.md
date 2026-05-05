# Seguro Complementario MetLife - Descarga de Reembolsos

Script Python que descarga desde el portal de MetLife:
- Listado de claims (reembolsos) en CSV
- Liquidaciones (PDF)
- Bonos y boletas asociados a cada claim (PDF)

## Requisitos

- Python 3 con `requests` instalado:
  ```bash
  pip install requests
  ```

## Pasos para correr el script (CADA VEZ)

El JWT de MetLife expira en ~1 hora, así que estos pasos hay que repetirlos en cada ejecución.

### 1. Loguearse en el portal

- Abrir https://portaldeclientes.metlife.cl
- Ingresar como **Cliente** con RUT y Clave de Acceso
- Completar el segundo factor (SMS / Email)

### 2. Capturar un cURL fresco desde DevTools

1. Abrir **DevTools** (F12 o Cmd+Opt+I)
2. Ir a la pestaña **Network**
3. Activar **Preserve log** (importante)
4. En el filtro escribir: `latam.apis.metlife.com`
5. En el portal, navegar a **Reembolsos** → **Mis reembolsos** (o donde se ven los claims)
6. En Network buscar una request del tipo `claims?page=1&status=historico` o `claims?page=1&status=enProceso`
7. **Click derecho sobre esa request** → `Copy` → **`Copy as cURL`**

### 3. Pegar el cURL en `metlife_curl.txt`

- Abrir el archivo `metlife_curl.txt` (al lado del script)
- **Reemplazar todo el contenido** con el cURL recién copiado
- Guardar

### 4. Ejecutar el script

```bash
cd "/Users/paulita/Library/Mobile Documents/com~apple~CloudDocs/Respaldo MacBook Pro M3/Documentos/DEV/Personal/reembolsos_salud/seguro_complementario"
python seguro_complementario.py
```

El script generará una carpeta `metlife_data/` con:
- `claims_metlife.csv` — listado de todos los claims (siempre se regenera)
- `metlife_state.json` — estado interno: qué claims ya están descargados y con qué status
- `<claimNumber>_<claimId>/liquidacion.pdf` — liquidación de cada claim
- `<claimNumber>_<claimId>/Bono_o_Reembols_1.pdf`, `Boleta_o_Factur_1.pdf` — documentos adjuntos (solo si el claim los tiene; típicamente los rechazados)

### Modo incremental (descarga solo lo nuevo o cambiado)

A partir de la 2ª ejecución, el script:
- **Salta** claims que ya tiene descargados Y cuyo status no cambió desde la última corrida
- **Descarga** solo claims **nuevos** o aquellos cuyo status cambió (`statusId`, `statusName`, `statusModDate` o `approvedStatus`)
- Si **borraste manualmente** la carpeta de un claim, la vuelve a descargar

Al final muestra un resumen tipo: `📊 Resumen: 3 descargado(s), 44 sin cambios (de 47 claims totales)`.

### Forzar redescarga total

Si quieres redescargar todo desde cero (por ejemplo, si sospechas que un PDF se corrompió):

```bash
python seguro_complementario.py --force
```

## Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `401 Invalid JWT` | JWT no se pegó bien o no empieza con `eyJ` | Volver a copiar desde DevTools (sin la palabra `Bearer`) |
| `401 Token Missmatch` | El header `token` (numérico largo) está desactualizado | Capturar un cURL fresco — ese token también cambia por sesión |
| `401 Unauthorized` | JWT expiró (más de ~1h después del login) | Volver a loguearse y capturar cURL nuevo |
| `No se encontró el archivo con el cURL` | Falta el archivo `metlife_curl.txt` | Crearlo y pegar el cURL ahí |

## Estructura de archivos

```
seguro_complementario/
├── README.md                    # este archivo
├── seguro_complementario.py     # script principal
├── metlife_curl.txt             # cURL pegado desde DevTools (se actualiza cada sesión)
└── metlife_data/                # output (claims y PDFs)
    ├── claims_metlife.csv
    ├── metlife_state.json       # estado para descarga incremental
    └── <claimNumber>_<claimId>/
        ├── liquidacion.pdf
        ├── Bono_o_Reembols_1.pdf       # solo si existen
        └── Boleta_o_Factur_1.pdf       # solo si existen
```

## Notas técnicas

- El JWT proviene de Azure AD (`login.microsoftonline.com`) — válido ~1h.
- El header `token` (numérico largo) es generado por MetLife por sesión y también expira.
- El header `ocp-apim-subscription-key` es estático (clave del API Gateway de MetLife).
- Headers que el script reenvía desde el cURL: `Authorization`, `token`, `ocp-apim-subscription-key`, `role`, `rut`, `origin`, `referer`, `User-Agent`.

## TODO (mejoras futuras)

- Automatizar el login OAuth2 con Selenium/Playwright para evitar copiar el cURL manualmente (requiere manejar 2FA).
- Manejar paginación cuando haya más de una página de claims.
- Reintentos automáticos en errores de red.
