from pathlib import Path
import pandas as pd
import time
import os
import glob

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException,
)

download_path = "/Users/pvallejo/Documents/Personal/Salud/Isapre/"
start_page = "https://sv.nuevamasvida.cl/"
# -------------------------------------------------------------------
# Helper para cerrar / manejar el overlay de fancybox
# -------------------------------------------------------------------
def cerrar_fancybox_overlay(driver, timeout=5):
    wait = WebDriverWait(driver, timeout)
    try:
        # Intentar encontrar un botón de cerrar típico de fancybox
        close_btn = wait.until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "a.fancybox-close, a.fancybox-item.fancybox-close, button.fancybox-close",
                )
            )
        )
        close_btn.click()
        # pequeño tiempo para que desaparezca
        time.sleep(0.5)
        return
    except TimeoutException:
        pass

    # Si no hay botón de cerrar, esperar a que el overlay no sea visible
    try:
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.fancybox-overlay")
            )
        )
    except TimeoutException:
        # Si sigue ahí, ya no insistimos más
        pass


# -------------------------------------------------------------------
# CONFIGURACIÓN DEL DRIVER (SIN selenium-driver-updater)
# -------------------------------------------------------------------
chrome_options = Options()
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
# chrome_options.add_argument("--headless")  # actívalo si quieres sin ventana

# Si tienes chromedriver en el PATH, esto basta:
# service = ChromeService()
# driver = webdriver.Chrome(service=service, options=chrome_options)

# Si quieres usar una ruta específica al chromedriver:
# service = ChromeService("/ruta/a/tu/chromedriver")

intentos = 3
driver = None
datos = []

# ⚠️ Recomendado: usar variables de entorno en vez de credenciales hardcodeadas
USERNAME = os.environ.get("ISAPRE_RUT", "13676513-2")   # cambia o exporta en tu shell
PASSWORD = os.environ.get("ISAPRE_PASSWORD", "anto146") # cambia o exporta en tu shell

for i in range(intentos):
    try:
        service = ChromeService()  # asume chromedriver en el PATH
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 20)

        driver.get(start_page)

        # Por si aparece un overlay apenas cargando la página
        cerrar_fancybox_overlay(driver, timeout=5)

        # ----------------------------------------------------------------
        # LOGIN
        # ----------------------------------------------------------------
        rut_input = wait.until(
            EC.visibility_of_element_located((By.ID, "rut"))
        )
        clave_input = wait.until(
            EC.visibility_of_element_located((By.ID, "clave"))
        )

        rut_input.clear()
        rut_input.send_keys(USERNAME)
        clave_input.clear()
        clave_input.send_keys(PASSWORD)

        # Botón "Ingresar"
        ingresar_btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//*[@id='ingreso']")
            )
        )

        try:
            ingresar_btn.click()
        except ElementClickInterceptedException:
            # Si el overlay tapa el botón, intentamos cerrarlo y luego click de nuevo
            cerrar_fancybox_overlay(driver, timeout=5)
            try:
                ingresar_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//*[@id='ingreso']")
                    )
                )
                ingresar_btn.click()
            except ElementClickInterceptedException:
                # Último recurso: click vía JS
                driver.execute_script("arguments[0].click();", ingresar_btn)

        # Pequeña espera a que cargue el portal autenticado
        time.sleep(2)

        # ----------------------------------------------------------------
        # Click en botón btn3, que antes daba "element click intercepted"
        # ----------------------------------------------------------------
        try:
            btn3 = wait.until(
                EC.element_to_be_clickable((By.ID, "btn3"))
            )
            try:
                btn3.click()
            except ElementClickInterceptedException:
                cerrar_fancybox_overlay(driver, timeout=5)
                btn3 = wait.until(
                    EC.element_to_be_clickable((By.ID, "btn3"))
                )
                try:
                    btn3.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", btn3)
        except TimeoutException:
            print("No se encontró el botón btn3; puede que la página haya cambiado.")

        time.sleep(1)

        # ----------------------------------------------------------------
        # Navegación al menú "Estado de reembolsos"
        # ----------------------------------------------------------------
        menu_desplegable = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//li[@class='largo_tres ']")
            )
        )
        actions = ActionChains(driver)
        actions.move_to_element(menu_desplegable).perform()

        estado_reembolsos_link = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//li[@class='largo_tres ']//ul//li//a[@href='estado_reembolso.php'"
                    " and normalize-space()='Estado de reembolsos']",
                )
            )
        )
        estado_reembolsos_link.click()
        time.sleep(1)

        # ----------------------------------------------------------------
        # EXTRACCIÓN DE ACORDEONES
        # ----------------------------------------------------------------
        datos = []
        try:
            acordeones = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div.accordion-group[id^='solic_']")
                )
            )

            for indice, acordeon in enumerate(acordeones):
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                        acordeon,
                    )
                    time.sleep(1)

                    toggle = acordeon.find_element(
                        By.CSS_SELECTOR, "a.accordion-toggle"
                    )
                    driver.execute_script("arguments[0].click();", toggle)

                    # Esperar a que la tabla del acordeón sea visible
                    wait.until(
                        lambda d: acordeon.find_element(By.TAG_NAME, "table").is_displayed()
                    )

                    heading_info = acordeon.find_element(
                        By.CLASS_NAME, "panel-title2"
                    ).text
                    partes = heading_info.split("\n")

                    if len(partes) >= 2:
                        folio, estado = partes[:2]
                    else:
                        folio = "Folio no disponible"
                        estado = "Estado no disponible"

                    tabla = acordeon.find_element(By.TAG_NAME, "table")
                    filas = tabla.find_elements(By.TAG_NAME, "tr")
                    for fila in filas:
                        celdas = fila.find_elements(By.TAG_NAME, "td")
                        fila_datos = []
                        for celda in celdas:
                            # 1. Intentar obtener texto visible/oculto
                            texto = celda.text.strip()
                            if not texto:
                                texto = celda.get_attribute("textContent").strip()
                            
                            # 2. Buscar inputs (ej. botones o campos de texto readonly) y agregar su valor
                            inputs = celda.find_elements(By.TAG_NAME, "input")
                            found_input_val = False
                            for inp in inputs:
                                val = inp.get_attribute("value")
                                if val and val.strip():
                                    if texto:
                                        texto += " " + val.strip()
                                    else:
                                        texto = val.strip()
                                    found_input_val = True
                                    # Asumimos un solo input relevante por celda si encontramos uno
                                    break
                            
                            fila_datos.append(texto)

                        print(partes, fila_datos)
                        fila_completa = [folio, estado] + fila_datos
                        datos.append(fila_completa)

                    # Esperar a que las celdas tengan contenido
                    wait.until(
                        lambda d: len(tabla.find_elements(By.TAG_NAME, "td")) > 0
                    )

                except (TimeoutException, NoSuchElementException) as e:
                    print(f"No se pudo interactuar con el acordeón {indice}: {e}")
        except Exception as e:
            print(f"Se encontró un error al procesar los acordeones: {e}")

        # Si todo salió bien, salimos del for de intentos
        break

    except WebDriverException as e:
        print(f"Error de conexión con WebDriver, reintento {i+1} de {intentos}: {e}")
        time.sleep(3)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        driver = None

# Cerrar el driver si sigue vivo
if driver is not None:
    driver.quit()

# Agregar diagnóstico de los datos extraídos
print(f"\n=== DIAGNÓSTICO DE DATOS EXTRAÍDOS ===")
print(f"Total de filas extraídas: {len(datos)}")
if len(datos) > 0:
    print("Primeras 5 filas extraídas:")
    for i, fila in enumerate(datos[:5]):
        print(f"Fila {i+1}: {fila}")

nombres_columnas = ['Folio', 'Estado'] + [f'Dato_{i}' for i in range(1, (len(max(datos, key=len)) - 1))]
df_tablas = pd.DataFrame(datos, columns=nombres_columnas)

df_tablas['Folio'] = df_tablas.Folio.apply(lambda x: x.replace('Folio: ', ''))
df_tablas['Estado'] = df_tablas.Estado.apply(lambda x: x.replace('Estado: ', ''))
df_tablas['Folio'] = df_tablas.Folio.apply(lambda x: x.replace('Solicitud: ', ''))

# Función para normalizar estados
def normalizar_estado(estado):
    estado_clean = estado.strip().upper()
    # Manejar el carácter especial que aparece en "EN TRMITE"
    if 'TRMITE' in estado_clean or 'TRÁMITE' in estado_clean or 'TRAMITE' in estado_clean:
        return 'EN TRÁMITE'
    elif 'AUTORIZADA' in estado_clean:
        return 'AUTORIZADA'
    elif 'DEVUELTA' in estado_clean:
        return 'DEVUELTA'
    elif 'INGRESADA' in estado_clean:
        return 'INGRESADA'
    else:
        return estado_clean

# Función alternativa más robusta para normalizar estados
def normalizar_estado_robusto(estado):
    if pd.isna(estado):
        return estado
    
    # Convertir a string y limpiar
    estado_str = str(estado).strip().upper()
    
    # Normalizar caracteres especiales
    estado_str = estado_str.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
    
    # Buscar patrones en lugar de coincidencias exactas
    if any(palabra in estado_str for palabra in ['TRMITE', 'TRAMITE', 'TRÁMITE']):
        return 'EN TRÁMITE'
    elif 'AUTORIZADA' in estado_str:
        return 'AUTORIZADA'
    elif 'DEVUELTA' in estado_str:
        return 'DEVUELTA'
    elif 'INGRESADA' in estado_str:
        return 'INGRESADA'
    else:
        return estado_str

# Aplicar normalización de estados
df_tablas['Estado_Normalizado'] = df_tablas['Estado'].apply(normalizar_estado_robusto)

# Diagnóstico de distribución de estados
print(f"\n=== DISTRIBUCIÓN DE ESTADOS ===")
print("Estados originales:")
print(df_tablas['Estado'].value_counts())
print("\nEstados normalizados:")
print(df_tablas['Estado_Normalizado'].value_counts())

# Verificar que la normalización esté funcionando
print(f"\n=== VERIFICACIÓN DE NORMALIZACIÓN ===")
estados_originales = df_tablas['Estado'].unique()
for estado_orig in estados_originales:
    estado_norm = normalizar_estado_robusto(estado_orig)
    print(f"'{estado_orig}' -> '{estado_norm}'")

# Agregar diagnóstico después de la limpieza
print(f"\n=== DIAGNÓSTICO DESPUÉS DE LIMPIEZA ===")
print(f"Estados únicos después de limpieza:")
print(df_tablas['Estado'].unique())
print(f"Estados normalizados:")
print(df_tablas['Estado_Normalizado'].unique())
print(f"Total de filas después de limpieza: {len(df_tablas)}")

# Diagnóstico detallado del estado problemático
print(f"\n=== DIAGNÓSTICO DETALLADO DEL ESTADO PROBLEMÁTICO ===")
estado_problematico = 'EN TRMITE'
print(f"Estado problemático: '{estado_problematico}'")
print(f"Longitud: {len(estado_problematico)}")
print(f"Caracteres ASCII:")
for i, char in enumerate(estado_problematico):
    print(f"  Posición {i}: '{char}' (ASCII: {ord(char)})")

# Verificar si la normalización está funcionando
estado_normalizado = normalizar_estado(estado_problematico)
print(f"Estado normalizado: '{estado_normalizado}'")

datos_norm = (df_tablas.set_index(['Folio', 'Estado_Normalizado'])
                .apply(lambda x: {x['Dato_1'].strip(): x['Dato_2'].split(': ')[-1]}, axis=1)
                .apply(pd.Series)
                .reset_index())

datos_explod = datos_norm.melt(id_vars=['Folio', 'Estado_Normalizado'], var_name='Clave', value_name='Valor')
datos_explod.dropna(subset=['Valor'], inplace=True)

pivot_df = datos_explod.pivot_table(index=['Folio', 'Estado_Normalizado'], columns='Clave', values='Valor', aggfunc='first').reset_index()

# Agregar diagnóstico para ver qué estados están presentes
print("Estados únicos encontrados:")
print(pivot_df['Estado_Normalizado'].unique())
print(f"Total de filas en pivot_df: {len(pivot_df)}")

# Usar el estado normalizado para el filtrado
autorizadas = pivot_df.query('Estado_Normalizado=="AUTORIZADA"')
devueltas = pivot_df.query('Estado_Normalizado=="DEVUELTA"')
ingresadas = pivot_df.query('Estado_Normalizado=="INGRESADA"')
en_tramite = pivot_df.query('Estado_Normalizado=="EN TRÁMITE"')

# Agregar diagnóstico para ver cuántas filas tiene cada estado
print(f"Filas AUTORIZADA: {len(autorizadas)}")
print(f"Filas DEVUELTA: {len(devueltas)}")
print(f"Filas INGRESADA: {len(ingresadas)}")
print(f"Filas EN TRÁMITE: {len(en_tramite)}")

# Verificar si hay variaciones en el texto del estado
print("Verificando variaciones en el texto del estado:")
for estado in pivot_df['Estado_Normalizado'].unique():
    print(f"Estado: '{estado}' (longitud: {len(estado)})")

# Mejorar la lógica de filtrado para manejar variaciones
autorizadas = pivot_df[pivot_df['Estado_Normalizado'].str.contains('AUTORIZADA', case=False, na=False)]
devueltas = pivot_df[pivot_df['Estado_Normalizado'].str.contains('DEVUELTA', case=False, na=False)]
ingresadas = pivot_df[pivot_df['Estado_Normalizado'].str.contains('INGRESADA', case=False, na=False)]
en_tramite = pivot_df[pivot_df['Estado_Normalizado'].str.contains('TRÁMITE', case=False, na=False)]

print(f"\nDespués de mejorar el filtrado:")
print(f"Filas AUTORIZADA: {len(autorizadas)}")
print(f"Filas DEVUELTA: {len(devueltas)}")
print(f"Filas INGRESADA: {len(ingresadas)}")
print(f"Filas EN TRÁMITE: {len(en_tramite)}")

autorizadas = autorizadas.dropna(axis=1, how='all')
devueltas = devueltas.dropna(axis=1, how='all')
ingresadas = ingresadas.dropna(axis=1, how='all')
en_tramite = en_tramite.dropna(axis=1, how='all')
try:
    autorizadas.drop(['', 'Detalle prestaciones'], axis=1, inplace=True, errors='ignore')
    devueltas.drop(['Archivo Certificado', 'Archivo Orden médica', 'Archivo Receta médica', 'Archivo documento'], axis=1, inplace=True, errors='ignore')
    ingresadas.drop(['Archivo documento'], axis=1, inplace=True, errors='ignore')
    en_tramite.drop(['Archivo documento'], axis=1, inplace=True, errors='ignore')

    # Convertir fechas solo si las columnas existen
    if 'Fecha de emisión' in autorizadas.columns:
        autorizadas['Fecha de emisión'] = pd.to_datetime(autorizadas['Fecha de emisión'], format='%d/%m/%Y').dt.date
        autorizadas = autorizadas.sort_values(by="Fecha de emisión", ascending=False)
    
    if 'Fecha ingreso' in devueltas.columns:
        devueltas['Fecha ingreso'] = pd.to_datetime(devueltas['Fecha ingreso'], format='%d/%m/%Y').dt.date
        devueltas = devueltas.sort_values(by="Fecha ingreso", ascending=False)
    
    if 'Fecha ingreso' in ingresadas.columns:
        ingresadas['Fecha ingreso'] = pd.to_datetime(ingresadas['Fecha ingreso'], format='%d/%m/%Y').dt.date
        ingresadas = ingresadas.sort_values(by="Fecha ingreso", ascending=False)
    
    if 'Fecha ingreso' in en_tramite.columns:
        en_tramite['Fecha ingreso'] = pd.to_datetime(en_tramite['Fecha ingreso'], format='%d/%m/%Y').dt.date
        en_tramite = en_tramite.sort_values(by="Fecha ingreso", ascending=False)
except Exception as e:
    print(f"Error al procesar las columnas: {e}")
    pass

# Agregar diagnóstico final antes de guardar
print("\n=== DIAGNÓSTICO FINAL ===")
print(f"autorizadas.shape: {autorizadas.shape}")
print(f"devueltas.shape: {devueltas.shape}")
print(f"ingresadas.shape: {ingresadas.shape}")
print(f"en_tramite.shape: {en_tramite.shape}")

# Verificar si en_tramite está vacío
if len(en_tramite) == 0:
    print("⚠️  ADVERTENCIA: en_tramite está vacío!")
    # Mostrar todas las filas que podrían ser "EN TRÁMITE"
    posibles_en_tramite = pivot_df[pivot_df['Estado_Normalizado'].str.contains('TRÁMITE', case=False, na=False)]
    print(f"Filas que contienen 'TRÁMITE': {len(posibles_en_tramite)}")
    if len(posibles_en_tramite) > 0:
        print("Estados encontrados con 'TRÁMITE':")
        print(posibles_en_tramite['Estado_Normalizado'].unique())
else:
    print("✅ en_tramite tiene datos")

autorizadas.to_excel('autorizadas.xlsx')
devueltas.to_excel('devueltas.xlsx')
ingresadas.to_excel('ingresadas.xlsx')
en_tramite.to_excel('en_tramite.xlsx')