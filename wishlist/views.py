from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from products.models import Product

from .models import Wishlist

@require_POST
@login_required
def add_to_wishlist(request, id):
    product = get_object_or_404(Product, id=id)

    Wishlist.objects.get_or_create(
        user=request.user,
        product=product
    )

    return redirect('wishlist')


@login_required
def wishlist_view(request):
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request, 'wishlist.html', {'items': items})


@require_POST
@login_required
def remove_from_wishlist(request, id):
    Wishlist.objects.filter(user=request.user, product_id=id).delete()
    return redirect('wishlist')
