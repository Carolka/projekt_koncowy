def library_role(request):
    user = request.user
    return {
        "konto_bibliotekarki": (
            user.is_authenticated
            and user.groups.filter(name="Bibliotekarki").exists()
        ),
    }
