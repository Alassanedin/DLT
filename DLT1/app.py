import os
import hashlib
import json
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from hedera_mock import hedera_client
import database 
from werkzeug.utils import secure_filename 

app = Flask(__name__)
app.secret_key = "supersecret_key_for_sessions_and_flash" 

UPLOAD_FOLDER = "uploads"
CERT_FOLDER = "certificats"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CERT_FOLDER, exist_ok=True)

# ARCHIVED_FILES_MAP est maintenue pour le téléchargement immédiat des fichiers physiques
# C'est un cache : {topic_id: filename, ...}
ARCHIVED_FILES_MAP = {} 

database.init_db(app)
database.register_db_teardown(app)

def calculer_hash(fichier):
    "Calcule le hash SHA-256 d'un fichier."
    hash_sha256 = hashlib.sha256()
    with open(fichier, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            hash_sha256.update(block)
        return hash_sha256.hexdigest()

# --- ROUTES D'AUTHENTIFICATION (INCHANGÉES) ---

@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = database.get_user(username)

        if user and user["password_hash"] == database.hash_password(password):
            session['logged_in'] = True
            session['username'] = user['username']
            flash(f"Connexion réussie, {username} !", "success")
            return redirect(url_for("tableau_de_bord")) # Redirection vers le tableau de bord
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "danger")
    
    return render_template("connexion.html")

@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if len(username) < 3:
            flash("Le nom d'utilisateur doit contenir au moins 3 caractères.", "danger")
            return redirect(url_for("inscription"))
        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
            return redirect(url_for("inscription"))
        
        password_hash = database.hash_password(password)
        
        if database.add_user(username, password_hash):
            flash("Compte créé avec succès ! Veuillez vous connecter.", "success")
            return redirect(url_for("connexion"))
        else:
            flash("Nom d'utilisateur déjà existant. Veuillez en choisir un autre.", "danger")
    
    return render_template("inscription.html")
    
@app.route("/deconnexion")
def deconnexion():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("connexion"))

# --- ROUTES PRINCIPALES (MODIFIÉES) ---

@app.route("/")
def index():
    if not session.get('logged_in'):
        return redirect(url_for("connexion"))
    # La page d'accueil principale est désormais la page d'archivage/vérification (index.html)
    return render_template("index.html")

@app.route("/tableau_de_bord")
def tableau_de_bord():
    if not session.get('logged_in'):
        flash("Veuillez vous connecter pour accéder au tableau de bord.", "danger")
        return redirect(url_for("connexion"))
    
    # Récupérer les données pour le tableau de bord
    archives = database.get_all_archives()
    stats = database.get_stats()
    
    return render_template("dashboard.html", archives=archives, stats=stats)


@app.route("/archiver", methods=["POST"])
def archiver():
    if not session.get('logged_in'):
        flash("Vous devez être connecté pour archiver un document.", "danger")
        return redirect(url_for("connexion"))
    
    if "document" not in request.files:
        flash("Aucun fichier sélectionné.", "danger")
        return redirect(url_for("index"))

    file = request.files["document"]
    if file.filename == "":
        flash("Aucun fichier sélectionné.", "danger")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    doc_hash = calculer_hash(filepath)
    
    # Simuler la soumission à Hedera et obtenir le Topic ID et l'horodatage
    topic_id, timestamp = hedera_client.submit_document(doc_hash, filename)
    
    # Enregistrer les métadonnées de l'archive dans la base de données
    taille_fichier = os.path.getsize(filepath)
    type_fichier = os.path.splitext(filename)[1].lstrip('.')
    database.insert_archive(filename, doc_hash, topic_id, timestamp, taille_fichier, type_fichier, session['username'])
    
    # Sauvegarder le hash pour le téléchargement
    ARCHIVED_FILES_MAP[topic_id] = filename
    
    flash("Document archivé avec succès!", "success")
    return render_template("resultat_archivage.html", 
                           filename=filename, 
                           doc_hash=doc_hash, 
                           topic_id=topic_id, 
                           timestamp=timestamp)

@app.route("/verifier", methods=["GET", "POST"])
def verifier():
    if not session.get('logged_in'):
        flash("Veuillez vous connecter pour vérifier un document.", "danger")
        return redirect(url_for("connexion"))
        
    topic_id = request.values.get("topic_id")
    file = request.files.get("document") if request.files else None # Pour gérer les requêtes POST et GET

    # Si c'est une requête GET (e.g. depuis le tableau de bord) avec topic_id
    if request.method == 'GET' and topic_id:
        valide, timestamp, stored_hash, stored_filename = hedera_client.retrieve_document_info(topic_id)
        
        doc_hash_display = stored_hash
        filename_display = stored_filename
        download_hash = topic_id if valide else None
        
        return render_template("resultat_verification.html",
                               filename=filename_display,
                               topic_id=topic_id,
                               valide=valide,
                               timestamp=timestamp,
                               doc_hash=doc_hash_display,
                               download_hash=download_hash)
    
    # Si c'est une requête POST (e.g. depuis index.html)
    if request.method == "POST":
        
        doc_hash_display = None
        filename_display = None

        if file and file.filename != "":
            # Vérification avec un fichier et un Topic ID
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            doc_hash_to_check = calculer_hash(filepath)
            
            valide, timestamp, stored_hash, stored_filename = hedera_client.verify_document_with_file(doc_hash_to_check, topic_id)
            
            doc_hash_display = doc_hash_to_check
            filename_display = filename
            
            # Enregistrer le résultat de la vérification dans la base de données
            archive = database.find_archive_by_topic_id(topic_id)
            if archive:
                verifie_par = session['username'] if 'username' in session else 'Anonyme'
                database.insert_verification(archive['id'], int(valide), doc_hash_to_check, verifie_par)
        else:
            # Recherche d'archive uniquement avec un Topic ID
            valide, timestamp, stored_hash, stored_filename = hedera_client.retrieve_document_info(topic_id)
            doc_hash_display = stored_hash
            filename_display = stored_filename
            
        download_hash = topic_id if valide else None

        return render_template("resultat_verification.html",
                               filename=filename_display,
                               topic_id=topic_id,
                               valide=valide,
                               timestamp=timestamp,
                               doc_hash=doc_hash_display,
                               download_hash=download_hash)

    # Si on arrive ici sans action (e.g. GET sans topic_id), on redirige vers l'index.
    return redirect(url_for("index"))


@app.route("/telecharger/<download_hash>")
def telecharger_document(download_hash):
    if not session.get('logged_in'):
        flash("Vous devez être connecté pour télécharger un document.", "danger")
        return redirect(url_for("connexion"))
        
    if download_hash not in ARCHIVED_FILES_MAP:
        # Tentative de recharger la map à partir de la DB si le cache a été perdu
        archive = database.find_archive_by_topic_id(download_hash)
        if archive:
            # Si trouvé dans la DB, mettre à jour le cache
            ARCHIVED_FILES_MAP[download_hash] = archive['nom_fichier']
        else:
            flash("Document introuvable pour le téléchargement.", "danger")
            return redirect(url_for("tableau_de_bord"))

    filename = ARCHIVED_FILES_MAP[download_hash]
    
    try:
        return send_from_directory(
            UPLOAD_FOLDER,
            filename,
            as_attachment=True
        )
    except FileNotFoundError:
        flash(f"Le fichier physique {filename} n'existe plus sur le serveur. Seule la trace d'archivage persiste.", "danger")
        return redirect(url_for("tableau_de_bord"))

if __name__ == "__main__":
    app.run(debug=True)