import random

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import EmailAuthCode, FX_TJS_TO_RUB, Order


OWNER_ACCOUNTS = {
    "orange.juice.112.top@gmail.com": {
        "username": "Foltraz",
        "password": "idrisd10",
        "display_name": "Foltraz",
    },
    "tytyty112112tytyty@gmail.com": {
        "username": "Kiyutol",
        "password": "kira2424",
        "display_name": "Kiyutol",
    },
}
PRIMARY_OWNER_EMAIL = "orange.juice.112.top@gmail.com"
AUDIENCE_CLIENT = "client"
AUDIENCE_OWNER = "owner"
DUSHANBE_CITY_NUMBER = "+992997077810"
DUSHANBE_CITY_LABEL = "Dushanbe City"


def _json_error(message, status=400):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _normalize_email(raw_email):
    return raw_email.strip().lower()


def _generate_code():
    return f"{random.randint(0, 999999):06d}"


def _owner_user(email=PRIMARY_OWNER_EMAIL):
    return User.objects.filter(email=email).first()


def _is_owner_email(email):
    return email in OWNER_ACCOUNTS


def _ensure_owner_credentials(email=PRIMARY_OWNER_EMAIL):
    config = OWNER_ACCOUNTS[email]
    owner = _owner_user(email)
    if owner is None:
        owner = User.objects.create_user(
            username=config["username"],
            email=email,
            password=config["password"],
            first_name=config["display_name"],
        )
    else:
        changed = False
        if owner.username != config["username"]:
            owner.username = config["username"]
            changed = True
        if owner.first_name != config["display_name"]:
            owner.first_name = config["display_name"]
            changed = True
        if not owner.check_password(config["password"]):
            owner.set_password(config["password"])
            changed = True
        if changed:
            owner.save()
    return owner


def _get_user_role(user):
    if user.is_authenticated and _is_owner_email(user.email.lower()):
        return "owner"
    return "client"


def _display_name(user):
    if not user.is_authenticated:
        return ""
    if _is_owner_email(user.email.lower()):
        return OWNER_ACCOUNTS[user.email.lower()]["display_name"]
    return user.first_name or user.username


def _serialize_order(order):
    return {
        "id": order.id,
        "game": order.game,
        "game_label": dict(Order.GAME_CHOICES).get(order.game, order.game),
        "type": order.order_type,
        "type_label": dict(Order.TYPE_CHOICES).get(order.order_type, order.order_type),
        "product_code": order.product_code,
        "product_label": order.product_label,
        "quantity": order.quantity,
        "price_tjs": f"{order.price_tjs:.2f}",
        "price_rub": f"{order.price_rub:.2f}",
        "status": order.status,
        "status_label": order.status_label,
        "payment_status": order.payment_status,
        "payment_status_label": order.payment_status_label,
        "payment_phone": DUSHANBE_CITY_NUMBER,
        "payment_provider": DUSHANBE_CITY_LABEL,
        "payment_email": order.payment_email,
        "customer_email": order.user.email,
        "customer_name": order.user.first_name or order.user.username,
        "created_at": order.created_at.strftime("%d.%m.%Y %H:%M"),
    }


def _latest_code(email, mode):
    return (
        EmailAuthCode.objects.filter(email=email, mode=mode, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )


@require_GET
@ensure_csrf_cookie
def home(request):
    return render(
        request,
        "home.html",
        {
            "user_email": request.user.email if request.user.is_authenticated else "",
            "display_name": _display_name(request.user),
            "user_role": _get_user_role(request.user),
            "fx_rate": f"{FX_TJS_TO_RUB:.2f}",
            "payment_phone": DUSHANBE_CITY_NUMBER,
            "payment_provider": DUSHANBE_CITY_LABEL,
        },
    )


@require_POST
def request_email_code(request):
    email = _normalize_email(request.POST.get("email", ""))
    mode = request.POST.get("mode", "").strip().lower()
    audience = request.POST.get("audience", AUDIENCE_CLIENT).strip().lower()

    if not email:
        return _json_error("Введите почту")
    if "@" not in email:
        return _json_error("Введите корректную почту")
    if mode not in {EmailAuthCode.MODE_LOGIN, EmailAuthCode.MODE_SIGNUP, EmailAuthCode.MODE_RESET}:
        return _json_error("Выберите действие")
    if audience not in {AUDIENCE_CLIENT, AUDIENCE_OWNER}:
        return _json_error("Выберите тип входа")

    if audience == AUDIENCE_OWNER:
        if mode not in {EmailAuthCode.MODE_LOGIN, EmailAuthCode.MODE_RESET}:
            return _json_error("Для владельца доступны вход и восстановление")
        if not _is_owner_email(email):
            return _json_error("Неверная почта владельца", status=403)
        _ensure_owner_credentials(email)

    user_exists = User.objects.filter(email=email).exists()
    if mode == EmailAuthCode.MODE_SIGNUP and user_exists:
        return _json_error("Учетная запись с этой почтой уже существует")
    if mode == EmailAuthCode.MODE_LOGIN and not user_exists and not _is_owner_email(email):
        return _json_error("Учетная запись с этой почтой не найдена")
    if mode == EmailAuthCode.MODE_RESET and not user_exists and not _is_owner_email(email):
        return _json_error("Учетная запись с этой почтой не найдена")
    if mode == EmailAuthCode.MODE_SIGNUP and _is_owner_email(email):
        return _json_error("Эта почта недоступна для обычной регистрации", status=403)

    EmailAuthCode.objects.filter(email=email, mode=mode, consumed_at__isnull=True).update(consumed_at=timezone.now())
    code = _generate_code()
    auth_code = EmailAuthCode.create_for_email(email=email, code=code, mode=mode)

    send_mail(
        subject="Код подтверждения DonatFast",
        message=f"Ваш код подтверждения: {code}. Код действует 10 минут.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@donatfast.local"),
        recipient_list=[email],
        fail_silently=False,
    )

    response = {
        "status": "ok",
        "message": "Код отправлен на почту",
        "email": email,
        "mode": mode,
        "audience": audience,
        "expires_at": auth_code.expires_at.isoformat(),
    }
    if settings.DEBUG:
        response["debug_code"] = code
    return JsonResponse(response)


@require_POST
def verify_email_code(request):
    email = _normalize_email(request.POST.get("email", ""))
    code = request.POST.get("code", "").strip()
    mode = request.POST.get("mode", "").strip().lower()

    if not email or not code:
        return _json_error("Введите почту и код")
    if mode not in {EmailAuthCode.MODE_LOGIN, EmailAuthCode.MODE_SIGNUP, EmailAuthCode.MODE_RESET}:
        return _json_error("Выберите действие")

    auth_code = _latest_code(email, mode)
    if auth_code is None or auth_code.expires_at <= timezone.now():
        return _json_error("Код истек. Запросите новый")
    if auth_code.code != code:
        return _json_error("Неверный код")

    auth_code.verified_at = timezone.now()
    auth_code.save(update_fields=["verified_at"])
    return JsonResponse({"status": "ok", "message": "Код подтвержден"})


@require_POST
def complete_login(request):
    email = _normalize_email(request.POST.get("email", ""))
    auth_code = _latest_code(email, EmailAuthCode.MODE_LOGIN)

    if auth_code is None or auth_code.expires_at <= timezone.now() or auth_code.verified_at is None:
        return _json_error("Сначала подтвердите код")

    user = User.objects.filter(email=email).first()
    if user is None and _is_owner_email(email):
        user = _ensure_owner_credentials(email)
    if user is None:
        return _json_error("Учетная запись не найдена")

    auth_code.consumed_at = timezone.now()
    auth_code.save(update_fields=["consumed_at"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse(
        {
            "status": "ok",
            "message": "Вход выполнен",
            "user": {
                "email": user.email,
                "display_name": _display_name(user),
                "role": _get_user_role(user),
            },
        }
    )


@require_POST
def complete_owner_setup(request):
    email = _normalize_email(request.POST.get("email", ""))
    auth_code = _latest_code(email, EmailAuthCode.MODE_LOGIN)

    if not _is_owner_email(email):
        return _json_error("Неверная почта владельца", status=403)
    if auth_code is None or auth_code.expires_at <= timezone.now() or auth_code.verified_at is None:
        return _json_error("Сначала подтвердите код")

    owner = _ensure_owner_credentials(email)
    auth_code.consumed_at = timezone.now()
    auth_code.save(update_fields=["consumed_at"])
    login(request, owner, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse(
        {
            "status": "ok",
            "message": "Владелец вошел",
            "user": {"email": owner.email, "display_name": _display_name(owner), "role": "owner"},
        }
    )


@require_POST
def owner_password_login(request):
    identifier = request.POST.get("identifier", "").strip()
    password = request.POST.get("password", "")

    if not identifier or not password:
        return _json_error("Введите логин или почту и пароль")

    user = User.objects.filter(username=identifier).first() or User.objects.filter(email=_normalize_email(identifier)).first()
    if user is None or not _is_owner_email(user.email.lower()):
        return _json_error("Неверный логин или пароль", status=403)

    authenticated = authenticate(request, username=user.username, password=password)
    if authenticated is None or not _is_owner_email(authenticated.email.lower()):
        return _json_error("Неверный логин или пароль", status=403)

    login(request, authenticated, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse(
        {
            "status": "ok",
            "message": "Вход выполнен",
            "user": {
                "email": authenticated.email,
                "display_name": _display_name(authenticated),
                "role": "owner",
            },
        }
    )


@require_POST
def complete_signup(request):
    email = _normalize_email(request.POST.get("email", ""))
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    password_repeat = request.POST.get("password_repeat", "")
    auth_code = _latest_code(email, EmailAuthCode.MODE_SIGNUP)

    if auth_code is None or auth_code.expires_at <= timezone.now() or auth_code.verified_at is None:
        return _json_error("Сначала подтвердите код")
    if not username or not password or not password_repeat:
        return _json_error("Заполните логин и оба поля пароля")
    if password != password_repeat:
        return _json_error("Пароли не совпадают")
    if User.objects.filter(username=username).exists():
        return _json_error("Этот логин уже занят")
    if User.objects.filter(email=email).exists():
        return _json_error("Учетная запись с этой почтой уже существует")

    user = User.objects.create_user(username=username, email=email, password=password, first_name=username)
    auth_code.consumed_at = timezone.now()
    auth_code.save(update_fields=["consumed_at"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse(
        {
            "status": "ok",
            "message": "Учетная запись создана",
            "user": {
                "email": user.email,
                "display_name": _display_name(user),
                "role": _get_user_role(user),
            },
        }
    )


@require_POST
def complete_password_reset(request):
    email = _normalize_email(request.POST.get("email", ""))
    password = request.POST.get("password", "")
    password_repeat = request.POST.get("password_repeat", "")
    auth_code = _latest_code(email, EmailAuthCode.MODE_RESET)

    if auth_code is None or auth_code.expires_at <= timezone.now() or auth_code.verified_at is None:
        return _json_error("Сначала подтвердите код")
    if not password or not password_repeat:
        return _json_error("Заполните оба поля пароля")
    if password != password_repeat:
        return _json_error("Пароли не совпадают")

    user = User.objects.filter(email=email).first()
    if user is None and _is_owner_email(email):
        user = _ensure_owner_credentials(email)
    if user is None:
        return _json_error("Учетная запись не найдена")

    user.set_password(password)
    user.save(update_fields=["password"])
    auth_code.consumed_at = timezone.now()
    auth_code.save(update_fields=["consumed_at"])
    return JsonResponse({"status": "ok", "message": "Пароль обновлен"})


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"status": "ok", "message": "Вы вышли из аккаунта"})


@require_GET
def session_state(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse(
        {
            "authenticated": True,
            "user": {
                "email": request.user.email,
                "display_name": _display_name(request.user),
                "role": _get_user_role(request.user),
            },
        }
    )


@require_GET
def orders_list(request):
    if not request.user.is_authenticated:
        return _json_error("Требуется вход", status=401)
    if _get_user_role(request.user) == "owner":
        orders = Order.objects.select_related("user").all()
    else:
        orders = Order.objects.select_related("user").filter(user=request.user)
    return JsonResponse({"status": "ok", "orders": [_serialize_order(order) for order in orders]})


@require_GET
def payments_list(request):
    if not request.user.is_authenticated:
        return _json_error("Требуется вход", status=401)
    if _get_user_role(request.user) != "owner":
        return _json_error("Только владелец видит оплаты", status=403)
    orders = Order.objects.select_related("user").filter(payment_status=Order.PAYMENT_REVIEW)
    return JsonResponse({"status": "ok", "payments": [_serialize_order(order) for order in orders]})


@require_POST
def create_order(request):
    if not request.user.is_authenticated:
        return _json_error("Войдите в аккаунт", status=401)
    if _get_user_role(request.user) != "client":
        return _json_error("Владелец не создает клиентские заказы", status=403)

    game = request.POST.get("game", Order.GAME_FC_MOBILE).strip()
    order_type = request.POST.get("order_type", "").strip()
    product_code = request.POST.get("product_code", "").strip()
    responsibility = request.POST.get("responsibility", "").strip().lower()
    quantity_raw = request.POST.get("quantity", "").strip()
    if responsibility not in {"1", "true", "on", "yes"}:
        return _json_error("Подтвердите, что берете всю ответственность на себя")
    if quantity_raw and not quantity_raw.isdigit():
        return _json_error("Укажите количество числом")

    quantity = int(quantity_raw) if quantity_raw else 0
    try:
        order = Order(user=request.user, game=game, order_type=order_type, product_code=product_code, quantity=quantity)
        order.save()
    except ValidationError as exc:
        return _json_error(exc.messages[0] if getattr(exc, "messages", None) else "Не удалось создать заказ")

    return JsonResponse({"status": "ok", "message": "Заказ создан. Теперь оплатите его.", "order": _serialize_order(order)})


@require_POST
def mark_order_paid(request, order_id):
    if not request.user.is_authenticated:
        return _json_error("Войдите в аккаунт", status=401)
    if _get_user_role(request.user) != "client":
        return _json_error("Только клиент отмечает оплату", status=403)

    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment_email = _normalize_email(request.POST.get("payment_email", ""))
    payment_password = request.POST.get("payment_password", "")
    if not payment_email:
        return _json_error("Введите почту для оплаты")
    if "@" not in payment_email:
        return _json_error("Введите корректную почту для оплаты")
    if not payment_password:
        return _json_error("Введите пароль для оплаты")
    paid_at = timezone.now()
    Order.objects.filter(id=order.id).update(
        payment_status=Order.PAYMENT_REVIEW,
        payment_email=payment_email,
        payment_password=payment_password,
        paid_at=paid_at,
        updated_at=paid_at,
    )
    order.refresh_from_db()
    return JsonResponse({"status": "ok", "message": "Оплата отправлена на проверку", "order": _serialize_order(order)})


@require_POST
def approve_order_payment(request, order_id):
    if not request.user.is_authenticated:
        return _json_error("Требуется вход", status=401)
    if _get_user_role(request.user) != "owner":
        return _json_error("Только владелец подтверждает оплату", status=403)

    order = get_object_or_404(Order, id=order_id)
    approved_at = timezone.now()
    Order.objects.filter(id=order.id).update(
        payment_status=Order.PAYMENT_APPROVED,
        payment_approved_at=approved_at,
        updated_at=approved_at,
    )
    order.refresh_from_db()
    return JsonResponse({"status": "ok", "message": "Оплата разрешена", "order": _serialize_order(order)})


@require_POST
def update_order_status(request, order_id):
    if not request.user.is_authenticated:
        return _json_error("Требуется вход", status=401)
    if _get_user_role(request.user) != "owner":
        return _json_error("Только владелец может менять статусы", status=403)

    status_value = request.POST.get("status", "").strip()
    if status_value not in {choice[0] for choice in Order.STATUS_CHOICES}:
        return _json_error("Некорректный статус")

    order = get_object_or_404(Order, id=order_id)
    updated_at = timezone.now()
    Order.objects.filter(id=order.id).update(status=status_value, updated_at=updated_at)
    order.refresh_from_db()
    return JsonResponse({"status": "ok", "message": "Статус обновлен", "order": _serialize_order(order)})


@require_POST
def delete_order(request, order_id):
    if not request.user.is_authenticated:
        return _json_error("Требуется вход", status=401)
    if _get_user_role(request.user) != "owner":
        return _json_error("Только владелец может удалять заказы", status=403)

    order = get_object_or_404(Order, id=order_id)
    order.delete()
    return JsonResponse({"status": "ok", "message": "Заказ удален"})
