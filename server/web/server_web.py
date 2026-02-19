"""
Interface web du serveur d'upscaling (FastAPI + WebSocket)
Permet l'accès à l'interface de contrôle via un navigateur.
"""

import asyncio
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import NetworkConfig, ProcessingConfig


# ============================================================================
# MODÈLES PYDANTIC (corps des requêtes)
# ============================================================================

class AuthRequest(BaseModel):
    password: str

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

class JobCreateRequest(BaseModel):
    path: str
    upscale_factor: int = 4
    engine: str = "realesrgan"
    model: str = "realesr-animevideov3"
    tta_mode: bool = False
    denoise_level: int = -1

class WebhookUpdateRequest(BaseModel):
    enabled: bool = False
    url: str = ""
    events: str = ""  # JSON string des événements configurés

class ConfigBatchRequest(BaseModel):
    params: dict  # {key: value, ...}


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class ServerWebInterface:
    """
    Interface web du serveur d'upscaling.
    Tourne dans un thread asyncio dédié, indépendant du serveur TCP.
    """

    def __init__(self, Database):
        """
        Initialise l'interface web

        Args:
            Database: Instance de DatabaseManager (toujours disponible)
        """
        self.Logger = GetModuleLogger("ServerWeb")
        self.Database = Database

        # Composants upscaling (optionnels — disponibles après StartServer)
        self.Server = None         # UpscalingServer
        self.JobManager = None     # JobManager
        self.Distributor = None    # BatchDistributor
        self.ServerStartTime = None

        # Sécurité
        self._Token = str(uuid.uuid4())
        self._Lock = threading.Lock()

        # Thread/boucle dédiés
        self._Thread = None
        self._Loop = None
        self._UvicornServer = None
        self._Running = False

        # Dossier des fichiers statiques
        self._StaticDir = Path(__file__).parent / "static"

        # Application FastAPI
        self._App = FastAPI(title="Upscaling Server Web UI", docs_url=None, redoc_url=None)
        self._SetupMiddleware()
        self._SetupRoutes()

    def SetServerComponents(self, Server, JobManager, Distributor, ServerLoop=None):
        """
        Appelé quand le serveur d'upscaling démarre.
        Donne accès aux composants pour les endpoints.

        Args:
            Server: Instance UpscalingServer
            JobManager: Instance JobManager
            Distributor: Instance BatchDistributor
            ServerLoop: Boucle asyncio du serveur upscaling (pour run_coroutine_threadsafe)
        """
        with self._Lock:
            self.Server = Server
            self.JobManager = JobManager
            self.Distributor = Distributor
            self.ServerStartTime = time.time()
            self._ServerLoop = ServerLoop  # Boucle asyncio du serveur upscaling
        self.Logger.info("Composants serveur upscaling connectés à la web UI")

    def ClearServerComponents(self):
        """Appelé quand le serveur d'upscaling s'arrête."""
        with self._Lock:
            self.Server = None
            self.JobManager = None
            self.Distributor = None
            self.ServerStartTime = None
            self._ServerLoop = None
        self.Logger.info("Composants serveur upscaling déconnectés de la web UI")

    def GetToken(self) -> str:
        """Retourne le token d'authentification actuel."""
        return self._Token

    def Start(self, Host: str = "0.0.0.0", Port: int = None):
        """
        Démarre l'interface web dans un thread asyncio dédié.

        Args:
            Host: Adresse d'écoute
            Port: Port (défaut : NetworkConfig.SERVER_WEB_PORT)
        """
        if Port is None:
            Port = NetworkConfig.SERVER_WEB_PORT

        if self._Running:
            self.Logger.warning("Web UI déjà en cours d'exécution")
            return

        self._WebHost = Host
        self._WebPort = Port

        def _RunThread():
            import uvicorn
            self._Loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._Loop)

            Config = uvicorn.Config(
                self._App,
                host=Host,
                port=Port,
                loop="none",
                log_level="warning",
                access_log=False
            )
            self._UvicornServer = uvicorn.Server(Config)
            self._Running = True

            try:
                self._Loop.run_until_complete(self._UvicornServer.serve())
            except Exception as e:
                self.Logger.error(f"Erreur web UI: {e}")
            finally:
                self._Running = False
                self._Loop.close()

        self._Thread = threading.Thread(target=_RunThread, daemon=True, name="ServerWebUI")
        self._Thread.start()
        self.Logger.info(f"Web UI serveur démarrée sur http://{Host}:{Port}")

    def Stop(self):
        """Arrête l'interface web proprement."""
        if self._UvicornServer and self._Running:
            self._UvicornServer.should_exit = True
        self._Running = False

    # ========================================================================
    # SETUP FASTAPI
    # ========================================================================

    def _SetupMiddleware(self):
        """Configure les middlewares FastAPI."""
        self._App.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _VerifyToken(self, request: Request) -> bool:
        """Vérifie le token d'authentification dans les headers."""
        AuthHeader = request.headers.get("Authorization", "")
        if AuthHeader.startswith("Bearer "):
            Token = AuthHeader[7:]
            return Token == self._Token
        # Accepte aussi token en query param pour WebSocket
        Token = request.query_params.get("token", "")
        return Token == self._Token

    def _SetupRoutes(self):
        """Configure toutes les routes FastAPI."""
        App = self._App

        # Monter les fichiers statiques si le dossier existe
        if self._StaticDir.exists():
            App.mount("/static", StaticFiles(directory=str(self._StaticDir)), name="static")

        # ----------------------------------------------------------------
        # PAGE PRINCIPALE
        # ----------------------------------------------------------------

        @App.get("/", response_class=HTMLResponse)
        async def Index():
            IndexPath = self._StaticDir / "index.html"
            if IndexPath.exists():
                return HTMLResponse(content=IndexPath.read_text(encoding="utf-8"))
            return HTMLResponse(content="<h1>Web UI non disponible (fichiers statiques manquants)</h1>")

        # ----------------------------------------------------------------
        # AUTHENTIFICATION
        # ----------------------------------------------------------------

        @App.post("/api/auth")
        async def Auth(Body: AuthRequest):
            """Authentification par mot de passe. Retourne le token si succès."""
            DbPassword = self.Database.GetParameter("server_password", "")

            if not DbPassword:
                # Aucun mot de passe configuré → accès libre
                return {"token": self._Token, "no_password": True}

            # Vérifie le mot de passe (comparaison directe — le hash est géré côté protocole réseau)
            if Body.password == DbPassword:
                return {"token": self._Token}

            # Tentative avec hash PBKDF2 (si le mot de passe stocké est hashé)
            try:
                from shared.protocol.encryption import AESEncryption
                Enc = AESEncryption.__new__(AESEncryption)
                Hashed = Enc._HashPassword(Body.password) if hasattr(Enc, '_HashPassword') else None
                if Hashed and Hashed == DbPassword:
                    return {"token": self._Token}
            except Exception:
                pass

            raise HTTPException(status_code=401, detail="Mot de passe incorrect")

        @App.get("/api/auth/check")
        async def AuthCheck(request: Request):
            """Vérifie si le token est valide."""
            Valid = self._VerifyToken(request)
            NoPassword = not bool(self.Database.GetParameter("server_password", ""))
            return {"valid": Valid or NoPassword, "no_password": NoPassword}

        # ----------------------------------------------------------------
        # STATUT GÉNÉRAL
        # ----------------------------------------------------------------

        @App.get("/api/status")
        async def GetStatus(request: Request):
            self._RequireAuth(request)
            with self._Lock:
                ServerRunning = self.Server is not None
                Uptime = int(time.time() - self.ServerStartTime) if self.ServerStartTime else 0

            return {
                "server_running": ServerRunning,
                "uptime": Uptime,
                "uptime_str": self._FormatUptime(Uptime)
            }

        # ----------------------------------------------------------------
        # DASHBOARD
        # ----------------------------------------------------------------

        @App.get("/api/dashboard")
        async def GetDashboard(request: Request):
            self._RequireAuth(request)
            return self._BuildDashboard()

        # ----------------------------------------------------------------
        # CLIENTS
        # ----------------------------------------------------------------

        @App.get("/api/clients")
        async def GetClients(request: Request):
            self._RequireAuth(request)
            return self._BuildClientsList()

        @App.post("/api/clients/{ClientId}/disconnect")
        async def DisconnectClient(ClientId: str, request: Request):
            self._RequireAuth(request)
            with self._Lock:
                if not self.Server:
                    raise HTTPException(status_code=503, detail="Serveur non démarré")
                Manager = self.Server.ClientManager
            # DisconnectClient est async → l'appeler dans la boucle du serveur
            await self._RunInServerLoop(Manager.DisconnectClient(ClientId, "Déconnecté via web UI"))
            return {"success": True}

        # ----------------------------------------------------------------
        # JOBS (VIDÉOS)
        # ----------------------------------------------------------------

        @App.get("/api/jobs")
        async def GetJobs(request: Request):
            self._RequireAuth(request)
            Videos = self.Database.GetAllVideos(Limit=100)
            return {"jobs": [self._VideoToDict(V) for V in Videos]}

        @App.post("/api/jobs")
        async def CreateJob(Body: JobCreateRequest, request: Request):
            self._RequireAuth(request)
            with self._Lock:
                if not self.JobManager:
                    raise HTTPException(status_code=503, detail="Serveur non démarré")
                JobMgr = self.JobManager

            if not os.path.isfile(Body.path):
                raise HTTPException(status_code=400, detail=f"Fichier introuvable: {Body.path}")

            VideoId = await self._RunInServerLoop(
                JobMgr.AddJob(
                    VideoPath=Body.path,
                    UpscaleFactor=Body.upscale_factor,
                    Engine=Body.engine,
                    Model=Body.model,
                    TtaMode=Body.tta_mode,
                    DenoiseLevel=Body.denoise_level
                )
            )
            if not VideoId:
                raise HTTPException(status_code=500, detail="Impossible d'ajouter la vidéo")
            return {"success": True, "video_id": VideoId}

        @App.delete("/api/jobs/{VideoId}")
        async def DeleteJob(VideoId: str, request: Request):
            self._RequireAuth(request)
            with self._Lock:
                if not self.JobManager:
                    raise HTTPException(status_code=503, detail="Serveur non démarré")
                JobMgr = self.JobManager

            Success = await self._RunInServerLoop(JobMgr.CancelJob(VideoId))
            if not Success:
                # Essayer juste la suppression en DB
                self.Database.DeleteVideo(VideoId)
            return {"success": True}

        # ----------------------------------------------------------------
        # CONFIGURATION
        # ----------------------------------------------------------------

        @App.get("/api/config")
        async def GetConfig(request: Request):
            self._RequireAuth(request)
            Config = self.Database.GetServerConfig()
            # Ajouter webhooks
            Config["webhook_enabled"] = self.Database.GetParameter("webhook_enabled", "false") == "true"
            Config["webhook_url"] = self.Database.GetParameter("webhook_url", "")
            Config["webhook_events"] = self.Database.GetParameter("webhook_events", "")
            return Config

        @App.put("/api/config")
        async def UpdateConfig(Body: ConfigBatchRequest, request: Request):
            self._RequireAuth(request)
            for Key, Value in Body.params.items():
                self.Database.SetParameter(Key, str(Value))
            return {"success": True}

        # ----------------------------------------------------------------
        # WEBHOOKS
        # ----------------------------------------------------------------

        @App.get("/api/webhooks")
        async def GetWebhooks(request: Request):
            self._RequireAuth(request)
            return {
                "enabled": self.Database.GetParameter("webhook_enabled", "false") == "true",
                "url": self.Database.GetParameter("webhook_url", ""),
                "events": self.Database.GetParameter("webhook_events", "")
            }

        @App.put("/api/webhooks")
        async def UpdateWebhooks(Body: WebhookUpdateRequest, request: Request):
            self._RequireAuth(request)
            self.Database.SetParameter("webhook_enabled", "true" if Body.enabled else "false")
            self.Database.SetParameter("webhook_url", Body.url)
            self.Database.SetParameter("webhook_events", Body.events)
            return {"success": True}

        @App.post("/api/webhooks/test")
        async def TestWebhook(request: Request):
            self._RequireAuth(request)
            try:
                from shared.utils.webhook_manager import TriggerServerWebhook
                await self._RunInServerLoop(TriggerServerWebhook("test", {"message": "Test depuis Web UI"}))
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ----------------------------------------------------------------
        # WEBSOCKET (push état toutes les 1s)
        # ----------------------------------------------------------------

        @App.websocket("/ws")
        async def WebSocketEndpoint(Ws: WebSocket, token: str = ""):
            # Vérifie le token
            NoPassword = not bool(self.Database.GetParameter("server_password", ""))
            if not NoPassword and token != self._Token:
                await Ws.close(code=4001, reason="Token invalide")
                return

            await Ws.accept()
            self.Logger.debug("WebSocket client connecté")
            try:
                while True:
                    State = self._BuildFullState()
                    await Ws.send_json(State)
                    await asyncio.sleep(1.0)
            except WebSocketDisconnect:
                self.Logger.debug("WebSocket client déconnecté")
            except Exception as e:
                self.Logger.debug(f"Erreur WebSocket: {e}")

    # ========================================================================
    # MÉTHODES UTILITAIRES
    # ========================================================================

    def _RequireAuth(self, request: Request):
        """Lève HTTPException 401 si non authentifié."""
        NoPassword = not bool(self.Database.GetParameter("server_password", ""))
        if NoPassword:
            return
        if not self._VerifyToken(request):
            raise HTTPException(status_code=401, detail="Non authentifié")

    async def _RunInServerLoop(self, Coro):
        """
        Exécute une coroutine dans la boucle asyncio du serveur upscaling
        via run_coroutine_threadsafe (thread-safe depuis la boucle web).
        Si la boucle serveur n'est pas disponible, tente dans la boucle courante.
        """
        import concurrent.futures
        try:
            with self._Lock:
                ServerLoop = getattr(self, '_ServerLoop', None)

            if ServerLoop and ServerLoop.is_running():
                Future = asyncio.run_coroutine_threadsafe(Coro, ServerLoop)
                # Attendre le résultat de manière non-bloquante dans la boucle web
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: Future.result(timeout=10)
                )
            else:
                # Pas de boucle serveur connue → exécuter localement (cas fallback)
                return await Coro
        except Exception as e:
            self.Logger.error(f"Erreur _RunInServerLoop: {e}")
            return None

    def _BuildFullState(self) -> dict:
        """Construit l'état complet pour le WebSocket."""
        with self._Lock:
            ServerRunning = self.Server is not None
            Uptime = int(time.time() - self.ServerStartTime) if self.ServerStartTime else 0

        return {
            "server_running": ServerRunning,
            "uptime": Uptime,
            "uptime_str": self._FormatUptime(Uptime),
            "dashboard": self._BuildDashboard(),
            "clients": self._BuildClientsList(),
            "jobs": [self._VideoToDict(V) for V in (self.Database.GetAllVideos(Limit=50) or [])]
        }

    def _BuildDashboard(self) -> dict:
        """Construit les stats du dashboard."""
        try:
            Stats = self.Database.GetStatistics() or {}
            VideosByStatus = Stats.get("videos_by_status", {})
            BatchesByStatus = Stats.get("batches_by_status", {})

            with self._Lock:
                ActiveClients = 0
                if self.Server and self.Server.ClientManager:
                    ActiveClients = self.Server.ClientManager.GetClientCount()

            # Activité récente (dernières vidéos)
            RecentVideos = self.Database.GetAllVideos(Limit=5) or []
            RecentActivity = [
                {
                    "video_id": V.VideoId[:8] if V.VideoId else "",
                    "filename": os.path.basename(V.VideoPath) if V.VideoPath else "",
                    "status": V.Status,
                    "progress": V.Progress or 0
                }
                for V in RecentVideos
            ]

            return {
                "active_clients": ActiveClients,
                "videos_queued": VideosByStatus.get("queued", 0),
                "videos_processing": (
                    VideosByStatus.get("processing", 0) +
                    VideosByStatus.get("extracting", 0) +
                    VideosByStatus.get("distributing", 0) +
                    VideosByStatus.get("reassembling", 0) +
                    VideosByStatus.get("encoding", 0)
                ),
                "videos_completed": VideosByStatus.get("completed", 0),
                "videos_failed": VideosByStatus.get("failed", 0),
                "batches_pending": BatchesByStatus.get("pending", 0) + BatchesByStatus.get("assigned", 0),
                "batches_completed": BatchesByStatus.get("completed", 0),
                "batches_failed": BatchesByStatus.get("failed", 0),
                "recent_activity": RecentActivity
            }
        except Exception as e:
            self.Logger.error(f"Erreur BuildDashboard: {e}")
            return {}

    def _BuildClientsList(self) -> list:
        """Construit la liste des clients connectés."""
        try:
            with self._Lock:
                if not self.Server or not self.Server.ClientManager:
                    return []
                Clients = self.Server.ClientManager.GetAllClients()
                BatchInfo = {}
                if self.Distributor:
                    BatchInfo = self.Distributor.GetAllClientsBatchInfo()

            Result = []
            for ClientId, Info in Clients.items():
                BInfo = BatchInfo.get(ClientId, {})
                LastHB = getattr(Info, 'LastHeartbeat', None)
                LastHBStr = f"{int(time.time() - LastHB)}s" if LastHB else "N/A"
                ConnectedAt = getattr(Info, 'ConnectedAt', None)
                UptimeSeconds = int((time.time() - ConnectedAt.timestamp())) if ConnectedAt else 0

                Result.append({
                    "client_id": ClientId,
                    "client_id_short": ClientId[:8] if len(ClientId) > 8 else ClientId,
                    "ip_address": getattr(Info, 'IpAddress', "?"),
                    "status": getattr(Info, 'Status', "?"),
                    "active_batches": BInfo.get("active_count", 0),
                    "max_batches": BInfo.get("max_batches", 1),
                    "batch_ids": BInfo.get("batch_ids", []),
                    "last_heartbeat": LastHBStr,
                    "uptime": self._FormatUptime(UptimeSeconds),
                    "authenticated": getattr(Info, 'Authenticated', False)
                })
            return Result
        except Exception as e:
            self.Logger.error(f"Erreur BuildClientsList: {e}")
            return []

    def _VideoToDict(self, Video) -> dict:
        """Convertit un objet Video en dict JSON-serializable."""
        if Video is None:
            return {}
        return {
            "video_id": getattr(Video, 'VideoId', ''),
            "video_id_short": (getattr(Video, 'VideoId', '') or '')[:8],
            "filename": os.path.basename(getattr(Video, 'VideoPath', '') or ''),
            "video_path": getattr(Video, 'VideoPath', ''),
            "status": getattr(Video, 'Status', ''),
            "progress": getattr(Video, 'Progress', 0) or 0,
            "total_batches": getattr(Video, 'TotalBatches', 0) or 0,
            "completed_batches": getattr(Video, 'CompletedBatches', 0) or 0,
            "upscale_factor": getattr(Video, 'UpscaleFactor', 4),
            "engine": getattr(Video, 'Engine', ''),
            "model": getattr(Video, 'Model', ''),
            "tta_mode": getattr(Video, 'TtaMode', False),
            "denoise_level": getattr(Video, 'DenoiseLevel', -1),
            "created_at": str(getattr(Video, 'CreatedAt', '') or ''),
            "started_at": str(getattr(Video, 'StartedAt', '') or ''),
            "completed_at": str(getattr(Video, 'CompletedAt', '') or ''),
            "error_message": getattr(Video, 'ErrorMessage', '') or ''
        }

    @staticmethod
    def _FormatUptime(Seconds: int) -> str:
        """Formate une durée en secondes en chaîne lisible."""
        if Seconds < 60:
            return f"{Seconds}s"
        elif Seconds < 3600:
            return f"{Seconds // 60}m {Seconds % 60}s"
        else:
            H = Seconds // 3600
            M = (Seconds % 3600) // 60
            return f"{H}h {M}m"
