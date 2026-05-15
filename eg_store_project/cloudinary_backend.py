import cloudinary
import cloudinary.uploader
import cloudinary.api
from django.core.files.storage import Storage
from django.conf import settings
import os

class CloudinaryStorage(Storage):
    def _save(self, name, content):
        cloudinary.config(
            cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
            api_key=os.environ.get('CLOUDINARY_API_KEY'),
            api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        )
        result = cloudinary.uploader.upload(content, public_id=os.path.splitext(name)[0])
        return result['public_id']

    def url(self, name):
        cloudinary.config(
            cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
            api_key=os.environ.get('CLOUDINARY_API_KEY'),
            api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        )
        return cloudinary.CloudinaryImage(name).build_url()

    def exists(self, name):
        return False

    def delete(self, name):
        cloudinary.uploader.destroy(name)