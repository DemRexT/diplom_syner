def role(request):
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    return {
        "profile": profile,
        "is_it": bool(profile and profile.is_staff_it),
        "is_manager": bool(profile and profile.role == "manager"),
    }
