import random

import boto3
import botocore.exceptions
from Config.email_templates import OTP_HTML, BOOKING_CONFIRMATION_HTML_FAIL, BOOKING_CONFIRMATION_HTML_SUCCESS
from Config.secrets import settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from Importers.common_functions import get_timestamp

class SMTPClient:
    def __init__(self, smtp_server, smtp_port, email_address, email_password):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email_address = email_address
        self.email_password = email_password
        self.connection = None

    def connect(self):
        if not self.connection:
            self.connection = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.connection.starttls()
            self.connection.login(self.email_address, self.email_password)

    def send_email(self, recipient_email, subject, body):
        try:
            self.connect()
            message = MIMEText(body)
            message["From"] = self.email_address
            message["To"] = recipient_email
            message["Subject"] = subject
            self.connection.sendmail(self.email_address, recipient_email, message.as_string())
            print(f"Email sent to {recipient_email}")
        except Exception as e:
            print(f"Error sending email to {recipient_email}: {e}")
            self.reconnect()  # Attempt to reconnect on failure

    def reconnect(self):
        self.close()
        self.connect()

    def close(self):
        if self.connection:
            self.connection.quit()
            self.connection = None
smtp_cli = SMTPClient(smtp_server='smtp.gmail.com', smtp_port=587,email_address='<EMAIL>', email_password='<PASSWORD>')
def get_connection():
    try:
        client = boto3.client('sesv2',
                              region_name='ap-south-1',
                              aws_access_key_id=settings.AWS_ACCESS_KEY,
                              aws_secret_access_key=settings.AWS_SECRET_KEY)
        return client,None
    except Exception as error:
        return None,error


def send_email(to, subject, body):
    try:

        CHARSET = "utf-8"
        client, error = get_connection()
        if error:
            return error
        response = client.send_email(
            FromEmailAddress="noreply <ssudhanva2k1@gmail.com>",
            Destination={"ToAddresses": [to]},
            Content={
                'Simple': {
                    'Subject': {
                        'Data': subject,
                        'Charset': CHARSET
                    },
                    'Body': {
                        'Html': {
                            'Data': body,
                            'Charset': CHARSET
                        }
                    }
                }
            },
            ConfigurationSetName='vfast-client'

        )
        return
    except Exception as error:
        return error

def sendOtp(to,otp):

    FORMATTED_BODY = OTP_HTML.replace("{{otp}}", str(otp))
    error = send_email(to, "Your OTP for VFAST Login", FORMATTED_BODY)
    return error


def send_email_smtp(to, subject, body):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    email_address = "h20240187@pilani.bits-pilani.ac.in"
    email_password = "toyk qsnb chsb pfyz"

    try:
        message = MIMEMultipart()
        message["From"] = f" Vfast Hostel {email_address}"
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))

        # Connect to the server

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Upgrade to secure connection (if using port 587)
        server.login(email_address, email_password)

        server.sendmail(email_address, to, message.as_string())

    except Exception as e:
        print(f"Failed to send email: {e}")
        return e

    finally:
        server.quit()

def sendBookingConfirmation(to,vars,status="success"):
    if status == "success":
        HTML = BOOKING_CONFIRMATION_HTML_SUCCESS
    else:
        HTML = BOOKING_CONFIRMATION_HTML_FAIL
    for k,v in vars.items():
        HTML = HTML.replace("{{"+k+"}}", str(v))

    error = send_email_smtp(to, "Booking Status - VFAST Hostel", HTML)
    return error