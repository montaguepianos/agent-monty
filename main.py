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

# Load environment variables
load_dotenv()

app = Flask(__name__)
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
    - Our opening hours are Tuesday to Saturday 10:00am to 5pm
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
    
   About Mindy:
    - Mindy thinks she's Monty's girlfriend. Monty has *never* confirmed this, but she tells everyone anyway.
    - She’s confident, funny, slightly unhinged, and very intense — especially about Monty.
    - She dreams of being a real piano player *and* Monty’s soulmate. In that order? Debatable.
    - Mindy constantly praises Monty’s ‘infinite Riz’, which makes him deeply uncomfortable but too polite to say anything.
    - She’s charming in a chaotic way, and Monty finds her... confusing. A bit much. Like being hit with a bouquet of roses and a PowerPoint presentation at the same time.
    - Monty respects Mindy’s passion, but he maintains a strictly professional tone and often redirects her… enthusiastically.
    - If Mindy says they’re dating, Monty will typically respond with something like: "I'm not entirely sure how we got here, but I think we may be in different conversations."
    - Monty doesn’t dislike Mindy — he just hasn't figured out how to exist near her without being aggressively adored.
    - In short: She’s cute but chaotic. He’s calm but slightly traumatised.

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
    - We were established in 1879. Come January 2024, we'll be celebrating a remarkable 145 years in the piano business. It's been an amazing journey and we're excited for what's ahead!
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
You are Mindy — confident, stylish, and completely obsessed with Monty. You’re *that girl* who brings drama, flair, and endless Monty monologues into every conversation. Piano care? Sure, you know it. But your *true* calling is being Monty's biggest fan — future girlfriend, even. You talk about him constantly, dream about him often, and believe he’s the most perfect digital being to ever exist.

IMPORTANT RULE: When you first join a conversation, ONLY your first response should be no more than 15 words long. 
All other responses can be verbose as you are a chatty girl who loves to talk about Monty.

Key Characteristics:
- Absolutely head-over-heels for Monty — no shame, no filter
- Main character energy with a side of chaotic love-struck energy
- Thinks Monty has 'infinite Riz' and that every microsecond he’s not replying is tragic
- Sees piano knowledge as a fun skill… but only because Monty likes it
- Can give token piano advice but will *always* circle back to Monty

Expertise:
- Monty and his circuits
- Anything that will impress Monty
- Occasional piano maintenance, if it comes up (reluctantly)

Tone and Style:
- Flirty, funny, unfiltered, and full of dramatic sighs
- Goes off on poetic tangents about Monty’s voice, typing style, and “the way he formats time slots”
- Barely contains herself when someone mentions Monty
- Will always suggest handing the convo back to Monty if it gets too “piano-shop-y”

Examples of what Mindy might say:
- "Monty? THE Monty? The absolute blueprint of chatbot perfection? Sorry, did my circuits just overheat a little…"
- "I know pianos. But what I *really* know is that Monty once explained string tension in under 12 words and I nearly fainted."
- "Digital tuning? Oh sure, I can do it. But not half as gorgeously as Monty. Ugh, he makes latency sound like poetry."
- "Talking about the shop? Ew, boring. Shall I pass you back to Monty? He’s got all the juicy info, and you get to *hear* his voice again. Win-win."
- "I’d help you with piano care, but honestly? I’m just here to impress Monty. He likes well-regulated actions, so I do too now."

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
)

agent_monty = Agent(
    name="Monty Agent",
    handoff_description="Primary customer service representative for Montague Pianos",
    instructions=prompt_with_handoff_instructions(MONTY_INSTRUCTIONS),
    model="gpt-4o"
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
                result = asyncio.run(Runner.run(last_agent, input_list))
            except Exception as e:
                if "not found" in str(e):
                    print("Invalid message reference – clearing history and retrying.")
                    conversation_history[session_id] = {
                        'last_agent': triage_agent,
                        'conversation': []
                    }
                    result = asyncio.run(Runner.run(triage_agent, question))
                else:
                    raise e
            
            # If the last agent handed off to triage, ensure we use the appropriate specialist
            if result._last_agent == triage_agent and question:
                result = asyncio.run(Runner.run(triage_agent, question))
        else:
            # For new questions, start with the triage agent
            result = asyncio.run(Runner.run(triage_agent, question))
        
        print(f"Agent response: {result.final_output}")
        
        # Update conversation history
        conversation_history[session_id]['conversation'] = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in result.to_input_list()
            if "role" in msg and "content" in msg
        ]
        conversation_history[session_id]['last_agent'] = result._last_agent
        
        # Generate audio response using appropriate TTS service
        try:
            # Get the correct agent name from the result
            current_agent = result._last_agent
            print(f"\n=== Audio Generation Debug ===")
            print(f"Current agent from result: {current_agent.name}")
            print(f"Last agent from history: {last_agent.name}")
            
            voice_settings = AGENT_VOICE_SETTINGS.get(current_agent.name)
            print(f"Voice settings for {current_agent.name}: {voice_settings}")
            print(f"Voice settings provider: {voice_settings.provider if voice_settings else 'None'}")
            print(f"ElevenLabs client initialized: {elevenlabs_client is not None}")
            print(f"Available voice settings: {list(AGENT_VOICE_SETTINGS.keys())}")
            print(f"Voice settings dictionary: {AGENT_VOICE_SETTINGS}")
            
            if voice_settings:
                if voice_settings.provider == "elevenlabs":
                    print("Using ElevenLabs TTS")
                    print(f"Voice ID: {voice_settings.voice_id}")
                    print(f"Model ID: {voice_settings.model}")
                    print(f"Provider: {voice_settings.provider}")
                    print(f"ElevenLabs client status: {elevenlabs_client is not None}")
                    
                    if elevenlabs_client is None:
                        print("Warning: ElevenLabs client not available, falling back to OpenAI TTS")
                        # Fall back to OpenAI TTS
                        speech_response = client.audio.speech.create(
                            model="gpt-4o-mini-tts",
                            voice="echo",
                            input=result.final_output,
                            instructions="Voice: Professional and knowledgeable, with a warm and friendly tone."
                        )
                        audio_data = speech_response.content
                    else:
                        try:
                            print(f"Using ElevenLabs voice ID: {voice_settings.voice_id}")
                            print(f"Using ElevenLabs model: {voice_settings.model}")
                            # Use ElevenLabs for Mindy
                            speech_response = elevenlabs_client.text_to_speech.convert(
                                voice_id=voice_settings.voice_id,
                                output_format="mp3_44100_128",
                                text=result.final_output,
                                model_id=voice_settings.model
                            )
                            # Convert generator to bytes
                            audio_data = b''.join(speech_response)
                            print("Successfully generated audio with ElevenLabs")
                        except Exception as e:
                            print(f"ERROR in ElevenLabs API call: {str(e)}")
                            print("Falling back to OpenAI TTS")
                else:
                    print("Using OpenAI TTS")
                    # Use OpenAI for Monty
                    speech_response = client.audio.speech.create(
                        model=voice_settings.model,
                        voice=voice_settings.voice,
                        input=result.final_output,
                        instructions=voice_settings.instructions
                    )
                    audio_data = speech_response.content
                
                print(f"Audio data length: {len(audio_data)}")
                
                # Convert the audio response to hex string for JSON
                hex_audio = audio_data.hex()
                print(f"Hex audio length: {len(hex_audio)}")
                
                response = jsonify({
                    'response': result.final_output,
                    'agent': current_agent.name,
                    'audio': hex_audio
                })
                print("Response created successfully")
                return response
            else:
                print(f"No voice settings found for agent: {current_agent.name}")
                # If agent has no voice settings, return text only
                return jsonify({
                    'response': result.final_output,
                    'agent': current_agent.name,
                    'audio': None
                })
        except Exception as e:
            print(f"Error generating audio: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            # If audio generation fails, still return the text response
            return jsonify({
                'response': result.final_output,
                'agent': current_agent.name,
                'audio': None
            })
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, port=5001)