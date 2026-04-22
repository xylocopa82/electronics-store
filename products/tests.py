import shutil
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from orders.models import Order

from .models import Product, Review

TEST_MEDIA_ROOT = Path(__file__).resolve().parent / '_test_media'


def create_test_image():
    return SimpleUploadedFile('product.jpg', b'filecontent', content_type='image/jpeg')


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    RAZORPAY_KEY_ID='rzp_test_key',
    RAZORPAY_KEY_SECRET='test_secret',
)
class ProductFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(username='buyer', password='StrongPass123')
        self.other_user = User.objects.create_user(username='other', password='StrongPass123')
        self.product = Product.objects.create(
            name='Phone',
            brand='Acme',
            category='mobile',
            description='A test phone',
            price='100.00',
            stock=2,
            image=create_test_image(),
        )
        self.address = Address.objects.create(
            user=self.user,
            name='Buyer',
            phone='9999999999',
            address_line='123 Main Street',
            city='Delhi',
            state='Delhi',
            pincode='110001',
            is_default=True,
        )
        self.other_address = Address.objects.create(
            user=self.other_user,
            name='Other User',
            phone='8888888888',
            address_line='404 Side Street',
            city='Mumbai',
            state='Maharashtra',
            pincode='400001',
            is_default=True,
        )

    def set_cart(self, quantity):
        session = self.client.session
        session['cart'] = {str(self.product.id): quantity}
        session.save()

    def test_add_to_cart_requires_post(self):
        get_response = self.client.get(reverse('add_to_cart', args=[self.product.id]))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse('add_to_cart', args=[self.product.id]))
        self.assertRedirects(post_response, reverse('cart'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['cart'], {str(self.product.id): 1})

    def test_product_detail_invalid_id_returns_404(self):
        response = self.client.get(reverse('product_detail', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_checkout_rejects_other_users_address(self):
        self.client.force_login(self.user)
        self.set_cart(quantity=1)

        response = self.client.post(reverse('checkout'), {'address': self.other_address.id})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(self.client.session['cart'], {str(self.product.id): 1})

    def test_checkout_preserves_cart_when_stock_is_insufficient(self):
        self.client.force_login(self.user)
        self.product.stock = 1
        self.product.save(update_fields=['stock'])
        self.set_cart(quantity=2)

        response = self.client.post(reverse('checkout'), {'address': self.address.id}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'checkout_select.html')
        self.assertContains(response, 'Only 1 item(s) of Phone are available.')
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(self.client.session['cart'], {str(self.product.id): 2})

    @patch('products.views.razorpay.Client')
    def test_checkout_starts_razorpay_order_for_valid_cart(self, mock_client_cls):
        self.client.force_login(self.user)
        self.set_cart(quantity=1)

        mock_client = mock_client_cls.return_value
        mock_client.order.create.return_value = {'id': 'order_test_123', 'amount': 10000}

        response = self.client.post(reverse('checkout'), {'address': self.address.id})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payment.html')
        self.assertContains(response, 'order_test_123')
        self.assertEqual(self.client.session['payment_order_id'], 'order_test_123')
        self.assertEqual(self.client.session['payment_amount'], 10000)
        self.assertEqual(self.client.session['address_id'], self.address.id)

        mock_client.order.create.assert_called_once()
        created_order_payload = mock_client.order.create.call_args.args[0]
        self.assertEqual(created_order_payload['amount'], 10000)
        self.assertEqual(created_order_payload['currency'], 'INR')
        self.assertIn('receipt', created_order_payload)

    @patch('products.views.razorpay.Client')
    def test_payment_success_creates_order_and_clears_checkout_session(self, mock_client_cls):
        self.client.force_login(self.user)
        self.set_cart(quantity=1)

        session = self.client.session
        session['payment_order_id'] = 'order_test_123'
        session['payment_amount'] = 10000
        session['address_id'] = self.address.id
        session.save()

        response = self.client.get(
            reverse('payment_success'),
            {
                'payment_id': 'pay_test_123',
                'order_id': 'order_test_123',
                'signature': 'test_signature',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'checkout.html')
        self.assertEqual(Order.objects.count(), 1)

        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.product, self.product)
        self.assertEqual(order.quantity, 1)
        self.assertEqual(order.address, self.address)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

        session = self.client.session
        self.assertEqual(session['cart'], {})
        self.assertNotIn('payment_order_id', session)
        self.assertNotIn('payment_amount', session)
        self.assertNotIn('address_id', session)

        mock_client = mock_client_cls.return_value
        mock_client.utility.verify_payment_signature.assert_called_once_with(
            {
                'razorpay_payment_id': 'pay_test_123',
                'razorpay_order_id': 'order_test_123',
                'razorpay_signature': 'test_signature',
            }
        )

    @patch('products.views.razorpay.Client')
    def test_payment_success_rejects_mismatched_order_id(self, mock_client_cls):
        self.client.force_login(self.user)
        self.set_cart(quantity=1)

        session = self.client.session
        session['payment_order_id'] = 'order_expected'
        session['address_id'] = self.address.id
        session.save()

        response = self.client.get(
            reverse('payment_success'),
            {
                'payment_id': 'pay_test_123',
                'order_id': 'order_other',
                'signature': 'test_signature',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'payment_failed.html')
        self.assertEqual(Order.objects.count(), 0)
        mock_client_cls.return_value.utility.verify_payment_signature.assert_not_called()

    def test_add_review_requires_post(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('add_review', args=[self.product.id]))

        self.assertEqual(response.status_code, 405)

    def test_add_review_rejects_invalid_rating(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('add_review', args=[self.product.id]), {'rating': '7'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rating must be between 1 and 5.')
        self.assertEqual(Review.objects.count(), 0)

    def test_add_review_updates_existing_review_without_duplicates(self):
        self.client.force_login(self.user)

        first_response = self.client.post(reverse('add_review', args=[self.product.id]), {'rating': '4'})
        self.assertRedirects(first_response, reverse('product_detail', args=[self.product.id]), fetch_redirect_response=False)

        second_response = self.client.post(
            reverse('add_review', args=[self.product.id]),
            {'rating': '5', 'comment': 'Excellent'},
        )
        self.assertRedirects(second_response, reverse('product_detail', args=[self.product.id]), fetch_redirect_response=False)

        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.get(product=self.product, user=self.user)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Excellent')
