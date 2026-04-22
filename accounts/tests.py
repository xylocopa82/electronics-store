from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class AuthViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='StrongPass123')

    def test_login_page_renders_without_next_parameter(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next" value=""', html=False)

    def test_login_ignores_external_next_url(self):
        response = self.client.post(
            f"{reverse('login')}?next=https://evil.example/phish",
            {
                'username': 'alice',
                'password': 'StrongPass123',
                'next': 'https://evil.example/phish',
            },
        )

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)

    def test_logout_page_renders_and_post_logs_out(self):
        self.client.force_login(self.user)

        get_response = self.client.get(reverse('logout'))
        self.assertEqual(get_response.status_code, 200)
        self.assertTemplateUsed(get_response, 'logout.html')
        self.assertContains(get_response, 'Log out of ElectroStore?')
        self.assertIn('_auth_user_id', self.client.session)

        post_response = self.client.post(reverse('logout'))
        self.assertRedirects(post_response, reverse('home'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
