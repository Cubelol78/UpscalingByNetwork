# UpscalingByNetwork/client/windows/core/batch_processor.py

import asyncio


async def process_received_batch(self, encrypted_data: bytes, batch_id: str):
    """Traite un lot reçu du serveur"""
    
    # 1. Déchiffrement
    session_key = self.security_client.get_session_key()
    batch_zip = self.security_client.decrypt_batch(encrypted_data, session_key)
    
    # 2. Décompression
    batch_dir = f"temp/received_batches/{batch_id}"
    self.extract_batch_zip(batch_zip, f"{batch_dir}/input")
    
    # 3. Upscaling avec Real-ESRGAN
    input_dir = f"{batch_dir}/input"
    output_dir = f"{batch_dir}/output"
    
    await self.run_realesrgan(input_dir, output_dir)
    
    # 4. Vérification de la complétude
    input_count = len(list(Path(input_dir).glob("*.png")))
    output_count = len(list(Path(output_dir).glob("*.png")))
    
    if input_count != output_count:
        raise Exception(f"Traitement incomplet: {output_count}/{input_count}")
    
    # 5. Compression des résultats
    result_zip = f"temp/processed_batches/result_{batch_id}.zip"
    self.create_result_zip(output_dir, result_zip)
    
    # 6. Chiffrement des résultats
    encrypted_result = self.security_client.encrypt_batch(result_zip, session_key)
    
    # 7. Renvoi au serveur
    await self.send_encrypted_result(batch_id, encrypted_result)

async def run_realesrgan(self, input_dir: str, output_dir: str):
    """Exécute Real-ESRGAN sur un dossier d'images"""
    
    realesrgan_path = "realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe"
    
    cmd = [
        realesrgan_path,
        "-i", input_dir,
        "-o", output_dir,
        "-n", "realesr-animevideov3",
        "-s", "4",
        "-t", "256",
        "-g", "0"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise Exception(f"Erreur Real-ESRGAN: {stderr.decode()}")