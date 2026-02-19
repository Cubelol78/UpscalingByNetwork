"""
Interface web du client d'upscaling (FastAPI + WebSocket)
Permet l'accès à l'interface de monitoring via un navigateur.
"""

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import NetworkConfig


# ============================================================================
# MODÈLES PYDANTIC
# ============================================================================

class AuthRequest(BaseModel):
    password: str = ""

class ServerAddRequest(BaseModel):
    name: str
    host: str
    port: int
    password: str = ""

class ConnectRequest(BaseModel):
    host: str
    port: int
    password: str = ""
    data_port: int = None

class ConfigUpdateRequest(BaseModel):
    params: dict

class WebhookUpdateRequest(BaseModel):
    enabled: bool = False
    url: str = ""
    events: str = ""


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class ClientWebInterface:
    """
    Interface web du client d'upscaling.
    Tourne dans un thread asyncio dédié, indépendant de la connexion TCP.
    """

    def __init__(self):
        """Initialise l'interface web."""
        self.Logger = GetModuleLogger("ClientWeb")

        # Référence au client (set quand connecté)
        self.Client = None
        self._ClientLock = threading.Lock()

        # Gestionnaire de serveurs sauvegardés
        try:
            from client.core.connection import SavedServersManager
            self.ServerManager = SavedServersManager()
        except Exception:
            self.ServerManager = None

        # Gestionnaire de config performances
        try:
            from client.utils.performance_config import PerformanceConfigManager
            self.PerfManager = PerformanceConfigManager()
        except Exception:
            self.PerfManager = None

        # Sécurité (pas de mot de passe côté client par défaut — accès local)
        self._Token = str(uuid.uuid4())
        self._AuthEnabled = False  # Désactivé par défaut (accès local uniquement)

        # Thread/boucle dédiés
        self._Thread = None
        self._Loop = None
        self._UvicornServer = None
        self._Running = False

        # Dossier statique
        self._StaticDir = Path(__file__).parent / "static"

        # Application FastAPI
        self._App = FastAPI(title="Upscaling Client Web UI", docs_url=None, redoc_url=None)
        self._SetupMiddleware()
        self._SetupRoutes()

    def SetClient(self, Client):
        """Appelé quand le client se connecte à un serveur."""
        with self._ClientLock:
            self.Client = Client
        self.Logger.info("Client connecté à la web UI")

    def ClearClient(self):
        """Appelé quand le client se déconnecte."""
        with self._ClientLock:
            self.Client = None

    def Start(self, Host: str = "127.0.0.1", Port: int = None):
        """Démarre l'interface web dans un thread asyncio dédié."""
        if Port is None:
            Port = NetworkConfig.CLIENT_WEB_PORT

        if self._Running:
            return

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
                self.Logger.error(f"Erreur web UI client: {e}")
            finally:
                self._Running = False
                self._Loop.close()

        self._Thread = threading.Thread(target=_RunThread, daemon=True, name="ClientWebUI")
        self._Thread.start()
        self.Logger.info(f"Web UI client démarrée sur http://{Host}:{Port}")

    def Stop(self):
        """Arrête l'interface web."""
        if self._UvicornServer and self._Running:
            self._UvicornServer.should_exit = True
        self._Running = False

    # ========================================================================
    # SETUP FASTAPI
    # ========================================================================

    def _SetupMiddleware(self):
        self._App.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _SetupRoutes(self):
        App = self._App

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
            return HTMLResponse(content="<h1>Web UI client non disponible</h1>")

        # ----------------------------------------------------------------
        # AUTH (pas de mot de passe par défaut)
        # ----------------------------------------------------------------

        @App.post("/api/auth")
        async def Auth(Body: AuthRequest):
            return {"token": self._Token, "no_password": True}

        @App.get("/api/auth/check")
        async def AuthCheck():
            return {"valid": True, "no_password": True}

        # ----------------------------------------------------------------
        # STATUT
        # ----------------------------------------------------------------

        @App.get("/api/status")
        async def GetStatus():
            with self._ClientLock:
                Client = self.Client
            if Client:
                Status = Client.GetStatus()
            else:
                Status = {"connected": False, "running": False, "status": "disconnected"}
            return Status

        # ----------------------------------------------------------------
        # MONITORING
        # ----------------------------------------------------------------

        @App.get("/api/monitoring")
        async def GetMonitoring():
            with self._ClientLock:
                Client = self.Client
            if not Client:
                return {
                    "connected": False, "status": "disconnected",
                    "batches_processed": 0, "batches_failed": 0,
                    "images_processed": 0, "queue_size": 0,
                    "current_batch": None, "batch_progress": 0, "batch_total": 0
                }
            return Client.GetStatus()

        # ----------------------------------------------------------------
        # LOGS
        # ----------------------------------------------------------------

        @App.get("/api/logs")
        async def GetLogs(count: int = 50):
            with self._ClientLock:
                Client = self.Client
            if Client:
                return {"logs": Client.GetRecentLogs(Count=count)}
            return {"logs": []}

        # ----------------------------------------------------------------
        # SERVEURS SAUVEGARDÉS
        # ----------------------------------------------------------------

        @App.get("/api/servers")
        async def GetServers():
            if not self.ServerManager:
                return {"servers": {}}
            return {"servers": self.ServerManager.GetAllServers()}

        @App.post("/api/servers")
        async def AddServer(Body: ServerAddRequest):
            if not self.ServerManager:
                raise HTTPException(status_code=503, detail="ServerManager non disponible")
            self.ServerManager.AddServer(Body.name, Body.host, Body.port, Body.password)
            return {"success": True}

        @App.delete("/api/servers/{name}")
        async def DeleteServer(name: str):
            if not self.ServerManager:
                raise HTTPException(status_code=503, detail="ServerManager non disponible")
            self.ServerManager.RemoveServer(name)
            return {"success": True}

        # ----------------------------------------------------------------
        # CONNEXION
        # ----------------------------------------------------------------

        @App.post("/api/connect")
        async def Connect(Body: ConnectRequest):
            with self._ClientLock:
                Client = self.Client
            if Client and Client.GetStatus().get("connected"):
                raise HTTPException(status_code=400, detail="Déjà connecté")

            # Créer un nouveau client et démarrer la connexion
            from client.core.client import UpscalingClient
            NewClient = UpscalingClient()
            self.SetClient(NewClient)

            # Lancer la connexion dans un thread asyncio dédié
            def _RunConnect():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        NewClient.Start(
                            Body.host, Body.port, Body.password, Body.data_port
                        )
                    )
                except Exception as e:
                    self.Logger.error(f"Erreur connexion web: {e}")
                finally:
                    self.ClearClient()
                    loop.close()

            t = threading.Thread(target=_RunConnect, daemon=True, name="ClientFromWeb")
            t.start()
            return {"success": True, "message": "Connexion en cours..."}

        @App.post("/api/disconnect")
        async def Disconnect():
            with self._ClientLock:
                Client = self.Client
            if not Client:
                return {"success": True}
            Client.RequestStop()
            self.ClearClient()
            return {"success": True}

        # ----------------------------------------------------------------
        # CONFIGURATION PERFORMANCES
        # ----------------------------------------------------------------

        @App.get("/api/config")
        async def GetConfig():
            if not self.PerfManager:
                return {}
            return self.PerfManager.GetAll()

        @App.put("/api/config")
        async def UpdateConfig(Body: ConfigUpdateRequest):
            if not self.PerfManager:
                raise HTTPException(status_code=503, detail="PerfManager non disponible")
            for Key, Value in Body.params.items():
                self.PerfManager.Set(Key, Value)
            self.PerfManager.Save()
            return {"success": True}

        # ----------------------------------------------------------------
        # WEBHOOKS
        # ----------------------------------------------------------------

        @App.get("/api/webhooks")
        async def GetWebhooks():
            if not self.PerfManager:
                return {"enabled": False, "url": "", "events": ""}
            return {
                "enabled": self.PerfManager.Get("webhook_enabled", False),
                "url": self.PerfManager.Get("webhook_url", ""),
                "events": self.PerfManager.Get("webhook_events", "")
            }

        @App.put("/api/webhooks")
        async def UpdateWebhooks(Body: WebhookUpdateRequest):
            if not self.PerfManager:
                raise HTTPException(status_code=503, detail="PerfManager non disponible")
            self.PerfManager.Set("webhook_enabled", Body.enabled)
            self.PerfManager.Set("webhook_url", Body.url)
            self.PerfManager.Set("webhook_events", Body.events)
            self.PerfManager.Save()
            return {"success": True}

        @App.post("/api/webhooks/test")
        async def TestWebhook():
            try:
                from shared.utils.webhook_manager import TriggerClientWebhook
                TriggerClientWebhook("test", {"message": "Test depuis Web UI"})
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ----------------------------------------------------------------
        # WEBSOCKET
        # ----------------------------------------------------------------

        @App.websocket("/ws")
        async def WebSocketEndpoint(Ws: WebSocket, token: str = ""):
            await Ws.accept()
            try:
                while True:
                    State = self._BuildFullState()
                    await Ws.send_json(State)
                    await asyncio.sleep(1.0)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                self.Logger.debug(f"Erreur WebSocket client: {e}")

    # ========================================================================
    # ÉTAT COMPLET
    # ========================================================================

    def _BuildFullState(self) -> dict:
        with self._ClientLock:
            Client = self.Client

        if Client:
            Status = Client.GetStatus()
            try:
                Logs = Client.GetRecentLogs(Count=20)
            except Exception:
                Logs = []
        else:
            Status = {"connected": False, "running": False, "status": "disconnected",
                      "batches_processed": 0, "batches_failed": 0, "images_processed": 0,
                      "queue_size": 0, "current_batch": None, "batch_progress": 0, "batch_total": 0}
            Logs = []

        return {
            "status": Status,
            "logs": Logs,
            "servers": self.ServerManager.GetAllServers() if self.ServerManager else {}
        }
