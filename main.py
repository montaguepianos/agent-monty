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
        # First, return an intermediate message for the user
        intermediate_message = "Got it, thanks! Please give me a little bit of time to check the calendar. Lee has got me doing a hundred things, like checking your post code is close enough to us, then checking the next 30 days in the diary. The suggested appointments will also need to be close enough to any other booked tunings so that our piano tuner doesn't need a helicopter or time machine to get there in time... give me just a few more moments and I'll be right with you!"
        
        print(f"Checking availability for postcode: {postcode}")
        
        # Try up to 3 times with increasing timeouts
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            timeout = 30 * attempt  # Increase timeout with each retry
            try:
                print(f"Attempt {attempt} of {max_retries} with timeout {timeout}s")
                print(f"Making request to: https://monty-mcp.onrender.com/check-availability")
                print(f"Request payload: {{'postcode': '{postcode}'}}")
                
                # Create a requests session to control exactly how the request is made
                session = requests.Session()
                
                # Explicitly set the method to POST
                req = requests.Request(
                    'POST',
                    'https://monty-mcp.onrender.com/check-availability',
                    json={'postcode': postcode},
                    headers={'Content-Type': 'application/json'}
                )
                prepared_req = session.prepare_request(req)
                
                # Log the prepared request for debugging
                print(f"Request method: {prepared_req.method}")
                print(f"Request headers: {prepared_req.headers}")
                
                # Make the request with the session
                response = session.send(prepared_req, timeout=timeout)
                
                print(f"Response status code: {response.status_code}")
                print(f"Response headers: {response.headers}")
                
                if response.content:
                    try:
                        print(f"Response content (first 200 chars): {response.content[:200]}")
                    except:
                        print("Could not display response content")
                
                # If successful, process the response
                if response.status_code == 200:
                    try:
                        data = response.json()
                        slots = data.get('available_slots', [])
                        total_slots = data.get('total_slots', 0)
                        
                        print(f"Successfully parsed response. Found {total_slots} slots.")
                        
                        if not slots:
                            return "I couldn't find any available slots that meet our distance criteria. Please call Lee on 01442 876131 to discuss your booking."
                        
                        # Format the slots into a readable message
                        slot_list = []
                        for i, slot in enumerate(slots, 1):
                            try:
                                # Ensure we're working with naive datetime objects
                                date = datetime.strptime(slot['date'], '%Y-%m-%d')
                                formatted_date = date.strftime('%A, %B %d')
                                slot_list.append(f"{i}. {formatted_date} at {slot['time']}")
                            except Exception as date_err:
                                print(f"Error formatting date: {date_err}")
                                # Fallback to using the date string directly
                                slot_list.append(f"{i}. {slot['date']} at {slot['time']}")
                        
                        message = (
                            f"Thank you for your patience! I found {total_slots} suitable tuning slots:\n\n" +
                            "\n".join(slot_list) +
                            "\n\nWould any of these times work for you? If not, I can suggest more options."
                        )
                        return message
                    except json.JSONDecodeError as json_err:
                        print(f"JSON decode error: {json_err}")
                        print(f"Full response content: {response.content}")
                        # Continue to the next retry attempt
                
                elif response.status_code == 400:
                    try:
                        data = response.json()
                        if 'message' in data:
                            return data['message']
                        return "I couldn't find any suitable slots. Please call Lee on 01442 876131 to discuss your booking."
                    except json.JSONDecodeError as json_err:
                        print(f"JSON decode error on 400 response: {json_err}")
                        # Continue to the next retry attempt
                    
                # Only if we've reached the last attempt and haven't returned yet
                if attempt == max_retries:
                    print(f"All {max_retries} attempts failed")
                    break
                    
            except requests.exceptions.Timeout:
                print(f"Request timed out after {timeout} seconds on attempt {attempt}")
                if attempt == max_retries:
                    print("Max retries reached with timeout errors")
                    break
                continue
                
            except requests.exceptions.RequestException as req_err:
                print(f"Request exception on attempt {attempt}: {req_err}")
                if attempt == max_retries:
                    print("Max retries reached with request exceptions")
                    break
                continue
        
        # If we get here, all attempts failed or returned unexpected results
        return "I'm sorry, I'm currently having trouble accessing our booking system. Please call Lee directly on 01442 876131 to check availability and book your piano tuning appointment."
            
    except Exception as e:
        print(f"Error checking availability: {type(e).__name__}: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
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
    print(f"DEBUG: book_piano_tuning tool called.")
    try:
        print(f"\nAttempting to book tuning with data:")
        print(f"Date: {date}")
        print(f"Time: {time}")
        print(f"Customer: {customer_name}")
        print(f"Address: {address}")
        print(f"Phone: {phone}")
        
        # Check if date is already in YYYY-MM-DD format
        try:
            # Ensure we're working with naive datetime objects
            parsed_date = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date
        except ValueError:
            try:
                # Try to parse the date in the format "Monday, January 1"
                # Replace missing year with current year
                current_year = datetime.now().year
                # Try to handle different date formats
                if ',' in date:
                    # Format like "Monday, January 1"
                    parsed_date = datetime.strptime(date, '%A, %B %d')
                    parsed_date = parsed_date.replace(year=current_year)
                else:
                    # Try other common formats
                    date_formats = ['%B %d', '%d %B', '%d/%m', '%m/%d']
                    parsed_date = None
                    
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(date, fmt)
                            parsed_date = parsed_date.replace(year=current_year)
                            break
                        except ValueError:
                            continue
                
                if parsed_date is None:
                    raise ValueError(f"Could not parse date: {date}")
                
                formatted_date = parsed_date.strftime('%Y-%m-%d')
            except ValueError as e:
                print(f"Error parsing date in tool: {e}")
                return "Sorry, the date format was unclear. Please provide the date as shown in the available slots."
        
        # Make request to booking server with retry mechanism
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            timeout = 30 * attempt  # Increase timeout with each retry
            print(f"\nMaking request to booking server (attempt {attempt}/{max_retries}, timeout {timeout}s)...")
            print(f"URL: https://monty-mcp.onrender.com/create-booking")
            print(f"Request payload: {{'date': '{formatted_date}', 'time': '{time}', 'customer_name': '{customer_name}', 'address': '{address}', 'phone': '{phone}'}}")
            
            try:
                # Create a requests session to control exactly how the request is made
                session = requests.Session()
                
                # Explicitly set the method to POST
                req = requests.Request(
                    'POST',
                    'https://monty-mcp.onrender.com/create-booking',
                    json={
                        'date': formatted_date, 
                        'time': time,
                        'customer_name': customer_name,
                        'address': address,
                        'phone': phone
                    },
                    headers={'Content-Type': 'application/json'}
                )
                prepared_req = session.prepare_request(req)
                
                # Log the prepared request for debugging
                print(f"Request method: {prepared_req.method}")
                print(f"Request headers: {prepared_req.headers}")
                
                # Make the request with the session
                response = session.send(prepared_req, timeout=timeout)
                
                print(f"Response status code: {response.status_code}")
                print(f"Response headers: {response.headers}")
                
                if response.content:
                    try:
                        print(f"Response content (first 200 chars): {response.content[:200]}")
                    except:
                        print("Could not display response content")
                
                # Process the response if we got one
                try:
                    data = response.json()
                    # Prioritize error message if status is not OK
                    if not response.ok:
                        error_msg = data.get('error') or data.get('message') or f"Booking failed (status {response.status_code})"
                        print(f"DEBUG: Tool returning error message: {error_msg}")
                        return error_msg
                    
                    # If OK, return the message
                    message_from_server = data.get('message')
                    if message_from_server:
                        print(f"DEBUG: Tool returning success message: {message_from_server}")
                        return message_from_server
                    else:
                        # Fallback success message if server message missing
                        print(f"DEBUG: Tool returning generic success message (server message missing).")
                        return f"Booking confirmed for {formatted_date} at {time}."
                except json.JSONDecodeError as json_err:
                    print(f"JSON decode error on attempt {attempt}: {json_err}")
                    print(f"Full response content: {response.content}")
                    # Only return error on last attempt
                    if attempt == max_retries:
                        return f"Booking system response was unclear. Please call Lee on 01442 876131 to confirm your booking."
                    continue
                    
            except requests.exceptions.Timeout:
                print(f"Request timed out after {timeout}s on attempt {attempt}")
                if attempt == max_retries:
                    print("Max retries reached with timeout")
                    break
                continue
                
            except requests.exceptions.RequestException as req_err:
                print(f"Request exception on attempt {attempt}: {req_err}")
                if attempt == max_retries:
                    print("Max retries reached with request exceptions")
                    break
                continue
        
        # If we get here, all attempts failed
        # Return a friendly message asking the user to call instead
        formatted_date_str = parsed_date.strftime("%A, %B %d") if 'parsed_date' in locals() else date
        return (
            f"I'm sorry, I'm having trouble connecting to our booking system at the moment. "
            f"Please call Lee directly on 01442 876131 to book your piano tuning appointment."
        )

    except Exception as e:
        print(f"Error in book_piano_tuning tool processing: {type(e).__name__}: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return ("I apologize, but an unexpected error occurred during the booking process. "
                "Please call Lee on 01442 876131 to book your appointment directly.")

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
    data = request.get_json()
    question = data.get('message', '')
    session_id = data.get('session_id', 'default')
    
    try:
        # Get or initialize conversation history for this session
        if session_id not in conversation_history:
            conversation_history[session_id] = {
                'last_agent': triage_agent,
                'conversation': []
            }
        
        # Get the last agent and conversation history
        last_agent = conversation_history[session_id]['last_agent']
        conversation = conversation_history[session_id]['conversation']
        
        print(f"Processing question with agent: {last_agent.name}")
        
        # If this is a follow-up question, use the last agent and include conversation history
        if conversation:
            input_list = conversation + [{"role": "user", "content": question}]
            try:
                print(f"Running agent with input: {input_list[-1]}")
                result = asyncio.run(Runner.run(last_agent, input_list))
                print(f"Agent run completed successfully")
            except Exception as e:
                print(f"Error running agent with conversation history: {e}")
                print(f"Agent error type: {type(e).__name__}")
                import traceback
                print(f"Agent error traceback: {traceback.format_exc()}")
                
                if "not found" in str(e):
                    print("Invalid message reference – clearing history and retrying.")
                    conversation_history[session_id] = {
                        'last_agent': triage_agent,
                        'conversation': []
                    }
                    try:
                        result = asyncio.run(Runner.run(triage_agent, question))
                    except Exception as retry_err:
                        print(f"Error on retry after clearing history: {retry_err}")
                        print(f"Retry error traceback: {traceback.format_exc()}")
                        raise retry_err
                else:
                    raise e
            
            # If the last agent handed off to triage, ensure we use the appropriate specialist
            if result._last_agent == triage_agent and question:
                try:
                    result = asyncio.run(Runner.run(triage_agent, question))
                except Exception as triage_err:
                    print(f"Error running triage agent: {triage_err}")
                    raise triage_err
        else:
            # For new questions, start with the triage agent
            try:
                result = asyncio.run(Runner.run(triage_agent, question))
            except Exception as new_q_err:
                print(f"Error running triage agent for new question: {new_q_err}")
                raise new_q_err
        
        print(f"Agent response: {result.final_output}")
        final_message_text = result.final_output # Use agent's text response directly
        
        # Update conversation history
        conversation_history[session_id]['conversation'] = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in result.to_input_list()
            if "role" in msg and "content" in msg
        ]
        conversation_history[session_id]['last_agent'] = result._last_agent

        # Generate audio response using final_message_text
        try:
            current_agent = result._last_agent
            voice_settings = AGENT_VOICE_SETTINGS.get(current_agent.name)
            hex_audio = None
            audio_data = None

            if voice_settings:
                if voice_settings.provider == "elevenlabs":
                    if elevenlabs_client:
                         try:
                            # Use ElevenLabs
                            speech_response = elevenlabs_client.text_to_speech.convert(
                                voice_id=voice_settings.voice_id,
                                output_format="mp3_44100_128",
                                text=final_message_text, 
                                model_id=voice_settings.model
                            )
                            audio_data = b''.join(speech_response)
                         except Exception as e:
                             print(f"ERROR in ElevenLabs API call: {str(e)}. Falling back to OpenAI.")
                             # Fallback needed here if you want audio on error
                             pass # Or set audio_data to None/handle error
                    else:
                        print("Warning: ElevenLabs client not available.")
                        # Fallback needed if you want audio
                else:
                    # Use OpenAI
                    speech_response = client.audio.speech.create(
                        model=voice_settings.model,
                        voice=voice_settings.voice,
                        input=final_message_text, 
                        instructions=voice_settings.instructions
                    )
                    audio_data = speech_response.content
                
                if audio_data:
                    hex_audio = audio_data.hex()
            
            # Construct the JSON response
            response_data = {
                'response': final_message_text, 
                'agent': current_agent.name,
                'audio': hex_audio
            }
                
            response = jsonify(response_data)
            print("Response created successfully (simple text + audio)")
            return response

        except Exception as e:
            print(f"Error generating audio or constructing final response: {str(e)}")
            # Fallback response without audio if error occurs
            return jsonify({
                'response': final_message_text,
                'agent': current_agent.name if 'current_agent' in locals() else 'Unknown Agent',
                'audio': None
            })
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Check if postcode is in question and this might be a tuning request
        contains_postcode = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', question, re.IGNORECASE)
        contains_tuning_keywords = re.search(r'(piano|tuning|tune|appointment)', question, re.IGNORECASE)
        
        if contains_postcode or contains_tuning_keywords:
            # Provide straightforward error message for tuning inquiries
            error_msg = (
                "I'm sorry, I'm having technical difficulties accessing our booking system right now. "
                "Please call Lee directly on 01442 876131 to check availability and book your piano tuning appointment."
            )
            
            return jsonify({
                'response': error_msg,
                'agent': 'Monty Agent',
                'audio': None
            })
        else:
            # Generic error for non-tuning requests
            return jsonify({
                'response': "I'm sorry, I encountered a temporary technical issue. Could you please try again or rephrase your question?",
                'agent': 'Monty Agent',
                'audio': None
            }), 500

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