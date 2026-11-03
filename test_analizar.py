"""Pruebas independientes de datos/movies.csv; ejecutar con unittest discover."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analizar


CABECERA = "imdb,title,year,budget,domgross\n"


def datos(filas):
    return analizar.validar_csv(io.StringIO(CABECERA + filas))


class TestAnalizar(unittest.TestCase):
    def test_suma_y_media_conocidas(self):
        peliculas = datos("tt1,Uno,2001,10,30\ntt2,Dos,2002,20,50\n")
        resultado = analizar.calcular_estadisticas(peliculas)
        self.assertEqual(resultado["total"], 2)
        self.assertEqual(resultado["suma_domgross"], Decimal("80"))
        self.assertEqual(resultado["media_budget"], Decimal("15"))
        self.assertEqual(resultado["top_diez"][0]["imdb"], "tt2")

    def test_na_y_vacio_no_se_convierten_en_cero(self):
        peliculas = datos("tt1,Uno,2001,10,NA\ntt2,Dos,2002,NA,0\ntt3,Tres,2003,,\n")
        self.assertIsNone(peliculas[0]["domgross"])
        self.assertIsNone(peliculas[1]["budget"])
        self.assertIsNone(peliculas[2]["domgross"])
        resultado = analizar.calcular_estadisticas(peliculas)
        self.assertEqual(resultado["media_budget"], Decimal("10"))
        self.assertEqual(resultado["suma_domgross"], Decimal("0"))
        self.assertEqual(resultado["ingresos_faltantes"], 2)
        self.assertEqual(len(resultado["top_diez"]), 1)

    def test_todos_los_importes_faltantes(self):
        resultado = analizar.calcular_estadisticas(datos("tt1,Uno,2001,NA,\n"))
        self.assertIsNone(resultado["suma_domgross"])
        self.assertIsNone(resultado["media_budget"])
        self.assertEqual(resultado["top_diez"], [])

    def test_marcador_faltante_del_csv_original(self):
        peliculas = datos("tt1,Uno,2001,#N/A,#N/A\n")
        self.assertIsNone(peliculas[0]["budget"])
        self.assertIsNone(peliculas[0]["domgross"])

    def test_rechazo_domgross_negativo(self):
        with self.assertRaisesRegex(analizar.ErrorDatos, r"Fila 2, columna domgross"):
            datos("tt1,Uno,2001,10,-1\n")

    def test_rechazo_columna_obligatoria_ausente(self):
        with self.assertRaisesRegex(analizar.ErrorDatos, r"Fila 1, columna domgross"):
            analizar.validar_csv(io.StringIO("imdb,title,year,budget\ntt1,Uno,2001,10\n"))

    def test_validaciones_de_cabecera_y_registros(self):
        casos = [
            ("", "cabecera"),
            (CABECERA, "registro"),
            (CABECERA.rstrip() + ",imdb\n", "cabecera"),
            (CABECERA + "tt1,Uno,2001,10,20,extra\n", "campos"),
            (CABECERA + "tt1,Uno,2001,10\n", "domgross"),
            (CABECERA + ",Uno,2001,10,20\n", "imdb"),
            (CABECERA + "tt1,Uno,2001,10,20\ntt1,Dos,2002,1,2\n", "imdb"),
            (CABECERA + "tt1, ,2001,10,20\n", "title"),
        ]
        for texto, columna in casos:
            with self.subTest(texto=texto):
                with self.assertRaisesRegex(analizar.ErrorDatos, f"columna {columna}"):
                    analizar.validar_csv(io.StringIO(texto))

    def test_anio_y_numeros_invalidos(self):
        for anio in ("0", "-1", "1.5", "NA", ""):
            with self.subTest(anio=anio):
                with self.assertRaisesRegex(analizar.ErrorDatos, "columna year"):
                    datos(f"tt1,Uno,{anio},10,20\n")
        for columna in ("budget", "domgross"):
            for valor in ("NaN", "Infinity", "-Infinity", "-1", "texto"):
                with self.subTest(columna=columna, valor=valor):
                    budget, domgross = (valor, "20") if columna == "budget" else ("10", valor)
                    with self.assertRaisesRegex(analizar.ErrorDatos, f"columna {columna}"):
                        datos(f"tt1,Uno,2001,{budget},{domgross}\n")

    def test_conserva_columnas_extra_sin_usarlas(self):
        peliculas = analizar.validar_csv(io.StringIO(
            "imdb,title,year,budget,domgross,intgross,domgross_2013$\n"
            "tt1,Uno,2001,10,20,999999,888888\n"))
        self.assertEqual(peliculas[0]["intgross"], "999999")
        self.assertEqual(peliculas[0]["domgross_2013$"], "888888")
        resultado = analizar.calcular_estadisticas(peliculas)
        self.assertEqual(resultado["suma_domgross"], Decimal("20"))

    def test_html_decodifica_y_escapa_y_conserva_orden(self):
        peliculas = datos("tt1,A &amp; &lt;script&gt;,2001,10,20\ntt2,Dos,2002,20,30\n")
        self.assertEqual(peliculas[0]["title"], "A & <script>")
        pagina = analizar.generar_html(
            peliculas, analizar.calcular_estadisticas(peliculas), "Ana <B>",
            datetime(2026, 1, 2, tzinfo=timezone.utc), "sha<123>")
        self.assertIn("A &amp; &lt;script&gt;", pagina)
        self.assertNotIn("<script>", pagina)
        self.assertNotIn("&amp;amp;", pagina)
        self.assertIn("Ana &lt;B&gt;", pagina)
        self.assertIn("sha&lt;123&gt;", pagina)
        self.assertIn("2026-01-02 00:00:00 UTC", pagina)
        tabla = pagina.split("<tbody>")[1]
        self.assertLess(tabla.index("tt1"), tabla.index("tt2"))

    def test_limite_top_diez_y_primeras_filas(self):
        peliculas = datos("".join(f"tt{i},Pelicula {i},2001,10,{i}\n" for i in range(12)))
        resultado = analizar.calcular_estadisticas(peliculas)
        self.assertEqual([p["imdb"] for p in resultado["top_diez"]],
                         [f"tt{i}" for i in range(11, 1, -1)])
        tabla = analizar.generar_html(peliculas, resultado, "Ana").split("<tbody>")[1]
        self.assertIn("<td>tt0</td>", tabla)
        self.assertIn("<td>tt9</td>", tabla)
        self.assertNotIn("<td>tt10</td>", tabla)

    def test_main_publica_y_preserva_informe_si_datos_invalidos(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as carpeta:
            base = Path(carpeta)
            (base / "datos").mkdir()
            csv = base / "datos" / "movies.csv"
            csv.write_text(CABECERA + "tt1,Uno,2001,10,20\n", encoding="utf-8")
            with patch.object(analizar, "BASE", base), redirect_stdout(io.StringIO()):
                self.assertEqual(analizar.main(["--estudiante", "Ana"]), 0)
            destino = base / "public" / "index.html"
            anterior = destino.read_bytes()
            csv.write_text(CABECERA + "tt1,Uno,2001,10,-1\n", encoding="utf-8")
            errores = io.StringIO()
            with patch.object(analizar, "BASE", base), redirect_stderr(errores):
                self.assertNotEqual(analizar.main([]), 0)
            self.assertIn("Fila 2, columna domgross", errores.getvalue())
            self.assertEqual(destino.read_bytes(), anterior)


if __name__ == "__main__":
    unittest.main()
