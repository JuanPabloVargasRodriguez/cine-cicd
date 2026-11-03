"""Informe educativo de cine. Solo utiliza la biblioteca estándar de Python 3.12."""

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import html
import os
from pathlib import Path
import re
import sys
import tempfile


OBLIGATORIAS = ("imdb", "title", "year", "budget", "domgross")
BASE = Path(__file__).resolve().parent


class ErrorDatos(ValueError):
    """Un error de datos con fila y columna identificables."""


def error(fila, columna, mensaje):
    raise ErrorDatos(f"Fila {fila}, columna {columna}: {mensaje}")


def numero_opcional(valor, fila, columna):
    valor = valor.strip()
    if valor in ("", "NA", "#N/A"):
        return None
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        error(fila, columna, "se esperaba un número o NA/vacío")
    if not numero.is_finite() or numero < 0:
        error(fila, columna, "debe ser un número finito no negativo")
    return numero


def validar_csv(fuente):
    """Lee y valida un archivo de texto abierto; conserva las columnas adicionales.

    Convierte year a int y los importes a Decimal o None; decodifica title.
    Las filas indicadas son líneas físicas del CSV (incluida la cabecera).
    """
    lector = csv.DictReader(fuente, strict=True)
    peliculas = []
    identificadores = set()
    try:
        cabecera = lector.fieldnames
        if not cabecera:
            error(1, "cabecera", "falta la cabecera")
        for columna in OBLIGATORIAS:
            if columna not in cabecera:
                error(1, columna, "falta la columna obligatoria")
        if any(not nombre.strip() for nombre in cabecera):
            error(1, "cabecera", "hay nombres de columna vacíos")
        if len(set(cabecera)) != len(cabecera):
            error(1, "cabecera", "hay nombres de columna duplicados")
        for registro in lector:
            fila = lector.line_num
            if None in registro:
                error(fila, "campos", "la fila tiene más campos que la cabecera")
            for columna, valor in registro.items():
                if valor is None:
                    error(fila, columna, "falta un campo en la fila")
            identificador = registro["imdb"].strip()
            if not identificador:
                error(fila, "imdb", "el identificador está vacío")
            if not re.fullmatch(r"tt[0-9]+", identificador):
                error(fila, "imdb", "debe comenzar por 'tt' seguido únicamente de dígitos")
            if identificador in identificadores:
                error(fila, "imdb", "el identificador está duplicado")
            identificadores.add(identificador)
            titulo = html.unescape(registro["title"]).strip()
            if not titulo:
                error(fila, "title", "el título está vacío")
            anio = registro["year"].strip()
            if not re.fullmatch(r"[0-9]+", anio):
                error(fila, "year", "se esperaba un entero positivo")
            try:
                anio = int(anio)
            except ValueError:
                error(fila, "year", "el entero es demasiado largo")
            if anio <= 0:
                error(fila, "year", "se esperaba un entero positivo")
            registro.update(imdb=identificador, title=titulo, year=anio)
            for columna in ("budget", "domgross"):
                registro[columna] = numero_opcional(registro[columna], fila, columna)
            peliculas.append(registro)
    except csv.Error as exc:
        error(max(lector.line_num, 1), "CSV", str(exc))
    if not peliculas:
        error(2, "registro", "se necesita al menos una película")
    return peliculas


def cargar_datos(ruta):
    """Abre un CSV UTF-8 y devuelve sus registros validados."""
    with Path(ruta).open(encoding="utf-8-sig", newline="") as fuente:
        return validar_csv(fuente)


def calcular_estadisticas(peliculas):
    """Calcula solo con budget y domgross disponibles, sin imputar faltantes."""
    presupuestos = [p["budget"] for p in peliculas if p["budget"] is not None]
    ingresos = [p["domgross"] for p in peliculas if p["domgross"] is not None]
    # Amplía la precisión para sumar importes sin redondeo intermedio.
    valores = presupuestos + ingresos
    with localcontext() as contexto:
        if valores:
            contexto.prec = max(28, max(v.adjusted() for v in valores)
                                - min(v.as_tuple().exponent for v in valores)
                                + len(str(len(valores))) + 4)
        suma = sum(ingresos, Decimal(0)) if ingresos else None
        media = sum(presupuestos, Decimal(0)) / len(presupuestos) if presupuestos else None
    return {
        "total": len(peliculas),
        "suma_domgross": suma,
        "media_budget": media,
        "ingresos_faltantes": len(peliculas) - len(ingresos),
        "ingresos_disponibles": len(ingresos),
        "presupuestos_disponibles": len(presupuestos),
        "top_diez": sorted((p for p in peliculas if p["domgross"] is not None),
                           key=lambda p: p["domgross"], reverse=True)[:10],
    }


def importe(valor):
    return "No disponible" if valor is None else f"{valor:,.2f}"


def generar_html(peliculas, estadisticas, estudiante, fecha=None, sha=None):
    """Devuelve HTML completo sin escribir archivos ni consultar servicios."""
    fecha = datetime.now(timezone.utc) if fecha is None else fecha
    if fecha.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria")
    fecha_utc = fecha.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sha = (os.environ.get("GITHUB_SHA") or "local") if sha is None else sha
    escapar = lambda valor: html.escape(str(valor), quote=True)
    top = estadisticas["top_diez"]
    maximo = top[0]["domgross"] if top else Decimal(0)
    barras = []
    for pelicula in top:
        ancho = pelicula["domgross"] / maximo * 100 if maximo else Decimal(0)
        barras.append(
            f'<li><div class="dato-barra"><span>{escapar(pelicula["title"])}</span> '
            f'<strong>{importe(pelicula["domgross"])} USD</strong></div>'
            f'<div class="pista" aria-hidden="true"><div class="barra" style="width:{ancho:.2f}%"></div></div></li>'
        )
    filas = []
    for pelicula in peliculas[:10]:
        celdas = [importe(pelicula[c]) if c in ("budget", "domgross")
                  else pelicula[c] for c in OBLIGATORIAS]
        filas.append("<tr>" + "".join(f"<td>{escapar(c)}</td>" for c in celdas) + "</tr>")
    return f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cine: informe educativo de CI/CD</title>
<style>
:root {{color-scheme:light;--tinta:#182c48;--papel:#f3f4f8;--oro:#c19a5b;--vino:#8c364a;--gris:#526075;--linea:#dce1e9}}
* {{box-sizing:border-box}} html {{scroll-padding-top:1rem}}
body {{font-family:"Segoe UI",Arial,sans-serif;margin:0;background:var(--papel);color:var(--tinta);line-height:1.6}}
.contenedor {{width:min(1180px,calc(100% - 64px));margin:auto}}
.saltar {{position:absolute;left:1rem;top:-100px;background:white;padding:1rem;z-index:2}}
.saltar:focus {{top:1rem}} a {{color:#275276;text-underline-offset:4px}}
a:focus-visible,.tabla:focus-visible {{outline:3px solid var(--vino);outline-offset:5px}}
header {{background:var(--tinta);color:white;padding:24px 0 48px;border-bottom:8px solid var(--oro)}}
.cabecera {{display:flex;justify-content:space-between;align-items:center;gap:1rem;border-bottom:1px solid #536178;padding-bottom:18px}}
.marca {{font-weight:650;font-size:1.05rem}} .autor {{text-align:right;font-size:.85rem;color:#d9e0eb}}
.autor strong {{display:block;color:white;font-size:1rem}} nav {{display:flex;gap:1.5rem;flex-wrap:wrap;margin-top:22px}}
nav a {{color:#e3e8f1;font-size:.85rem}} h1 {{font-family:Georgia,"Times New Roman",serif;font-weight:400;font-size:clamp(2.8rem,6vw,5rem);line-height:1.08;max-width:18ch;margin:36px 0 20px;letter-spacing:-.04em}}
.bajada {{max-width:58ch;color:#d9e0eb;font-size:1.05rem;margin:0}}
.aviso {{font-size:.8rem;color:#f5dfb9;border:1px dashed #8b7c64;display:inline-block;padding:7px 12px;margin:24px 0 0}}
main {{padding-top:36px;padding-bottom:48px}} section {{margin-bottom:42px}}
h2 {{font-family:Georgia,"Times New Roman",serif;font-weight:400;font-size:clamp(1.7rem,3vw,2.2rem);line-height:1.2;margin:0 0 14px;letter-spacing:-.02em}}
p {{max-width:78ch}} .introduccion {{color:var(--gris);margin:0 0 24px}}
.metricas {{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:white;border:1px solid var(--linea);border-radius:8px;overflow:hidden}}
.metrica {{padding:24px 20px;min-width:0;border-right:1px solid var(--linea);display:flex;flex-direction:column}}
.metrica:last-child {{border:0}} .etiqueta {{font-size:.86rem;min-height:4.8em;color:var(--gris)}}
.metrica strong {{display:block;font-size:clamp(1.15rem,1.8vw,1.6rem);line-height:1.3;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;margin:12px 0}}
.metrica:first-child strong {{font-family:Georgia,serif;font-size:2.8rem;margin-top:0}}
.metrica small {{color:var(--gris);font-size:.75rem;margin-top:auto}} .faltantes strong {{color:var(--vino)}}
.nota {{font-size:.8rem;color:var(--gris);margin:14px 0 0}}
.panel {{background:white;border:1px solid var(--linea);border-radius:8px;padding:30px}}
.encabezado-seccion {{display:flex;align-items:baseline;justify-content:space-between;gap:1rem}}
.unidad {{color:var(--gris);font-size:.8rem;white-space:nowrap}}
.descripcion {{color:var(--gris);font-size:.9rem;margin:0 0 24px}}
ol {{margin:0;padding-left:28px}} li {{padding:10px 0 10px 12px}} li::marker {{color:var(--gris);font-size:.8rem;font-variant-numeric:tabular-nums}}
.dato-barra {{display:flex;justify-content:space-between;align-items:baseline;gap:20px;font-size:.93rem}}
.dato-barra span {{overflow-wrap:anywhere}} .dato-barra strong {{font-size:.8rem;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}}
.pista {{height:9px;background:#eef1f6;margin-top:9px;border-radius:2px;overflow:hidden}}
.barra {{height:100%;background:#5a718f;border-radius:2px}} li:first-child .barra {{background:var(--oro)}}
.tabla {{overflow-x:auto;border:1px solid var(--linea);border-radius:6px}}
table {{border-collapse:collapse;width:100%;background:white;font-size:.88rem;white-space:nowrap}}
caption {{text-align:left;padding:14px 18px;font-size:.78rem;color:var(--gris);background:#f7f8fb}}
th,td {{border-bottom:1px solid var(--linea);padding:14px 18px;text-align:left}}
th {{background:#edf0f5;font-weight:600;font-size:.8rem}} td:nth-child(2) {{white-space:normal;min-width:190px}}
td:nth-child(n+3),th:nth-child(n+3) {{text-align:right;font-variant-numeric:tabular-nums}}
tbody tr:nth-child(even) {{background:#f8f9fc}} tbody tr:last-child td {{border-bottom:0}} tbody tr:hover {{background:#edf2f8}}
.metodologia {{border-left:3px solid var(--oro);padding:4px 0 4px 22px;margin:30px 0 0}} .metodologia h3 {{font-size:1rem;margin:0 0 8px}}
.metodologia p {{margin:0;font-size:.88rem;color:var(--gris)}}
footer {{border-top:1px solid var(--linea);padding:28px 0 38px;color:var(--gris);font-size:.8rem}}
.pie {{display:grid;grid-template-columns:2fr 1fr;gap:40px}} footer p {{margin:0 0 10px}} .generacion {{overflow-wrap:anywhere}}
@media(min-width:1400px) {{.metrica strong {{font-size:1.6rem}}}}
@media(max-width:900px) {{.metricas {{grid-template-columns:repeat(2,minmax(0,1fr))}} .metrica:nth-child(2) {{border-right:0}} .metrica:nth-child(-n+2) {{border-bottom:1px solid var(--linea)}} .etiqueta {{min-height:3.2em}}}}
@media(max-width:600px) {{.contenedor {{width:calc(100% - 32px)}} header {{padding-top:18px}} .cabecera {{align-items:flex-start}} .marca {{font-size:.9rem;max-width:14ch}} .autor {{max-width:19ch}} .autor strong {{font-size:.88rem}} nav {{gap:18px}} .panel {{padding:22px 16px}} .metrica {{padding:18px 14px}} .metrica strong {{font-size:1.05rem}} .etiqueta {{font-size:.78rem;min-height:5em}} .encabezado-seccion {{display:block}} .unidad {{display:block;margin-bottom:12px}} .dato-barra {{display:block}} .dato-barra strong {{display:block;font-size:.75rem}} li {{padding-left:4px}} .pie {{grid-template-columns:1fr;gap:16px}}}}
@media print {{body {{background:white}} .contenedor {{width:100%}} header {{background:white;color:var(--tinta);padding:0 0 20px}} .autor,.autor strong,.bajada {{color:var(--tinta)}} nav,.saltar {{display:none}} .aviso {{color:var(--tinta)}} .panel {{padding:16px}} .pista,.barra {{print-color-adjust:exact}} .tabla {{overflow:visible}} table {{white-space:normal}} .metrica strong {{font-size:1rem}}}}
</style></head>
<body><a class="saltar" href="#resumen">Saltar al informe</a>
<header><div class="contenedor">
<div class="cabecera"><span class="marca">Archivo de cine / CI/CD</span>
<div class="autor">Estudiante<strong>{escapar(estudiante)}</strong></div></div>
<nav aria-label="Secciones del informe"><a href="#resumen">La muestra</a><a href="#taquilla">Top diez</a><a href="#registros">Primeros registros</a></nav>
<h1>El cine, en cifras.</h1>
<p class="bajada">Una mirada a la taquilla y los presupuestos de una muestra histórica de películas. Informe educativo de CI/CD.</p>
<p class="aviso">Copia educativa: contiene modificaciones simuladas</p>
</div></header>
<main class="contenedor"><section id="resumen" aria-labelledby="titulo-resumen">
<h2 id="titulo-resumen">Una muestra, cuatro cifras</h2>
<p class="introduccion">Esta muestra histórica utiliza domgross: ingresos de taquilla en Estados Unidos,
en dólares nominales del año de estreno. No incluye intgross ni columnas ajustadas
por inflación. Las sumas corresponden únicamente a esta muestra histórica y no
constituyen una comparación ajustada por inflación.</p>
<div class="metricas">
<div class="metrica"><span class="etiqueta">Total de películas</span><strong>{estadisticas['total']}</strong><small>Registros de esta muestra</small></div>
<div class="metrica"><span class="etiqueta">Suma de domgross disponible<br>Muestra histórica · USD nominales</span>
<strong>{importe(estadisticas['suma_domgross'])}</strong><small>{estadisticas['ingresos_disponibles']} valores disponibles</small></div>
<div class="metrica"><span class="etiqueta">Media del presupuesto disponible<br>USD nominales</span>
<strong>{importe(estadisticas['media_budget'])}</strong><small>{estadisticas['presupuestos_disponibles']} valores disponibles</small></div>
<div class="metrica faltantes"><span class="etiqueta">Ingresos faltantes</span><strong>{estadisticas['ingresos_faltantes']}</strong><small>Excluidos del cálculo de ingresos</small></div>
</div>
<p class="nota">NA, #N/A y vacío son faltantes; se excluyen de las sumas y medias. Si no hay valores
disponibles, se indica «No disponible». Los importes se muestran con dos decimales,
coma de miles y punto decimal.</p></section>
<section id="taquilla" class="panel" aria-labelledby="titulo-taquilla">
<div class="encabezado-seccion"><h2 id="titulo-taquilla">Diez películas con mayor domgross</h2><span class="unidad">Taquilla de EE. UU.</span></div>
<p class="descripcion">Taquilla en Estados Unidos, USD nominales del año de estreno, sin ajuste por inflación.
En los empates se conserva el orden original.</p>
<ol>{''.join(barras)}</ol>
{'<p>No hay ingresos disponibles para el gráfico.</p>' if not top else ''}
</section>
<section id="registros" aria-labelledby="titulo-registros">
<h2 id="titulo-registros">Primeras diez filas en su orden original</h2>
<p class="descripcion">El inicio del archivo, tal como fue cargado. Permite identificar cambios aunque una película no aparezca en el top diez.</p>
<div class="tabla" tabindex="0" role="region" aria-label="Primeros registros; tabla desplazable horizontalmente"><table><caption>Importes en USD nominales; faltantes indicados expresamente.</caption>
<thead><tr>{''.join(f'<th scope="col">{c}</th>' for c in OBLIGATORIAS)}</tr></thead>
<tbody>{''.join(filas)}</tbody></table></div>
<aside class="metodologia"><h3>Cómo leer este informe</h3>
<p>Los ingresos corresponden a la taquilla en Estados Unidos. Los presupuestos y los ingresos se muestran por separado;
esta muestra histórica no establece una comparación ajustada por inflación.</p></aside>
</section></main>
<footer><div class="contenedor pie"><div><p>Fuente y atribución: FiveThirtyEight,
<a href="https://github.com/fivethirtyeight/data/tree/master/bechdel">datos de películas (Bechdel)</a>.
Licencia <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
Esta copia educativa contiene modificaciones simuladas y un informe derivado.</p></div>
<div class="generacion"><p>Generado: {fecha_utc}</p><p>GITHUB_SHA: {escapar(sha)}</p></div></div></footer>
</body></html>
"""


def publicar_html(contenido, destino):
    """Reemplaza el informe de forma atómica una vez completada la generación."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        os.replace(temporal, destino)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estudiante", default=os.environ.get("NOMBRE_ESTUDIANTE") or "Juan Pablo Vargas",
                        help="Nombre del estudiante (también NOMBRE_ESTUDIANTE)")
    argumentos = parser.parse_args(argv)
    try:
        peliculas = cargar_datos(BASE / "datos" / "movies.csv")
        estadisticas = calcular_estadisticas(peliculas)
        contenido = generar_html(peliculas, estadisticas, argumentos.estudiante)
        publicar_html(contenido, BASE / "public" / "index.html")
    except (ErrorDatos, OSError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Informe generado: public/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
