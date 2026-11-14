from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import RegistrationForm


class LibraryLoginView(LoginView):
    def get_success_url(self):
        user = self.request.user
        if user.is_staff and user.groups.filter(name="Bibliotekarki").exists():
            return reverse("admin:index")
        return super().get_success_url()


# Create your views here.
def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("login")
    else:
        form = RegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )
