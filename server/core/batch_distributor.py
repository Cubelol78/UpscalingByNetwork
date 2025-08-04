# UpscalingByNetwork/server/core/batch_distributor.py

import time


async def distribute_batches(self):
    """Distribution intelligente des lots"""
    
    available_clients = self.get_available_clients()
    pending_batches = self.get_pending_batches()
    
    # Gestion des doublons si plus de clients que de lots
    if len(available_clients) > len(pending_batches) and len(pending_batches) < 5:
        # Créer des doublons des lots les plus anciens
        for i in range(len(pending_batches), len(available_clients)):
            duplicate_batch = self.create_duplicate_batch(pending_batches[i % len(pending_batches)])
            pending_batches.append(duplicate_batch)
    
    # Attribution des lots
    for client_mac, batch in zip(available_clients, pending_batches):
        await self.assign_batch_to_client(client_mac, batch)

async def assign_batch_to_client(self, client_mac: str, batch: dict):
    """Assigne un lot à un client spécifique"""
    
    # 1. Génération clé de session
    session_key = self.security_manager.generate_session_key()
    
    # 2. Chiffrement du lot
    encrypted_batch = self.security_manager.encrypt_batch(
        batch['zip_path'], 
        session_key
    )
    
    # 3. Handshake sécurisé avec le client
    await self.security_manager.exchange_keys(client_mac, session_key)
    
    # 4. Envoi du lot chiffré
    await self.send_encrypted_batch(client_mac, encrypted_batch, batch['id'])
    
    # 5. Mise à jour du statut
    batch['status'] = 'assigned'
    batch['assigned_to'] = client_mac
    batch['assigned_at'] = time.time()