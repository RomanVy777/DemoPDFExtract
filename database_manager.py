import os
import json
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────
# CONEXIÓN
# ─────────────────────────────────────────────

def conectar():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )


# ─────────────────────────────────────────────
# INICIALIZACIÓN DE TABLAS
# ─────────────────────────────────────────────

def inicializar_bbdd():
    con = conectar()
    cur = con.cursor()

    # Tabla maestra de documentos importados
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            nombre_archivo  VARCHAR(255),
            tipo_poliza     VARCHAR(50),
            texto_extraido  LONGTEXT,
            datos_json      JSON,
            fecha           DATETIME
        )
    """)

    # Migración: añadir columnas nuevas si la tabla ya existía sin ellas
    cur.execute("SHOW COLUMNS FROM documentos LIKE 'tipo_poliza'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE documentos ADD COLUMN tipo_poliza VARCHAR(50) AFTER nombre_archivo")

    cur.execute("SHOW COLUMNS FROM documentos LIKE 'datos_json'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE documentos ADD COLUMN datos_json JSON AFTER texto_extraido")

    cur.execute("SHOW COLUMNS FROM documentos LIKE 'respuesta_claude'")
    if cur.fetchone():
        cur.execute("ALTER TABLE documentos DROP COLUMN respuesta_claude")


    # Migración garantias: columnas nuevas
    cur.execute("SHOW COLUMNS FROM garantias LIKE 'categoria'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE garantias ADD COLUMN categoria VARCHAR(100) AFTER nombre")
    cur.execute("SHOW COLUMNS FROM garantias LIKE 'descripcion_limite'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE garantias ADD COLUMN descripcion_limite VARCHAR(500)")

    # Migración polizas: columnas nuevas
    cur.execute("SHOW COLUMNS FROM polizas LIKE 'tipo_documento'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE polizas ADD COLUMN tipo_documento VARCHAR(100) AFTER tipo_poliza")
    cur.execute("SHOW COLUMNS FROM polizas LIKE 'fecha_emision'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE polizas ADD COLUMN fecha_emision DATE AFTER opcion_cobertura")
    cur.execute("SHOW COLUMNS FROM polizas LIKE 'lugar_emision'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE polizas ADD COLUMN lugar_emision VARCHAR(100) AFTER fecha_emision")

    # Migración aseguradores: columnas nuevas
    cur.execute("SHOW COLUMNS FROM aseguradores LIKE 'cp'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE aseguradores ADD COLUMN cp VARCHAR(10)")
    cur.execute("SHOW COLUMNS FROM aseguradores LIKE 'email_dpo'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE aseguradores ADD COLUMN email_dpo VARCHAR(150)")
    cur.execute("SHOW COLUMNS FROM aseguradores LIKE 'web'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE aseguradores ADD COLUMN web VARCHAR(255)")

    # ── TABLAS COMPARTIDAS ──────────────────────────────────────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aseguradores (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            nombre      VARCHAR(255),
            cif         VARCHAR(20),
            direccion   VARCHAR(255),
            ciudad      VARCHAR(100),
            cp          VARCHAR(10),
            email_dpo   VARCHAR(150),
            web         VARCHAR(255)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mediadores (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            codigo      VARCHAR(50),
            nombre      VARCHAR(255),
            tipo        VARCHAR(100),
            direccion   VARCHAR(255),
            telefono    VARCHAR(30),
            email       VARCHAR(150)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tomadores (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            nombre          VARCHAR(150),
            apellidos       VARCHAR(150),
            nif             VARCHAR(20),
            direccion       VARCHAR(255),
            ciudad          VARCHAR(100),
            cp              VARCHAR(10),
            email           VARCHAR(150),
            fecha_nacimiento DATE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS polizas (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            doc_id              INT,
            numero_poliza       VARCHAR(100),
            suplemento          VARCHAR(50),
            tipo_poliza         VARCHAR(50),
            tipo_documento      VARCHAR(100),
            efecto              DATE,
            vencimiento         DATE,
            duracion            VARCHAR(50),
            forma_pago          VARCHAR(50),
            opcion_cobertura    VARCHAR(100),
            fecha_emision       DATE,
            lugar_emision       VARCHAR(100),
            id_asegurador       INT,
            id_mediador         INT,
            id_tomador          INT,
            FOREIGN KEY (doc_id)        REFERENCES documentos(id),
            FOREIGN KEY (id_asegurador) REFERENCES aseguradores(id),
            FOREIGN KEY (id_mediador)   REFERENCES mediadores(id),
            FOREIGN KEY (id_tomador)    REFERENCES tomadores(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recibos (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza       INT,
            tipo            VARCHAR(50),
            periodo_inicio  DATE,
            periodo_fin     DATE,
            prima           DECIMAL(10,2),
            consorcio       DECIMAL(10,2),
            dgs             DECIMAL(10,2),
            impuestos       DECIMAL(10,2),
            total           DECIMAL(10,2),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS domiciliaciones (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            banco               VARCHAR(100),
            iban                VARCHAR(34),
            bic                 VARCHAR(15),
            tipo_pago           VARCHAR(50),
            referencia_mandato  VARCHAR(100),
            fecha_firma         DATE,
            lugar_firma         VARCHAR(100),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS garantias (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            nombre              VARCHAR(255),
            categoria           VARCHAR(100),
            capital_asegurado   DECIMAL(12,2),
            incluida            TINYINT(1),
            territorio          VARCHAR(100),
            franquicia          VARCHAR(100),
            copago              VARCHAR(100),
            descripcion_limite  VARCHAR(500),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    # ── TABLAS AUTO ─────────────────────────────────────────────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS centros_reale (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza   INT,
            codigo      VARCHAR(20),
            nombre      VARCHAR(150),
            direccion   VARCHAR(255),
            telefono    VARCHAR(30),
            fax         VARCHAR(30),
            email       VARCHAR(150),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculos (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            matricula           VARCHAR(20),
            tipo                VARCHAR(50),
            marca               VARCHAR(100),
            modelo              VARCHAR(150),
            uso                 VARCHAR(50),
            fecha_matriculacion DATE,
            tiene_alarma        TINYINT(1),
            garaje              TINYINT(1),
            km_anuales          VARCHAR(50),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accesorios (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_vehiculo     INT,
            descripcion     VARCHAR(255),
            valor           DECIMAL(10,2),
            incluido        TINYINT(1),
            FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conductores (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza       INT,
            nombre          VARCHAR(150),
            apellidos       VARCHAR(150),
            nif             VARCHAR(20),
            fecha_nacimiento DATE,
            fecha_carnet    DATE,
            puntos_carnet   INT,
            sexo            VARCHAR(20),
            estado_civil    VARCHAR(30),
            ocupacion       VARCHAR(150),
            cp              VARCHAR(10),
            tipo_conductor  VARCHAR(50),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    # ── TABLAS HOGAR ─────────────────────────────────────────────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inmuebles (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            direccion           VARCHAR(255),
            ciudad              VARCHAR(100),
            cp                  VARCHAR(10),
            tipo                VARCHAR(100),
            uso                 VARCHAR(50),
            metros_cuadrados    DECIMAL(8,2),
            anio_construccion   INT,
            num_plantas         INT,
            tiene_alarma        TINYINT(1),
            tipo_construccion   VARCHAR(100),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS capitales_hogar (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            continente          DECIMAL(12,2),
            contenido           DECIMAL(12,2),
            rc_privada          DECIMAL(12,2),
            valor_reconstruccion DECIMAL(12,2),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    # ── TABLAS VIDA ──────────────────────────────────────────────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS asegurados_vida (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza       INT,
            nombre          VARCHAR(150),
            apellidos       VARCHAR(150),
            nif             VARCHAR(20),
            fecha_nacimiento DATE,
            sexo            VARCHAR(20),
            profesion       VARCHAR(150),
            fumador         TINYINT(1),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS beneficiarios (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza   INT,
            nombre      VARCHAR(255),
            nif         VARCHAR(20),
            porcentaje  DECIMAL(5,2),
            parentesco  VARCHAR(100),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS capitales_vida (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            fallecimiento       DECIMAL(12,2),
            invalidez_absoluta  DECIMAL(12,2),
            invalidez_parcial   DECIMAL(12,2),
            enfermedad_grave    DECIMAL(12,2),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    # ── TABLAS SALUD ─────────────────────────────────────────────────────

    cur.execute("""
        CREATE TABLE IF NOT EXISTS asegurados_salud (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza       INT,
            nombre          VARCHAR(150),
            apellidos       VARCHAR(150),
            nif             VARCHAR(20),
            fecha_nacimiento DATE,
            sexo            VARCHAR(20),
            parentesco      VARCHAR(100),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS coberturas_salud (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            id_poliza           INT,
            tipo_cuadro_medico  VARCHAR(100),
            ambito_territorial  VARCHAR(100),
            copago              VARCHAR(50),
            dental_incluido     TINYINT(1),
            optica_incluida     TINYINT(1),
            FOREIGN KEY (id_poliza) REFERENCES polizas(id)
        )
    """)

    con.commit()
    cur.close()
    con.close()
    print("✓ Base de datos inicializada con todas las tablas")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _bool(val):
    """Convierte 'SI'/'NO'/True/False/None a 1/0/None."""
    if val is None:
        return None
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, str):
        return 1 if val.strip().upper() in ("SI", "SÍ", "YES", "TRUE", "S", "1") else 0
    return int(bool(val))


def _dec(val):
    """Limpia strings como '356,01 €' a float."""
    if val is None:
        return None
    try:
        return float(str(val).replace(".", "").replace(",", ".").replace("€", "").replace(" ", ""))
    except ValueError:
        return None


def _fecha(val):
    """Intenta parsear fechas en varios formatos a YYYY-MM-DD."""
    if not val:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _str(val, maxlen=None):
    if val is None:
        return None
    s = str(val).strip()
    return s[:maxlen] if maxlen else s


# ─────────────────────────────────────────────
# GUARDAR DOCUMENTO MAESTRO
# ─────────────────────────────────────────────

def guardar_documento(nombre: str, texto: str, tipo_poliza: str = None, datos: dict = None) -> int:
    con = conectar()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO documentos (nombre_archivo, tipo_poliza, texto_extraido, datos_json, fecha)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        nombre,
        tipo_poliza,
        texto,
        json.dumps(datos, ensure_ascii=False) if datos else None,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    doc_id = cur.lastrowid
    con.commit()
    cur.close()
    con.close()
    return doc_id


# ─────────────────────────────────────────────
# INSERTAR ENTIDADES COMUNES
# ─────────────────────────────────────────────

def _insertar_asegurador(cur, d: dict) -> int | None:
    if not d:
        return None
    cur.execute("""
        INSERT INTO aseguradores (nombre, cif, direccion, ciudad, cp, email_dpo, web)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (_str(d.get("nombre"), 255), _str(d.get("cif"), 20),
          _str(d.get("direccion"), 255), _str(d.get("ciudad"), 100),
          _str(d.get("cp"), 10), _str(d.get("email_dpo"), 150),
          _str(d.get("web"), 255)))
    return cur.lastrowid


def _insertar_mediador(cur, d: dict) -> int | None:
    if not d:
        return None
    cur.execute("""
        INSERT INTO mediadores (codigo, nombre, tipo, direccion, telefono, email)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (_str(d.get("codigo"), 50), _str(d.get("nombre"), 255),
          _str(d.get("tipo"), 100), _str(d.get("direccion"), 255),
          _str(d.get("telefono"), 30), _str(d.get("email"), 150)))
    return cur.lastrowid


def _insertar_tomador(cur, d: dict) -> int | None:
    if not d:
        return None
    cur.execute("""
        INSERT INTO tomadores (nombre, apellidos, nif, direccion, ciudad, cp, email, fecha_nacimiento)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (_str(d.get("nombre"), 150), _str(d.get("apellidos"), 150),
          _str(d.get("nif"), 20), _str(d.get("direccion"), 255),
          _str(d.get("ciudad"), 100), _str(d.get("cp"), 10),
          _str(d.get("email"), 150), _fecha(d.get("fecha_nacimiento"))))
    return cur.lastrowid


def _insertar_poliza(cur, doc_id, tipo, datos, id_aseg, id_med, id_tom) -> int | None:
    d = datos.get("poliza", {}) or {}
    cur.execute("""
        INSERT INTO polizas (doc_id, numero_poliza, suplemento, tipo_poliza,
                             tipo_documento, efecto, vencimiento, duracion, forma_pago,
                             opcion_cobertura, fecha_emision, lugar_emision,
                             id_asegurador, id_mediador, id_tomador)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (doc_id, _str(d.get("numero_poliza"), 100), _str(d.get("suplemento"), 50),
          tipo, _str(d.get("tipo_documento"), 100),
          _fecha(d.get("efecto")), _fecha(d.get("vencimiento")),
          _str(d.get("duracion"), 50), _str(d.get("forma_pago"), 50),
          _str(d.get("opcion_cobertura") or d.get("modalidad"), 100),
          _fecha(d.get("fecha_emision")), _str(d.get("lugar_emision"), 100),
          id_aseg, id_med, id_tom))
    return cur.lastrowid


def _insertar_recibo(cur, id_poliza, d: dict):
    if not d:
        return
    cur.execute("""
        INSERT INTO recibos (id_poliza, tipo, periodo_inicio, periodo_fin,
                             prima, consorcio, dgs, impuestos, total)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (id_poliza, _str(d.get("tipo"), 50),
          _fecha(d.get("periodo_inicio")), _fecha(d.get("periodo_fin")),
          _dec(d.get("prima")), _dec(d.get("consorcio")),
          _dec(d.get("dgs")), _dec(d.get("impuestos")),
          _dec(d.get("total"))))


def _insertar_domiciliacion(cur, id_poliza, d: dict):
    if not d:
        return
    cur.execute("""
        INSERT INTO domiciliaciones (id_poliza, banco, iban, bic, tipo_pago,
                                     referencia_mandato, fecha_firma, lugar_firma)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (id_poliza, _str(d.get("banco"), 100), _str(d.get("iban"), 34),
          _str(d.get("bic"), 15), _str(d.get("tipo_pago"), 50),
          _str(d.get("referencia_mandato"), 100),
          _fecha(d.get("fecha_firma")), _str(d.get("lugar_firma"), 100)))


def _insertar_garantias(cur, id_poliza, lista: list):
    for g in (lista or []):
        if not g or not g.get("nombre"):
            continue
        cur.execute("""
            INSERT INTO garantias (id_poliza, nombre, categoria, capital_asegurado,
                                   incluida, territorio, franquicia, copago, descripcion_limite)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(g.get("nombre"), 255),
              _str(g.get("categoria"), 100),
              _dec(g.get("capital_asegurado")), _bool(g.get("incluida")),
              _str(g.get("territorio"), 100),
              _str(g.get("franquicia"), 100), _str(g.get("copago"), 100),
              _str(g.get("descripcion_limite"), 500)))


# ─────────────────────────────────────────────
# INSERTAR POR TIPO DE PÓLIZA
# ─────────────────────────────────────────────

def _insertar_datos_auto(cur, id_poliza, datos):
    # Centro REALE
    c = datos.get("centro_reale") or {}
    if c:
        cur.execute("""
            INSERT INTO centros_reale (id_poliza, codigo, nombre, direccion, telefono, fax, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(c.get("codigo"), 20), _str(c.get("nombre"), 150),
              _str(c.get("direccion"), 255), _str(c.get("telefono"), 30),
              _str(c.get("fax"), 30), _str(c.get("email"), 150)))

    # Vehículo
    v = datos.get("vehiculo") or {}
    if v:
        cur.execute("""
            INSERT INTO vehiculos (id_poliza, matricula, tipo, marca, modelo, uso,
                                   fecha_matriculacion, tiene_alarma, garaje, km_anuales)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(v.get("matricula"), 20), _str(v.get("tipo"), 50),
              _str(v.get("marca"), 100), _str(v.get("modelo"), 150),
              _str(v.get("uso"), 50), _fecha(v.get("fecha_matriculacion")),
              _bool(v.get("tiene_alarma")), _bool(v.get("garaje")),
              _str(v.get("km_anuales"), 50)))
        id_vehiculo = cur.lastrowid

        # Accesorios
        for acc in (datos.get("accesorios") or []):
            if not acc or not acc.get("descripcion"):
                continue
            cur.execute("""
                INSERT INTO accesorios (id_vehiculo, descripcion, valor, incluido)
                VALUES (%s, %s, %s, %s)
            """, (id_vehiculo, _str(acc.get("descripcion"), 255),
                  _dec(acc.get("valor")), _bool(acc.get("incluido"))))

    # Conductores
    for con_d in (datos.get("conductores") or []):
        if not con_d or not con_d.get("nif"):
            continue
        cur.execute("""
            INSERT INTO conductores (id_poliza, nombre, apellidos, nif, fecha_nacimiento,
                                     fecha_carnet, puntos_carnet, sexo, estado_civil,
                                     ocupacion, cp, tipo_conductor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(con_d.get("nombre"), 150), _str(con_d.get("apellidos"), 150),
              _str(con_d.get("nif"), 20), _fecha(con_d.get("fecha_nacimiento")),
              _fecha(con_d.get("fecha_carnet")), con_d.get("puntos_carnet"),
              _str(con_d.get("sexo"), 20), _str(con_d.get("estado_civil"), 30),
              _str(con_d.get("ocupacion"), 150), _str(con_d.get("cp"), 10),
              _str(con_d.get("tipo_conductor"), 50)))


def _insertar_datos_hogar(cur, id_poliza, datos):
    # Inmueble
    i = datos.get("inmueble") or {}
    if i:
        cur.execute("""
            INSERT INTO inmuebles (id_poliza, direccion, ciudad, cp, tipo, uso,
                                   metros_cuadrados, anio_construccion, num_plantas,
                                   tiene_alarma, tipo_construccion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(i.get("direccion"), 255), _str(i.get("ciudad"), 100),
              _str(i.get("cp"), 10), _str(i.get("tipo"), 100), _str(i.get("uso"), 50),
              _dec(i.get("metros_cuadrados")), i.get("anio_construccion"),
              i.get("num_plantas"), _bool(i.get("tiene_alarma")),
              _str(i.get("tipo_construccion"), 100)))

    # Capitales hogar
    cap = datos.get("capitales") or {}
    if cap:
        cur.execute("""
            INSERT INTO capitales_hogar (id_poliza, continente, contenido, rc_privada, valor_reconstruccion)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_poliza, _dec(cap.get("continente")), _dec(cap.get("contenido")),
              _dec(cap.get("rc_privada")), _dec(cap.get("valor_reconstruccion"))))


def _insertar_datos_vida(cur, id_poliza, datos):
    # Asegurado
    a = datos.get("asegurado") or {}
    if a:
        cur.execute("""
            INSERT INTO asegurados_vida (id_poliza, nombre, apellidos, nif,
                                         fecha_nacimiento, sexo, profesion, fumador)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(a.get("nombre"), 150), _str(a.get("apellidos"), 150),
              _str(a.get("nif"), 20), _fecha(a.get("fecha_nacimiento")),
              _str(a.get("sexo"), 20), _str(a.get("profesion"), 150),
              _bool(a.get("fumador"))))

    # Beneficiarios
    for b in (datos.get("beneficiarios") or []):
        if not b or not b.get("nombre"):
            continue
        cur.execute("""
            INSERT INTO beneficiarios (id_poliza, nombre, nif, porcentaje, parentesco)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_poliza, _str(b.get("nombre"), 255), _str(b.get("nif"), 20),
              _dec(b.get("porcentaje")), _str(b.get("parentesco"), 100)))

    # Capitales vida
    cap = datos.get("capitales") or {}
    if cap:
        cur.execute("""
            INSERT INTO capitales_vida (id_poliza, fallecimiento, invalidez_absoluta,
                                        invalidez_parcial, enfermedad_grave)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_poliza, _dec(cap.get("fallecimiento")), _dec(cap.get("invalidez_absoluta")),
              _dec(cap.get("invalidez_parcial")), _dec(cap.get("enfermedad_grave"))))


def _insertar_datos_salud(cur, id_poliza, datos):
    # Asegurados
    for a in (datos.get("asegurados") or []):
        if not a or not a.get("nif"):
            continue
        cur.execute("""
            INSERT INTO asegurados_salud (id_poliza, nombre, apellidos, nif,
                                          fecha_nacimiento, sexo, parentesco)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(a.get("nombre"), 150), _str(a.get("apellidos"), 150),
              _str(a.get("nif"), 20), _fecha(a.get("fecha_nacimiento")),
              _str(a.get("sexo"), 20), _str(a.get("parentesco"), 100)))

    # Cobertura
    cob = datos.get("cobertura") or {}
    if cob:
        cur.execute("""
            INSERT INTO coberturas_salud (id_poliza, tipo_cuadro_medico, ambito_territorial,
                                          copago, dental_incluido, optica_incluida)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (id_poliza, _str(cob.get("tipo_cuadro_medico"), 100),
              _str(cob.get("ambito_territorial"), 100), _str(cob.get("copago"), 50),
              _bool(cob.get("dental_incluido")), _bool(cob.get("optica_incluida"))))


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def insertar_poliza_completa(doc_id: int, tipo: str, datos: dict) -> int:
    """
    Inserta todos los datos de una póliza en las tablas correspondientes.
    Devuelve el id de la poliza insertada.
    """
    con = conectar()
    cur = con.cursor()

    try:
        # Entidades comunes
        id_aseg = _insertar_asegurador(cur, datos.get("asegurador"))
        id_med  = _insertar_mediador(cur, datos.get("mediador"))
        id_tom  = _insertar_tomador(cur, datos.get("tomador"))
        id_pol  = _insertar_poliza(cur, doc_id, tipo, datos, id_aseg, id_med, id_tom)

        # Recibo y domiciliación (comunes)
        _insertar_recibo(cur, id_pol, datos.get("recibo"))
        _insertar_domiciliacion(cur, id_pol, datos.get("domiciliacion"))
        _insertar_garantias(cur, id_pol, datos.get("garantias"))

        # Tablas específicas por tipo
        if tipo == "AUTO":
            _insertar_datos_auto(cur, id_pol, datos)
        elif tipo == "HOGAR":
            _insertar_datos_hogar(cur, id_pol, datos)
        elif tipo == "VIDA":
            _insertar_datos_vida(cur, id_pol, datos)
        elif tipo == "SALUD":
            _insertar_datos_salud(cur, id_pol, datos)

        con.commit()
        return id_pol

    except Exception as e:
        con.rollback()
        raise e
    finally:
        cur.close()
        con.close()