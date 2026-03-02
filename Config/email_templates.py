OTP_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OTP Verification</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        background-color: #f4f4f4;
        margin: 0;
        padding: 0;
      }
      .container {
        max-width: 600px;
        margin: 50px auto;
        background-color: #ffffff;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
      }
      h2 {
        color: #333;
        text-align: center;
      }
      p {
        font-size: 16px;
        color: #555;
      }
      .otp {
        display: inline-block;
        background-color: #007bff;
        color: #ffffff;
        font-size: 24px;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 5px;
        margin: 15px 0;
        text-align: center;
      }
      .footer {
        text-align: center;
        font-size: 14px;
        color: #999;
        margin-top: 20px;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h2>Your OTP Code</h2>
      <p>Hello,</p>
      <p>Please use the following One-Time Password (OTP) to verify your email address:</p>
      <div class="otp">{{otp}}</div>
      <p>This OTP is valid for the next 10 minutes. If you did not request this, please ignore this email.</p>
      <div class="footer">
        <p>Thank you,<br>The Team</p>
      </div>
    </div>
  </body>
</html>


"""


BOOKING_CONFIRMATION_HTML_SUCCESS = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #333;
            background-color: #f9f9f9;
            padding: 20px;
        }
        .container {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
            padding: 20px;
            max-width: 600px;
            margin: 0 auto;
        }
        h2 {
            color: #004085;
        }
        p {
            margin: 0;
            padding: 10px 0;
        }
        .booking-details {
            background-color: #f1f1f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .footer {
            font-size: 12px;
            color: #777;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Booking Confirmation - VFAST Hostel</h2>
        <p>Dear Customer,</p>
        <p>Thank you for booking with us at VFAST Hostel, BITS Pilani Campus. Here are your booking details:</p>
        
        <div class="booking-details">
            <p><strong>Check-in Date:</strong> {{check_in_date}}</p>
            <p><strong>Check-out Date:</strong> {{check_out_date}}</p>
            <p><strong>Number of Persons:</strong> {{number_of_persons}}</p>
            <p><strong>Number of Rooms:</strong> {{number_of_rooms}}</p>
        </div>

        <h3>General Guidelines</h3>
        <p><strong>Check-in Time:</strong> 11:30 AM</p>
        <p><strong>Check-out Time:</strong> 12:00 PM</p>
        <p>Please make sure to have your booking confirmation and a valid ID during check-in. For any assistance, feel free to contact our support team.</p>

        <p>We look forward to hosting you at VFAST Hostel!</p>

        <div class="footer">
            <p>Regards,</p>
            <p>VFAST Hostel Team</p>
            <p>Email: support@vfasthostel.com</p>
        </div>
    </div>
</body>
</html>

"""

BOOKING_CONFIRMATION_HTML_FAIL = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #333;
            background-color: #f9f9f9;
            padding: 20px;
        }
        .container {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
            padding: 20px;
            max-width: 600px;
            margin: 0 auto;
        }
        h2 {
            color: #d9534f; /* Red color for failure */
        }
        p {
            margin: 0;
            padding: 10px 0;
        }
        .footer {
            font-size: 12px;
            color: #777;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }
        .note {
            background-color: #f1f1f1;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Booking Rejected - VFAST Hostel</h2>
        <p>Dear Customer,</p>
        <p>We regret to inform you that your booking attempt with VFAST Hostel, BITS Pilani Campus, was unsuccessful. Please find the details below:</p>
        
        <p><strong>Attempted Check-in Date:</strong> {{check_in_date}}</p>
        <p><strong>Attempted Check-out Date:</strong> {{check_out_date}}</p>
        <p><strong>Number of Persons:</strong> {{rejected_reason}}</p>
        

        
        <p>If you have any questions, please do not hesitate to reach out to our support team.</p>

        <div class="footer">
            <p>Regards,</p>
            <p>VFAST Hostel Team</p>
            <p>Email: support@vfasthostel.com</p>
        </div>
    </div>
</body>
</html>


"""