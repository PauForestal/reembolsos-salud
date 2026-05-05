import os
import re
import sys
import csv
import json
import shlex
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests

# =====================================================
# CONFIGURACIÓN
# =====================================================

USER_ID = "136765132"
RUT = "136765132"

PRODUCT_PATH = "2/340011620"

BASE_LATAM = (
    "https://latam.apis.metlife.com/external/csp/channel/v1/tenants/digital/products"
)
CLAIMS_BASE = f"{BASE_LATAM}/{PRODUCT_PATH}/claims"

BASE_PORTAL = "https://portaldeclientes.metlife.cl"

BASE_DIR = "metlife_data"
os.makedirs(BASE_DIR, exist_ok=True)

# Archivos donde el usuario pega el cURL y donde se guarda el estado entre ejecuciones
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CURL_FILE = os.path.join(SCRIPT_DIR, "metlife_curl.txt")
STATE_FILE = os.path.join(BASE_DIR, "metlife_state.json")


# =====================================================
# PARSEO DEL cURL
# =====================================================

def parse_curl(curl_text: str) -> Dict[str, str]:
    """Extract headers from a cURL command copied from Chrome DevTools."""
    cleaned = curl_text.replace("\\\n", " ").replace("\\\r\n", " ")
    try:
        tokens = shlex.split(cleaned)
    except ValueError as e:
        raise ValueError(f"No se pudo parsear el cURL: {e}")

    headers: Dict[str, str] = {}
    i = 0
    while i < len(tokens):
        if tokens[i] in ("-H", "--header") and i + 1 < len(tokens):
            raw = tokens[i + 1]
            if ":" in raw:
                name, value = raw.split(":", 1)
                headers[name.strip().lower()] = value.strip()
            i += 2
        else:
            i += 1
    return headers


def load_session_headers() -> Dict[str, str]:
    curl_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CURL_FILE

    if not os.path.exists(curl_path):
        print("❌ No se encontró el archivo con el cURL.")
        print()
        print("Pasos:")
        print("  1. Abre portaldeclientes.metlife.cl y logueate.")
        print("  2. DevTools (F12) → pestaña Network → filtra por 'latam.apis.metlife.com'.")
        print("  3. Click derecho sobre cualquier request claims → Copy → Copy as cURL.")
        print(f"  4. Pega el contenido en: {DEFAULT_CURL_FILE}")
        print("  5. Vuelve a ejecutar el script.")
        sys.exit(1)

    with open(curl_path, "r", encoding="utf-8") as f:
        curl_text = f.read()

    parsed = parse_curl(curl_text)

    auth = parsed.get("authorization", "")
    token_hdr = parsed.get("token", "")
    apim_key = parsed.get("ocp-apim-subscription-key", "")

    if not auth.lower().startswith("bearer ey"):
        print("❌ El cURL no contiene un header 'authorization: Bearer eyJ...'")
        sys.exit(1)
    if not token_hdr:
        print("❌ El cURL no contiene el header 'token'")
        sys.exit(1)
    if not apim_key:
        print("⚠️  No se encontró 'ocp-apim-subscription-key' en el cURL — usando default")
        apim_key = "e4a3c30848c84971bb214e561c6dcc0f"

    return {
        "Authorization": auth,
        "token": token_hdr,
        "ocp-apim-subscription-key": apim_key,
        "role": parsed.get("role", "cliente"),
        "rut": parsed.get("rut", RUT),
        "origin": parsed.get("origin", BASE_PORTAL),
        "referer": parsed.get("referer", f"{BASE_PORTAL}/"),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-ES,es;q=0.9",
        "User-Agent": parsed.get(
            "user-agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        ),
    }


HEADERS = load_session_headers()
COOKIES: Dict[str, str] = {}

# =====================================================
# 1) OBTENER TODOS LOS CLAIMS
# =====================================================

def fetch_claims(status: str) -> List[Dict[str, Any]]:
    """
    status: 'enProceso' o 'historico'
    """
    claims: List[Dict[str, Any]] = []
    page = 1

    while True:
        params = {"page": page, "status": status}
        print(f"🔎 claims page={page}, status={status}")
        resp = requests.get(CLAIMS_BASE, headers=HEADERS, params=params)
        print("Status:", resp.status_code)
        if resp.status_code != 200:
            print("Respuesta:", resp.text[:500])
        resp.raise_for_status()
        data = resp.json()

        page_claims = data.get("claims", [])
        metadata = data.get("metadata", {}) or {}

        claims.extend(page_claims)

        page_size = metadata.get("itemsPerPage", len(page_claims))
        current_page = metadata.get("currentPage", page)

        if not page_claims or len(page_claims) < page_size:
            break

        page += 1

    print(f"✅ Total claims ({status}): {len(claims)}")
    return claims


def flatten_claim(c: Dict[str, Any]) -> Dict[str, Any]:
    status = c.get("status", {}) or {}
    beneficiary = c.get("beneficiary", {}) or {}
    return {
        "claimId":         c.get("claimId"),
        "claimNumber":     c.get("claimNumber"),
        "reportDate":      c.get("reportDate"),
        "reportChannel":   c.get("reportChannel"),
        "benefKind":       beneficiary.get("kind"),
        "benefName":       beneficiary.get("name"),
        "statusId":        status.get("id"),
        "statusName":      status.get("name"),
        "statusModDate":   status.get("modificationDate"),
        "approvedStatus":  status.get("approvedStatus"),
        "claimedAmount":   c.get("claimedAmount"),
        "paidAmount":      c.get("paidAmount"),
        "note":            c.get("note"),
    }


def save_claims_csv(claims: List[Dict[str, Any]]) -> None:
    rows = [flatten_claim(c) for c in claims]
    if not rows:
        return
    path = os.path.join(BASE_DIR, "claims_metlife.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"📄 CSV guardado: {path}")


# =====================================================
# 2) SUMMARY DEL CLAIM (metadata + lista de archivos)
# =====================================================

# Endpoint summary: devuelve la liquidación PDF (en v2, con /2/ antes de 340011620)
SUMMARY_URL = (
    "https://latam.apis.metlife.com/external/csp/channel/v2"
    "/tenants/digital/products/2/340011620/claims/summary"
)

# Endpoint files: devuelve la lista de archivos adjuntos (en v1, sin /2/)
FILES_URL_TEMPLATE = (
    "https://latam.apis.metlife.com/external/csp/channel/v1"
    "/tenants/digital/products/340011620/claims/{claim_number}/files"
)

# Endpoint download: descarga un archivo individual por fileId (en v1, sin /2/)
DOWNLOAD_URL_TEMPLATE = (
    "https://latam.apis.metlife.com/external/csp/channel/v1"
    "/tenants/digital/products/340011620/claims/{claim_id}/files/download"
)


def fetch_claim_summary(claim_number: str) -> Dict[str, Any]:
    """POST /v2/.../claims/summary devuelve la liquidación como fileBase64."""
    resp = requests.post(
        SUMMARY_URL,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"claimNumber": claim_number},
    )
    if resp.status_code != 200:
        print(f"   ⚠️ Summary no disponible ({resp.status_code}): {resp.text[:200]}")
        return {}
    return resp.json()


def fetch_files_metadata(claim_number: str, claim_id: str) -> List[Dict[str, Any]]:
    """POST /v1/.../claims/{claim_number}/files devuelve la lista de archivos adjuntos."""
    url = FILES_URL_TEMPLATE.format(claim_number=claim_number)
    resp = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"claimId": claim_id},
    )
    if resp.status_code != 200:
        print(f"   ⚠️ Files no disponible ({resp.status_code}): {resp.text[:200]}")
        return []
    return resp.json().get("files", [])


def download_file_by_id(claim_id: str, file_id: str) -> Optional[bytes]:
    """POST /v1/.../files/download con body {fileId: "..."} -> base64 del PDF."""
    url = DOWNLOAD_URL_TEMPLATE.format(claim_id=claim_id)
    resp = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"fileId": file_id},
    )
    if resp.status_code != 200:
        print(f"   ⚠️ Download falló para {file_id} ({resp.status_code})")
        return None
    data = resp.json()
    b64 = data.get("fileBase64")
    if not b64:
        return None
    return base64.b64decode(b64.strip())


def safe_filename(name: str) -> str:
    """Limpia el nombre de archivo para que sea válido en el sistema."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def download_attachments(claim: Dict[str, Any], folder: str) -> None:
    """Descarga liquidación + archivos adjuntos de un claim."""
    claim_id = str(claim.get("claimId"))
    claim_number = str(claim.get("claimNumber"))

    # 1) Liquidación: viene en fileBase64 del endpoint /summary
    summary = fetch_claim_summary(claim_number)
    liquidacion_b64 = summary.get("fileBase64") if summary else None
    if liquidacion_b64:
        try:
            pdf = base64.b64decode(liquidacion_b64.strip())
            path = os.path.join(folder, "liquidacion.pdf")
            with open(path, "wb") as f:
                f.write(pdf)
            print(f"   ✅ Liquidación descargada ({len(pdf)//1024} KB)")
        except Exception as e:
            print(f"   ⚠️ Error decodificando liquidación: {e}")
    else:
        print("   ℹ️ Sin liquidación")

    # 2) Lista de archivos adjuntos: endpoint /files separado
    files = fetch_files_metadata(claim_number, claim_id)
    if not files:
        print("   ℹ️ Sin archivos adjuntos")
        return

    # 3) Descarga cada adjunto usando el endpoint /files/download con su fileId
    for fmeta in files:
        name = fmeta.get("name", "archivo")
        file_id = fmeta.get("id")
        ftype = fmeta.get("type", ".pdf")
        if not file_id:
            continue

        out_name = safe_filename(f"{name}{ftype}")
        file_bytes = download_file_by_id(claim_id, file_id)
        if not file_bytes:
            print(f"   ⚠️ No se pudo descargar {out_name}")
            continue

        path = os.path.join(folder, out_name)
        with open(path, "wb") as f:
            f.write(file_bytes)
        print(f"   ✅ {out_name} ({len(file_bytes)//1024} KB)")


# =====================================================
# 4) ESTADO INCREMENTAL (sólo descarga lo nuevo o cambiado)
# =====================================================

def load_state() -> Dict[str, Dict[str, Any]]:
    """Carga el estado guardado en la ejecución anterior. Retorna {} si no existe."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ No se pudo leer el estado anterior: {e}")
        return {}


def save_state(state: Dict[str, Dict[str, Any]]) -> None:
    """Guarda el estado actual en disco para usar en la próxima ejecución."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def claim_signature(claim: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae los campos relevantes para detectar cambios de estado."""
    status = claim.get("status", {}) or {}
    return {
        "claimId": str(claim.get("claimId") or ""),
        "statusId": status.get("id"),
        "statusName": status.get("name"),
        "statusModDate": status.get("modificationDate"),
        "approvedStatus": status.get("approvedStatus"),
    }


def needs_download(
    claim: Dict[str, Any],
    folder: str,
    previous_state: Dict[str, Dict[str, Any]],
    force: bool,
) -> tuple[bool, str]:
    """Decide si un claim necesita (re)descargarse. Retorna (necesita, razon)."""
    if force:
        return True, "force"

    claim_number = str(claim.get("claimNumber") or "")
    sig_now = claim_signature(claim)
    sig_prev = previous_state.get(claim_number)

    if sig_prev is None:
        return True, "claim nuevo"

    if not os.path.isdir(folder):
        return True, "carpeta borrada"

    # Comparar campos relevantes (todos menos downloadedAt)
    for key in ("claimId", "statusId", "statusName", "statusModDate", "approvedStatus"):
        if sig_prev.get(key) != sig_now.get(key):
            return True, f"cambio en {key}: {sig_prev.get(key)!r} → {sig_now.get(key)!r}"

    return False, "sin cambios"


# =====================================================
# 5) MAIN
# =====================================================

def main():
    force = "--force" in sys.argv

    if force:
        print("⚙️  Modo --force activado: redescargando todo")

    claims_hist = fetch_claims("historico")
    claims_proc = fetch_claims("enProceso")
    all_claims = claims_hist + claims_proc

    save_claims_csv(all_claims)

    previous_state = load_state()
    new_state: Dict[str, Dict[str, Any]] = {}

    n_downloaded = 0
    n_skipped = 0

    for c in all_claims:
        claim_number = str(c.get("claimNumber") or "")
        claim_id = str(c.get("claimId") or "")
        if not claim_number or not claim_id:
            continue

        folder = os.path.join(BASE_DIR, f"{claim_number}_{claim_id}")

        download, reason = needs_download(c, folder, previous_state, force)

        if download:
            os.makedirs(folder, exist_ok=True)
            print(f"\n📂 Claim {claim_number} (id={claim_id}) — {reason}")
            download_attachments(c, folder)
            n_downloaded += 1
            sig = claim_signature(c)
            sig["downloadedAt"] = datetime.now().isoformat(timespec="seconds")
            new_state[claim_number] = sig
        else:
            # Sin cambios: conserva el snapshot anterior tal cual
            n_skipped += 1
            new_state[claim_number] = previous_state[claim_number]

    save_state(new_state)

    print(
        f"\n📊 Resumen: {n_downloaded} descargado(s), {n_skipped} sin cambios "
        f"(de {len(all_claims)} claims totales)"
    )


if __name__ == "__main__":
    main()
