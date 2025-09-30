import time
import random

class HederaMock:
    def __init__(self):
        # La clé est le Topic ID, la valeur est un tuple: (doc_hash, timestamp, filename)
        self.ledger = {}

    def submit_document(self, doc_hash, filename):
        """Soumet le hash et le nom du fichier au 'ledger'."""
        topic_id = f"0.0.{random.randint(100000, 999999)}"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        # Stocke le hash, le timestamp ET le nom de fichier
        self.ledger[topic_id] = (doc_hash, timestamp, filename)
        return topic_id, timestamp

    def verify_document_with_file(self, doc_hash_to_check, topic_id):
        """Vérifie le hash d'un document fourni par l'utilisateur par rapport au Topic ID."""
        if topic_id not in self.ledger:
            # Topic ID inconnu
            return False, None, None, None # valide, timestamp, stored_hash, stored_filename
        
        stored_hash, timestamp, stored_filename = self.ledger[topic_id]
        
        # Vérification du Hash
        is_valid = stored_hash == doc_hash_to_check
        
        return is_valid, timestamp, stored_hash, stored_filename

    def retrieve_document_info(self, topic_id):
        """Récupère l'information d'archivage uniquement avec le Topic ID."""
        if topic_id not in self.ledger:
            # Topic ID inconnu
            return False, None, None, None # valide, timestamp, stored_hash, stored_filename
        
        stored_hash, timestamp, stored_filename = self.ledger[topic_id]
        
        # Le Topic ID est trouvé, on retourne les infos d'archive
        return True, timestamp, stored_hash, stored_filename

hedera_client = HederaMock()