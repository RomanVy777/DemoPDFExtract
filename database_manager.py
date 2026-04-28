import os
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def conectar():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )


def inicializar_bbdd():
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre_archivo VARCHAR(255),
            texto_extraido LONGTEXT,
            respuesta_claude LONGTEXT,
            fecha DATETIME
        )
    """)

    conexion.commit()
    cursor.close()
    conexion.close()


def guardar_documento(nombre, texto):
    conexion = conectar()
    cursor = conexion.cursor()

    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO documentos (nombre_archivo, texto_extraido, fecha)
        VALUES (%s, %s, %s)
    """, (nombre, texto, fecha_actual))

    ultimo_id = cursor.lastrowid

    conexion.commit()
    cursor.close()
    conexion.close()

    return ultimo_id


def actualizar_respuesta_claude(doc_id, respuesta):
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        UPDATE documentos 
        SET respuesta_claude = %s 
        WHERE id = %s
    """, (respuesta, doc_id))

    conexion.commit()
    cursor.close()
    conexion.close()