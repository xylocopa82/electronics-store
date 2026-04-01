from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Order

@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).select_related('product')
    return render(request, 'orders.html', {'orders': orders})