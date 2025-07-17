import os

# Define directories to be created
directories = [
    'templates',
    'templates/financial',
    'templates/analytics',
    'templates/registration',
    'static',
    'static/css',
    'static/js',
    'static/images',
    'media'
]

# Create each directory
for directory in directories:
    os.makedirs(directory, exist_ok=True)
    print(f"Created directory: {directory}")

print("All directories created successfully!") 