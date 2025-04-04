# Piano Tuning Booking System with Stripe Payments

This system allows customers to book piano tuning services and pay for them using Stripe.

## Setup Instructions

### 1. Install Dependencies

```bash
pip install flask flask-cors google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client stripe requests
```

### 2. Configure Stripe

1. Sign up for a Stripe account at [stripe.com](https://stripe.com)
2. Get your API keys from the Stripe Dashboard
3. Update the API keys in `mcp_booking_server.py`:
   ```python
   stripe.api_key = 'sk_test_your_secret_key'
   STRIPE_PUBLISHABLE_KEY = 'pk_test_your_publishable_key'
   ```

### 3. Set Up Stripe Webhook

1. In the Stripe Dashboard, go to Developers > Webhooks
2. Add an endpoint: `https://your-domain.com/webhook`
3. Select the event: `checkout.session.completed`
4. Get the webhook signing secret and update it in `mcp_booking_server.py`:
   ```python
   event = stripe.Webhook.construct_event(
       payload, sig_header, 'whsec_your_webhook_secret'
   )
   ```

### 4. Configure Google Calendar

1. Set up a Google Cloud project
2. Enable the Google Calendar API
3. Create a service account and download the credentials
4. Place the credentials file in the `credentials` directory
5. Update the `CALENDAR_ID` in `mcp_booking_server.py` with your calendar ID

### 5. Run the Server

```bash
python mcp_booking_server.py
```

## How It Works

1. Customer fills out the booking form with their details and selects a date and time
2. When they click "Pay and Book", the system:
   - Checks if the slot is available
   - Verifies the distance from the shop
   - Creates a Stripe payment session
   - Redirects to Stripe Checkout
3. After successful payment:
   - Stripe sends a webhook notification
   - The system creates the booking in Google Calendar
   - The customer is redirected to a success page

## Important Notes

- **Email Handling**: An email address is not required for booking. If needed, Stripe will collect the customer's email during the payment process.

- **Payment Process**: After collecting customer details, the system will create a booking and generate a Stripe payment link. The booking will be confirmed once payment is received.

- **Direct Booking**: For testing purposes, a `/direct-booking` endpoint is available that creates bookings without requiring payment. This is useful for testing the calendar integration.

## API Endpoints

### Check Availability
- **Method**: POST
- **Endpoint**: `/check-availability`
- **Description**: Check available slots for a given postcode
- **Request Body**:
  ```json
  {
    "postcode": "SW1A 1AA"
  }
  ```
- **Response**:
  ```json
  {
    "available_slots": [
      {
        "date": "2024-03-20",
        "time": "10:00"
      }
    ]
  }
  ```

### Create Booking
- **Method**: POST
- **Endpoint**: `/create-booking`
- **Description**: Create a booking and return a Stripe payment link
- **Request Body**:
  ```json
  {
    "date": "2024-03-20",
    "time": "10:00",
    "customer_name": "John Doe",
    "address": "123 Main St, London",
    "phone": "07123456789",
    "email": "john@example.com"  // Optional
  }
  ```
- **Response**:
  ```json
  {
    "message": "Booking created successfully",
    "booking_details": {
      "date": "2024-03-20",
      "time": "10:00",
      "customer_name": "John Doe",
      "address": "123 Main St, London",
      "phone": "07123456789",
      "distance": 5000
    },
    "payment_session": {
      "session_id": "cs_test_...",
      "booking_id": "booking_20240320123456_John_Doe",
      "payment_url": "https://checkout.stripe.com/..."
    }
  }
  ```

### Create Payment Link
- **Method**: POST
- **Endpoint**: `/create-payment-link`
- **Description**: Create a pending booking and return a Stripe Payment Link
- **Request Body**: Same as Create Booking
- **Response**:
  ```json
  {
    "payment_link": "https://buy.stripe.com/...",
    "booking_id": "booking_20240320123456_John_Doe",
    "message": "Please complete your payment using the provided link to confirm your piano tuning on Wednesday, March 20, 2024 at 10:00. Your booking will be confirmed once payment is received."
  }
  ```

### Confirm Booking
- **Method**: POST
- **Endpoint**: `/confirm-booking`
- **Description**: Confirm a booking after payment
- **Request Body**:
  ```json
  {
    "booking_id": "booking_20240320123456_John_Doe"
  }
  ```

### Direct Booking
- **Method**: POST
- **Endpoint**: `/direct-booking`
- **Description**: Create a booking directly without payment (for testing)
- **Request Body**: Same as Create Payment Link
- **Response**:
  ```json
  {
    "message": "Booking created successfully"
  }
  ```

### Stripe Webhook
- **Method**: POST
- **Endpoint**: `/webhook`
- **Description**: Handle Stripe webhook events for payment confirmation
- **Request Body**: Stripe webhook event data
- **Response**: 200 OK

## Integration with Agent

The booking system is designed to work with an agent (like Monty) that can:

1. Check slot availability using the `/check-availability` endpoint
2. Collect customer details (name, email, phone, address)
3. Create a booking using the `/create-booking` endpoint
4. Send the payment link to the customer
5. Once payment is confirmed via the webhook, the booking is automatically created in the calendar

### Agent Workflow Example

1. **Check Availability**:
   - Ask customer for their postcode
   - Use the `/check-availability` endpoint to find available slots
   - Present available dates and times to the customer

2. **Collect Customer Details**:
   - Ask for the customer's name
   - Ask for their address
   - Ask for their phone number
   - Confirm all details with the customer

3. **Create Booking**:
   - Use the `/create-booking` endpoint with all collected details
   - The system will validate the slot is still available
   - A booking will be created and a payment link will be generated
   - Send the payment link to the customer
   - Explain that the booking will be confirmed once payment is received

4. **Confirm Booking**:
   - After payment is received, the system will automatically create the booking in the calendar
   - If needed, you can use the `/confirm-booking` endpoint with the booking ID
   - The customer will receive a confirmation email if they provided an email during payment

### Important Notes for Agents

- **Email is optional** - The system will work without an email address, and Stripe will collect it during payment if needed
- **Always provide the payment link to the customer** - The booking is not confirmed until payment is received
- **Don't create multiple bookings for the same slot** - Check availability before creating a new booking
- **If the customer doesn't complete payment, the slot remains available** - You can create a new booking for another customer

This approach simplifies the payment flow and provides a more reliable experience for customers.

## Testing

For testing, use Stripe's test card numbers:
- 4242 4242 4242 4242 (successful payment)
- 4000 0000 0000 9995 (declined payment)

## Production Deployment

Before going live:
1. Switch to Stripe live API keys
2. Set up proper error handling and logging
3. Implement a database for storing pending bookings
4. Add email notifications for successful bookings
5. Set up SSL for secure connections

## Files

- `mcp_booking_server.py`: Main server code with Flask routes and Stripe integration
- `payment.js`: Frontend JavaScript for handling payments
- `booking_form.html`: HTML form for collecting booking details
- `credentials/service-account-key.json`: Google Calendar API credentials 