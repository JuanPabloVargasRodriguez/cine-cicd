# Cine: proyecto educativo de CI/CD

Requiere Python 3.12 y únicamente su biblioteca estándar. No instala paquetes,
descarga datos ni utiliza servicios externos.

Desde la carpeta del proyecto, ejecutar las pruebas y generar el informe:

```console
python -m unittest discover -v
python analizar.py
```

Para mostrar el nombre del estudiante en la página:

```console
python analizar.py --estudiante "Juan Pablo Vargas"
```

También se puede definir `NOMBRE_ESTUDIANTE`; sin configuración aparece
«Juan Pablo Vargas» como nombre predeterminado.
El programa lee `datos/movies.csv` y crea `public/index.html` (incluida la
carpeta). Las rutas se resuelven respecto a `analizar.py`.
Abrir el HTML generado en un navegador. El documento incluye su CSS y no
necesita conexión para visualizarse; los enlaces de atribución son referencias.

El CSV debe incluir `imdb`, `title`, `year`, `budget` y `domgross`.
Cada `imdb` debe ser único y tener el prefijo `tt` seguido de uno o más
dígitos del 0 al 9 (por ejemplo, `tt1711425`). Se eliminan los espacios de
los extremos antes de validarlo. Esta regla comprueba el formato localmente,
sin consultar si el identificador existe en IMDb.
Las demás columnas se conservan en los registros cargados, pero no intervienen
en los cálculos ni en la página. `NA` o vacío significan datos faltantes, nunca
cero. También se admite `#N/A`, presente en la copia original, como faltante.
Se admiten importes cero. Si todos los importes de una medida faltan,
aparece «No disponible». Los importes se calculan con `Decimal` y se muestran
con dos decimales.

`domgross` corresponde a taquilla en Estados Unidos, en USD nominales del año
de estreno. La suma describe esta muestra histórica: no se suma con `intgross`
ni se combina con columnas ajustadas por inflación, y no permite comparar
importes ajustados por inflación. La media excluye los presupuestos faltantes.
El gráfico muestra hasta diez ingresos disponibles en orden descendente; los
empates conservan el orden del archivo. La tabla muestra las primeras diez
filas originales, aunque no aparezcan en el gráfico.

Un error de validación indica la fila física del CSV (cabecera = 1) y la columna,
devuelve un código distinto de cero y conserva cualquier informe anterior.
La publicación se realiza mediante reemplazo atómico tras validar y generar
todo el contenido. Importar `analizar` no ejecuta el programa.
Las funciones `validar_csv`, `cargar_datos`, `calcular_estadisticas` y
`generar_html` pueden utilizarse por separado. Las pruebas usan datos pequeños
propios y no fijan cifras del CSV local.

El informe registra fecha UTC y `GITHUB_SHA`, o `local` si no está definido.

Fuente: [FiveThirtyEight, datos de Bechdel](https://github.com/fivethirtyeight/data/tree/master/bechdel).
Licencia: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
La copia y el informe se identifican con el aviso:
«Copia educativa: contiene modificaciones simuladas».
