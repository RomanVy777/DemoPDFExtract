import sqlite3
from datetime import datetime

def inicializar_bbdd():
    # Se crea el archivo 'proyecto_claude.db' si no existe
    conexion = sqlite3.connect("proyecto_claude.db")
    cursor = conexion.cursor()

    # Creamos una tabla para los documentos
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS documentos (
                                                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                             nombre_archivo TEXT,
                                                             texto_extraido TEXT,
                                                             respuesta_claude TEXT,
                                                             fecha DATETIME
                   )
                   ''')
    conexion.commit()
    conexion.close()

def guardar_documento(nombre, texto):
    conexion = sqlite3.connect("proyecto_claude.db")
    cursor = conexion.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
                   INSERT INTO documentos (nombre_archivo, texto_extraido, fecha)
                   VALUES (?, ?, ?)
                   ''', (nombre, texto, fecha_actual))

    ultimo_id = cursor.lastrowid

    conexion.commit()
    conexion.close()
    return ultimo_id

def actualizar_respuesta_claude(doc_id, respuesta):
    conexion = sqlite3.connect("proyecto_claude.db")
    cursor = conexion.cursor()
    cursor.execute('''
                   UPDATE documentos SET respuesta_claude = ? WHERE id = ?
                   ''', (respuesta, doc_id))
    conexion.commit()
    conexion.close()