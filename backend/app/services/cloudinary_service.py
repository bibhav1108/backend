import cloudinary
import cloudinary.uploader
from backend.app.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Cloudinary
if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True
    )
    logger.info("Cloudinary configured successfully.")
else:
    logger.warning("Cloudinary credentials missing. Uploads will fail.")

def upload_image(file_obj, folder="profiles", public_id=None):
    """
    Uploads an image to Cloudinary.
    :param file_obj: The file-like object to upload.
    :param folder: The directory in Cloudinary.
    :param public_id: Optional specific public ID.
    :return: secure_url
    """
    try:
        options = {
            "folder": f"sahyog_setu/{folder}",
            "resource_type": "image"
        }
        if public_id:
            options["public_id"] = public_id

        result = cloudinary.uploader.upload(file_obj, **options)
        return result.get("secure_url")
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
        return None

def delete_image(image_url):
    """
    Deletes an image from Cloudinary given its URL.
    """
    if not image_url or "cloudinary" not in image_url:
        return False

    try:
        # Extract public_id from URL
        # URL format: https://res.cloudinary.com/cloud_name/image/upload/v12345/sahyog_setu/profiles/filename.jpg
        parts = image_url.split("/")
        # The public_id starts after 'upload/' and skipping the version 'vXXX' if present
        # It includes the folder structure
        
        # Find index of 'upload'
        if "upload" in parts:
            idx = parts.index("upload")
            # public_id is everything after version (which starts with 'v' and is numeric-ish)
            start_idx = idx + 2 if parts[idx+1].startswith('v') else idx + 1
            public_id_with_ext = "/".join(parts[start_idx:])
            public_id = public_id_with_ext.split(".")[0]
            
            cloudinary.uploader.destroy(public_id)
            return True
    except Exception as e:
        logger.error(f"Cloudinary deletion failed: {e}")
        return False
    
    return False
