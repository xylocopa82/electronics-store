from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import AddressForm, CustomerForm, RegisterForm
from .models import Address, Customer

def register_view(request):
    form = RegisterForm()

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')

    return render(request, 'register.html', {'form': form})


def login_view(request):
    next_url = request.POST.get('next') or request.GET.get('next', '')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect('home')

        messages.error(request, 'Invalid username or password.')

    return render(request, 'login.html', {'next_url': next_url})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    customer, _ = Customer.objects.get_or_create(user=request.user)
    addresses = Address.objects.filter(user=request.user)

    form = CustomerForm(instance=customer)
    address_form = AddressForm()

    if request.method == 'POST':

        if 'update_profile' in request.POST:
            form = CustomerForm(request.POST, request.FILES, instance=customer)
            if form.is_valid():
                form.save()
                return redirect('profile')

        elif 'add_address' in request.POST:
            address_form = AddressForm(request.POST)
            if address_form.is_valid():
                address = address_form.save(commit=False)
                address.user = request.user

                # Only one default address
                if address.is_default:
                    Address.objects.filter(user=request.user).update(is_default=False)

                address.save()
                return redirect('profile')

    return render(request, 'profile.html', {
        'form': form,
        'address_form': address_form,
        'addresses': addresses
    })
