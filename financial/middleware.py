from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth.views import redirect_to_login
from django.utils.deprecation import MiddlewareMixin


class RequireLoginMiddleware(MiddlewareMixin):
    """
    Middleware to require login for all pages except those explicitly exempted.
    """
    
    # Paths that don't require authentication
    exempt_urls = [
        '/',                   # Home page
        '/accounts/login/',    # Login page
        '/accounts/logout/',   # Logout page
        '/accounts/signup/',   # Signup page
        '/admin/login/',       # Admin login
        '/admin/logout/',      # Admin logout
        '/static/',            # Static files
        '/media/',             # Media files
        '/favicon.ico',        # Favicon
    ]
    
    def process_request(self, request):
        # Skip middleware if user is already authenticated
        if request.user.is_authenticated:
            return None
            
        # Allow access to exempt URLs without authentication
        current_path = request.path_info
        
        # Check if the current path is in the exempt list
        for exempt_url in self.exempt_urls:
            if current_path.startswith(exempt_url):
                return None
                
        # For all non-exempt paths, redirect to login with next parameter
        return redirect_to_login(
            next=request.path,
            login_url=reverse('login')
        ) 