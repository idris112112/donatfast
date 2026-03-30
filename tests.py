from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import EmailAuthCode, Order
from .views import OWNER_ACCOUNTS, PRIMARY_OWNER_EMAIL


class EmailAuthFlowTests(TestCase):
    def test_home_page_contains_client_and_owner_entry(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Как клиент")
        self.assertContains(response, "Как владелец")
        self.assertContains(response, "Мои покупки")

    @override_settings(DEBUG=True)
    @patch("main.views.send_mail")
    def test_request_signup_code_sends_email(self, send_mail_mock):
        response = self.client.post("/auth/request-code/", {"email": "new@example.com", "mode": "signup"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "signup")
        self.assertIn("debug_code", response.json())
        send_mail_mock.assert_called_once()

    @override_settings(DEBUG=True)
    @patch("main.views.send_mail")
    def test_owner_login_accepts_owner_email(self, send_mail_mock):
        response = self.client.post(
            "/auth/request-code/",
            {"email": PRIMARY_OWNER_EMAIL, "mode": "login", "audience": "owner"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["audience"], "owner")
        send_mail_mock.assert_called_once()

    def test_complete_signup_creates_account(self):
        code = EmailAuthCode.create_for_email(email="new@example.com", code="123456", mode="signup")
        code.verified_at = timezone.now()
        code.save(update_fields=["verified_at"])

        response = self.client.post(
            "/auth/complete-signup/",
            {
                "email": "new@example.com",
                "username": "zarri",
                "password": "secret123",
                "password_repeat": "secret123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email="new@example.com", username="zarri").exists())

    def test_owner_can_login_with_password(self):
        User.objects.create_user(username="Foltraz", email=PRIMARY_OWNER_EMAIL, password="idrisd10", first_name="Foltraz")

        response = self.client.post(
            "/auth/owner-password-login/",
            {"identifier": "Foltraz", "password": "idrisd10"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "owner")

    def test_second_owner_can_login_with_password(self):
        second_email = "tytyty112112tytyty@gmail.com"
        second_config = OWNER_ACCOUNTS[second_email]
        User.objects.create_user(
            username=second_config["username"],
            email=second_email,
            password=second_config["password"],
            first_name=second_config["display_name"],
        )

        response = self.client.post(
            "/auth/owner-password-login/",
            {"identifier": second_config["username"], "password": second_config["password"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], second_email)

    @override_settings(DEBUG=True)
    @patch("main.views.send_mail")
    def test_request_reset_code_sends_email(self, send_mail_mock):
        User.objects.create_user(username="reset_user", email="reset@example.com", password="oldpass123")

        response = self.client.post("/auth/request-code/", {"email": "reset@example.com", "mode": "reset"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "reset")
        send_mail_mock.assert_called_once()

    def test_complete_password_reset_updates_password(self):
        user = User.objects.create_user(username="reset_user", email="reset@example.com", password="oldpass123")
        code = EmailAuthCode.create_for_email(email="reset@example.com", code="654321", mode="reset")
        code.verified_at = timezone.now()
        code.save(update_fields=["verified_at"])

        response = self.client.post(
            "/auth/complete-password-reset/",
            {"email": "reset@example.com", "password": "newpass123", "password_repeat": "newpass123"},
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("newpass123"))


class OrdersAndPaymentsTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client",
            email="client@example.com",
            password="secret123",
            first_name="Client",
        )
        self.owner_user = User.objects.create_user(
            username="Foltraz",
            email=PRIMARY_OWNER_EMAIL,
            password="idrisd10",
            first_name="Foltraz",
        )

    def test_guest_cannot_create_order(self):
        response = self.client.post(
            "/orders/create/",
            {"game": "fc_mobile", "order_type": "points", "product_code": "fc_points_80", "quantity": "80", "responsibility": "1"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "Войдите в аккаунт")

    def test_client_can_create_order_with_waiting_payment(self):
        self.client.force_login(self.client_user)

        response = self.client.post(
            "/orders/create/",
            {"game": "fc_mobile", "order_type": "points", "product_code": "fc_points_80", "quantity": "80", "responsibility": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order"]["payment_status"], "waiting")

    def test_client_must_confirm_responsibility_before_order(self):
        self.client.force_login(self.client_user)

        response = self.client.post(
            "/orders/create/",
            {"game": "fc_mobile", "order_type": "points", "product_code": "fc_points_80", "quantity": "80"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ответственность", response.json()["message"])

    def test_client_can_mark_order_paid(self):
        order = Order.objects.create(
            user=self.client_user,
            game="fc_mobile",
            order_type="points",
            product_code="fc_points_80",
            quantity=80,
        )
        self.client.force_login(self.client_user)

        response = self.client.post(
            f"/orders/{order.id}/mark-paid/",
            {"payment_email": "pay@example.com", "payment_password": "secret-pay"},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_REVIEW)
        self.assertEqual(order.payment_email, "pay@example.com")

    def test_owner_can_approve_payment(self):
        order = Order.objects.create(
            user=self.client_user,
            game="fc_mobile",
            order_type="points",
            product_code="fc_points_80",
            quantity=80,
            payment_status=Order.PAYMENT_REVIEW,
        )
        self.client.force_login(self.owner_user)

        response = self.client.post(f"/orders/{order.id}/approve-payment/")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_APPROVED)

    def test_owner_payments_list_returns_review_orders(self):
        Order.objects.create(
            user=self.client_user,
            game="fc_mobile",
            order_type="points",
            product_code="fc_points_80",
            quantity=80,
            payment_status=Order.PAYMENT_REVIEW,
        )
        self.client.force_login(self.owner_user)

        response = self.client.get("/payments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["payments"]), 1)

    def test_owner_can_delete_order(self):
        order = Order.objects.create(
            user=self.client_user,
            game="fc_mobile",
            order_type="points",
            product_code="fc_points_80",
            quantity=80,
        )
        self.client.force_login(self.owner_user)

        response = self.client.post(f"/orders/{order.id}/delete/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.filter(id=order.id).exists())
