import shutil
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import Product

from .models import Wishlist

TEST_MEDIA_ROOT = Path(__file__).resolve().parent / '_test_media'


def create_test_image():
    return SimpleUploadedFile('product.jpg', b'filecontent', content_type='image/jpeg')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class WishlistViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(username='buyer', password='StrongPass123')
        self.product = Product.objects.create(
            name='Headphones',
            brand='Acme',
            category='accessory',
            description='A test accessory',
            price='49.99',
            stock=5,
            image=create_test_image(),
        )

    def test_add_to_wishlist_requires_post(self):
        self.client.force_login(self.user)

        get_response = self.client.get(reverse('add_to_wishlist', args=[self.product.id]))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse('add_to_wishlist', args=[self.product.id]))
        self.assertRedirects(post_response, reverse('wishlist'), fetch_redirect_response=False)
        self.assertEqual(Wishlist.objects.count(), 1)

    def test_remove_from_wishlist_requires_post(self):
        self.client.force_login(self.user)
        Wishlist.objects.create(user=self.user, product=self.product)

        get_response = self.client.get(reverse('remove_wishlist', args=[self.product.id]))
        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(Wishlist.objects.count(), 1)

        post_response = self.client.post(reverse('remove_wishlist', args=[self.product.id]))
        self.assertRedirects(post_response, reverse('wishlist'), fetch_redirect_response=False)
        self.assertEqual(Wishlist.objects.count(), 0)
