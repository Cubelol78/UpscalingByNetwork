"""
Tests d'intégration pour UpscalingByNetwork
UpscalingByNetwork/tests/test_integration.py
"""

import asyncio
import pytest
import tempfile
import shutil
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import des modules à tester
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.core.distributed_server import DistributedServer
from client.windows.core.distributed_client import DistributedClient
from shared.protocol.messages import MessageType, NetworkMessage
from shared.utils.mac_address import get_primary_mac_address

class TestDistributedSystem:
    """Tests d'intégration du système distribué"""
    
    @pytest.fixture
    async def server(self):
        """Fixture pour créer un serveur de test"""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = DistributedServer("localhost", 8889)  # Port différent pour tests
            server.work_dir = Path(temp_dir)
            server.jobs_dir = server.work_dir / "jobs"
            server.temp_dir = server.work_dir / "temp"
            server.setup_directories()
            
            yield server
            
            if server.running:
                await server.stop_server()
    
    @pytest.fixture
    async def client(self):
        """Fixture pour créer un client de test"""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = DistributedClient()
            client.work_dir = Path(temp_dir)
            client.temp_dir = client.work_dir / "temp"
            client.setup_directories()
            
            yield client
            
            if client.connected:
                await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_server_startup_shutdown(self, server):
        """Test du démarrage et arrêt du serveur"""
        # Test démarrage
        start_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)  # Laisser le temps de démarrer
        
        assert server.running is True
        
        # Test arrêt
        await server.stop_server()
        assert server.running is False
        
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_client_connection(self, server, client):
        """Test de connexion client-serveur"""
        # Démarrage du serveur
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            # Connexion du client
            success = await client.connect_to_server("localhost", 8889)
            assert success is True
            assert client.connected is True
            
            # Vérification côté serveur
            assert len(server.clients) == 1
            assert client.mac_address in server.clients
            
            # Déconnexion
            await client.disconnect()
            assert client.connected is False
            
        finally:
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_message_exchange(self, server, client):
        """Test d'échange de messages"""
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            await client.connect_to_server("localhost", 8889)
            
            # Test heartbeat
            original_send = client.websocket.send
            sent_messages = []
            
            async def mock_send(message):
                sent_messages.append(message)
                return await original_send(message)
            
            client.websocket.send = mock_send
            
            # Déclenchement d'un heartbeat
            await client.heartbeat_sender()
            
            # Vérification qu'un message a été envoyé
            assert len(sent_messages) > 0
            
            # Parsing du message
            message_data = json.loads(sent_messages[0])
            assert message_data['type'] == MessageType.HEARTBEAT.value
            
        finally:
            await client.disconnect()
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_job_creation(self, server):
        """Test de création de job"""
        # Création d'un fichier vidéo factice
        test_video = server.work_dir / "test_video.mp4"
        test_video.write_bytes(b"fake video data")
        
        # Création du job
        job_id = await server.create_distributed_job(str(test_video))
        
        assert job_id is not None
        assert job_id in server.jobs
        
        job = server.jobs[job_id]
        assert job.input_video_path == str(test_video)
        assert (server.jobs_dir / job_id).exists()
    
    @pytest.mark.asyncio
    @patch('server.core.distributed_server.subprocess')
    async def test_frame_extraction_mock(self, mock_subprocess, server):
        """Test d'extraction de frames (mocké)"""
        # Mock du processus FFmpeg
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")
        mock_subprocess.create_subprocess_exec.return_value = mock_process
        
        # Création d'un job
        test_video = server.work_dir / "test_video.mp4"
        test_video.write_bytes(b"fake video data")
        
        job_id = await server.create_distributed_job(str(test_video))
        
        # Création manuelle de quelques frames factices
        frames_dir = server.jobs_dir / job_id / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        for i in range(1, 101):  # 100 frames factices
            frame_file = frames_dir / f"frame_{i:06d}.png"
            frame_file.write_bytes(b"fake frame data")
        
        # Test d'extraction
        success = await server.extract_frames_and_create_batches(job_id)
        
        assert success is True
        assert len(server.jobs[job_id].batch_ids) == 2  # 100 frames / 50 par lot = 2 lots
    
    @pytest.mark.asyncio
    async def test_batch_processing_flow(self, server, client):
        """Test du flux complet de traitement de lot"""
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            await client.connect_to_server("localhost", 8889)
            
            # Création d'un lot factice
            from server.models.network_batch import NetworkBatch, BatchStatus
            
            batch = NetworkBatch(
                job_id="test_job",
                frame_start=0,
                frame_end=49,
                frame_paths=[f"frame_{i:06d}.png" for i in range(50)]
            )
            
            server.batches[batch.id] = batch
            
            # Simulation d'assignation
            batch.assign_to_client(client.mac_address)
            
            assert batch.status == BatchStatus.ASSIGNED
            assert batch.assigned_client == client.mac_address
            
            # Simulation de démarrage de traitement
            batch.start_processing()
            assert batch.status == BatchStatus.PROCESSING
            
            # Simulation de completion
            batch.complete()
            assert batch.status == BatchStatus.COMPLETED
            assert batch.progress == 100.0
            
        finally:
            await client.disconnect()
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_multiple_clients(self, server):
        """Test avec plusieurs clients connectés"""
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        clients = []
        
        try:
            # Création de 3 clients
            for i in range(3):
                client = DistributedClient()
                client.mac_address = f"00:00:00:00:00:0{i}"  # MAC factice unique
                success = await client.connect_to_server("localhost", 8889)
                assert success is True
                clients.append(client)
            
            # Vérification côté serveur
            assert len(server.clients) == 3
            
            # Test de distribution de lots
            available_clients = [
                mac for mac, client in server.clients.items()
                if client.is_online
            ]
            
            assert len(available_clients) == 3
            
        finally:
            # Déconnexion de tous les clients
            for client in clients:
                if client.connected:
                    await client.disconnect()
            
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_client_reconnection(self, server, client):
        """Test de reconnexion automatique"""
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            # Première connexion
            await client.connect_to_server("localhost", 8889)
            assert client.connected is True
            
            original_mac = client.mac_address
            
            # Simulation d'une déconnexion brutale
            await client.websocket.close()
            await asyncio.sleep(1)
            
            # Reconnexion
            await client.connect_to_server("localhost", 8889)
            assert client.connected is True
            assert client.mac_address == original_mac
            
        finally:
            await client.disconnect()
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_security_handshake(self, server, client):
        """Test du handshake de sécurité"""
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            # Mock des méthodes de sécurité pour tester le flux
            original_handshake = server.security_manager.handshake_with_client
            handshake_called = False
            
            async def mock_handshake(client_mac, websocket):
                nonlocal handshake_called
                handshake_called = True
                return b"fake_session_key"
            
            server.security_manager.handshake_with_client = mock_handshake
            
            await client.connect_to_server("localhost", 8889)
            
            assert handshake_called is True
            
        finally:
            await client.disconnect()
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

class TestUtilities:
    """Tests des utilitaires"""
    
    def test_mac_address_detection(self):
        """Test de détection d'adresse MAC"""
        mac = get_primary_mac_address()
        
        assert mac is not None
        assert len(mac) == 17  # Format XX:XX:XX:XX:XX:XX
        assert mac.count(':') == 5
    
    def test_message_serialization(self):
        """Test de sérialisation des messages"""
        from shared.protocol.messages import NetworkMessage, MessageType
        
        message = NetworkMessage(
            type=MessageType.HEARTBEAT,
            client_mac="00:11:22:33:44:55",
            timestamp=time.time(),
            data={'status': 'idle', 'progress': 0.0}
        )
        
        # Sérialisation
        json_str = message.to_json()
        assert isinstance(json_str, str)
        
        # Désérialisation
        restored_message = NetworkMessage.from_json(json_str)
        
        assert restored_message.type == message.type
        assert restored_message.client_mac == message.client_mac
        assert restored_message.data == message.data
    
    def test_batch_status_transitions(self):
        """Test des transitions d'état des lots"""
        from server.models.network_batch import NetworkBatch, BatchStatus
        
        batch = NetworkBatch(
            job_id="test_job",
            frame_paths=["frame1.png", "frame2.png"]
        )
        
        # État initial
        assert batch.status == BatchStatus.PENDING
        
        # Assignation
        batch.assign_to_client("test_client")
        assert batch.status == BatchStatus.ASSIGNED
        assert batch.assigned_client == "test_client"
        
        # Démarrage
        batch.start_processing()
        assert batch.status == BatchStatus.PROCESSING
        assert batch.start_time is not None
        
        # Progression
        batch.update_progress(50.0, 1)
        assert batch.progress == 50.0
        assert batch.frames_processed == 1
        
        # Completion
        batch.complete()
        assert batch.status == BatchStatus.COMPLETED
        assert batch.progress == 100.0
    
    def test_job_statistics(self):
        """Test des statistiques de job"""
        from server.models.distributed_job import DistributedJob, JobStatus
        
        job = DistributedJob(
            input_video_path="test.mp4",
            output_video_path="output.mp4"
        )
        
        # État initial
        assert job.status == JobStatus.CREATED
        assert job.progress == 0.0
        
        # Simulation de lots
        job.batch_ids = ["batch1", "batch2", "batch3"]
        assert job.total_batches == 3
        
        # Progression
        job.update_batch_completion("batch1", True, 50)
        assert job.completed_batches == 1
        assert job.frames_processed == 50
        assert job.progress == pytest.approx(33.33, rel=1e-2)
        
        job.update_batch_completion("batch2", True, 50)
        assert job.completed_batches == 2
        assert job.progress == pytest.approx(66.67, rel=1e-2)

@pytest.mark.asyncio
async def test_end_to_end_simulation():
    """Test de simulation complète bout en bout"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Configuration des chemins temporaires
        work_dir = Path(temp_dir)
        
        # Création du serveur
        server = DistributedServer("localhost", 8890)
        server.work_dir = work_dir / "server"
        server.setup_directories()
        
        # Démarrage du serveur
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1)
        
        try:
            # Création d'un client
            client = DistributedClient()
            client.work_dir = work_dir / "client"
            client.setup_directories()
            
            # Connexion
            await client.connect_to_server("localhost", 8890)
            assert client.connected is True
            
            # Simulation d'un job avec traitement (sans Real-ESRGAN réel)
            test_video = work_dir / "test.mp4"
            test_video.write_bytes(b"fake video content")
            
            # Le test s'arrête ici car il faudrait mocker Real-ESRGAN
            # pour un test complet
            
            # Nettoyage
            await client.disconnect()
            
        finally:
            await server.stop_server()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    # Exécution des tests
    pytest.main([__file__, "-v"])