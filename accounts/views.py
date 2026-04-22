from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import AddressForm, CustomerForm, RegisterForm
from .models import Address, Customer

from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect
from django.contrib import messages

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            messages.success(request, "Account created successfully. Please login.")
            return redirect('login')
        else:
            messages.error(request, "Please fix the errors below.")

    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # 🔥 FORCE SESSION SAVE
            request.session.save()

            return redirect('home')
        else:
            messages.error(request, "Invalid credentials")

    return render(request, 'login.html')

@login_required
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
