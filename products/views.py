from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from types import SimpleNamespace

from accounts.models import Address
from orders.models import Order
from .models import Product, Review


class RazorpayUnavailableError(Exception):
    pass


try:
    import razorpay
    from razorpay.errors import (
        BadRequestError,
        GatewayError,
        ServerError,
        SignatureVerificationError,
    )
except ImportError:
    class BadRequestError(Exception):
        pass

    class GatewayError(Exception):
        pass

    class ServerError(Exception):
        pass

    class SignatureVerificationError(Exception):
        pass

    def _missing_razorpay_client(*args, **kwargs):
        raise RazorpayUnavailableError(
            'Razorpay SDK is not installed. Install project dependencies with '
            '`pip install -r requirements.txt` and try again.'
        )

    razorpay = SimpleNamespace(Client=_missing_razorpay_client)


def _get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RazorpayUnavailableError(
            'Razorpay credentials are not configured. Set RAZORPAY_KEY_ID and '
            'RAZORPAY_KEY_SECRET and try again.'
        )

    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def _get_cart_items(request):
    raw_cart = request.session.get('cart', {})
    normalized_cart = {}

    for product_id, qty in raw_cart.items():
        try:
            parsed_product_id = int(product_id)
            parsed_qty = int(qty)
        except (TypeError, ValueError):
            continue

        if parsed_qty > 0:
            normalized_cart[parsed_product_id] = parsed_qty

    products = Product.objects.in_bulk(normalized_cart.keys())
    cart_items = []
    cleaned_cart = {}
    total = 0

    for product_id, qty in normalized_cart.items():
        product = products.get(product_id)
        if not product:
            continue

        product.qty = qty
        product.subtotal = product.price * qty
        cart_items.append(product)
        cleaned_cart[str(product_id)] = qty
        total += product.subtotal

    if raw_cart != cleaned_cart:
        request.session['cart'] = cleaned_cart

    return cart_items, total


def _get_products_with_ratings():
    return Product.objects.all().annotate(avg_rating=Avg('reviews__rating'))


def _render_checkout_selection(request, addresses, products, total):
    return render(
        request,
        'checkout_select.html',
        {'addresses': addresses, 'products': products, 'total': total},
    )


def _cart_has_available_stock(request, products):
    stock_is_available = True

    for product in products:
        if product.stock < product.qty:
            messages.error(
                request,
                f'Only {product.stock} item(s) of {product.name} are available.',
            )
            stock_is_available = False

    return stock_is_available


def home(request):
    products = Product.objects.all().order_by('-created_at')

    for product in products:
        rating_data = product.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
        product.avg_rating = rating_data['avg'] or 0
        product.review_count = rating_data['count']

    return render(request, 'home.html', {'products': products})


def product_list(request):
    products = _get_products_with_ratings().order_by('-created_at')
    return render(request, 'products.html', {'products': products})


def product_detail(request, id):
    product = get_object_or_404(Product, id=id)

    rating_data = product.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
    avg_rating = rating_data['avg'] or 0
    review_count = rating_data['count']

    user_review = None
    if request.user.is_authenticated:
        user_review = Review.objects.filter(product=product, user=request.user).first()

    reviews = product.reviews.select_related('user').order_by('-created_at')

    return render(
        request,
        'product_detail.html',
        {
            'product': product,
            'avg_rating': avg_rating,
            'review_count': review_count,
            'user_review': user_review,
            'reviews': reviews,
        },
    )


@require_POST
def add_to_cart(request, id):
    product = get_object_or_404(Product, id=id)
    cart = request.session.get('cart', {})
    cart_key = str(product.id)

    try:
        current_qty = int(cart.get(cart_key, 0))
    except (TypeError, ValueError):
        current_qty = 0

    if product.stock < 1:
        messages.error(request, f'{product.name} is out of stock.')
        return redirect('product_detail', id=product.id)

    if current_qty >= product.stock:
        messages.error(request, f'Only {product.stock} item(s) of {product.name} are available.')
        return redirect('cart')

    cart[cart_key] = current_qty + 1
    request.session['cart'] = cart
    return redirect('cart')


def cart_view(request):
    products, total = _get_cart_items(request)
    return render(request, 'cart.html', {'products': products, 'total': total})


@require_POST
def remove_from_cart(request, id):
    cart = request.session.get('cart', {})

    if str(id) in cart:
        del cart[str(id)]

    request.session['cart'] = cart
    return redirect('cart')


@login_required
def checkout(request):
    products, total = _get_cart_items(request)

    if not products:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    addresses = Address.objects.filter(user=request.user)
    if not addresses.exists():
        messages.error(request, 'Add a delivery address from your profile before checking out.')
        return redirect('profile')

    if request.method == 'POST':
        address_id = request.POST.get('address')
        if not address_id:
            messages.error(request, 'Select a delivery address.')
            return _render_checkout_selection(request, addresses, products, total)

        address = get_object_or_404(Address, id=address_id, user=request.user)

        if not _cart_has_available_stock(request, products):
            return _render_checkout_selection(request, addresses, products, total)

        receipt = f"order_{request.user.id}_{timezone.now().strftime('%Y%m%d%H%M%S%f')}"[:40]

        try:
            amount_paise = int(total * 100)
            client = _get_razorpay_client()
            payment = client.order.create(
                {
                    'amount': amount_paise,
                    'currency': 'INR',
                    'receipt': receipt,
                }
            )
        except (BadRequestError, GatewayError, ServerError) as exc:
            messages.error(request, f'Unable to start Razorpay checkout: {exc}')
            return _render_checkout_selection(request, addresses, products, total)
        except RazorpayUnavailableError as exc:
            messages.error(request, str(exc))
            return _render_checkout_selection(request, addresses, products, total)
        except Exception:
            messages.error(request, 'Unable to connect to Razorpay right now. Please try again.')
            return _render_checkout_selection(request, addresses, products, total)

        request.session['payment_order_id'] = payment['id']
        request.session['payment_amount'] = payment['amount']
        request.session['address_id'] = address.id

        return render(
            request,
            'payment.html',
            {
                'payment_id': payment['id'],
                'payment_amount': payment['amount'],
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'customer_name': address.name or request.user.get_full_name() or request.user.username,
                'customer_email': request.user.email,
                'customer_contact': address.phone,
                'total_rupees': total,
            },
        )

    return _render_checkout_selection(request, addresses, products, total)


@login_required
@require_POST
def add_review(request, id):
    product = get_object_or_404(Product, id=id)
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '').strip()

    if not rating:
        messages.error(request, 'Please select a rating.')
        return redirect('product_detail', id=id)

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        messages.error(request, 'Invalid rating value.')
        return redirect('product_detail', id=id)

    if rating < 1 or rating > 5:
        messages.error(request, 'Rating must be between 1 and 5.')
        return redirect('product_detail', id=id)

    review, created = Review.objects.get_or_create(
        product=product,
        user=request.user,
        defaults={'rating': rating, 'comment': comment},
    )

    if not created:
        review.rating = rating
        review.comment = comment
        review.save(update_fields=['rating', 'comment'])

    messages.success(request, 'Your review has been saved.')
    return redirect('product_detail', id=id)


@csrf_exempt
@login_required
def payment_success(request):
    payment_id = request.GET.get('payment_id')
    order_id = request.GET.get('order_id')
    signature = request.GET.get('signature')

    expected_order_id = request.session.get('payment_order_id')
    address_id = request.session.get('address_id')

    # 🔒 Step 1: Validate request data
    if not all([payment_id, order_id, signature, expected_order_id, address_id]):
        messages.error(request, 'Invalid payment data.')
        return render(request, 'payment_failed.html', status=400)

    # 🔒 Step 2: Verify order ID match
    if order_id != expected_order_id:
        messages.error(request, 'Order mismatch detected.')
        return render(request, 'payment_failed.html', status=400)

    # 🔒 Step 3: Verify Razorpay signature
    try:
        client = _get_razorpay_client()
        client.utility.verify_payment_signature({
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': signature
        })
    except SignatureVerificationError:
        messages.error(request, 'Payment verification failed.')
        return render(request, 'payment_failed.html', status=400)

    # 🔒 Step 4: Get cart items  ← (THIS IS WHERE STEP 4 STARTS)
    cart_items, _ = _get_cart_items(request)

    if not cart_items:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    # 🔒 Step 5: Check stock again ← (THIS IS YOUR CURRENT STEP 4)
    if not _cart_has_available_stock(request, cart_items):
        messages.error(request, 'Items out of stock.')
        return render(request, 'payment_failed.html', status=409)

    # 🔒 Step 6: Get address
    address = get_object_or_404(Address, id=address_id, user=request.user)

    # 🔒 Step 7: Create orders safely
    with transaction.atomic():
        for product in cart_items:
            Order.objects.create(
                user=request.user,
                product=product,
                quantity=product.qty,
                total_price=product.price * product.qty,
                address=address,
            )

            product.stock -= product.qty
            product.save(update_fields=['stock'])

    # 🔒 Step 8: Clear session
    request.session['cart'] = {}
    request.session.pop('address_id', None)
    request.session.pop('payment_order_id', None)
    request.session.pop('payment_amount', None)

    # ✅ Step 9: Success response
    return render(request, 'checkout.html', {'success': True})
