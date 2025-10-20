import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- Toyyibpay Configuration ---
TOYYIBPAY_API_URL = "https://toyyibpay.com/index.php/api/createBill"
TOYYIBPAY_SECRET_KEY = os.getenv("TOYYIBPAY_SECRET_KEY")
TOYYIBPAY_CATEGORY_CODE = os.getenv("TOYYIBPAY_CATEGORY_CODE")

# --- IMPORTANT: Update these placeholders ---
# This should be your Vercel app's URL. Toyyibpay will send payment status updates here.
APP_BASE_URL = os.getenv("VERCEL_URL", "https://your-app-name.vercel.app") 
# Your telegram bot username
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "YourBotUsername")

def create_bill(user_telegram_id: int, user_name: str, user_email: str, amount: float) -> dict:
    """
    Creates a new bill using the Toyyibpay API and returns the payment URL.
    """
    if not TOYYIBPAY_SECRET_KEY or not TOYYIBPAY_CATEGORY_CODE:
        return {"error": "Toyyibpay credentials are not set in the .env file."}

    # The amount must be in cents
    bill_amount_cents = int(amount * 100)

    # A unique reference number for this transaction
    bill_external_reference_no = f"MYK-{user_telegram_id}-{int(datetime.now().timestamp())}"

    payload = {
        'userSecretKey': TOYYIBPAY_SECRET_KEY,
        'categoryCode': TOYYIBPAY_CATEGORY_CODE,
        'billName': 'MyKewanganBot Premium',
        'billDescription': 'Langganan 1 Bulan MyKewanganBot Premium',
        'billPriceSetting': 1, # 1 for fixed price
        'billPayorInfo': 1, # 1 to require payor info
        'billAmount': bill_amount_cents,
        'billReturnUrl': f'https://t.me/{TELEGRAM_BOT_USERNAME}',
        'billCallbackUrl': f'https://{APP_BASE_URL}/webhook/toyyibpay',
        'billExternalReferenceNo': bill_external_reference_no,
        'billTo': user_name,
        'billEmail': user_email,
        'billPhone': '0123456789' # A placeholder phone number
    }

    try:
        response = requests.post(TOYYIBPAY_API_URL, data=payload)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        # Toyyibpay returns a list with a single dictionary
        result = response.json()
        if result and isinstance(result, list) and 'BillCode' in result[0]:
            bill_code = result[0]['BillCode']
            payment_url = f"https://toyyibpay.com/{bill_code}"
            return {"success": True, "payment_url": payment_url, "bill_code": bill_code}
        else:
            return {"error": f"Failed to create bill. API response: {result}"}

    except requests.exceptions.RequestException as e:
        return {"error": f"Could not connect to Toyyibpay API: {e}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}
