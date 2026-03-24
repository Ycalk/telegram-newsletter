import os

import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.environ["RESEND_API_KEY"]

params: resend.Emails.SendParams = {
    "from": os.environ["SEND_FROM_EMAIL"],
    "to": ["alosev752@gmail.com"],
    "subject": "Это телеграмм рассылка",
    "html": "<strong>it works!</strong>",
}

email = resend.Emails.send(params)
print(email)
