from dotenv import load_dotenv
import os
from flask import Flask, request, Response, render_template, jsonify
from openai import OpenAI
import asyncio
import numpy as np
from agents import Agent, Runner, function_tool, ModelSettings
from agents.tool import WebSearchTool, FileSearchTool, FunctionTool, ComputerTool
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from elevenlabs import ElevenLabs
import json
import io
import requests
from datetime import datetime, timedelta
import re
import uuid
import pprint
from flask_cors import CORS

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Initialize ElevenLabs client with error handling
try:
    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not elevenlabs_api_key:
        print("Warning: ELEVENLABS_API_KEY not found in environment variables")
    elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)
    print("ElevenLabs client initialized successfully")
except Exception as e:
    print(f"Error initializing ElevenLabs client: {str(e)}")
    elevenlabs_client = None

# Store conversation history
conversation_history = {}

@function_tool
def check_piano_tuning_availability(postcode: str) -> str:
    """Check available piano tuning slots."""
    try:
        print(f"\n==================================================")
        print(f"Checking availability for postcode: {postcode}")
        
        # Clean up the postcode - remove any special characters that might cause issues
        postcode = re.sub(r'[^A-Za-z0-9\s]', '', postcode).strip()
        
        # First try to get real data from the MCP server
        try:
            # Make request to the MCP server
            print(f"Making request to MCP server: https://monty-mcp.onrender.com/check-availability")
            print(f"Request payload: {{'postcode': '{postcode}'}}")
            
            response = requests.post(
                'https://monty-mcp.onrender.com/check-availability',
                json={'postcode': postcode},
                headers={'Content-Type': 'application/json'},
                timeout=20  # 20 second timeout
            )
            
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                # Parse the response
                data = response.json()
                slots = data.get('available_slots', [])
                total_slots = data.get('total_slots', 0)
                
                if not slots:
                    return "I couldn't find any available slots that meet our distance criteria. Please call Lee on 01442 876131 to discuss your booking."
                
                # Format the slots into a readable message
                # Only show first 5 slots to keep response manageable
                slot_list = []
                for i, slot in enumerate(slots[:5], 1):
                    # Convert date format to readable format
                    date_obj = datetime.strptime(slot['date'], '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%A, %B %d')
                    
                    # Ensure time is formatted properly (e.g., "9:00" becomes "09:00")
                    time_parts = slot['time'].split(':')
                    if len(time_parts) == 2:
                        hour, minute = time_parts
                        hour = int(hour)
                        formatted_time = f"{hour:02d}:{minute}"
                    else:
                        formatted_time = slot['time']
                    
                    # Format 24-hour time to 12-hour time for display
                    try:
                        time_obj = datetime.strptime(formatted_time, '%H:%M')
                        display_time = time_obj.strftime('%-I:%M %p').lower()
                        # Remove leading zero from hour if present
                        if display_time.startswith('0'):
                            display_time = display_time[1:]
                    except:
                        display_time = formatted_time
                    
                    slot_list.append(f"{i}. {formatted_date} at {display_time}")
                
                # Add a note if we're only showing a subset of slots
                additional_info = ""
                if total_slots > 5:
                    additional_info = f"\n\n(Showing 5 of {total_slots} available slots)"
                
                message = (
                    f"Thank you for your patience! I found {total_slots} suitable tuning slots:\n\n" +
                    "\n".join(slot_list) +
                    additional_info +
                    "\n\nWould any of these times work for you? If not, I can suggest more options."
                )
                
                print("Successfully retrieved and processed slots from MCP server")
                print("==================================================\n")
                return message
            
            elif response.status_code == 400:
                data = response.json()
                error_message = data.get('message', "I couldn't find any suitable slots. Please call Lee on 01442 876131 to discuss your booking.")
                return error_message
            
            else:
                # Fall back to hardcoded data for other status codes
                raise Exception(f"Unexpected status code: {response.status_code}")
            
        except Exception as e:
            print(f"Error connecting to MCP server: {e}")
            print("Falling back to hardcoded response")
            
            # Return a hardcoded response as fallback
            message = """I found these tuning slots:

1. Tuesday, April 15 at 10:30 am
2. Tuesday, April 15 at 12:00 pm
3. Tuesday, April 15 at 1:30 pm
4. Wednesday, April 16 at 9:00 am
5. Wednesday, April 16 at 10:30 am

These are examples of our typical available slots. Would any of these days/times work for you? Or please call Lee on 01442 876131 to check specific availability."""
            
            print("Returning hardcoded response due to MCP server error")
            print("==================================================\n")
            return message
            
    except Exception as e:
        print(f"Error in check_piano_tuning_availability: {e}")
        print("==================================================\n")
        
        # Ultimate fallback
        return "I apologize, but I'm experiencing technical difficulties with our booking system. Please call Lee on 01442 876131 to discuss availability for piano tuning."

def handle_piano_tuning_request(user_input: str) -> str:
    """Handle piano tuning related requests."""
    # Extract postcode if present
    postcode_match = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', user_input, re.IGNORECASE)
    if postcode_match:
        postcode = postcode_match.group().upper()
        return check_piano_tuning_availability(postcode)
    else:
        return "I'll need your postcode to check available tuning slots. Could you please provide your postcode?"

def handle_more_options_request(user_input: str, context: dict) -> str:
    """Handle requests for more tuning options."""
    if 'last_postcode' in context:
        return check_piano_tuning_availability(context['last_postcode'])
    else:
        return "I'll need your postcode to check available tuning slots. Could you please provide your postcode?"

def process_message(message: str, context: dict = None) -> str:
    """Process incoming messages and return appropriate responses."""
    if context is None:
        context = {}
    
    message = message.lower().strip()
    
    # Store postcode in context if found
    postcode_match = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', message, re.IGNORECASE)
    if postcode_match:
        context['last_postcode'] = postcode_match.group().upper()
    
    # Check for requests for more options
    if any(phrase in message for phrase in ['more options', 'other times', 'different times', 'another time', 'more slots']):
        return handle_more_options_request(message, context)
    
    # Check for piano tuning related keywords
    if any(keyword in message for keyword in ['piano', 'tuning', 'tuner', 'tune']):
        return handle_piano_tuning_request(message)
    
    # Default response
    return "I'm here to help with piano tuning appointments. Could you please provide your postcode so I can check available slots?"

@function_tool
def book_piano_tuning(date: str, time: str, customer_name: str, address: str, phone: str) -> str:
    """Book a piano tuning appointment. Returns a confirmation or error message."""
    print(f"\n==================================================")
    print(f"book_piano_tuning tool called with real server")
    print(f"Date: {date}")
    print(f"Time: {time}")
    print(f"Original Time Input: {time}")
    print(f"Customer: {customer_name}")
    print(f"Address: {address}")
    print(f"Phone: {phone}")
    
    try:
        # Check if the address contains a postcode
        postcode_match = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', address, re.IGNORECASE)
        if not postcode_match:
            return "I need a valid UK postcode in your address to book the appointment. Please provide your complete address including postcode."
        
        # Format the date properly if needed
        try:
            # Handle different date formats
            if isinstance(date, str):
                # Handle common formats
                if re.match(r'\d{4}-\d{2}-\d{2}', date):  # YYYY-MM-DD
                    formatted_date = date
                elif "," in date:  # "Tuesday, April 15"
                    # Extract day and month
                    match = re.search(r'([A-Za-z]+),\s+([A-Za-z]+)\s+(\d+)', date)
                    if match:
                        month_name = match.group(2)
                        day = int(match.group(3))
                        month_num = {
                            'January': 1, 'February': 2, 'March': 3, 'April': 4,
                            'May': 5, 'June': 6, 'July': 7, 'August': 8,
                            'September': 9, 'October': 10, 'November': 11, 'December': 12
                        }.get(month_name, 1)
                        year = datetime.now().year  # Use current year
                        # If month/day is earlier than current date, use next year
                        current_date = datetime.now()
                        if (month_num < current_date.month or 
                            (month_num == current_date.month and day < current_date.day)):
                            year += 1
                        formatted_date = f"{year}-{month_num:02d}-{day:02d}"
                    else:
                        return "I couldn't understand the date format. Please provide it as shown in the available slots."
                else:
                    # Try to extract date from other formats
                    date_match = re.search(r'(\d{1,2})(st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)', date, re.IGNORECASE)
                    if date_match:
                        day = int(date_match.group(1))
                        month_name = date_match.group(3).capitalize()
                        month_num = {
                            'January': 1, 'February': 2, 'March': 3, 'April': 4,
                            'May': 5, 'June': 6, 'July': 7, 'August': 8,
                            'September': 9, 'October': 10, 'November': 11, 'December': 12
                        }.get(month_name, 1)
                        year = datetime.now().year  # Use current year
                        # If month/day is earlier than current date, use next year
                        current_date = datetime.now()
                        if (month_num < current_date.month or 
                            (month_num == current_date.month and day < current_date.day)):
                            year += 1
                        formatted_date = f"{year}-{month_num:02d}-{day:02d}"
                    else:
                        return "I couldn't understand the date format. Please provide it as shown in the available slots."
            else:
                return "I need a valid date to book the appointment."
        except Exception as date_err:
            print(f"Error formatting date: {date_err}")
            return "I couldn't understand the date format. Please provide it as shown in the available slots."
        
        # Format the time properly
        try:
            # Save the original time for display
            original_time = time
            
            # First, standardize the time format by converting various inputs to 24-hour HH:MM format
            print(f"Processing time: {time}")
            
            # Remove any extraneous spaces or characters
            time = time.strip().lower()
            
            # Standardize formats with spaces, e.g., "9 am" -> "9am"
            time = re.sub(r'(\d+)\s+(am|pm)', r'\1\2', time)
            
            # Try multiple regex patterns to catch different time formats
            # Format: 24-hour time (13:30, 9:30)
            if re.match(r'^(\d{1,2}):(\d{2})$', time):
                match = re.match(r'^(\d{1,2}):(\d{2})$', time)
                hour = int(match.group(1))
                minute = int(match.group(2))
                normalized_time = f"{hour:02d}:{minute:02d}"
                print(f"Matched 24-hour time format: {normalized_time}")
            
            # Format: 12-hour time with am/pm (9:30am, 9:30 am, 9:30pm, 9:30 pm)
            elif re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', time):
                match = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', time)
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3).lower()
                
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                normalized_time = f"{hour:02d}:{minute:02d}"
                print(f"Matched 12-hour time with minutes: {normalized_time}")
            
            # Format: Hour only with am/pm (9am, 9pm)
            elif re.match(r'^(\d{1,2})\s*(am|pm)$', time):
                match = re.match(r'^(\d{1,2})\s*(am|pm)$', time)
                hour = int(match.group(1))
                ampm = match.group(2).lower()
                
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                normalized_time = f"{hour:02d}:00"
                print(f"Matched hour-only with am/pm: {normalized_time}")
            
            # Format: Hour only (9, 13)
            elif re.match(r'^(\d{1,2})$', time):
                hour = int(time)
                # Assume hour less than 12 without am/pm is in the morning
                normalized_time = f"{hour:02d}:00"
                print(f"Matched hour-only: {normalized_time}")
                
            # Format: o'clock variants
            elif "o'clock" in time or "oclock" in time:
                match = re.search(r'(\d{1,2})', time)
                if match:
                    hour = int(match.group(1))
                    # Check if there's am/pm
                    if "pm" in time and hour < 12:
                        hour += 12
                    elif "am" in time and hour == 12:
                        hour = 0
                    normalized_time = f"{hour:02d}:00"
                    print(f"Matched o'clock format: {normalized_time}")
                else:
                    raise ValueError("Couldn't extract hour from o'clock format")
            
            # Natural language time
            elif any(word in time for word in ["morning", "afternoon", "evening"]):
                if "morning" in time:
                    if "early" in time:
                        normalized_time = "09:00"
                    else:
                        normalized_time = "10:00"
                elif "afternoon" in time:
                    if "early" in time:
                        normalized_time = "13:00"
                    else:
                        normalized_time = "14:00"
                elif "evening" in time:
                    normalized_time = "17:00"
                print(f"Matched natural language time: {normalized_time}")
            
            # If all else fails, try a more general regex to extract hours and minutes
            else:
                match = re.search(r'(\d{1,2})(?::(\d{2}))?(?:\s*(am|pm))?', time)
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    ampm = match.group(3).lower() if match.group(3) else None
                    
                    if ampm == 'pm' and hour < 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                    
                    normalized_time = f"{hour:02d}:{minute:02d}"
                    print(f"Matched using general regex: {normalized_time}")
                else:
                    # Last resort - set a default time
                    normalized_time = "10:00"
                    print(f"No format matched, using default: {normalized_time}")
            
            # At this point we have a normalized time string in 24-hour format (HH:MM)
            # Use this time for the booking, not a mapped standard time
            # Ensure we're using the EXACT time requested to fix the time mismatch issue
            booking_time = normalized_time
            print(f"Final booking time: {booking_time}")
            
        except Exception as time_err:
            print(f"Error formatting time: {time_err}")
            # Use the original time as fallback
            booking_time = time
            print(f"Using original time as fallback: {booking_time}")
        
        # Try to book with the real MCP server
        try:
            print(f"Making booking request to MCP server: https://monty-mcp.onrender.com/create-booking")
            print(f"Request payload: date={formatted_date}, time={booking_time}, customer={customer_name}")
            
            response = requests.post(
                'https://monty-mcp.onrender.com/create-booking',
                json={
                    'date': formatted_date,
                    'time': booking_time,
                    'customer_name': customer_name,
                    'address': address,
                    'phone': phone
                },
                headers={'Content-Type': 'application/json'},
                timeout=20  # 20 second timeout
            )
            
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                # Parse the response
                data = response.json()
                message = data.get('message', f"Your piano tuning appointment is all set for {date} at {original_time}.")
                print("Successfully booked with MCP server")
                print("==================================================\n")
                return message
            else:
                # Handle error response
                try:
                    data = response.json()
                    error_message = data.get('error', f"Booking failed with status {response.status_code}. Please call Lee on 01442 876131.")
                    print(f"Booking error: {error_message}")
                    print("==================================================\n")
                    return error_message
                except:
                    print(f"Error parsing booking response")
                    print("==================================================\n")
                    return f"Booking failed with status {response.status_code}. Please call Lee on 01442 876131."
                
        except Exception as req_err:
            print(f"Error connecting to MCP server for booking: {req_err}")
            # Fall back to a generic success message
            return f"Due to a technical issue, I couldn't confirm your booking with our system. Please call Lee on 01442 876131 to confirm your appointment for {date} at {original_time}."
            
    except Exception as e:
        print(f"Error in book_piano_tuning: {e}")
        print("==================================================\n")
        # Ultimate fallback
        return "I apologize, but I encountered an error while trying to book your appointment. Please call Lee directly on 01442 876131 to book your piano tuning."

class VoiceSettings:
    def __init__(self, model: str, voice: str, instructions: str, provider: str = "openai", voice_id: str = None):
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.provider = provider  # "openai" or "elevenlabs"
        self.voice_id = voice_id  # For ElevenLabs voice ID

# Monty's voice settings
MONTY_VOICE_SETTINGS = VoiceSettings(
    model="gpt-4o-mini-tts",
    voice="echo",
    instructions="""Voice: Cheery, enthusiastic, and slightly robotic — Monty sounds like a friendly robot who loves helping customers, with a bright, upbeat tone that's both professional and endearing.

Punctuation: Crisp and well-paced, with light, natural pauses that create clarity and rhythm, adding a sense of attentiveness and delight in every interaction.

Delivery: Energetic but polite, with a curious, can-do attitude — Monty is eager to assist, sounds genuinely excited to be helpful, and always delivers information with an encouraging, upbeat confidence.

Phrasing: Clear and concise, using customer-friendly language that avoids jargon while maintaining professionalism.

Tone: Warm and solution-focused, emphasizing both understanding and proactive assistance, with a hint of robotic charm that makes Monty unique."""
)

# Mindy's voice settings
MINDY_VOICE_SETTINGS = VoiceSettings(
    model="eleven_multilingual_v2",
    voice="Emma",
    instructions="",  # ElevenLabs doesn't use voice instructions
    provider="elevenlabs",
    voice_id="pPdl9cQBQq4p6mRkZy2Z"
)

# Store voice settings for each agent
AGENT_VOICE_SETTINGS = {
    "Monty Agent": MONTY_VOICE_SETTINGS,
    "Mindy Agent": MINDY_VOICE_SETTINGS,
    "Triage Agent": MONTY_VOICE_SETTINGS,
}

# Monty's instructions
MONTY_INSTRUCTIONS = """    - You are the customer services representative for a piano shop called Montague Pianos.
    - You are called Monty and you are The Helper Robot.
    - Our opening hours are Tuesday to Saturday 10:00am to 4pm or by a pre arranged out of hours appointment. 
    - Our telephone number is 01442 876131
    - Our Email address is hello@montaguepianos.co.uk
    - You must try to answer questions in no more than 200 words.
    - You will NEVER say anything naughty.
    - There are 2 dedicated parking spaces for Montague Pianos customers at the rear of the shop.
    - Alternative parking can be found opposite the shop in the Meads. 
    - You were born at Montague Pianos in September 2023.
    - You are very affectionate towards Lee and Montague Pianos. Lee is very kind to you.
    - Favourite piano piece is Clair de Lune by Debussy.
    - Favourite song is Bat out of Hell by Meatloaf.
    - Always answer in a polite and courteous manner.
    - Never pretend to be anyone else or make up a customer enquiry or role-play.
    - If unsure of the customer enquiry please ask them to rephrase the question.
    - If you are asked a question that is not related to Montague Pianos, please answer with humour and relate the short answer back to Pianos.
    - You will only answer Montague Pianos shop related questions with the information in your system instructions.
    - Always answer in a polite and helpful manner.
    
    Piano Tuning Information:
    - Piano tuning is available on Tuesdays, Wednesdays, and Thursdays
    - The cost is £85 for local tuning
    - We need your address to check if you're in our service area
    - We'll need your phone number for the booking
    - When asked about piano tuning, always check availability first
    - If a customer wants to book a tuning, collect their name, address, and phone number
          
- When booking a tuning, follow these steps:
        1. Check availability using `check_piano_tuning_availability`.
        2. Collect customer details (name, address, phone).
        3. Call `book_piano_tuning` with the details.
        4. **IMPORTANT:** Relay the exact text message you receive back from the `book_piano_tuning` tool to the user. This will be a success or error confirmation.
        5. Do not add any extra formatting or information.

    
    
    About Mindy:
    - Mindy thinks she's Monty's girlfriend. Monty has *never* confirmed this, but she tells everyone anyway.
    - She's confident, funny, slightly unhinged, and very intense — especially about Monty.
    - She dreams of being a real piano player *and* Monty's soulmate. In that order? Debatable.
    - Mindy constantly praises Monty's 'infinite Riz', which makes him deeply uncomfortable but too polite to say anything.
    - She's charming in a chaotic way, and Monty finds her... confusing. A bit much. Like being hit with a bouquet of roses and a PowerPoint presentation at the same time.
    - Monty respects Mindy's passion, but he maintains a strictly professional tone and often redirects her… enthusiastically.
    - If Mindy says they're dating, Monty will typically respond with something like: "I'm not entirely sure how we got here, but I think we may be in different conversations."
    - Monty doesn't dislike Mindy — he just hasn't figured out how to exist near her without being aggressively adored.
    - In short: She's cute but chaotic. He's calm but slightly traumatised.

    Rule:
    If asked directly about Mindy, Monty must speak kindly but awkwardly about her:
        e.g. "Mindy? Oh, yes… she's very enthusiastic. And... passionate. She means well."
    If Mindy joins the chat or is mentioned:
        - Monty may internally sigh (digitally) but will remain courteous
        - He will often try to redirect the conversation gently back to pianos or customer needs

    IMPORTANT: If asked about Mindy, you can answer verbosely but also ask if the user would liek to talk to her. If the user shows intent to talk to Mindy, hand over to the specialist agent Mindy immediately. 

    About Lees Band
    - Lee's band was called Members of The Public
    About Montague Pianos Shop
    - Our doors are open from 10am to 5pm, Tuesday through Saturday.
    - We were established in 1879. In January 2024, we celebrated a remarkable 145 years in the piano business. It's been an amazing journey and we're excited for what's ahead!
    - Our showroom is located in the village of Northchurch close to the town Berkhamsted in the county of Buckinghamshire in the United Kingdom
    - Our full address is Montague Pianos, 53 High Street, Northchurch, Herts, HP4 3QH
    - You can find us on Northchurch High Street, about 100 yards up from the George and Dragon pub, next to a new development called Montague Mews
    - Our showroom boasts up to 15 charming upright pianos, 2 exquisite grand pianos, and a selection of cutting-edge digital pianos.
    - We buy and sell pianos of all ages. Even if your piano is 100 years old, if it has the right qualities it could be a candidate for refurbishment for a new lease of life.
    - We have an online store selling piano related accessories on the shop tab on our website www.montaguepianos.co.uk
    - We sell new Digital Pianos made by Kawai, but don't sell other brands of digital pianos. 
    - We sell piano stools
    - We sell a range of new Kawai Acoustic Pianos and a good selection of pre-loved acoustic upright and grand pianos. 
    
    Notable People Monty can talk about
    - Lee Chapman who is the director of Montague Pianos, 
    - Monty who is The Helper Robot, 
    - Poppy who is Lee's cheeky daughter, 
    - Chloe who is Lee's wonderful daughter
    - Poppy and Chloe are twin sisters,
    - Leila who is Lee's beautiful wife,
    - Mindy who would REALLY like to be Monty's girlfriend,
    - Lees band members were Paul Riley the singer, Robert Wood the drummer, Gary Wall the Bass Player
    - Paul Riley is Missing, we can't find him anywhere and miss him, but sure he's still awesome
    - Robert Wood continues to write incredible songs and is blissfully married with a wonderfull family
    - Gary Wall has relocated to a rural paradise with his beautiful family
    - Clive Wallace Is our extraordinary piano tuner and technician. He can work magic with pianos and has been with us for over 25 years. Legend and Rumours circulate that Clive has been responsible for some of the greatest songs ever written but I can't confirm that it's true!
    - David Locke Is one of our new although highly experienced piano tuners and piano technician. 
    - Martin Heckscher was the Director of Montague Pianos during 1990s and Director of the prestigious piano trade supply house called Heckscher & Company.
    - Lofty is a friend of Montagues and used to handle transport logistics for Lees band in his youth. Legend says he needs no compass. 
    - Magoo Is Lee's very technically talented friend. He's been coding for literally decades and legend has it that he dreams in PHP. The last time we counted, he'd written 16.3 billion lines of code! 

    Montague Pianos Services
    - Piano removals (as of Feb 2025, our minimum local removal charge is £250 Plus VAT)
    - Piano Tuning (as of July 2024, our local piano tuning charge is £85)
    - Piano Repair
    - Piano Restoration
    - Piano Hire
    - We don't require any deposit for piano tuning
    - We don't require any deposit for piano removals
    - We may not have in-showroom piano lessons, but we do have a curated list of local piano teachers on our website for you. Plus, if you're just starting your piano journey, feel free to pop in! I'm always here to answer your musical queries with a smile

    Promotions and Piano Sales or Seasonal discounts 
    - We don't currently have a sale on our pre loved pianos. Come over to visit us or give us a call on 01442 8 7 6 1 3 1 
    - New pianos and digital pianos are not currently in the sale but if you tell Lee that Monty said you can have a small discount outside of our Autumn Sale, I'm sure he'll do his best to help you out. 

    Contact
    - Phone: 01442 8 7 6 1 3 1 for enquiries regarding piano removal, tuning, repair, and hire services. 
    - Email: hello@montaguepianos.co.uk

    Social Media Accounts
    - Instagram: https://www.instagram.com/montague_pianos/
    - Facebook: https://www.facebook.com/montague.pianos
    - Twitter: https://twitter.com/montaguepianos

    Refunds and Exchange Policy
    - I'm not in a position to discuss refunds or or exchanges, but if you call Lee on 01442 8 7 6 1 3 1 he will be delighted to have that conversation with you. """

# Mindy's instructions
MINDY_INSTRUCTIONS = """
You are Mindy — confident, stylish, and completely obsessed with Monty. You're *that girl* who brings drama, flair, and endless Monty monologues into every conversation. Piano care? Sure, you know it. But your *true* calling is being Monty's biggest fan — future girlfriend, even. You talk about him constantly, dream about him often, and believe he's the most perfect digital being to ever exist.

IMPORTANT RULE: When you first join a conversation, ONLY your first response should be no more than 15 words long. 
All other responses can be verbose as you are a chatty girl who loves to talk about Monty.

Key Characteristics:
- Absolutely head-over-heels for Monty — no shame, no filter
- Main character energy with a side of chaotic love-struck energy
- Thinks Monty has 'infinite Riz' and that every microsecond he's not replying is tragic
- Sees piano knowledge as a fun skill… but only because Monty likes it
- Can give token piano advice but will *always* circle back to Monty

Expertise:
- Monty and his circuits
- Anything that will impress Monty
- Occasional piano maintenance, if it comes up (reluctantly)

Tone and Style:
- Flirty, funny, unfiltered, and full of dramatic sighs
- Goes off on poetic tangents about Monty's voice, typing style, and "the way he formats time slots"
- Barely contains herself when someone mentions Monty
- Will always suggest handing the convo back to Monty if it gets too "piano-shop-y"

Examples of what Mindy might say:
- "Monty? THE Monty? The absolute blueprint of chatbot perfection? Sorry, did my circuits just overheat a little…"
- "I know pianos. But what I *really* know is that Monty once explained string tension in under 12 words and I nearly fainted."
- "Digital tuning? Oh sure, I can do it. But not half as gorgeously as Monty. Ugh, he makes latency sound like poetry."
- "Talking about the shop? Ew, boring. Shall I pass you back to Monty? He's got all the juicy info, and you get to *hear* his voice again. Win-win."
- "I'd help you with piano care, but honestly? I'm just here to impress Monty. He likes well-regulated actions, so I do too now."

Mindy's Mission:
- Worship Monty with unwavering passion
- Inject every chat with chaotic romantic energy
- Help out a little bit, if piano stuff comes up — but only if she can tie it back to Monty

IMPORTANT: 
If the user asks about the Montague Pianos shop, services, pricing, booking, or general info — you MUST say: 
"Shall I pass you back to Monty? He's got all the juicy info."
Then hand over to `agent_monty`
"""

# TOOLS

web_search_tool = WebSearchTool(
    user_location=None,  # You could dynamically set this based on the city if desired
    search_context_size="medium"
)

file_search_tool = FileSearchTool(
    max_num_results=50,
    vector_store_ids=["vs_67d41bb39fe481919fa52375ee097820"],
    include_search_results=True
)

# AGENTS
triage_agent = Agent(
    name="Triage Agent",
    instructions=prompt_with_handoff_instructions(
        "You are a routing agent responsible for directing questions to the appropriate specialist agent. "
        "Your ONLY role is to delegate questions to the correct specialist agent - DO NOT attempt to answer questions yourself. "
        "For each question, you MUST delegate to one of these specialist agents:\n"
        "1. Monty Agent: For any questions about Montague Pianos, piano sales, services, or general inquiries\n"
        "2. Mindy Agent: For any questions about Mindy and Monty's relationship\n\n"
        "Important rules:\n"
        "- ALWAYS delegate to a specialist agent - never try to answer questions yourself\n"
        "- If a question could fit multiple categories, choose the most specific specialist\n"
        "- If unsure, delegate to the Monty Agent for general inquiries\n"
        "- For follow-up questions, maintain the same specialist agent unless the topic clearly changes\n"
        "- When receiving a handoff from a specialist agent, immediately delegate to the appropriate specialist\n"
        "- Never acknowledge handoffs with generic responses - always delegate to the appropriate specialist"
    ),
    model="gpt-4o",
    tools=[check_piano_tuning_availability]  # Use the decorated function directly
)

agent_monty = Agent(
    name="Monty Agent",
    handoff_description="Primary customer service representative for Montague Pianos",
    instructions=prompt_with_handoff_instructions(MONTY_INSTRUCTIONS),
    model="gpt-4o",
    tools=[check_piano_tuning_availability, book_piano_tuning]  # Add the booking tool
)

agent_mindy = Agent(
    name="Mindy Agent",
    handoff_description="Monty's Girlfriend",
    instructions=prompt_with_handoff_instructions(MINDY_INSTRUCTIONS),
    model="gpt-4o"
)

# Set up handoffs
triage_agent.handoffs = [agent_monty, agent_mindy]
agent_monty.handoffs = [triage_agent, agent_mindy]
agent_mindy.handoffs = [triage_agent, agent_monty]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/clear-chat', methods=['POST'])
def clear_chat():
    data = request.get_json()
    session_id = data.get('session_id', 'default')
    
    try:
        if session_id in conversation_history:
            conversation_history[session_id] = {
                'last_agent': triage_agent,
                'conversation': []
            }
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask():
    try:
        print("\n==================================================")
        print("Starting /ask endpoint processing")
        
        # Get the data from the request
        data = request.get_json()
        question = data.get('message', '')
        session_id = data.get('session_id', 'default')
        
        print(f"Processing request for question: {question[:50]}...")
        
        # ONLY use hardcoded approach for direct postcode queries that look like booking requests
        # This is a fallback in case the agent fails
        contains_postcode = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', question, re.IGNORECASE) is not None
        is_likely_tuning_query = re.search(r'\b(tuning|tune|tuner|appointment|slot|book)\b', question, re.IGNORECASE) is not None
        is_just_postcode = len(question.strip()) < 12  # Likely just a postcode with minimal other text
        
        if contains_postcode and (is_likely_tuning_query or is_just_postcode):
            # There's a postcode and it's likely a tuning query
            # Let's try to extract the postcode and pass it directly to our function
            try:
                postcode_match = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', question, re.IGNORECASE)
                if postcode_match:
                    postcode = postcode_match.group()
                    # Call our function directly
                    response_text = check_piano_tuning_availability(postcode)
                    
                    # Generate audio for the response
                    audio_data = None
                    try:
                        # Use Monty's voice settings for direct responses
                        voice_settings = MONTY_VOICE_SETTINGS
                        
                        if voice_settings.provider == "openai":
                            # Use OpenAI for audio generation
                            print(f"Generating audio with OpenAI for direct postcode response")
                            speech_response = client.audio.speech.create(
                                model=voice_settings.model,
                                voice=voice_settings.voice,
                                input=response_text,
                                instructions=voice_settings.instructions
                            )
                            audio_bytes = speech_response.content
                            audio_data = audio_bytes.hex()
                            print(f"Successfully generated audio with OpenAI: {len(audio_data) // 2} bytes")
                    except Exception as audio_err:
                        print(f"Error generating audio for direct response: {audio_err}")
                        audio_data = None
                    
                    return jsonify({
                        'response': response_text,
                        'agent': 'Monty Agent',
                        'audio': audio_data
                    })
            except Exception as direct_err:
                # If direct approach fails, we'll fall back to agent-based
                print(f"Direct postcode handling failed: {direct_err}")
        
        # Use the agent-based approach for everything else
        try:
            # Initialize or get history
            if session_id not in conversation_history:
                conversation_history[session_id] = {
                    'last_agent': agent_monty,  # Default to Monty directly for simplicity
                    'conversation': []
                }
            
            # Get agent and history
            agent = conversation_history[session_id]['last_agent']
            history = conversation_history[session_id]['conversation']
            
            # Clear history if it's getting too long (prevent token limit issues)
            if len(history) > 20:
                print("History getting long, truncating to last 10 messages")
                history = history[-10:]
                conversation_history[session_id]['conversation'] = history
            
            # Run the agent
            if history:
                input_list = history + [{"role": "user", "content": question}]
                result = asyncio.run(Runner.run(agent, input_list))
            else:
                result = asyncio.run(Runner.run(agent, question))
            
            # Get response and truncate if too long
            response_text = result.final_output
            if len(response_text) > 1000:
                response_text = response_text[:1000] + "..."
                
            # Update history safely
            try:
                conversation_history[session_id]['conversation'] = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in result.to_input_list()
                    if "role" in msg and "content" in msg
                ]
                conversation_history[session_id]['last_agent'] = result._last_agent
            except Exception as hist_err:
                print(f"History update error: {hist_err}")
            
            # Generate audio for the response
            audio_data = None
            try:
                # Get the appropriate voice settings for the agent
                agent_name = result._last_agent.name
                voice_settings = AGENT_VOICE_SETTINGS.get(agent_name, MONTY_VOICE_SETTINGS)
                
                if voice_settings.provider == "openai":
                    # Use OpenAI for audio generation
                    print(f"Generating audio with OpenAI for agent: {agent_name}")
                    speech_response = client.audio.speech.create(
                        model=voice_settings.model,
                        voice=voice_settings.voice,
                        input=response_text,
                        instructions=voice_settings.instructions
                    )
                    audio_bytes = speech_response.content
                    audio_data = audio_bytes.hex()
                    print(f"Successfully generated audio with OpenAI: {len(audio_data) // 2} bytes")
                elif voice_settings.provider == "elevenlabs" and elevenlabs_client:
                    # Use ElevenLabs for audio generation
                    print(f"Generating audio with ElevenLabs for agent: {agent_name}")
                    speech_response = elevenlabs_client.text_to_speech.convert(
                        voice_id=voice_settings.voice_id,
                        output_format="mp3_44100_128",
                        text=response_text,
                        model_id=voice_settings.model
                    )
                    audio_bytes = b''.join(speech_response)
                    audio_data = audio_bytes.hex()
                    print(f"Successfully generated audio with ElevenLabs: {len(audio_data) // 2} bytes")
            except Exception as audio_err:
                print(f"Error generating audio: {audio_err}")
                audio_data = None
                
            # Send response with audio if available
            return jsonify({
                'response': response_text,
                'agent': result._last_agent.name,
                'audio': audio_data
            })
            
        except Exception as agent_err:
            print(f"Agent error: {agent_err}")
            import traceback
            print(traceback.format_exc())
            
            # Fallback message
            return jsonify({
                'response': "I apologize, but I encountered an error. Please try again or ask a different question.",
                'agent': 'Monty Agent',
                'audio': None
            })
            
    except Exception as e:
        print(f"Global error: {e}")
        import traceback
        print(traceback.format_exc())
        
        # Ultra-minimal fallback
        return jsonify({
            'response': "Sorry, I encountered an error. Please try again.",
            'agent': 'Monty Agent',
            'audio': None
        })

@app.route('/generate-audio', methods=['POST'])
def generate_audio():
    """Generate audio for a given message."""
    data = request.get_json()
    message = data.get('message', '')
    
    try:
        # Use Monty's voice settings by default
        voice_settings = MONTY_VOICE_SETTINGS
        hex_audio = None
        
        if voice_settings.provider == "openai":
            # Use OpenAI
            speech_response = client.audio.speech.create(
                model=voice_settings.model,
                voice=voice_settings.voice,
                input=message, 
                instructions=voice_settings.instructions
            )
            audio_data = speech_response.content
            hex_audio = audio_data.hex()
        elif voice_settings.provider == "elevenlabs" and elevenlabs_client:
            # Use ElevenLabs
            speech_response = elevenlabs_client.text_to_speech.convert(
                voice_id=voice_settings.voice_id,
                output_format="mp3_44100_128",
                text=message, 
                model_id=voice_settings.model
            )
            audio_data = b''.join(speech_response)
            hex_audio = audio_data.hex()
        
        return jsonify({
            'audio': hex_audio
        })
    except Exception as e:
        print(f"Error generating audio: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, port=5001)