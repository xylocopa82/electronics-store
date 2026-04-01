import shutil
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings

from accounts.models import Address

from .models import Order
from products.models import Product

TEST_MEDIA_ROOT = Path(__file__).resolve().parent / '_test_media'


def create_test_image():
    return SimpleUploadedFile('product.jpg', b'filecontent', content_type='image/jpeg')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class OrderModelTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_product_with_orders_cannot_be_deleted(self):
        user = User.objects.create_user(username='buyer', password='StrongPass123')
        product = Product.objects.create(
            name='Laptop',
            brand='Acme',
            category='laptop',
            description='A test laptop',
            price='999.99',
            stock=3,
            image=create_test_image(),
        )
        address = Address.objects.create(
            user=user,
            name='Buyer',
            phone='9999999999',
            address_line='123 Main Street',
            city='Delhi',
            state='Delhi',
            pincode='110001',
        )
        Order.objects.create(
            user=user,
            product=product,
            address=address,
            quantity=1,
            total_price='999.99',
        )

        with self.assertRaises(ProtectedError):
            product.delete()
