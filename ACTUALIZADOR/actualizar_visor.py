# -*- coding: utf-8 -*-
"""
Actualizacion diaria del visor Neumo23 2026 - Nuble.

Consolida en UN solo script la logica ya validada previamente en el proyecto
(generar_datos_visor.py + fix_comuna_completa.py + generar_agregados_publicos.py),
para que la actualizacion diaria no dependa de scripts sueltos ni duplique logica.

QUE HACE:
  1. Valida que existan y sean legibles la base RNI (Programaticas_2026.csv) y la
     nomina operacional (Nacidos 1961 cobertura Nuble.xlsx, hoja COMPLETA).
  2. Lee la base RNI en una sola pasada (chunks), identifica registros Neumo23 y
     aplica los 3 filtros de exclusion previa (REGISTRO_ELIMINADO="NO",
     VACUNA_ADMINISTRADA="SI", DOSIS!="EPRO"). Un registro que falle CUALQUIERA de
     estos 3 se excluye por completo: no es valido, y si ademas es el UNICO
     registro Neumo23 de esa persona, la deja en "Requiere revision" (evidencia de
     un intento no valido), nunca en "Registro valido" ni en "Sin registro".
  3. Cruza la base filtrada contra la nomina de 6.480 (por RUN+DV normalizado) y
     clasifica en las 5 categorias ya validadas.
  4. Calcula el grupo independiente de "fuera de nomina" (607).
  5. Genera los 6 JSON agregados + un archivo de metadatos de actualizacion, TODO
     en una carpeta temporal primero.
  6. Valida estructuralmente los JSON generados (sumas, ausencia de RUN/nombres,
     ausencia de supresion "<10" y de agrupacion "Otros establecimientos", 607
     separado del universo). Si CUALQUIER validacion falla, NO se toca /data:
     el visor sigue mostrando los datos de la actualizacion anterior.
  7. Si todo pasa, reemplaza atomicamente los archivos de /data y registra la
     ejecucion en HISTORIAL/.

NO modifica Programaticas_2026.csv ni la nomina Excel (solo lectura).
NO cambia la clasificacion metodologica ni el diseno del visor.
NO aplica supresion n<10 ni agrupa establecimientos (politica vigente del visor,
uso interno/local).

Uso:
    python actualizar_visor.py
Codigo de salida: 0 = OK, distinto de 0 = error (y /data queda intacto).
"""
import sys
import io
import os
import re
import json
import time
import shutil
import unicodedata
import traceback
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

# ============================================================
# CONFIGURACION (unico lugar donde se definen rutas y umbrales)
# ============================================================
# VISOR_RNI_CSV_OVERRIDE: variable de entorno opcional, solo para pruebas de robustez
# (permite apuntar a un archivo de prueba sin tocar nunca la base real). En uso normal
# no se define y se usa la ruta de siempre.
RNI_CSV = Path(os.environ.get("VISOR_RNI_CSV_OVERRIDE") or r"D:\PROG\NACIONAL\Programaticas_2026.csv")
NOMINA_XLSX = Path(r"D:\PROG\NACIONAL\Nacidos 1961 cobertura Ñuble.xlsx")

VISOR_DIR = Path(__file__).resolve().parent.parent  # .../VISOR_NEUMO23_2026_NUBLE
DATA_DIR = VISOR_DIR / "data"
TMP_DIR = VISOR_DIR / "_tmp_actualizacion"
HISTORIAL_DIR = VISOR_DIR / "HISTORIAL"

N_UNIVERSO_ESPERADO = 6480          # tamaño conocido de la nomina COMPLETA
MIN_FILAS_RNI = 1_000_000           # piso de sanidad: si hay menos, se sospecha
                                     # archivo truncado/incompleto (el archivo real
                                     # ronda ~4.000.000 de filas). Ajustable.

NEUMO23_SET = {"Neumocócica polisacárida 23V", "Neumocócica polisacárida 23V (sector privado)"}

COLUMNAS_RNI_REQUERIDAS = [
    "RUN", "NOMBRE_VACUNA", "VACUNA_ADMINISTRADA", "REGISTRO_ELIMINADO", "DOSIS",
    "FECHA_NACIMIENTO", "FECHA_INMUNIZACION", "CODIGO_DEIS", "ESTABLECIMIENTO",
    "COMUNA_OCURR", "COMUNA_RESIDENCIA",
]
COLUMNAS_NOMINA_REQUERIDAS = ["RUN", "DV", "COMUNA.RESIDENCIAL"]

COMUNAS_NUBLE_CANONICAS = [
    "Bulnes", "Chillán", "Chillán Viejo", "El Carmen", "Pemuco", "Pinto", "Quillón", "San Ignacio",
    "Cobquecura", "Coelemu", "Ninhue", "Portezuelo", "Quirihue", "Ránquil", "Trehuaco",
    "Coihueco", "Ñiquén", "San Carlos", "San Fabián", "San Nicolás", "Yungay",
]
COMUNAS_NUBLE_SET_BUCKET = set(COMUNAS_NUBLE_CANONICAS) | {"Treguaco"}
SIN_DATO_VALORES = {"", "(sin dato)", "No Informado", "Desconocido", "Sin Informacion", "Sin Información"}

RUN_DIGITS_RE = re.compile(r"^\d{7,8}$")
DV_RE = re.compile(r"^[0-9K]$")
RUN_NACIONAL_RE = re.compile(r"^\d{7,8}[0-9K]$")
PATRON_RUN_EN_TEXTO = re.compile(r"\b\d{7,8}[0-9K]\b")


def log(msg):
    print(msg, flush=True)


def error_fatal(msg):
    log(f"[ERROR] {msg}")
    log("[ERROR] La actualizacion NO fue aplicada.")
    log("Los datos anteriores del visor se mantienen intactos.")
    try:
        guardar_historial(resumen=None, actualizacion=None, estado="ERROR", mensaje_error=msg)
    except Exception:
        pass  # el registro de historial nunca debe impedir informar el error original
    sys.exit(1)


# ============================================================
# Utilidades de comuna (identicas a las ya validadas en el proyecto)
# ============================================================
def strip_accents(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def norm_txt(s):
    return strip_accents(s or "").upper().strip()


_NUBLE_NORM = set(norm_txt(c) for c in COMUNAS_NUBLE_CANONICAS) | {"TREGUACO"}


def es_comuna_nuble(s):
    return norm_txt(s) in _NUBLE_NORM


def comuna_bucket(c):
    if c in SIN_DATO_VALORES:
        return "Sin dato / no informado"
    if c in COMUNAS_NUBLE_SET_BUCKET:
        return "Trehuaco" if c == "Treguaco" else c
    return "Fuera de la Región de Ñuble (agregado)"


def norm_id(x):
    return re.sub(r"[.\-\s]", "", str(x or "")).strip().upper()


def build_key(run, dv):
    rn, dn = norm_id(run), norm_id(dv)
    if not rn or not dn or not RUN_DIGITS_RE.match(rn) or not DV_RE.match(dn):
        return None
    return rn + dn


def pct(a, b):
    return round(100 * a / b, 2) if b else None


# ============================================================
# PASO 0: validaciones previas (robustez, sin tocar nada aun)
# ============================================================
def validar_entradas():
    if not RNI_CSV.exists():
        error_fatal(f"No se encontró la base RNI en la ruta esperada: {RNI_CSV}")
    tam = RNI_CSV.stat().st_size
    if tam < 10_000_000:
        error_fatal(f"El archivo {RNI_CSV.name} pesa solo {tam:,} bytes; parece incompleto o corrupto.")

    try:
        cabecera = pd.read_csv(RNI_CSV, sep="|", encoding="cp1252", dtype=str,
                                keep_default_na=False, nrows=5, engine="c")
    except Exception as e:
        error_fatal(f"No se pudo leer {RNI_CSV.name} (¿encoding o delimitador distinto?): {e}")

    faltantes = [c for c in COLUMNAS_RNI_REQUERIDAS if c not in cabecera.columns]
    if faltantes:
        error_fatal(f"Faltan columnas requeridas en {RNI_CSV.name}: {faltantes}")

    if not NOMINA_XLSX.exists():
        error_fatal(f"No se encontró la nómina operacional en: {NOMINA_XLSX}")
    try:
        nom_cabecera = pd.read_excel(NOMINA_XLSX, sheet_name="COMPLETA", dtype=str,
                                      keep_default_na=False, nrows=5)
    except Exception as e:
        error_fatal(f"No se pudo leer la hoja COMPLETA de la nómina: {e}")
    faltantes_nom = [c for c in COLUMNAS_NOMINA_REQUERIDAS if c not in nom_cabecera.columns]
    if faltantes_nom:
        error_fatal(f"Faltan columnas requeridas en la nómina (hoja COMPLETA): {faltantes_nom}")

    return tam


# ============================================================
# PASO 1: nomina operacional (fuente independiente, NUNCA modificada)
# ============================================================
def cargar_nomina():
    nom = pd.read_excel(NOMINA_XLSX, sheet_name="COMPLETA", dtype=str, keep_default_na=False,
                         usecols=["RUN", "DV", "COMUNA.RESIDENCIAL"])
    n_universo = len(nom)
    if n_universo != N_UNIVERSO_ESPERADO:
        error_fatal(
            f"La nómina operacional tiene {n_universo} filas; se esperaban {N_UNIVERSO_ESPERADO}. "
            f"No se continúa para evitar recalcular sobre una nómina distinta a la oficial. "
            f"Si el cambio es intencional (nueva nómina oficial), actualice N_UNIVERSO_ESPERADO "
            f"en este script tras confirmarlo explícitamente."
        )
    key_list = [build_key(r, d) for r, d in zip(nom["RUN"], nom["DV"])]
    nomina_keys = set(k for k in key_list if k is not None)
    comuna_por_fila = list(nom["COMUNA.RESIDENCIAL"])
    return n_universo, key_list, nomina_keys, comuna_por_fila


# ============================================================
# PASO 2: pasada unica por la base RNI (filtros de exclusion previa incluidos)
# ============================================================
def leer_rni(nomina_keys):
    neumo_por_run = defaultdict(list)
    n_filas_leidas = 0
    n_neumo23_bruto = 0
    n_neumo23_validos = 0
    n_epro = 0

    for chunk in pd.read_csv(RNI_CSV, sep="|", encoding="cp1252", dtype=str, keep_default_na=False,
                              chunksize=400_000, quoting=3, engine="c", on_bad_lines="skip"):
        n_filas_leidas += len(chunk)
        sub = chunk[chunk["NOMBRE_VACUNA"].isin(NEUMO23_SET)]
        if len(sub) == 0:
            continue
        n_neumo23_bruto += len(sub)
        keys_nat = sub["RUN"].map(norm_id)
        es_epro = (sub["DOSIS"] == "EPRO")
        n_epro += int(es_epro.sum())

        for k, admin, elim, dosis, fecha_nac, fecha, cod_deis, establec, comuna_ocurr, comuna_resid_prog in zip(
            keys_nat, sub["VACUNA_ADMINISTRADA"], sub["REGISTRO_ELIMINADO"], sub["DOSIS"],
            sub["FECHA_NACIMIENTO"], sub["FECHA_INMUNIZACION"], sub["CODIGO_DEIS"], sub["ESTABLECIMIENTO"],
            sub["COMUNA_OCURR"], sub["COMUNA_RESIDENCIA"]
        ):
            if not k or not RUN_NACIONAL_RE.match(k):
                continue
            # Filtros de exclusion previa: los 3 deben cumplirse simultaneamente
            # para que el registro cuente como "valido". Un registro que falle
            # cualquiera de ellos NUNCA participa en ENCONTRADO_VALIDO,
            # NO_CUMPLE_CRITERIO ni en el hallazgo 607; solo puede sostener
            # REQUIERE_REVISION si es el unico registro Neumo23 de la persona.
            valido = (admin == "SI" and elim == "NO" and dosis != "EPRO")
            if valido:
                n_neumo23_validos += 1
            neumo_por_run[k].append(dict(
                valido=valido,
                anio_1961=(fecha_nac or "").startswith("1961"),
                vacunado_nuble=es_comuna_nuble(comuna_ocurr),
                reside_nuble_prog=es_comuna_nuble(comuna_resid_prog),
                fecha=fecha, cod_deis=cod_deis, establecimiento=establec,
                comuna_ocurr=comuna_ocurr, comuna_resid_prog=comuna_resid_prog,
            ))

    if n_filas_leidas < MIN_FILAS_RNI:
        error_fatal(
            f"Solo se leyeron {n_filas_leidas:,} filas de {RNI_CSV.name} "
            f"(mínimo esperado: {MIN_FILAS_RNI:,}). El archivo parece incompleto o truncado."
        )
    if n_neumo23_bruto == 0:
        error_fatal(
            "No se encontró ningún registro Neumo23 en la base RNI. "
            "Verifique que el archivo corresponde a la base correcta."
        )

    metadatos = dict(
        n_filas_leidas=n_filas_leidas,
        n_neumo23_bruto=n_neumo23_bruto,
        n_neumo23_validos=n_neumo23_validos,
        n_epro_excluidos=n_epro,
    )
    return neumo_por_run, metadatos


# ============================================================
# PASO 3: clasificacion de las 6.480 + grupo 607 (logica ya validada)
# ============================================================
def clasificar(key_list, nomina_keys, neumo_por_run):
    categoria_por_key = {}
    for k in key_list:
        if k is None:
            continue
        rows = neumo_por_run.get(k)
        if not rows:
            categoria_por_key[k] = "SIN_REGISTRO"
            continue
        validos = [r for r in rows if r["valido"]]
        if not validos:
            categoria_por_key[k] = "REQUIERE_REVISION"
            continue
        cumple_1961 = any(r["anio_1961"] for r in validos)
        cumple_vacun = any(r["vacunado_nuble"] for r in validos)
        cumple_reside = any(r["reside_nuble_prog"] for r in validos)
        if cumple_1961 and cumple_reside and cumple_vacun:
            categoria_por_key[k] = "ENCONTRADO_VALIDO"
        else:
            categoria_por_key[k] = "NO_CUMPLE_CRITERIO"

    cat_counts = Counter(categoria_por_key.values())
    cat_counts["SIN_RUN"] = sum(1 for k in key_list if k is None)

    fuera_nomina_keys = []
    for k, rows in neumo_por_run.items():
        if k in nomina_keys:
            continue
        validos = [r for r in rows if r["valido"]]
        if not validos:
            continue
        cumple_1961 = any(r["anio_1961"] for r in validos)
        cumple_reside = any(r["reside_nuble_prog"] for r in validos)
        cumple_vacun = any(r["vacunado_nuble"] for r in validos)
        if cumple_1961 and cumple_reside and cumple_vacun:
            fuera_nomina_keys.append(k)

    detalle_encontrados = {k: [r for r in neumo_por_run[k] if r["valido"]]
                            for k in nomina_keys if categoria_por_key.get(k) == "ENCONTRADO_VALIDO"}
    detalle_607 = {k: [r for r in neumo_por_run[k] if r["valido"]] for k in fuera_nomina_keys}

    return categoria_por_key, dict(cat_counts), fuera_nomina_keys, detalle_encontrados, detalle_607


# ============================================================
# PASO 4: generar los 6 JSON agregados (sin supresion, sin agrupar
# establecimientos -- politica vigente del visor interno) en TMP_DIR
# ============================================================
def generar_json_temporales(n_universo, cat_counts, comuna_por_fila, key_list, categoria_por_key,
                             fuera_nomina_keys, detalle_encontrados, detalle_607, metadatos_rni):
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True)

    # --- filas completas (las 6.480, incluye SIN_RUN con su comuna real) ---
    filas_6480 = []
    for i, k in enumerate(key_list):
        if k is None:
            filas_6480.append({"comuna": comuna_por_fila[i], "categoria": "SIN_RUN"})
        else:
            filas_6480.append({"comuna": comuna_por_fila[i], "categoria": categoria_por_key.get(k, "SIN_REGISTRO")})
    assert len(filas_6480) == n_universo

    # --- 1. resumen.json ---
    resumen = {
        "universo_nominal": n_universo,
        "categorias": {
            "encontrado_valido": cat_counts.get("ENCONTRADO_VALIDO", 0),
            "sin_registro": cat_counts.get("SIN_REGISTRO", 0),
            "requiere_revision": cat_counts.get("REQUIERE_REVISION", 0),
            "no_cumple_criterio": cat_counts.get("NO_CUMPLE_CRITERIO", 0),
            "sin_run": cat_counts.get("SIN_RUN", 0),
        },
        "suma_verificacion": sum(cat_counts.values()),
        "pct_avance_sobre_nomina": pct(cat_counts.get("ENCONTRADO_VALIDO", 0), n_universo),
        "n_607_fuera_nomina": len(fuera_nomina_keys),
        "fecha_generacion_datos": datetime.now().strftime("%Y-%m-%d"),
        "fuente_datos_nacionales": f"{RNI_CSV.name} (extracto usado en esta generación)",
    }
    if resumen["suma_verificacion"] != n_universo:
        error_fatal(f"La suma de categorías ({resumen['suma_verificacion']}) no coincide con el "
                    f"universo ({n_universo}). Se aborta antes de escribir ningún JSON.")
    (TMP_DIR / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 2. comunas.json ---
    comuna_cat = defaultdict(Counter)
    for fila in filas_6480:
        comuna_cat[comuna_bucket(fila["comuna"])][fila["categoria"]] += 1
    comunas_out = []
    for comuna, counts in sorted(comuna_cat.items(), key=lambda x: -sum(x[1].values())):
        total = sum(counts.values())
        enc = counts.get("ENCONTRADO_VALIDO", 0)
        comunas_out.append({
            "comuna": comuna,
            "total_nomina": total,
            "encontrado_valido": enc,
            "sin_registro": counts.get("SIN_REGISTRO", 0),
            "requiere_revision": counts.get("REQUIERE_REVISION", 0),
            "no_cumple_criterio": counts.get("NO_CUMPLE_CRITERIO", 0),
            "sin_run": counts.get("SIN_RUN", 0),
            "pct_encontrado_valido": pct(enc, total),
        })
    (TMP_DIR / "comunas.json").write_text(json.dumps(comunas_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # comuna de la nomina por key (para comuna_mes.json)
    comuna_nomina_por_key = {}
    for i, k in enumerate(key_list):
        if k is not None:
            comuna_nomina_por_key[k] = comuna_por_fila[i]

    # --- 3. evolucion_mensual.json ---
    def mes_de(rows):
        fechas = sorted(r["fecha"] for r in rows if r["fecha"])
        return fechas[0][:7] if fechas else None

    mes_counts = Counter()
    for k, rows in detalle_encontrados.items():
        m = mes_de(rows)
        if m:
            mes_counts[m] += 1
    meses_out = []
    acumulado = 0
    for m in sorted(mes_counts):
        acumulado += mes_counts[m]
        meses_out.append({"mes": m, "nuevos_encontrados": mes_counts[m], "acumulado": acumulado})
    (TMP_DIR / "evolucion_mensual.json").write_text(json.dumps(meses_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 4. comuna_mes.json ---
    cm = defaultdict(Counter)
    for k, rows in detalle_encontrados.items():
        m = mes_de(rows)
        if not m:
            continue
        cm[comuna_bucket(comuna_nomina_por_key.get(k))][m] += 1
    comuna_mes_out = [{"comuna": c, "mes": m, "n": n} for c, meses in cm.items() for m, n in meses.items()]
    (TMP_DIR / "comuna_mes.json").write_text(json.dumps(comuna_mes_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 5. establecimientos.json (todos individuales, sin agrupar) ---
    estab_counts = Counter()
    estab_comuna_ocurr = {}
    for k, rows in detalle_encontrados.items():
        rep = sorted(rows, key=lambda r: r["fecha"])[0]
        key_e = (rep["cod_deis"] or "(sin código)", rep["establecimiento"] or "(sin dato)")
        estab_counts[key_e] += 1
        estab_comuna_ocurr[key_e] = rep["comuna_ocurr"]
    estab_out = [
        {"codigo_deis": cod, "establecimiento": nombre, "comuna_ocurrencia": estab_comuna_ocurr[(cod, nombre)],
         "total_encontrados": n}
        for (cod, nombre), n in estab_counts.most_common()
    ]
    (TMP_DIR / "establecimientos.json").write_text(json.dumps(estab_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 6. hallazgo_607.json (todos individuales, sin agrupar) ---
    comuna_607 = Counter()
    estab_607 = Counter()
    estab_607_comuna = {}
    mes_607 = Counter()
    for k in fuera_nomina_keys:
        rows = detalle_607[k]
        rep = sorted(rows, key=lambda r: r["fecha"])[0]
        comuna_607[comuna_bucket(rep["comuna_resid_prog"])] += 1
        key_e = (rep["cod_deis"] or "(sin código)", rep["establecimiento"] or "(sin dato)")
        estab_607[key_e] += 1
        estab_607_comuna[key_e] = rep["comuna_ocurr"]
        m = rep["fecha"][:7] if rep["fecha"] else None
        if m:
            mes_607[m] += 1
    hallazgo_607 = {
        "total": len(fuera_nomina_keys),
        "advertencia": "Este grupo NO forma parte de la nómina oficial de 6.480 personas. Fue identificado "
                       "mediante cruce con Programaticas_2026.csv (RNI 2026). Su eventual incorporación a la "
                       "nómina debe ser evaluada por la instancia responsable de la estrategia. Estas cifras "
                       "NUNCA deben sumarse al universo de 6.480 en los indicadores principales.",
        "por_comuna_residencia": [{"comuna_residencia": c, "n": n} for c, n in comuna_607.most_common()],
        "por_establecimiento": [
            {"codigo_deis": cod, "establecimiento": nombre, "comuna_ocurrencia": estab_607_comuna[(cod, nombre)], "n": n}
            for (cod, nombre), n in estab_607.most_common()
        ],
        "por_mes": [{"mes": m, "n": mes_607[m]} for m in sorted(mes_607)],
    }
    (TMP_DIR / "hallazgo_607.json").write_text(json.dumps(hallazgo_607, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- metadatos de actualizacion (informativos; el visor aun no los muestra) ---
    ahora = datetime.now()
    actualizacion = {
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M:%S"),
        "archivo_procesado": RNI_CSV.name,
        "ruta_archivo_procesado": str(RNI_CSV),
        "tamano_bytes": RNI_CSV.stat().st_size,
        "registros_leidos_rni": metadatos_rni["n_filas_leidas"],
        "registros_neumo23_brutos": metadatos_rni["n_neumo23_bruto"],
        "registros_neumo23_validos": metadatos_rni["n_neumo23_validos"],
        "registros_epro_excluidos": metadatos_rni["n_epro_excluidos"],
        "estado": "OK",
    }
    (TMP_DIR / "actualizacion.json").write_text(json.dumps(actualizacion, ensure_ascii=False, indent=2), encoding="utf-8")

    return resumen, actualizacion


# ============================================================
# PASO 5: validaciones estructurales sobre lo generado en TMP_DIR
# (equivalente a validacion_final.py, pero corre ANTES de tocar /data)
# ============================================================
def validar_tmp(n_universo):
    problemas = []

    resumen = json.loads((TMP_DIR / "resumen.json").read_text(encoding="utf-8"))
    suma = sum(resumen["categorias"].values())
    if suma != n_universo:
        problemas.append(f"suma de categorías ({suma}) != universo ({n_universo})")

    pct_esp = pct(resumen["categorias"]["encontrado_valido"], n_universo)
    if resumen["pct_avance_sobre_nomina"] != pct_esp:
        problemas.append(f"pct_avance_sobre_nomina inconsistente: {resumen['pct_avance_sobre_nomina']} vs {pct_esp}")

    comunas = json.loads((TMP_DIR / "comunas.json").read_text(encoding="utf-8"))
    suma_comunas = sum(c["total_nomina"] for c in comunas)
    if suma_comunas != n_universo:
        problemas.append(f"suma de comunas ({suma_comunas}) != universo ({n_universo})")

    evol = json.loads((TMP_DIR / "evolucion_mensual.json").read_text(encoding="utf-8"))
    suma_evol = sum(m["nuevos_encontrados"] for m in evol)
    if suma_evol != resumen["categorias"]["encontrado_valido"]:
        problemas.append(f"suma de evolución mensual ({suma_evol}) != encontrado_valido "
                          f"({resumen['categorias']['encontrado_valido']})")

    estab = json.loads((TMP_DIR / "establecimientos.json").read_text(encoding="utf-8"))
    suma_estab = sum(e["total_encontrados"] for e in estab)
    if suma_estab != resumen["categorias"]["encontrado_valido"]:
        problemas.append(f"suma de establecimientos ({suma_estab}) != encontrado_valido "
                          f"({resumen['categorias']['encontrado_valido']})")

    hallazgo = json.loads((TMP_DIR / "hallazgo_607.json").read_text(encoding="utf-8"))
    n607 = resumen["n_607_fuera_nomina"]
    suma_estab_607 = sum(e["n"] for e in hallazgo["por_establecimiento"])
    suma_comuna_607 = sum(c["n"] for c in hallazgo["por_comuna_residencia"])
    if not (hallazgo["total"] == n607 == suma_estab_607 == suma_comuna_607):
        problemas.append(f"607 inconsistente: total={hallazgo['total']} n_resumen={n607} "
                          f"suma_estab={suma_estab_607} suma_comuna={suma_comuna_607}")

    # privacidad: sin RUN, sin supresion, sin agrupacion "Otros", sin variables sensibles
    sensibles = ["SECTOR", "CODIGO.FAMILIA.SECTOR", "GENERO", "HOGAR.O.INSTITUCION",
                 "FECHA.DE.NACIMIENTO", "CALLE.RESIDENCIAL", "NUMERO.RESIDENCIAL", "NOMBRE", "APELLIDO"]
    for fp in TMP_DIR.glob("*.json"):
        contenido = fp.read_text(encoding="utf-8")
        if PATRON_RUN_EN_TEXTO.search(contenido):
            problemas.append(f"{fp.name}: contiene un patrón tipo RUN")
        if "<10" in contenido:
            problemas.append(f"{fp.name}: contiene supresión '<10' (no debe aplicarse en este visor)")
        if "Otros establecimiento" in contenido or "(varios)" in contenido:
            problemas.append(f"{fp.name}: contiene agrupación de establecimientos (no debe aplicarse)")
        for s in sensibles:
            if s.upper() in contenido.upper():
                problemas.append(f"{fp.name}: contiene variable sensible '{s}'")

    return problemas


# ============================================================
# PASO 6: reemplazo atomico de /data + historial
# ============================================================
ARCHIVOS_DATA = ["resumen.json", "comunas.json", "evolucion_mensual.json",
                 "comuna_mes.json", "establecimientos.json", "hallazgo_607.json", "actualizacion.json"]


def reemplazar_data():
    DATA_DIR.mkdir(exist_ok=True)
    for nombre in ARCHIVOS_DATA:
        origen = TMP_DIR / nombre
        destino = DATA_DIR / nombre
        os.replace(str(origen), str(destino))  # atomico en el mismo volumen


def guardar_historial(resumen, actualizacion, estado, mensaje_error=None):
    HISTORIAL_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    registro = {
        "fecha": actualizacion.get("fecha") if actualizacion else datetime.now().strftime("%Y-%m-%d"),
        "hora": actualizacion.get("hora") if actualizacion else datetime.now().strftime("%H:%M:%S"),
        "archivo_procesado": actualizacion.get("archivo_procesado") if actualizacion else RNI_CSV.name,
        "estado": estado,
        "mensaje_error": mensaje_error,
        "universo": resumen["universo_nominal"] if resumen else None,
        "categorias": resumen["categorias"] if resumen else None,
        "n_607_fuera_nomina": resumen.get("n_607_fuera_nomina") if resumen else None,
        "registros_neumo23_validos": actualizacion.get("registros_neumo23_validos") if actualizacion else None,
    }
    (HISTORIAL_DIR / f"actualizacion_{ts}.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = HISTORIAL_DIR / "historial.csv"
    es_nuevo = not csv_path.exists()
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        if es_nuevo:
            f.write("fecha,hora,archivo_procesado,estado,universo,encontrado_valido,sin_registro,"
                    "requiere_revision,no_cumple_criterio,sin_run,n_607_fuera_nomina,registros_neumo23_validos\n")
        cat = registro["categorias"] or {}
        f.write(",".join(str(x) for x in [
            registro["fecha"], registro["hora"], registro["archivo_procesado"], registro["estado"],
            registro["universo"] or "", cat.get("encontrado_valido", ""), cat.get("sin_registro", ""),
            cat.get("requiere_revision", ""), cat.get("no_cumple_criterio", ""), cat.get("sin_run", ""),
            registro["n_607_fuera_nomina"] or "", registro["registros_neumo23_validos"] or "",
        ]) + "\n")


# ============================================================
# MAIN
# ============================================================
def main():
    t0 = time.time()
    log("[OK] Verificando archivos de entrada...")
    tam_rni = validar_entradas()
    log(f"[OK] Base encontrada: {RNI_CSV.name} ({tam_rni:,} bytes)")

    log("[OK] Base leída (validaciones de estructura superadas)")
    n_universo, key_list, nomina_keys, comuna_por_fila = cargar_nomina()

    neumo_por_run, metadatos_rni = leer_rni(nomina_keys)
    log(f"[OK] Filtros aplicados ({metadatos_rni['n_neumo23_bruto']:,} registros Neumo23 brutos -> "
        f"{metadatos_rni['n_neumo23_validos']:,} válidos; {metadatos_rni['n_epro_excluidos']:,} EPRO excluidos)")

    categoria_por_key, cat_counts, fuera_nomina_keys, detalle_encontrados, detalle_607 = clasificar(
        key_list, nomina_keys, neumo_por_run)
    log("[OK] Cruce con nómina")
    log(f"[OK] Indicadores calculados: {cat_counts}  (suma={sum(cat_counts.values())})  "
        f"fuera_de_nomina={len(fuera_nomina_keys)}")

    resumen, actualizacion = generar_json_temporales(
        n_universo, cat_counts, comuna_por_fila, key_list, categoria_por_key,
        fuera_nomina_keys, detalle_encontrados, detalle_607, metadatos_rni)
    log("[OK] JSON generados (en carpeta temporal, aún no aplicados)")

    problemas = validar_tmp(n_universo)
    if problemas:
        guardar_historial(resumen, actualizacion, estado="ERROR",
                           mensaje_error="; ".join(problemas))
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        error_fatal("Las validaciones NO se superaron:\n  - " + "\n  - ".join(problemas))
    log("[OK] Validaciones superadas")

    reemplazar_data()
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    guardar_historial(resumen, actualizacion, estado="OK")
    log("[OK] Historial guardado")

    log("")
    log(f"Universo: {resumen['universo_nominal']}")
    for k, v in resumen["categorias"].items():
        log(f"  {k}: {v}")
    log(f"Fuera de nómina: {resumen['n_607_fuera_nomina']}")
    log(f"\nTiempo total: {time.time()-t0:.1f} s")
    log("\nActualización completada correctamente.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("[ERROR] Fallo inesperado durante la actualización:")
        log(traceback.format_exc())
        log("[ERROR] La actualización NO fue aplicada.")
        log("Los datos anteriores del visor se mantienen intactos.")
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        sys.exit(1)
