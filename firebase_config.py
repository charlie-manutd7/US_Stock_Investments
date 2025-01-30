import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

def initialize_app():
    """Initialize Firebase Admin with service account and return initialized resources."""
    # Get the absolute path to the service account file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    service_account_path = os.path.join(current_dir, 'service-account.json')

    # Initialize Firebase Admin with your service account
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'stock-options-tool.appspot.com',
        'projectId': 'stock-options-tool'
    })

    # Initialize Firestore and Storage
    db = firestore.client()
    bucket = storage.bucket()
    
    return db, bucket

# Initialize resources on module import
db, bucket = initialize_app() 