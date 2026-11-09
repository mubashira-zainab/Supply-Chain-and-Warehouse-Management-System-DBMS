# Vercel entry point — imports the Flask app from the parent directory
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import app as application

# Vercel looks for a variable named `app` or `application`
app = application
