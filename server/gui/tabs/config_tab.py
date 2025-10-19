"""
Onglet de configuration
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                            QGroupBox, QGridLayout, QLabel, QLineEdit, QSpinBox,
                            QComboBox, QCheckBox, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt
from pathlib import Path
import socket

from utils.config import config

class ConfigTab(QScrollArea):
    """Onglet de configuration"""

    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window

        # Track validation state
        self.validation_errors = {}
        self.save_button = None

        self.setWidgetResizable(True)
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Configuration réseau
        self.create_network_group(layout)

        # Configuration réseau avancée
        self.create_network_advanced_group(layout)

        # Configuration stockage
        self.create_storage_group(layout)

        # Configuration lots
        self.create_batches_group(layout)

        # Configuration Real-ESRGAN
        self.create_esrgan_group(layout)

        # Configuration FFmpeg
        self.create_ffmpeg_group(layout)

        # Configuration sécurité
        self.create_security_group(layout)
        
        # Boutons
        self.create_buttons(layout)
        
        layout.addStretch()
        self.setWidget(content_widget)

        # Initialiser les disques
        self.refresh_drives()

        # Run initial validation
        self.validate_all()
    
    def create_network_group(self, parent_layout):
        """Crée le groupe de configuration réseau"""
        network_group = QGroupBox("Configuration Réseau")
        network_group.setMinimumWidth(400)
        network_layout = QGridLayout(network_group)
        network_layout.setSpacing(10)
        network_layout.setContentsMargins(15, 20, 15, 15)
        
        network_layout.addWidget(QLabel("Adresse IP:"), 0, 0)
        self.host_input = QLineEdit(config.HOST)
        self.host_input.setMaximumWidth(200)
        network_layout.addWidget(self.host_input, 0, 1)
        
        network_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(config.PORT)
        self.port_input.setMaximumWidth(100)
        self.port_input.setToolTip("Port réseau pour les connexions client (1024-65535)")
        network_layout.addWidget(self.port_input, 1, 1)

        # Validation error label for port
        self.port_error_label = QLabel("")
        self.port_error_label.setStyleSheet("font-size: 10px; color: #f44336; font-weight: bold;")
        self.port_error_label.setWordWrap(True)
        self.port_error_label.setVisible(False)
        network_layout.addWidget(self.port_error_label, 1, 2, 1, 2)

        # Connect validation signal
        self.port_input.valueChanged.connect(self.validate_port)
        
        network_layout.addWidget(QLabel("Clients maximum:"), 2, 0)
        self.max_clients_spin = QSpinBox()
        self.max_clients_spin.setRange(1, 1000)
        self.max_clients_spin.setValue(config.MAX_CLIENTS)
        self.max_clients_spin.setMaximumWidth(100)
        network_layout.addWidget(self.max_clients_spin, 2, 1)

        parent_layout.addWidget(network_group)

    def create_network_advanced_group(self, parent_layout):
        """Crée le groupe de configuration réseau avancée"""
        network_adv_group = QGroupBox("Configuration Réseau Avancée")
        network_adv_group.setMinimumWidth(400)
        network_adv_group.setCheckable(True)
        network_adv_group.setChecked(False)  # Replié par défaut
        network_adv_layout = QGridLayout(network_adv_group)
        network_adv_layout.setSpacing(10)
        network_adv_layout.setContentsMargins(15, 20, 15, 15)

        network_adv_layout.addWidget(QLabel("Intervalle heartbeat (s):"), 0, 0)
        self.heartbeat_interval_spin = QSpinBox()
        self.heartbeat_interval_spin.setRange(5, 120)
        self.heartbeat_interval_spin.setValue(config.HEARTBEAT_INTERVAL)
        self.heartbeat_interval_spin.setMaximumWidth(100)
        self.heartbeat_interval_spin.setToolTip("Intervalle entre les heartbeats pour vérifier la connexion client")
        network_adv_layout.addWidget(self.heartbeat_interval_spin, 0, 1)

        network_adv_layout.addWidget(QLabel("Timeout client (s):"), 1, 0)
        self.client_timeout_spin = QSpinBox()
        self.client_timeout_spin.setRange(30, 600)
        self.client_timeout_spin.setValue(config.CLIENT_TIMEOUT)
        self.client_timeout_spin.setMaximumWidth(100)
        self.client_timeout_spin.setToolTip("Durée avant de considérer un client comme déconnecté")
        network_adv_layout.addWidget(self.client_timeout_spin, 1, 1)

        # Validation error label for timeout
        self.timeout_error_label = QLabel("")
        self.timeout_error_label.setStyleSheet("font-size: 10px; color: #f44336; font-weight: bold;")
        self.timeout_error_label.setWordWrap(True)
        self.timeout_error_label.setVisible(False)
        network_adv_layout.addWidget(self.timeout_error_label, 2, 0, 1, 2)

        # Note de validation
        validation_note = QLabel("Note: Le timeout client doit être supérieur à l'intervalle heartbeat")
        validation_note.setStyleSheet("font-size: 10px; color: #FF9800; font-style: italic;")
        validation_note.setWordWrap(True)
        network_adv_layout.addWidget(validation_note, 3, 0, 1, 2)

        # Connect validation signals
        self.heartbeat_interval_spin.valueChanged.connect(self.validate_timeouts)
        self.client_timeout_spin.valueChanged.connect(self.validate_timeouts)

        parent_layout.addWidget(network_adv_group)
    
    def create_storage_group(self, parent_layout):
        """Crée le groupe de configuration stockage"""
        storage_group = QGroupBox("Configuration Stockage")
        storage_group.setMinimumWidth(400)
        storage_layout = QGridLayout(storage_group)
        storage_layout.setSpacing(10)
        storage_layout.setContentsMargins(15, 20, 15, 15)
        
        # Sélection du disque de travail
        storage_layout.addWidget(QLabel("Disque de travail:"), 0, 0)
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(200)
        self.drive_combo.currentTextChanged.connect(self.on_drive_changed)
        storage_layout.addWidget(self.drive_combo, 0, 1, 1, 2)
        
        # Bouton pour actualiser les disques
        refresh_drives_btn = QPushButton("Actualiser")
        refresh_drives_btn.setMaximumWidth(100)
        refresh_drives_btn.clicked.connect(self.refresh_drives)
        storage_layout.addWidget(refresh_drives_btn, 0, 3)
        
        # Informations sur l'espace disque
        self.drive_info_label = QLabel("Chargement des informations disque...")
        self.drive_info_label.setStyleSheet("font-size: 10px; color: #888888; padding: 5px;")
        self.drive_info_label.setWordWrap(True)
        storage_layout.addWidget(self.drive_info_label, 1, 0, 1, 4)
        
        # Nettoyage automatique
        self.auto_cleanup_check = QCheckBox("Nettoyage automatique des fichiers temporaires")
        self.auto_cleanup_check.setChecked(config.AUTO_CLEANUP)
        storage_layout.addWidget(self.auto_cleanup_check, 2, 0, 1, 4)

        # Age de nettoyage automatique
        storage_layout.addWidget(QLabel("Age nettoyage auto (heures):"), 3, 0)
        self.auto_cleanup_age_spin = QSpinBox()
        self.auto_cleanup_age_spin.setRange(1, 720)
        self.auto_cleanup_age_spin.setValue(config.AUTO_CLEANUP_AGE_HOURS)
        self.auto_cleanup_age_spin.setMaximumWidth(100)
        self.auto_cleanup_age_spin.setToolTip("Age des fichiers avant suppression automatique (1-720 heures)")
        storage_layout.addWidget(self.auto_cleanup_age_spin, 3, 1)

        # Espace libre minimum
        storage_layout.addWidget(QLabel("Espace libre minimum (GB):"), 4, 0)
        self.min_free_space_spin = QSpinBox()
        self.min_free_space_spin.setRange(10, 1000)
        self.min_free_space_spin.setValue(config.MIN_FREE_SPACE_GB)
        self.min_free_space_spin.setMaximumWidth(100)
        self.min_free_space_spin.setToolTip("Espace disque minimum requis avant d'accepter de nouveaux jobs")
        storage_layout.addWidget(self.min_free_space_spin, 4, 1)

        # Validation error label for free space
        self.free_space_error_label = QLabel("")
        self.free_space_error_label.setStyleSheet("font-size: 10px; color: #f44336; font-weight: bold;")
        self.free_space_error_label.setWordWrap(True)
        self.free_space_error_label.setVisible(False)
        storage_layout.addWidget(self.free_space_error_label, 4, 2, 1, 2)

        # Connect validation signal
        self.min_free_space_spin.valueChanged.connect(self.validate_free_space)
        
        # Bouton de nettoyage manuel
        cleanup_btn = QPushButton("Nettoyer fichiers temporaires")
        cleanup_btn.clicked.connect(self.manual_cleanup)
        cleanup_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        cleanup_btn.setMaximumWidth(250)
        storage_layout.addWidget(cleanup_btn, 5, 0, 1, 2)
        
        parent_layout.addWidget(storage_group)
    
    def create_batches_group(self, parent_layout):
        """Crée le groupe de configuration lots"""
        batches_group = QGroupBox("Configuration Lots")
        batches_group.setMinimumWidth(400)
        batches_layout = QGridLayout(batches_group)
        batches_layout.setSpacing(10)
        batches_layout.setContentsMargins(15, 20, 15, 15)
        
        batches_layout.addWidget(QLabel("Taille des lots (images):"), 0, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 200)
        self.batch_size_spin.setValue(config.BATCH_SIZE)
        self.batch_size_spin.setMaximumWidth(100)
        self.batch_size_spin.setToolTip("Nombre d'images par lot (recommandé: 30-100)")
        batches_layout.addWidget(self.batch_size_spin, 0, 1)

        # Validation warning label for batch size
        self.batch_size_warning_label = QLabel("")
        self.batch_size_warning_label.setStyleSheet("font-size: 10px; color: #FF9800; font-weight: bold;")
        self.batch_size_warning_label.setWordWrap(True)
        self.batch_size_warning_label.setVisible(False)
        batches_layout.addWidget(self.batch_size_warning_label, 0, 2, 1, 2)

        # Connect validation signal
        self.batch_size_spin.valueChanged.connect(self.validate_batch_size)
        
        batches_layout.addWidget(QLabel("Tentatives maximum:"), 1, 0)
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 10)
        self.max_retries_spin.setValue(config.MAX_RETRIES)
        self.max_retries_spin.setMaximumWidth(100)
        batches_layout.addWidget(self.max_retries_spin, 1, 1)

        batches_layout.addWidget(QLabel("Seuil de doublons:"), 2, 0)
        self.duplicate_threshold_spin = QSpinBox()
        self.duplicate_threshold_spin.setRange(1, 20)
        self.duplicate_threshold_spin.setValue(config.DUPLICATE_THRESHOLD)
        self.duplicate_threshold_spin.setMaximumWidth(100)
        self.duplicate_threshold_spin.setToolTip("Nombre de doublons à envoyer pour assurer la fiabilité")
        batches_layout.addWidget(self.duplicate_threshold_spin, 2, 1)

        parent_layout.addWidget(batches_group)
    
    def create_esrgan_group(self, parent_layout):
        """Crée le groupe de configuration Real-ESRGAN"""
        esrgan_group = QGroupBox("Configuration Real-ESRGAN")
        esrgan_group.setMinimumWidth(400)
        esrgan_layout = QGridLayout(esrgan_group)
        esrgan_layout.setSpacing(10)
        esrgan_layout.setContentsMargins(15, 20, 15, 15)
        
        esrgan_layout.addWidget(QLabel("Modèle d'upscaling:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3",
            "RealESRGAN_x4plus_anime_6B",
            "RealESRGAN_x4plus"
        ])
        self.model_combo.setCurrentText(config.REALESRGAN_MODEL)
        self.model_combo.setMinimumWidth(200)
        esrgan_layout.addWidget(self.model_combo, 0, 1)
        
        esrgan_layout.addWidget(QLabel("Taille des tuiles (pixels):"), 1, 0)
        self.tile_size_spin = QSpinBox()
        self.tile_size_spin.setRange(128, 1024)
        self.tile_size_spin.setSingleStep(128)
        self.tile_size_spin.setValue(config.TILE_SIZE)
        self.tile_size_spin.setMaximumWidth(100)
        self.tile_size_spin.setToolTip("Taille des tuiles pour le traitement (puissance de 2 recommandée: 128, 256, 512)")
        esrgan_layout.addWidget(self.tile_size_spin, 1, 1)

        # Validation warning label for tile size
        self.tile_size_warning_label = QLabel("")
        self.tile_size_warning_label.setStyleSheet("font-size: 10px; color: #FF9800; font-weight: bold;")
        self.tile_size_warning_label.setWordWrap(True)
        self.tile_size_warning_label.setVisible(False)
        esrgan_layout.addWidget(self.tile_size_warning_label, 1, 2, 1, 2)

        # Connect validation signal
        self.tile_size_spin.valueChanged.connect(self.validate_tile_size)

        esrgan_layout.addWidget(QLabel("GPU ID:"), 2, 0)
        self.gpu_id_spin = QSpinBox()
        self.gpu_id_spin.setRange(0, 8)
        self.gpu_id_spin.setValue(config.GPU_ID)
        self.gpu_id_spin.setMaximumWidth(100)
        esrgan_layout.addWidget(self.gpu_id_spin, 2, 1)

        # Description GPU
        gpu_desc = QLabel("ID du GPU à utiliser (0 = premier GPU, -1 = CPU uniquement)")
        gpu_desc.setStyleSheet("font-size: 10px; color: #888888; font-style: italic;")
        gpu_desc.setWordWrap(True)
        esrgan_layout.addWidget(gpu_desc, 3, 0, 1, 2)

        parent_layout.addWidget(esrgan_group)

        # Groupe Real-ESRGAN Avancé
        self.create_esrgan_advanced_group(parent_layout)

    def create_esrgan_advanced_group(self, parent_layout):
        """Crée le groupe de configuration Real-ESRGAN avancée"""
        esrgan_adv_group = QGroupBox("Configuration Real-ESRGAN Avancée")
        esrgan_adv_group.setMinimumWidth(400)
        esrgan_adv_group.setCheckable(True)
        esrgan_adv_group.setChecked(False)  # Replié par défaut
        esrgan_adv_layout = QGridLayout(esrgan_adv_group)
        esrgan_adv_layout.setSpacing(10)
        esrgan_adv_layout.setContentsMargins(15, 20, 15, 15)

        # USE_FP16
        self.use_fp16_check = QCheckBox("Use FP16 precision (2x faster, slightly lower quality)")
        self.use_fp16_check.setChecked(config.USE_FP16)
        self.use_fp16_check.setToolTip("Utilise la précision FP16 pour doubler la vitesse avec une perte de qualité minime")
        esrgan_adv_layout.addWidget(self.use_fp16_check, 0, 0, 1, 2)

        # TTA_MODE
        self.tta_mode_check = QCheckBox("TTA Mode (8x slower, better quality)")
        self.tta_mode_check.setChecked(config.TTA_MODE)
        self.tta_mode_check.setToolTip("Mode TTA pour meilleure qualité, mais 8x plus lent")
        esrgan_adv_layout.addWidget(self.tta_mode_check, 1, 0, 1, 2)

        # REALESRGAN_SCALE
        esrgan_adv_layout.addWidget(QLabel("Facteur d'upscaling:"), 2, 0)
        self.realesrgan_scale_combo = QComboBox()
        self.realesrgan_scale_combo.addItems(["2", "3", "4"])
        self.realesrgan_scale_combo.setCurrentText(str(config.REALESRGAN_SCALE))
        self.realesrgan_scale_combo.setMinimumWidth(100)
        self.realesrgan_scale_combo.setToolTip("Facteur d'agrandissement (2x, 3x ou 4x)")
        esrgan_adv_layout.addWidget(self.realesrgan_scale_combo, 2, 1)

        parent_layout.addWidget(esrgan_adv_group)

    def create_ffmpeg_group(self, parent_layout):
        """Crée le groupe de configuration FFmpeg"""
        ffmpeg_group = QGroupBox("Configuration Encodage Vidéo (FFmpeg)")
        ffmpeg_group.setMinimumWidth(400)
        ffmpeg_layout = QGridLayout(ffmpeg_group)
        ffmpeg_layout.setSpacing(10)
        ffmpeg_layout.setContentsMargins(15, 20, 15, 15)

        ffmpeg_layout.addWidget(QLabel("Qualité (CRF):"), 0, 0)
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(config.FFMPEG_CRF)
        self.crf_spin.setMaximumWidth(100)
        ffmpeg_layout.addWidget(self.crf_spin, 0, 1)

        # Description CRF
        crf_desc = QLabel("0 = Sans perte, 18-23 = Haute qualité, 28 = Moyenne, 51 = Pire qualité")
        crf_desc.setStyleSheet("font-size: 10px; color: #888888; font-style: italic;")
        crf_desc.setWordWrap(True)
        ffmpeg_layout.addWidget(crf_desc, 0, 2, 1, 2)

        ffmpeg_layout.addWidget(QLabel("Preset encodage:"), 1, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "ultrafast", "superfast", "veryfast", "faster",
            "fast", "medium", "slow", "slower", "veryslow"
        ])
        self.preset_combo.setCurrentText(config.FFMPEG_PRESET)
        self.preset_combo.setMinimumWidth(150)
        ffmpeg_layout.addWidget(self.preset_combo, 1, 1)

        # Description Preset
        preset_desc = QLabel("ultrafast = Rapide mais gros fichier, veryslow = Lent mais petit fichier")
        preset_desc.setStyleSheet("font-size: 10px; color: #888888; font-style: italic;")
        preset_desc.setWordWrap(True)
        ffmpeg_layout.addWidget(preset_desc, 1, 2, 1, 2)

        ffmpeg_layout.addWidget(QLabel("Threads:"), 2, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(config.FFMPEG_THREADS)
        self.threads_spin.setMaximumWidth(100)
        ffmpeg_layout.addWidget(self.threads_spin, 2, 1)

        # Description Threads
        threads_desc = QLabel("Nombre de threads CPU pour l'encodage (plus = plus rapide)")
        threads_desc.setStyleSheet("font-size: 10px; color: #888888; font-style: italic;")
        threads_desc.setWordWrap(True)
        ffmpeg_layout.addWidget(threads_desc, 2, 2, 1, 2)

        ffmpeg_layout.addWidget(QLabel("Bitrate audio:"), 3, 0)
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(["128k", "192k", "256k", "320k"])
        self.audio_bitrate_combo.setCurrentText(config.AUDIO_BITRATE)
        self.audio_bitrate_combo.setMinimumWidth(100)
        self.audio_bitrate_combo.setToolTip("Qualité audio (plus élevé = meilleure qualité)")
        ffmpeg_layout.addWidget(self.audio_bitrate_combo, 3, 1)

        ffmpeg_layout.addWidget(QLabel("Codec vidéo:"), 4, 0)
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["libx264", "libx265", "libvpx-vp9"])
        self.video_codec_combo.setCurrentText(config.VIDEO_CODEC)
        self.video_codec_combo.setMinimumWidth(150)
        self.video_codec_combo.setToolTip("x264=rapide/compatible, x265=meilleure compression, vp9=open source")
        ffmpeg_layout.addWidget(self.video_codec_combo, 4, 1)

        ffmpeg_layout.addWidget(QLabel("Format pixel:"), 5, 0)
        self.pixel_format_combo = QComboBox()
        self.pixel_format_combo.addItems(["yuv420p", "yuv422p", "yuv444p"])
        self.pixel_format_combo.setCurrentText(config.PIXEL_FORMAT)
        self.pixel_format_combo.setMinimumWidth(120)
        self.pixel_format_combo.setToolTip("420p=compatible, 422p=meilleur, 444p=meilleure qualité")
        ffmpeg_layout.addWidget(self.pixel_format_combo, 5, 1)

        parent_layout.addWidget(ffmpeg_group)

    def create_security_group(self, parent_layout):
        """Crée le groupe de configuration sécurité"""
        security_group = QGroupBox("Configuration Sécurité")
        security_group.setMinimumWidth(400)
        security_layout = QGridLayout(security_group)
        security_layout.setSpacing(10)
        security_layout.setContentsMargins(15, 20, 15, 15)
        
        self.encryption_check = QCheckBox("Activer le chiffrement des communications")
        self.encryption_check.setChecked(config.USE_ENCRYPTION)
        security_layout.addWidget(self.encryption_check, 0, 0, 1, 2)
        
        # Description du chiffrement
        encryption_desc = QLabel("Chiffre toutes les communications entre le serveur et les clients (recommandé pour WAN)")
        encryption_desc.setStyleSheet("font-size: 10px; color: #888888; font-style: italic;")
        encryption_desc.setWordWrap(True)
        security_layout.addWidget(encryption_desc, 1, 0, 1, 2)
        
        parent_layout.addWidget(security_group)
    
    def create_buttons(self, parent_layout):
        """Crée les boutons de contrôle"""
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.save_button = QPushButton("Sauvegarder Configuration")
        self.save_button.clicked.connect(self.main_window.save_configuration)
        self.save_button.setStyleSheet("background-color: #0d7377; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.save_button.setMinimumHeight(35)

        reset_config_btn = QPushButton("Réinitialiser")
        reset_config_btn.clicked.connect(self.main_window.reset_configuration)
        reset_config_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        reset_config_btn.setMinimumHeight(35)

        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(reset_config_btn)
        buttons_layout.addStretch()

        parent_layout.addLayout(buttons_layout)
    
    def refresh_drives(self):
        """Actualise la liste des disques disponibles"""
        try:
            if not hasattr(self, 'drive_combo') or not hasattr(self, 'drive_info_label'):
                return
                
            self.drive_combo.clear()
            drives = config.get_available_drives()
            
            for mountpoint, info in drives.items():
                free_gb = info['free_gb']
                total_gb = info['total_gb']
                percent_free = (free_gb / total_gb) * 100
                
                display_text = f"{mountpoint} - {free_gb:.1f}GB libre ({percent_free:.1f}% libre)"
                self.drive_combo.addItem(display_text, mountpoint)
            
            # Sélectionner le disque de travail actuel
            current_index = self.drive_combo.findData(config.WORK_DRIVE)
            if current_index >= 0:
                self.drive_combo.setCurrentIndex(current_index)
            else:
                # Si le disque n'est pas trouvé, essayer de le trouver par le début du nom
                for i in range(self.drive_combo.count()):
                    if self.drive_combo.itemData(i) == config.WORK_DRIVE:
                        self.drive_combo.setCurrentIndex(i)
                        break
            
            self.update_drive_info()
            
        except Exception as e:
            print(f"Erreur actualisation disques: {e}")
    
    def on_drive_changed(self):
        """Gestionnaire de changement de disque avec sauvegarde automatique"""
        try:
            if not hasattr(self, 'drive_combo') or not hasattr(self, 'drive_info_label'):
                return
                
            current_data = self.drive_combo.currentData()
            if current_data and current_data != config.WORK_DRIVE:
                # Utilisation de la méthode qui sauvegarde automatiquement
                config.set_work_drive(current_data)
                self.update_drive_info()
                print(f"Disque de travail changé et sauvegardé: {current_data}")
                
        except Exception as e:
            print(f"Erreur changement disque: {e}")
    
    def update_drive_info(self):
        """Met à jour les informations du disque sélectionné"""
        try:
            if not hasattr(self, 'drive_info_label'):
                return
                
            drives = config.get_available_drives()
            current_drive = config.WORK_DRIVE
            
            if current_drive in drives:
                info = drives[current_drive]
                
                info_text = (
                    f"📁 Disque: {info['device']} ({info['fstype']}) | "
                    f"💾 Total: {info['total_gb']:.1f}GB | "
                    f"📊 Utilisé: {info['used_gb']:.1f}GB ({info['percent_used']:.1f}%) | "
                    f"✅ Libre: {info['free_gb']:.1f}GB"
                )
                
                if info['free_gb'] < config.MIN_FREE_SPACE_GB:
                    color = "#f44336"
                    status = "⚠️ ESPACE INSUFFISANT"
                elif info['free_gb'] < config.MIN_FREE_SPACE_GB * 2:
                    color = "#FF9800"
                    status = "⚠️ Espace limité"
                else:
                    color = "#4CAF50"
                    status = "✅ Espace suffisant"
                
                self.drive_info_label.setText(f"{status}\n{info_text}")
                self.drive_info_label.setStyleSheet(f"""
                    font-size: 11px; 
                    color: {color}; 
                    font-weight: bold; 
                    padding: 8px; 
                    border: 1px solid {color}; 
                    border-radius: 4px;
                """)
                
        except Exception as e:
            print(f"Erreur mise à jour info disque: {e}")
    
    def manual_cleanup(self):
        """Nettoyage manuel des fichiers temporaires"""
        try:
            reply = QMessageBox.question(
                self, "Nettoyage",
                "Supprimer tous les fichiers temporaires?\n"
                "Cette action est irréversible et supprimera:\n"
                "- Toutes les frames extraites\n"
                "- Toutes les frames upscalées\n"
                "- Tous les fichiers audio temporaires",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                success = config.cleanup_temp_files()

                if success:
                    QMessageBox.information(self, "Succès", "Fichiers temporaires supprimés")
                    self.refresh_drives()
                else:
                    QMessageBox.warning(self, "Erreur", "Erreur lors du nettoyage")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur nettoyage: {str(e)}")

    # ====== VALIDATION METHODS ======

    def set_field_error(self, widget, error_label, message):
        """Set error styling and message for a field"""
        widget.setStyleSheet("border: 2px solid #f44336; background-color: #2b2b2b; color: #e0e0e0;")
        error_label.setText(f"⚠ {message}")
        error_label.setVisible(True)

    def clear_field_error(self, widget, error_label):
        """Clear error styling and message for a field"""
        widget.setStyleSheet("")
        error_label.setText("")
        error_label.setVisible(False)

    def set_field_warning(self, widget, warning_label, message):
        """Set warning styling and message for a field"""
        widget.setStyleSheet("border: 2px solid #FF9800; background-color: #2b2b2b; color: #e0e0e0;")
        warning_label.setText(f"⚡ {message}")
        warning_label.setVisible(True)

    def clear_field_warning(self, widget, warning_label):
        """Clear warning styling and message for a field"""
        widget.setStyleSheet("")
        warning_label.setText("")
        warning_label.setVisible(False)

    def update_save_button_state(self):
        """Update save button enabled state based on validation errors"""
        if self.save_button:
            has_errors = any(error for error in self.validation_errors.values())
            self.save_button.setEnabled(not has_errors)

            if has_errors:
                self.save_button.setToolTip("Corrigez les erreurs de validation avant de sauvegarder")
            else:
                self.save_button.setToolTip("Sauvegarder la configuration")

    def validate_timeouts(self):
        """Validate that CLIENT_TIMEOUT > HEARTBEAT_INTERVAL"""
        heartbeat = self.heartbeat_interval_spin.value()
        timeout = self.client_timeout_spin.value()

        if timeout <= heartbeat:
            self.set_field_error(
                self.client_timeout_spin,
                self.timeout_error_label,
                f"Le timeout client ({timeout}s) doit être supérieur à l'intervalle heartbeat ({heartbeat}s)"
            )
            self.validation_errors['timeout'] = True
        else:
            self.clear_field_error(self.client_timeout_spin, self.timeout_error_label)
            self.validation_errors['timeout'] = False

        self.update_save_button_state()

    def validate_port(self):
        """Validate that port is not already in use"""
        port = self.port_input.value()

        # Skip validation if server is running on this port
        if self.server.running and port == config.PORT:
            self.clear_field_error(self.port_input, self.port_error_label)
            self.validation_errors['port'] = False
            self.update_save_button_state()
            return

        # Check if port is in use
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(('localhost', port))
            sock.close()

            if result == 0:
                self.set_field_error(
                    self.port_input,
                    self.port_error_label,
                    f"Le port {port} est déjà utilisé par une autre application"
                )
                self.validation_errors['port'] = True
            else:
                self.clear_field_error(self.port_input, self.port_error_label)
                self.validation_errors['port'] = False

        except Exception as e:
            # If we can't check, assume it's OK
            self.clear_field_error(self.port_input, self.port_error_label)
            self.validation_errors['port'] = False

        self.update_save_button_state()

    def validate_free_space(self):
        """Validate that MIN_FREE_SPACE_GB doesn't exceed available space"""
        min_free_space = self.min_free_space_spin.value()

        try:
            drives = config.get_available_drives()
            current_drive = config.WORK_DRIVE

            if current_drive in drives:
                available_space = drives[current_drive]['free_gb']

                if min_free_space >= available_space:
                    self.set_field_error(
                        self.min_free_space_spin,
                        self.free_space_error_label,
                        f"L'espace minimum requis ({min_free_space}GB) dépasse l'espace disponible ({available_space:.1f}GB)"
                    )
                    self.validation_errors['free_space'] = True
                elif min_free_space > available_space * 0.8:
                    self.set_field_warning(
                        self.min_free_space_spin,
                        self.free_space_error_label,
                        f"Attention: L'espace minimum requis ({min_free_space}GB) est proche de l'espace disponible ({available_space:.1f}GB)"
                    )
                    self.validation_errors['free_space'] = False
                else:
                    self.clear_field_error(self.min_free_space_spin, self.free_space_error_label)
                    self.validation_errors['free_space'] = False
            else:
                self.clear_field_error(self.min_free_space_spin, self.free_space_error_label)
                self.validation_errors['free_space'] = False

        except Exception as e:
            self.clear_field_error(self.min_free_space_spin, self.free_space_error_label)
            self.validation_errors['free_space'] = False

        self.update_save_button_state()

    def validate_batch_size(self):
        """Validate batch size and provide warnings for extreme values"""
        batch_size = self.batch_size_spin.value()

        if batch_size < 20:
            self.set_field_warning(
                self.batch_size_spin,
                self.batch_size_warning_label,
                "Taille de lot très petite: peut réduire l'efficacité du traitement"
            )
        elif batch_size > 150:
            self.set_field_warning(
                self.batch_size_spin,
                self.batch_size_warning_label,
                "Taille de lot très grande: peut causer des problèmes de mémoire sur les clients"
            )
        else:
            self.clear_field_warning(self.batch_size_spin, self.batch_size_warning_label)

        # Batch size warnings don't block saving
        self.validation_errors['batch_size'] = False
        self.update_save_button_state()

    def validate_tile_size(self):
        """Validate tile size and warn if not a power of 2"""
        tile_size = self.tile_size_spin.value()

        # Check if power of 2
        is_power_of_2 = (tile_size & (tile_size - 1)) == 0 and tile_size != 0

        if not is_power_of_2:
            self.set_field_warning(
                self.tile_size_spin,
                self.tile_size_warning_label,
                f"Recommandation: Utiliser une puissance de 2 (128, 256, 512, 1024) pour de meilleures performances"
            )
        else:
            self.clear_field_warning(self.tile_size_spin, self.tile_size_warning_label)

        # Tile size warnings don't block saving
        self.validation_errors['tile_size'] = False
        self.update_save_button_state()

    def validate_all(self):
        """Run all validation checks"""
        self.validate_timeouts()
        self.validate_port()
        self.validate_free_space()
        self.validate_batch_size()
        self.validate_tile_size()

        return not any(error for error in self.validation_errors.values())

    def get_validation_errors(self):
        """Get list of current validation error messages"""
        errors = []

        if self.validation_errors.get('timeout'):
            heartbeat = self.heartbeat_interval_spin.value()
            timeout = self.client_timeout_spin.value()
            errors.append(f"Timeout client ({timeout}s) doit être > intervalle heartbeat ({heartbeat}s)")

        if self.validation_errors.get('port'):
            port = self.port_input.value()
            errors.append(f"Port {port} est déjà utilisé")

        if self.validation_errors.get('free_space'):
            min_free_space = self.min_free_space_spin.value()
            errors.append(f"Espace minimum requis ({min_free_space}GB) dépasse l'espace disponible")

        return errors