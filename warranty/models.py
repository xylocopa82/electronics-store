from django.db import models
from products.models import Product

class Warranty(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    warranty_period = models.CharField(max_length=50)  # Example: 1 Year
    start_date = models.DateField()
    end_date = models.DateField()
    support_contact = models.CharField(max_length=100)

    def __str__(self):
        return self.product.name