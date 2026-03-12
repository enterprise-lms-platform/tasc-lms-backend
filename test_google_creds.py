import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings

print("=" * 50)
print("GOOGLE CREDENTIALS DIAGNOSTIC")
print("=" * 50)

# Check .env value
creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
print(f"1. GOOGLE_APPLICATION_CREDENTIALS = '{creds_path}'")

# Check if path is empty
if not creds_path:
    print("❌ ERROR: GOOGLE_APPLICATION_CREDENTIALS is empty!")
    print("   Add it to your .env file like:")
    print("   GOOGLE_APPLICATION_CREDENTIALS=config/credentials/google-service-account.json")
    exit(1)

# Check absolute path
project_root = Path(__file__).parent
abs_path = project_root / creds_path
print(f"2. Absolute path: {abs_path}")

# Check if file exists
if abs_path.exists():
    print(f"3. ✅ File exists at: {abs_path}")
    
    # Check file size
    file_size = abs_path.stat().st_size
    print(f"4. File size: {file_size} bytes")
    
    # Check if it's a valid JSON (first few chars)
    with open(abs_path, 'r') as f:
        content = f.read(100)
        if content.strip().startswith('{'):
            print("5. ✅ File appears to be valid JSON")
        else:
            print("5. ❌ File does not look like JSON")
else:
    print(f"3. ❌ File NOT found at: {abs_path}")
    
    # Suggest where to look
    print("\nLooking for service account files...")
    for file in project_root.glob("**/*.json"):
        if "service" in file.name.lower() or "google" in file.name.lower():
            print(f"   Possible candidate: {file.relative_to(project_root)}")