# -*- coding: utf-8 -*-
"""
Orquestador de publicacion del visor Neumo23 2026 - Nuble.

Capa EXTERNA a actualizar_visor.py: este script NUNCA importa ni modifica
actualizar_visor.py. Lo ejecuta como subproceso y reacciona unicamente a su
codigo de salida y a los archivos que deja en /data. Toda la logica de Git vive
aqui, nunca en actualizar_visor.py.

FLUJO:
  1. Ejecutar ACTUALIZADOR/actualizar_visor.py como subproceso.
     - Si termina con codigo != 0: abortar. Cero comandos Git.
  2. Segunda validacion INDEPENDIENTE de los 7 JSON de /data (defensa en
     profundidad: no confiar ciegamente en que el codigo 0 garantiza que /data
     quedo bien). Reutiliza las mismas reglas que ya usa actualizar_visor.py
     (sumas, ausencia de RUN/"<10"/agrupaciones/variables sensibles), sin
     inventar reglas nuevas.
     - Si encuentra algo sospechoso: abortar. Cero comandos Git.
  3. `git status --porcelain` + allowlist explicito de rutas permitidas.
     - Si hay cambios fuera del allowlist: abortar. Cero comandos Git.
     - Si no hay cambios: terminar con exito, sin commit ni push.
  4. `git add` con rutas EXPLICITAS (nunca `-A`, `.` ni `--all`).
  5. `git commit` (datos) con mensaje generado desde data/resumen.json + data/actualizacion.json.
  6. `git push origin main` (nunca --force, nunca cambia de rama).
  7. Registrar el resultado en HISTORIAL/publicaciones.json y publicarlo con un
     SEGUNDO commit+push propio (ver nota de diseño dentro de main(), justo
     antes de este segundo commit, sobre por que se hace asi en vez de dejar
     el registro pendiente para la siguiente corrida).

Codigos de salida:
  0 = OK (se publico algo, o no habia nada que publicar)
  1 = abortado ANTES de cualquier operacion Git (dato invalido, allowlist, etc.)
  2 = el commit se creo localmente pero el push a GitHub fallo

NO modifica Programaticas_2026.csv, la nomina Excel, ni actualizar_visor.py.
NO cambia la clasificacion metodologica ni los indicadores.
"""
import sys
import os
import re
import json
import subprocess
import traceback
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================================
# CONFIGURACION
# ============================================================
VISOR_DIR = Path(__file__).resolve().parent.parent  # .../VISOR_NEUMO23_2026_NUBLE
DATA_DIR = VISOR_DIR / "data"
HISTORIAL_DIR = VISOR_DIR / "HISTORIAL"
ACTUALIZAR_SCRIPT = Path(__file__).resolve().parent / "actualizar_visor.py"

# Debe mantenerse igual a N_UNIVERSO_ESPERADO en actualizar_visor.py. Se duplica
# intencionalmente: esta es una validacion INDEPENDIENTE, no debe depender de
# importar constantes del otro script.
N_UNIVERSO_ESPERADO = 6480

ARCHIVOS_DATA_ESPERADOS = [
    "resumen.json", "comunas.json", "evolucion_mensual.json",
    "comuna_mes.json", "establecimientos.json", "hallazgo_607.json", "actualizacion.json",
]

PATRON_RUN = re.compile(r"\b\d{7,8}[0-9K]\b")
PATRON_DV_TOKEN = re.compile(r"\bDV\b", re.IGNORECASE)
PALABRAS_SENSIBLES = [
    "SECTOR", "CODIGO.FAMILIA.SECTOR", "GENERO", "HOGAR.O.INSTITUCION",
    "FECHA.DE.NACIMIENTO", "CALLE.RESIDENCIAL", "NUMERO.RESIDENCIAL",
    "NOMBRE", "APELLIDO", "DIRECCION", "DOMICILIO", "RUT", "TELEFONO", "EMAIL",
]

# Allowlist: unicas rutas que este script puede llevar a `git add`. Cualquier
# otra ruta detectada por `git status --porcelain` aborta todo el proceso.
ALLOWLIST_EXACTAS = {
    "data/resumen.json", "data/comunas.json", "data/evolucion_mensual.json",
    "data/comuna_mes.json", "data/establecimientos.json", "data/hallazgo_607.json",
    "data/actualizacion.json", "HISTORIAL/historial.csv", "HISTORIAL/publicaciones.json",
}
ALLOWLIST_PATRON = re.compile(r"^HISTORIAL/actualizacion_\d{8}_\d{6}\.json$")


def log(msg):
    print(msg, flush=True)


def ruta_permitida(ruta):
    ruta = ruta.replace("\\", "/")
    return ruta in ALLOWLIST_EXACTAS or bool(ALLOWLIST_PATRON.match(ruta))


def ejecutar_git(args):
    return subprocess.run(
        ["git"] + args, cwd=str(VISOR_DIR),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# ============================================================
# PASO 1: ejecutar actualizar_visor.py como SUBPROCESO (nunca importado)
# ============================================================
def ejecutar_actualizacion():
    log("=" * 60)
    log(" PASO 1/6: Ejecutando ACTUALIZADOR/actualizar_visor.py")
    log("=" * 60)
    # Se hereda stdout/stderr del proceso actual para mostrar su salida en vivo,
    # tal como la vería el usuario si lo corriera directamente.
    proceso = subprocess.run([sys.executable, str(ACTUALIZAR_SCRIPT)], cwd=str(VISOR_DIR))
    return proceso.returncode


# ============================================================
# PASO 2: segunda validacion INDEPENDIENTE sobre /data (no confia en el
# codigo de salida del paso 1; reutiliza las mismas reglas ya existentes)
# ============================================================
def validar_data_independiente():
    problemas = []
    contenidos = {}

    for nombre in ARCHIVOS_DATA_ESPERADOS:
        fp = DATA_DIR / nombre
        if not fp.exists():
            problemas.append(f"Falta el archivo data/{nombre}")
            continue
        texto = fp.read_text(encoding="utf-8")
        try:
            contenidos[nombre] = json.loads(texto)
        except Exception as e:
            problemas.append(f"data/{nombre} no es JSON valido: {e}")
            continue

        # Escaneo defensivo de privacidad sobre el TEXTO crudo del archivo.
        if PATRON_RUN.search(texto):
            problemas.append(f"data/{nombre}: contiene un patron tipo RUN")
        if "<10" in texto:
            problemas.append(f"data/{nombre}: contiene supresion '<10' (no debe aplicarse en este visor)")
        if "Otros establecimiento" in texto or '"(varios)"' in texto:
            problemas.append(f"data/{nombre}: contiene agrupacion de establecimientos (no debe aplicarse)")
        if PATRON_DV_TOKEN.search(texto):
            problemas.append(f"data/{nombre}: contiene el token 'DV'")
        for palabra in PALABRAS_SENSIBLES:
            if palabra.upper() in texto.upper():
                problemas.append(f"data/{nombre}: contiene variable sensible '{palabra}'")

    if problemas:
        return problemas, contenidos  # no seguir con chequeos de consistencia si falta/rompe algo

    # --- Chequeos de consistencia (mismas reglas que validar_tmp() en
    # actualizar_visor.py, aplicadas ahora sobre /data ya publicado) ---
    resumen = contenidos["resumen.json"]
    cats = resumen.get("categorias", {})

    for clave in ("encontrado_valido", "sin_registro", "requiere_revision", "no_cumple_criterio", "sin_run"):
        if clave not in cats:
            problemas.append(f"resumen.json: falta la categoria '{clave}'")
    if problemas:
        return problemas, contenidos

    universo = resumen.get("universo_nominal")
    if universo != N_UNIVERSO_ESPERADO:
        problemas.append(f"resumen.json: universo_nominal={universo}, esperado {N_UNIVERSO_ESPERADO}")

    suma_cats = sum(cats.values())
    if suma_cats != N_UNIVERSO_ESPERADO:
        problemas.append(f"resumen.json: suma de categorias ({suma_cats}) != {N_UNIVERSO_ESPERADO}")

    n607 = resumen.get("n_607_fuera_nomina")
    if not isinstance(n607, int):
        problemas.append("resumen.json: n_607_fuera_nomina ausente o no es un entero")

    comunas = contenidos["comunas.json"]
    suma_comunas = sum(c.get("total_nomina", 0) for c in comunas)
    if suma_comunas != N_UNIVERSO_ESPERADO:
        problemas.append(f"comunas.json: suma de total_nomina ({suma_comunas}) != {N_UNIVERSO_ESPERADO}")

    evol = contenidos["evolucion_mensual.json"]
    suma_evol = sum(m.get("nuevos_encontrados", 0) for m in evol)
    if suma_evol != cats.get("encontrado_valido"):
        problemas.append(
            f"evolucion_mensual.json: suma ({suma_evol}) != encontrado_valido ({cats.get('encontrado_valido')})")

    estab = contenidos["establecimientos.json"]
    suma_estab = sum(e.get("total_encontrados", 0) for e in estab)
    if suma_estab != cats.get("encontrado_valido"):
        problemas.append(
            f"establecimientos.json: suma ({suma_estab}) != encontrado_valido ({cats.get('encontrado_valido')})")

    hallazgo = contenidos["hallazgo_607.json"]
    total_607 = hallazgo.get("total")
    if total_607 != n607:
        problemas.append(f"hallazgo_607.json: total ({total_607}) != resumen.n_607_fuera_nomina ({n607})")
    suma_estab_607 = sum(e.get("n", 0) for e in hallazgo.get("por_establecimiento", []))
    suma_comuna_607 = sum(c.get("n", 0) for c in hallazgo.get("por_comuna_residencia", []))
    if not (total_607 == suma_estab_607 == suma_comuna_607):
        problemas.append(
            f"hallazgo_607.json: inconsistente (total={total_607} "
            f"suma_establecimientos={suma_estab_607} suma_comunas={suma_comuna_607})")

    actualizacion = contenidos["actualizacion.json"]
    if actualizacion.get("estado") != "OK":
        problemas.append(f"actualizacion.json: estado='{actualizacion.get('estado')}', esperado 'OK'")

    return problemas, contenidos


# ============================================================
# PASO 3: git status + allowlist
# ============================================================
def obtener_cambios_git():
    r = ejecutar_git(["status", "--porcelain"])
    cambios = []
    for linea in r.stdout.splitlines():
        if not linea.strip():
            continue
        ruta = linea[3:].strip()
        if ruta.startswith('"') and ruta.endswith('"'):
            ruta = ruta[1:-1]
        cambios.append(ruta.replace("\\", "/"))
    return cambios


def construir_mensaje_commit(resumen, actualizacion):
    cats = resumen["categorias"]
    fecha = resumen.get("fecha_generacion_datos") or datetime.now().strftime("%Y-%m-%d")
    asunto = f"Actualizar visor Neumo23 2026 - {fecha}"
    cuerpo = "\n".join([
        f"Registro válido encontrado: {cats['encontrado_valido']}",
        f"Sin registro válido encontrado: {cats['sin_registro']}",
        f"Requiere revisión: {cats['requiere_revision']}",
        f"No cumple año/territorio: {cats['no_cumple_criterio']}",
        f"RUN no disponible: {cats['sin_run']}",
        f"Fuera de nómina: {resumen['n_607_fuera_nomina']}",
        f"Registros Neumo23 válidos en la base: {actualizacion.get('registros_neumo23_validos', 's/d')}",
        "",
        "Generado automáticamente por publicar_visor.py.",
    ])
    return asunto, cuerpo


# ============================================================
# PASO 4 (registro): HISTORIAL/publicaciones.json
# ============================================================
def escribir_registro_publicacion(commit_hash, push_exitoso, mensaje_commit):
    """
    Escritura PURA (sin git): agrega un registro a HISTORIAL/publicaciones.json
    y devuelve la ruta del archivo. No decide si se commitea; eso lo hace quien
    llama a esta funcion (main()), porque solo ahi se sabe si corresponde
    intentar un commit adicional o no (ver NOTA DE DISEÑO en main()).
    """
    HISTORIAL_DIR.mkdir(exist_ok=True)
    ruta = HISTORIAL_DIR / "publicaciones.json"
    registros = []
    if ruta.exists():
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(data, list):
                registros = data
        except Exception:
            registros = []
    ahora = datetime.now()
    registros.append({
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M:%S"),
        "commit_hash": commit_hash,
        "push_exitoso": push_exitoso,
        "mensaje_commit": mensaje_commit,
    })
    ruta.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# ============================================================
# MAIN
# ============================================================
def main():
    log("=" * 60)
    log(" PUBLICACIÓN DEL VISOR NEUMO23 2026 - ÑUBLE")
    log("=" * 60)

    rc = ejecutar_actualizacion()
    if rc != 0:
        log(f"\n[ERROR] actualizar_visor.py terminó con código {rc}.")
        log("[ERROR] No se ejecutará ningún comando Git.")
        log("Los datos publicados anteriormente (si los hay) permanecen intactos.")
        sys.exit(1)
    log("\n[OK] actualizar_visor.py finalizó correctamente (código 0).")

    log("\n" + "=" * 60)
    log(" PASO 2/6: Validación independiente de /data")
    log("=" * 60)
    problemas, contenidos = validar_data_independiente()
    if problemas:
        log("[ERROR] La validación independiente encontró problemas:")
        for p in problemas:
            log(f"  - {p}")
        log("[ERROR] No se ejecutará ningún comando Git.")
        sys.exit(1)
    log("[OK] Los 7 JSON de data/ son válidos, consistentes y no contienen datos sensibles.")

    log("\n" + "=" * 60)
    log(" PASO 3/6: git status y allowlist")
    log("=" * 60)
    rama = ejecutar_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if rama != "main":
        log(f"[ERROR] La rama actual es '{rama}', se esperaba 'main'. Se aborta por seguridad.")
        sys.exit(1)

    cambios = obtener_cambios_git()
    if not cambios:
        log("No hay cambios que publicar.")
        log("El visor ya contiene los datos actuales.")
        sys.exit(0)

    log(f"Cambios detectados ({len(cambios)}):")
    for c in cambios:
        log(f"  - {c}")

    fuera_de_lista = [c for c in cambios if not ruta_permitida(c)]
    if fuera_de_lista:
        log("\n[ERROR] Se detectaron cambios fuera del allowlist:")
        for c in fuera_de_lista:
            log(f"  - {c}")
        log("No se ejecutará commit ni push.")
        sys.exit(1)
    log("[OK] Todos los cambios están dentro del allowlist permitido.")

    log("\n" + "=" * 60)
    log(" PASO 4/6: git add (rutas explícitas)")
    log("=" * 60)
    r = ejecutar_git(["add", "--"] + cambios)
    if r.returncode != 0:
        log(f"[ERROR] git add falló:\n{r.stdout}\n{r.stderr}")
        sys.exit(1)
    log(f"[OK] {len(cambios)} archivo(s) agregados al área de staging.")

    log("\n" + "=" * 60)
    log(" PASO 5/6: git commit")
    log("=" * 60)
    resumen = contenidos["resumen.json"]
    actualizacion = contenidos["actualizacion.json"]
    asunto, cuerpo = construir_mensaje_commit(resumen, actualizacion)
    r = ejecutar_git(["commit", "-m", asunto, "-m", cuerpo])
    if r.returncode != 0:
        salida = (r.stdout or "") + (r.stderr or "")
        if "nothing to commit" in salida:
            log("No hay cambios que publicar (nada que comitear).")
            sys.exit(0)
        log(f"[ERROR] git commit falló:\n{r.stdout}\n{r.stderr}")
        sys.exit(1)
    commit_hash = ejecutar_git(["rev-parse", "HEAD"]).stdout.strip()
    log(f"[OK] Commit creado localmente: {commit_hash}")
    log(f"Asunto: {asunto}")

    log("\n" + "=" * 60)
    log(" PASO 6/6: git push origin main")
    log("=" * 60)
    r = ejecutar_git(["push", "origin", "main"])
    push_exitoso = (r.returncode == 0)
    if push_exitoso:
        log("[OK] Push realizado correctamente. GitHub Pages se actualizará en 1-2 minutos.")
    else:
        log("[ERROR] El commit fue creado localmente, pero NO pudo publicarse en GitHub.")
        log(f"Hash del commit local: {commit_hash}")
        log(f"Detalle del error de git push:\n{r.stdout}\n{r.stderr}")
        log("Los datos SÍ cambiaron localmente en git, pero GitHub Pages NO se actualizó.")
        log("Reintente el push manualmente más tarde (por ejemplo: git push origin main).")

    # ------------------------------------------------------------
    # NOTA DE DISEÑO — registro del hash en HISTORIAL/publicaciones.json:
    #
    # El hash de un commit solo se conoce DESPUES de crearlo, así que no puede
    # incluirse en el mismo commit que describe (sería circular). En vez de
    # dejar esa escritura pendiente sin commitear hasta la siguiente ejecución
    # (diseño anterior), aquí se hace un SEGUNDO commit, inmediato, exclusivo
    # para ese registro, y se empuja con su propio `git push`. Resultado neto
    # en el camino feliz: dos commits, dos pushes, pero CERO cambios
    # pendientes al terminar esta corrida — `git status` queda limpio.
    #
    # Este segundo commit solo se intenta si el primer push (el de los datos)
    # tuvo éxito: si ya sabemos que git push está fallando, no tiene sentido
    # insistir de inmediato. En ese caso el registro igual se escribe en disco
    # (para no perder la información), pero queda sin commitear — el único
    # residual posible, y ocurre exclusivamente cuando ya hay un problema de
    # conectividad/credenciales que el usuario debe resolver de todas formas.
    # Ese registro pendiente se recuperará solo, sin código adicional: la
    # próxima vez que CUALQUIER commit se empuje (el de datos del día
    # siguiente, o un `git push` manual), se llevará también este de encima,
    # porque `git push` siempre envía todos los commits locales pendientes.
    # ------------------------------------------------------------
    ruta_registro = escribir_registro_publicacion(commit_hash, push_exitoso, asunto)

    if not push_exitoso:
        log(f"\n[AVISO] Se guardó el registro en {ruta_registro.name}, pero quedará sin "
            f"commitear hasta que el push vuelva a funcionar (se incluirá automáticamente "
            f"en el próximo push exitoso).")
        sys.exit(2)

    log("\n" + "=" * 60)
    log(" Registrando publicación en HISTORIAL/publicaciones.json (commit adicional)")
    log("=" * 60)
    r = ejecutar_git(["add", "--", "HISTORIAL/publicaciones.json"])
    if r.returncode != 0:
        log(f"[AVISO] No se pudo hacer git add de publicaciones.json: {r.stderr}")
        log("La publicación de los datos YA fue exitosa; solo el registro del historial quedó pendiente.")
        log("\nPublicación completada correctamente.")
        sys.exit(0)

    mensaje_log = f"Registrar publicación en HISTORIAL - {datetime.now().strftime('%Y-%m-%d')} ({commit_hash[:7]})"
    r = ejecutar_git(["commit", "-m", mensaje_log])
    if r.returncode != 0:
        salida = (r.stdout or "") + (r.stderr or "")
        if "nothing to commit" not in salida:
            log(f"[AVISO] No se pudo comitear publicaciones.json: {r.stdout}\n{r.stderr}")
        log("La publicación de los datos YA fue exitosa; solo el registro del historial quedó pendiente.")
        log("\nPublicación completada correctamente.")
        sys.exit(0)

    r = ejecutar_git(["push", "origin", "main"])
    if r.returncode == 0:
        log("[OK] Registro de publicación también publicado en GitHub.")
    else:
        log("[AVISO] El registro se commiteó localmente, pero ese segundo push falló.")
        log("Esto NO afecta a los datos ya publicados (commit anterior); se subirá solo, "
            "sin intervención, en el próximo push exitoso.")

    log("\nPublicación completada correctamente.")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("[ERROR] Fallo inesperado en publicar_visor.py:")
        log(traceback.format_exc())
        log("[ERROR] No se garantiza el estado de Git a partir de aquí. Revise 'git status' manualmente.")
        sys.exit(1)
