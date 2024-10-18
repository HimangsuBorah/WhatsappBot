from flask import Flask, request, send_file
from twilio.rest import Client
import requests
import os
from dotenv import load_dotenv
import io
import time
from PIL import Image
import logging
import redis
from rq import Queue
import huggingface_hub

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize Twilio client
twilio_client = Client(
    os.getenv('TWILIO_ACCOUNT_SID'),
    os.getenv('TWILIO_AUTH_TOKEN')
)

# Initialize Redis for job queue
redis_conn = redis.Redis()
job_queue = Queue(connection=redis_conn)

# Initialize Hugging Face client
hf_token = os.getenv('HUGGINGFACE_TOKEN')
API_URL = "https://api-inference.huggingface.co/models/Kolors-Virtual-Try-On"
headers = {"Authorization": f"Bearer {hf_token}"}

class UserSession:
    def __init__(self):
        self.person_image = None
        self.garment_image = None
        
    def reset(self):
        self.person_image = None
        self.garment_image = None

# Store user sessions
user_sessions = {}

def process_virtual_tryon(person_image, garment_image):
    """Process the virtual try-on request using Hugging Face API"""
    try:
        payload = {
            "person_image": person_image,
            "garment_image": garment_image
        }
        response = requests.post(API_URL, headers=headers, json=payload)
        return response.content
    except Exception as e:
        logging.error(f"Error in virtual try-on processing: {str(e)}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming WhatsApp messages"""
    try:
        # Get message details
        message = request.form.get('Body', '')
        sender = request.form.get('From', '')
        num_media = int(request.form.get('NumMedia', 0))
        
        # Initialize user session if not exists
        if sender not in user_sessions:
            user_sessions[sender] = UserSession()
        
        # Handle image uploads
        if num_media > 0:
            media_url = request.form.get('MediaUrl0', '')
            if not user_sessions[sender].person_image:
                user_sessions[sender].person_image = media_url
                send_whatsapp_message(sender, "Great! Now send me the garment image you want to try on.")
            else:
                user_sessions[sender].garment_image = media_url
                # Process virtual try-on
                job = job_queue.enqueue(process_virtual_tryon,
                                     user_sessions[sender].person_image,
                                     user_sessions[sender].garment_image)
                send_whatsapp_message(sender, "Processing your virtual try-on request... Please wait.")
                
                # Reset session
                user_sessions[sender].reset()
        else:
            if message.lower() == 'start':
                send_whatsapp_message(sender, "Welcome to Virtual Try-On! Please send me your full-body photo.")
            else:
                send_whatsapp_message(sender, "Please send images or type 'start' to begin.")
                
        return 'OK'
    except Exception as e:
        logging.error(f"Error in webhook: {str(e)}")
        return 'Error', 500

def send_whatsapp_message(to, message):
    """Send WhatsApp message using Twilio"""
    try:
        twilio_client.messages.create(
            from_=os.getenv('TWILIO_WHATSAPP_NUMBER'),
            body=message,
            to=to
        )
    except Exception as e:
        logging.error(f"Error sending WhatsApp message: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True)