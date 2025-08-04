# UpscalingByNetwork/server/core/video_assembler.py

import asyncio
import shutil


async def receive_batch_result(self, client_mac: str, batch_id: str, encrypted_data: bytes):
    """Reçoit et traite le résultat d'un lot"""
    
    # 1. Déchiffrement
    session_key = self.security_manager.get_session_key(client_mac)
    result_zip = self.security_manager.decrypt_batch(encrypted_data, session_key)
    
    # 2. Extraction et vérification
    batch_dir = f"jobs/{job_id}/batches/{batch_id}/output"
    self.extract_result_zip(result_zip, batch_dir)
    
    # 3. Vérification de la complétude
    expected_count = self.get_batch_frame_count(batch_id)
    received_count = len(list(Path(batch_dir).glob("*.png")))
    
    if received_count != expected_count:
        # Lot incomplet, remettre en attente
        self.reset_batch_status(batch_id)
        return False
    
    # 4. Copie vers le dossier final
    final_dir = f"jobs/{job_id}/upscaled"
    for frame in Path(batch_dir).glob("*.png"):
        shutil.copy(frame, final_dir)
    
    # 5. Mise à jour du statut
    self.mark_batch_completed(batch_id)
    
    # 6. Vérification si job terminé
    if self.all_batches_completed(job_id):
        await self.assemble_final_video(job_id)
    
    return True

async def assemble_final_video(self, job_id: str):
    """Assemble la vidéo finale"""
    
    upscaled_dir = f"jobs/{job_id}/upscaled"
    audio_path = f"jobs/{job_id}/audio/audio.aac"
    output_path = f"jobs/{job_id}/output/video_upscaled.mp4"
    
    # FFmpeg : assemblage final
    ffmpeg_cmd = [
        "ffmpeg/ffmpeg.exe",
        "-framerate", "30",
        "-i", f"{upscaled_dir}/frame_%06d.png",
        "-i", audio_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-crf", "20",
        "-preset", "medium",
        output_path
    ]
    
    await asyncio.create_subprocess_exec(*ffmpeg_cmd)