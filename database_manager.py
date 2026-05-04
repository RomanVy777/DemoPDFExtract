import os
import re
import json
import unicodedata
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "seguros_demo")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL")


# ─────────────────────────────────────────────
# CONEXIÓN MYSQL
# ─────────────────────────────────────────────

def proteger_nombre_mysql(nombre):
    return "`" + nombre.replace("`", "``") + "`"


def conectar(sin_bbdd=False):
    config = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "charset": "utf8mb4",
        "use_unicode": True
    }

    if not sin_bbdd:
        config["database"] = MYSQL_DATABASE

    return mysql.connector.connect(**config)


def crear_bbdd_si_no_existe():
    conexion = conectar(sin_bbdd=True)
    cursor = conexion.cursor()

    cursor.execute(
        f"""
        CREATE DATABASE IF NOT EXISTS {proteger_nombre_mysql(MYSQL_DATABASE)}
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci
        """
    )

    conexion.commit()
    cursor.close()
    conexion.close()


def inicializar_bbdd():
    """
    Solo crea tablas base.
    Las tablas de cada seguro se crearán dinámicamente.
    """
    crear_bbdd_si_no_existe()

    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre_archivo VARCHAR(255),
            tipo_seguro VARCHAR(100),
            texto_extraido LONGTEXT,
            json_claude LONGTEXT,
            fecha_importacion DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tablas_generadas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_documento INT,
            nombre_logico VARCHAR(150),
            nombre_mysql VARCHAR(150),
            filas_insertadas INT,
            fecha_creacion DATETIME,
            FOREIGN KEY (id_documento) REFERENCES documentos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS errores_importacion (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_documento INT NULL,
            mensaje_error TEXT,
            fecha DATETIME,
            FOREIGN KEY (id_documento) REFERENCES documentos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    conexion.commit()
    cursor.close()
    conexion.close()


# ─────────────────────────────────────────────
# LIMPIEZA DE NOMBRES
# ─────────────────────────────────────────────

def normalizar_nombre(texto, prefijo):
    """
    Convierte cualquier texto en un nombre válido para tabla o columna MySQL.
    Ejemplo:
    'Número de póliza' -> 'numero_de_poliza'
    """
    if texto is None:
        texto = "campo"

    texto = str(texto).strip().lower()

    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")

    texto = re.sub(r"[^a-z0-9_]+", "_", texto)
    texto = re.sub(r"_+", "_", texto)
    texto = texto.strip("_")

    if texto == "":
        texto = "campo"

    if texto[0].isdigit():
        texto = prefijo + "_" + texto

    palabras_reservadas = {
        "select", "insert", "update", "delete", "table", "from", "where",
        "order", "group", "by", "create", "drop", "alter", "index",
        "primary", "foreign", "key", "date", "int", "json"
    }

    if texto in palabras_reservadas:
        texto = prefijo + "_" + texto

    return texto[:60]


def nombre_tabla_dinamica(tipo_seguro, nombre_tabla):
    tipo = normalizar_nombre(tipo_seguro or "generico", "t")
    tabla = normalizar_nombre(nombre_tabla or "datos", "t")
    return f"seguro_{tipo}_{tabla}"[:64]


def limpiar_valor(valor):
    """
    Guarda todo como texto para evitar errores.
    Así no falla aunque Claude detecte fechas, importes, listas o textos largos.
    """
    if valor is None:
        return None

    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)

    return str(valor).strip()


# ─────────────────────────────────────────────
# EXTRACCIÓN DE TEXTO DEL PDF
# ─────────────────────────────────────────────

def extraer_texto_pdf(ruta_pdf):
    lector = PdfReader(ruta_pdf)

    paginas = []
    texto_total = ""

    for pagina in lector.pages:
        texto_pagina = pagina.extract_text() or ""
        paginas.append(texto_pagina)
        texto_total += texto_pagina + "\n\n"

    return texto_total.strip(), paginas


# ─────────────────────────────────────────────
# CLAUDE DETECTA TABLAS Y CAMPOS
# ─────────────────────────────────────────────

def extraer_json_desde_respuesta(texto):
    """
    Intenta quedarse solo con el JSON aunque Claude añada algo alrededor.
    """
    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio == -1 or fin == -1:
        raise ValueError("Claude no ha devuelto un JSON válido.")

    posible_json = texto[inicio:fin + 1]

    return json.loads(posible_json)


def analizar_pdf_con_claude(nombre_archivo, texto_pdf, tipo_seguro_usuario=None):
    if not ANTHROPIC_API_KEY:
        raise ValueError("Falta ANTHROPIC_API_KEY en el archivo .env")

    if not CLAUDE_MODEL:
        raise ValueError("Falta CLAUDE_MODEL en el archivo .env")

    cliente = Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""
Analiza el siguiente texto extraído de un PDF de seguros.

Nombre del archivo:
{nombre_archivo}

Tipo de seguro indicado por el usuario:
{tipo_seguro_usuario or "No indicado"}

Tu tarea:
1. Detecta automáticamente el tipo de seguro.
2. Detecta todas las secciones importantes del documento.
3. Crea una estructura de tablas lógica.
4. Cada sección importante debe convertirse en una tabla.
5. No uses una única tabla si puedes separar los datos.
6. No inventes datos.
7. Si un dato no aparece, no lo incluyas.
8. Devuelve exclusivamente JSON válido.

Formato obligatorio de salida:

{{
  "tipo_seguro": "auto | hogar | vida | salud | decesos | comercio | comunidad | otro",
  "descripcion": "breve descripcion del documento",
  "tablas": {{
    "nombre_de_tabla_1": {{
      "campo_1": "valor",
      "campo_2": "valor"
    }},
    "nombre_de_tabla_2": [
      {{
        "campo_1": "valor",
        "campo_2": "valor"
      }},
      {{
        "campo_1": "valor",
        "campo_2": "valor"
      }}
    ]
  }}
}}

Normas:
- En "tablas", cada clave será el nombre lógico de una tabla.
- Si una sección tiene un solo registro, usa un objeto.
- Si una sección tiene varios registros, usa una lista de objetos.
- Separa al máximo posible: tomador, aseguradora, mediador, poliza, recibos, garantias, vehiculos, conductores, inmuebles, beneficiarios, asegurados, capitales, exclusiones, coberturas, franquicias, etc.
- Los nombres de tablas y campos deben estar en español.
- No devuelvas explicaciones fuera del JSON.

Texto del PDF:
\"\"\"
{texto_pdf}
\"\"\"
"""

    respuesta = cliente.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    texto_respuesta = ""

    for bloque in respuesta.content:
        if hasattr(bloque, "text"):
            texto_respuesta += bloque.text

    return extraer_json_desde_respuesta(texto_respuesta)


# ─────────────────────────────────────────────
# GUARDAR DOCUMENTO BASE
# ─────────────────────────────────────────────

def guardar_documento(nombre_archivo, tipo_seguro, texto_extraido, datos_claude):
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO documentos
        (nombre_archivo, tipo_seguro, texto_extraido, json_claude, fecha_importacion)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        nombre_archivo,
        tipo_seguro,
        texto_extraido,
        json.dumps(datos_claude, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    id_documento = cursor.lastrowid

    conexion.commit()
    cursor.close()
    conexion.close()

    return id_documento


def guardar_error(id_documento, mensaje):
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO errores_importacion
        (id_documento, mensaje_error, fecha)
        VALUES (%s, %s, %s)
    """, (
        id_documento,
        str(mensaje),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conexion.commit()
    cursor.close()
    conexion.close()


# ─────────────────────────────────────────────
# CREACIÓN DINÁMICA DE TABLAS Y COLUMNAS
# ─────────────────────────────────────────────

def obtener_columnas_existentes(cursor, nombre_tabla):
    cursor.execute(f"SHOW COLUMNS FROM {proteger_nombre_mysql(nombre_tabla)}")
    filas = cursor.fetchall()

    columnas = set()

    for fila in filas:
        columnas.add(fila[0])

    return columnas


def crear_tabla_dinamica_si_no_existe(cursor, nombre_tabla):
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {proteger_nombre_mysql(nombre_tabla)} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_documento INT,
            fecha_importacion DATETIME,
            FOREIGN KEY (id_documento) REFERENCES documentos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)


def crear_columnas_si_no_existen(cursor, nombre_tabla, columnas):
    columnas_existentes = obtener_columnas_existentes(cursor, nombre_tabla)

    for columna in columnas:
        if columna not in columnas_existentes:
            cursor.execute(
                f"""
                ALTER TABLE {proteger_nombre_mysql(nombre_tabla)}
                ADD COLUMN {proteger_nombre_mysql(columna)} LONGTEXT
                """
            )


def aplanar_diccionario(diccionario, prefijo=""):
    """
    Convierte datos anidados en columnas.
    Ejemplo:
    {
      "direccion": {
        "calle": "Mayor",
        "cp": "37500"
      }
    }

    Resultado:
    {
      "direccion_calle": "Mayor",
      "direccion_cp": "37500"
    }
    """
    resultado = {}

    for clave, valor in diccionario.items():
        clave_limpia = normalizar_nombre(clave, "c")

        if prefijo:
            nueva_clave = f"{prefijo}_{clave_limpia}"
        else:
            nueva_clave = clave_limpia

        if isinstance(valor, dict):
            resultado.update(aplanar_diccionario(valor, nueva_clave))

        elif isinstance(valor, list):
            resultado[nueva_clave] = json.dumps(valor, ensure_ascii=False)

        else:
            resultado[nueva_clave] = limpiar_valor(valor)

    return resultado


def convertir_contenido_en_filas(contenido):
    """
    Claude puede devolver:
    - Un objeto
    - Una lista de objetos
    - Un texto suelto

    Esta función lo convierte siempre en lista de filas.
    """
    filas = []

    if isinstance(contenido, list):
        for elemento in contenido:
            if isinstance(elemento, dict):
                filas.append(aplanar_diccionario(elemento))
            else:
                filas.append({"valor": limpiar_valor(elemento)})

    elif isinstance(contenido, dict):
        filas.append(aplanar_diccionario(contenido))

    else:
        filas.append({"valor": limpiar_valor(contenido)})

    return filas


def insertar_fila_dinamica(cursor, nombre_tabla, id_documento, fila):
    columnas = ["id_documento", "fecha_importacion"]
    valores = [
        id_documento,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ]

    for columna, valor in fila.items():
        columnas.append(columna)
        valores.append(valor)

    columnas_sql = ", ".join(proteger_nombre_mysql(columna) for columna in columnas)
    marcadores_sql = ", ".join(["%s"] * len(valores))

    cursor.execute(
        f"""
        INSERT INTO {proteger_nombre_mysql(nombre_tabla)}
        ({columnas_sql})
        VALUES ({marcadores_sql})
        """,
        valores
    )


def guardar_registro_tabla_generada(cursor, id_documento, nombre_logico, nombre_mysql, filas_insertadas):
    cursor.execute("""
        INSERT INTO tablas_generadas
        (id_documento, nombre_logico, nombre_mysql, filas_insertadas, fecha_creacion)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        id_documento,
        nombre_logico,
        nombre_mysql,
        filas_insertadas,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))


def crear_tablas_desde_json_claude(id_documento, datos_claude):
    tipo_seguro = datos_claude.get("tipo_seguro", "otro")
    tablas = datos_claude.get("tablas", {})

    if not isinstance(tablas, dict):
        raise ValueError("El campo 'tablas' del JSON de Claude no es válido.")

    conexion = conectar()
    cursor = conexion.cursor()

    try:
        for nombre_logico, contenido in tablas.items():
            nombre_mysql = nombre_tabla_dinamica(tipo_seguro, nombre_logico)

            filas = convertir_contenido_en_filas(contenido)

            if not filas:
                continue

            crear_tabla_dinamica_si_no_existe(cursor, nombre_mysql)

            todas_las_columnas = set()

            for fila in filas:
                for columna in fila.keys():
                    todas_las_columnas.add(columna)

            crear_columnas_si_no_existen(cursor, nombre_mysql, todas_las_columnas)

            filas_insertadas = 0

            for fila in filas:
                insertar_fila_dinamica(cursor, nombre_mysql, id_documento, fila)
                filas_insertadas += 1

            guardar_registro_tabla_generada(
                cursor,
                id_documento,
                nombre_logico,
                nombre_mysql,
                filas_insertadas
            )

        conexion.commit()

    except Exception as e:
        conexion.rollback()
        guardar_error(id_documento, e)
        raise e

    finally:
        cursor.close()
        conexion.close()


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE IMPORTACIÓN
# ─────────────────────────────────────────────

def importar_pdf(ruta_pdf, tipo_seguro_usuario=None):
    """
    Flujo completo:
    1. Crea la base de datos si no existe.
    2. Extrae texto del PDF.
    3. Envía el texto a Claude.
    4. Claude devuelve tablas y campos.
    5. Guarda el documento.
    6. Crea tablas dinámicas.
    7. Inserta los datos.
    """
    inicializar_bbdd()

    nombre_archivo = os.path.basename(ruta_pdf)

    texto_pdf, paginas = extraer_texto_pdf(ruta_pdf)

    if not texto_pdf:
        raise ValueError("No se ha podido extraer texto del PDF. Puede que sea un PDF escaneado.")

    datos_claude = analizar_pdf_con_claude(
        nombre_archivo=nombre_archivo,
        texto_pdf=texto_pdf,
        tipo_seguro_usuario=tipo_seguro_usuario
    )

    tipo_seguro_detectado = datos_claude.get("tipo_seguro", tipo_seguro_usuario or "otro")

    id_documento = guardar_documento(
        nombre_archivo=nombre_archivo,
        tipo_seguro=tipo_seguro_detectado,
        texto_extraido=texto_pdf,
        datos_claude=datos_claude
    )

    crear_tablas_desde_json_claude(
        id_documento=id_documento,
        datos_claude=datos_claude
    )

    return {
        "id_documento": id_documento,
        "tipo_seguro": tipo_seguro_detectado,
        "tablas_detectadas": list(datos_claude.get("tablas", {}).keys())
    }


# ─────────────────────────────────────────────
# EJECUCIÓN DE PRUEBA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    ruta_pdf = "pdfs/poliza_demo.pdf"

    resultado = importar_pdf(
        ruta_pdf=ruta_pdf,
        tipo_seguro_usuario="auto"
    )

    print("Importación completada correctamente")
    print(json.dumps(resultado, ensure_ascii=False, indent=4))