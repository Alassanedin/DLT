import sqlite3
import hashlib
from flask import g
import time
from datetime import datetime

DATABASE = 'app_data.db' # Renommé pour englober toutes les données

def hash_password(password):
    "Hache le mot de passe en utilisant SHA256."
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db():
    "Établit ou retourne la connexion à la base de données."
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db(app):
    "Initialise les 3 tables de la base de données (users, archives, verifications)."
    with app.app_context():
        db = get_db()
        
        # 1. TABLE users (Authentification)
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        """)
        
        # 2. TABLE archives (Métadonnées des documents archivés)
        db.execute("""
            CREATE TABLE IF NOT EXISTS archives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom_fichier TEXT NOT NULL,
                hash_fichier TEXT UNIQUE NOT NULL,
                topic_id TEXT UNIQUE NOT NULL,
                horodatage TEXT NOT NULL,
                taille_fichier INTEGER NOT NULL,
                type_fichier TEXT NOT NULL,
                archive_par TEXT NOT NULL
            );
        """)
        
        # 3. TABLE verifications (Historique des vérifications)
        db.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_id INTEGER NOT NULL,
                resultat INTEGER NOT NULL,
                hash_calcule TEXT NOT NULL,
                verifie_par TEXT NOT NULL,
                horodatage TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (archive_id) REFERENCES archives (id)
            );
        """)
        db.commit()

def register_db_teardown(app):
    "Enregistre la fonction de fermeture de la connexion DB."
    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

def add_user(username, password_hash):
    "Ajoute un nouvel utilisateur. Retourne True si succès, False si l'utilisateur existe déjà."
    db = get_db()
    try:
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        # L'utilisateur existe déjà
        return False
        
def get_user(username):
    "Récupère un utilisateur par son nom."
    db = get_db()
    cursor = db.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cursor.fetchone()
        
# --- FONCTIONS D'ARCHIVAGE ---

def insert_archive(nom_fichier, hash_fichier, topic_id, horodatage, taille_fichier, type_fichier, archive_par):
    "Insère un nouvel enregistrement d'archive et retourne son ID."
    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO archives (nom_fichier, hash_fichier, topic_id, horodatage, taille_fichier, type_fichier, archive_par)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nom_fichier, hash_fichier, topic_id, horodatage, taille_fichier, type_fichier, archive_par)
        )
        db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Gérer l'erreur si le hash_fichier ou topic_id existe déjà
        return None

def find_archive_by_topic_id(topic_id):
    "Recherche une archive par Topic ID."
    db = get_db()
    cursor = db.execute("SELECT * FROM archives WHERE topic_id = ?", (topic_id,))
    return cursor.fetchone()

# --- FONCTION DE VÉRIFICATION ---

def insert_verification(archive_id, resultat, hash_calcule, verifie_par):
    "Enregistre un résultat de vérification."
    db = get_db()
    db.execute(
        """INSERT INTO verifications (archive_id, resultat, hash_calcule, verifie_par)
           VALUES (?, ?, ?, ?)""",
        (archive_id, resultat, hash_calcule, verifie_par)
    )
    db.commit()

# --- FONCTIONS POUR LE TABLEAU DE BORD (NOUVELLES) ---

def get_all_archives():
    "Récupère tous les enregistrements d'archives, triés par date la plus récente."
    db = get_db()
    # Utilise 'horodatage' qui est le champ stocké par HederaMock
    cursor = db.execute("SELECT * FROM archives ORDER BY horodatage DESC") 
    return cursor.fetchall()

def get_stats():
    "Récupère les statistiques d'archives et de vérifications."
    db = get_db()
    stats = {}
    
    # Total des documents archivés
    stats['total_archives'] = db.execute("SELECT COUNT(*) FROM archives").fetchone()[0]
    
    # Total des vérifications effectuées
    stats['total_verifications'] = db.execute("SELECT COUNT(*) FROM verifications").fetchone()[0]
    
    # Nombre de vérifications réussies (resultat = 1)
    stats['verifications_ok'] = db.execute("SELECT COUNT(*) FROM verifications WHERE resultat = 1").fetchone()[0]
    
    return stats