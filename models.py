from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


FX_TJS_TO_RUB = Decimal("8.24")


class EmailAuthCode(models.Model):
    MODE_LOGIN = "login"
    MODE_SIGNUP = "signup"
    MODE_RESET = "reset"
    MODE_CHOICES = [
        (MODE_LOGIN, "Login"),
        (MODE_SIGNUP, "Signup"),
        (MODE_RESET, "Reset"),
    ]

    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=6)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_LOGIN)
    full_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def create_for_email(cls, email, code, mode=MODE_LOGIN, full_name=""):
        return cls.objects.create(
            email=email,
            code=code,
            mode=mode,
            full_name=full_name,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    @property
    def is_active(self):
        return self.consumed_at is None and self.expires_at > timezone.now()


class Order(models.Model):
    GAME_FREE_FIRE = "free_fire"
    GAME_FC_MOBILE = "fc_mobile"
    GAME_CHOICES = [
        (GAME_FREE_FIRE, "Free Fire"),
        (GAME_FC_MOBILE, "FC Mobile"),
    ]

    TYPE_POINTS = "points"
    TYPE_COINS = "coins"
    TYPE_DIAMONDS = "diamonds"
    TYPE_VOUCHERS = "vouchers"
    TYPE_CHOICES = [
        (TYPE_POINTS, "Points"),
        (TYPE_COINS, "Coins"),
        (TYPE_DIAMONDS, "Алмазы"),
        (TYPE_VOUCHERS, "Ваучеры"),
    ]

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CHOICES = [
        (STATUS_PENDING, "В ожидании"),
        (STATUS_IN_PROGRESS, "В работе"),
        (STATUS_DONE, "Готово"),
    ]

    PAYMENT_WAITING = "waiting"
    PAYMENT_REVIEW = "review"
    PAYMENT_APPROVED = "approved"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_WAITING, "Ожидает оплату"),
        (PAYMENT_REVIEW, "На проверке"),
        (PAYMENT_APPROVED, "Оплата подтверждена"),
    ]

    PRODUCT_FC_POINTS_80 = "fc_points_80"
    PRODUCT_FC_POINTS_40 = "fc_points_40"
    PRODUCT_FC_COINS = "fc_coins"
    PRODUCT_FF_100 = "ff_100"
    PRODUCT_FF_310 = "ff_310"
    PRODUCT_FF_520 = "ff_520"
    PRODUCT_FF_1060 = "ff_1060"
    PRODUCT_FF_WEEKLY = "ff_weekly"
    PRODUCT_FF_LITE = "ff_lite"
    PRODUCT_CHOICES = [
        (PRODUCT_FC_POINTS_80, "FC Mobile: 80 Points"),
        (PRODUCT_FC_POINTS_40, "FC Mobile: 40 Points"),
        (PRODUCT_FC_COINS, "FC Mobile: Coins"),
        (PRODUCT_FF_100, "Free Fire: 100 алмазов"),
        (PRODUCT_FF_310, "Free Fire: 310 алмазов"),
        (PRODUCT_FF_520, "Free Fire: 520 алмазов"),
        (PRODUCT_FF_1060, "Free Fire: 1060 алмазов"),
        (PRODUCT_FF_WEEKLY, "Free Fire: Недельный ваучер"),
        (PRODUCT_FF_LITE, "Free Fire: Ваучер лайт"),
    ]

    FIXED_PRODUCTS = {
        PRODUCT_FC_POINTS_80: {
            "game": GAME_FC_MOBILE,
            "type": TYPE_POINTS,
            "quantity": 80,
            "price_tjs": Decimal("20"),
            "label": "80 Points",
            "promo_only_first": True,
        },
        PRODUCT_FC_POINTS_40: {
            "game": GAME_FC_MOBILE,
            "type": TYPE_POINTS,
            "quantity": 40,
            "price_tjs": Decimal("10"),
            "label": "40 Points",
        },
        PRODUCT_FF_100: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_DIAMONDS,
            "quantity": 100,
            "price_tjs": Decimal("12"),
            "label": "100 алмазов",
        },
        PRODUCT_FF_310: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_DIAMONDS,
            "quantity": 310,
            "price_tjs": Decimal("36"),
            "label": "310 алмазов",
        },
        PRODUCT_FF_520: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_DIAMONDS,
            "quantity": 520,
            "price_tjs": Decimal("56"),
            "label": "520 алмазов",
        },
        PRODUCT_FF_1060: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_DIAMONDS,
            "quantity": 1060,
            "price_tjs": Decimal("86"),
            "label": "1060 алмазов",
        },
        PRODUCT_FF_WEEKLY: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_VOUCHERS,
            "quantity": 450,
            "price_tjs": Decimal("18"),
            "label": "Недельный ваучер (450 алмазов)",
        },
        PRODUCT_FF_LITE: {
            "game": GAME_FREE_FIRE,
            "type": TYPE_VOUCHERS,
            "quantity": 90,
            "price_tjs": Decimal("6"),
            "label": "Ваучер лайт (90 алмазов)",
        },
    }

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="orders")
    game = models.CharField(max_length=20, choices=GAME_CHOICES, default=GAME_FC_MOBILE)
    order_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    product_code = models.CharField(max_length=40, choices=PRODUCT_CHOICES, blank=True)
    quantity = models.PositiveIntegerField()
    price_tjs = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    price_rub = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_WAITING)
    payment_email = models.EmailField(blank=True)
    payment_password = models.CharField(max_length=150, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def calculate_prices(cls, *, user, game, order_type, product_code="", quantity=0):
        product_code = product_code or ""

        if game == cls.GAME_FC_MOBILE:
            if order_type == cls.TYPE_POINTS:
                if product_code not in {cls.PRODUCT_FC_POINTS_80, cls.PRODUCT_FC_POINTS_40}:
                    raise ValidationError("Для FC Mobile доступны только пакеты 80 или 40 Points")
                product = cls.FIXED_PRODUCTS[product_code]
                if product.get("promo_only_first"):
                    has_previous_points = cls.objects.filter(
                        user=user,
                        game=cls.GAME_FC_MOBILE,
                        order_type=cls.TYPE_POINTS,
                    ).exists()
                    if has_previous_points:
                        raise ValidationError("80 Points доступны только на первый заказ, дальше доступно 40 Points")
                return product["quantity"], product["price_tjs"], (product["price_tjs"] * FX_TJS_TO_RUB).quantize(Decimal("0.01"))

            if order_type == cls.TYPE_COINS:
                if quantity < 1:
                    raise ValidationError("Минимальный заказ для Coins: 1 млн")
                price_tjs = Decimal(quantity) * Decimal("2")
                return quantity, price_tjs.quantize(Decimal("0.01")), (price_tjs * FX_TJS_TO_RUB).quantize(Decimal("0.01"))

            raise ValidationError("Для FC Mobile доступны только Points и Coins")

        if game == cls.GAME_FREE_FIRE:
            if product_code not in cls.FIXED_PRODUCTS:
                raise ValidationError("Выберите пакет Free Fire")
            product = cls.FIXED_PRODUCTS[product_code]
            if product["game"] != cls.GAME_FREE_FIRE:
                raise ValidationError("Для Free Fire доступны только алмазы и ваучеры")
            return product["quantity"], product["price_tjs"], (product["price_tjs"] * FX_TJS_TO_RUB).quantize(Decimal("0.01"))

        raise ValidationError("Неизвестная игра")

    def clean(self):
        quantity, price_tjs, price_rub = self.calculate_prices(
            user=self.user,
            game=self.game,
            order_type=self.order_type,
            product_code=self.product_code,
            quantity=self.quantity,
        )
        self.quantity = quantity
        self.price_tjs = price_tjs
        self.price_rub = price_rub

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def payment_status_label(self):
        return dict(self.PAYMENT_STATUS_CHOICES).get(self.payment_status, self.payment_status)

    @property
    def product_label(self):
        if self.product_code:
            return dict(self.PRODUCT_CHOICES).get(self.product_code, self.product_code)
        return dict(self.TYPE_CHOICES).get(self.order_type, self.order_type)
