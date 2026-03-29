import cloudinary
import cloudinary.uploader
from backend.app.config import settings
from typing import Optional
import os

class MediaService:
    def __init__(self):
        self.cloudinary_url = settings.CLOUDINARY_URL
        if self.cloudinary_url:
            # Cloudinary library can automatically use the environment variable CLOUDINARY_URL
            os.environ["CLOUDINARY_URL"] = self.cloudinary_url
            cloudinary.config()
        else:
            self.cloudinary_url = None

    async def upload_proof(self, file_path_or_buffer) -> Optional[str]:
        """
        Uploads image data to Cloudinary and returns the secure URL.
        """
        if not self.cloudinary_url:
            # Mock URL for development if no API key
            print("[MEDIA MOCK] Uploading photo...")
            return "https://res.cloudinary.com/demo/image/upload/sample.jpg"

        try:
            # upload is synchronous, but we can run it in a separate thread if needed
            # For simplicity in this prototype, we call directly
            response = cloudinary.uploader.upload(
                file_path_or_buffer,
                folder="sahyog_setu/proofs",
                resource_type="image"
            )
            return response.get("secure_url")
        except Exception as e:
            print(f"[MEDIA ERROR] Cloudinary upload failed: {e}")
            return None

media_service = MediaService()
