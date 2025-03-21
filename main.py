from dotenv import load_dotenv
import os
from flask import Flask, request, Response, render_template, jsonify
from openai import OpenAI
import asyncio
import numpy as np
import sounddevice as sd
from agents import Agent, Runner, function_tool, ModelSettings
from agents.tool import WebSearchTool, FileSearchTool, FunctionTool, ComputerTool
from agents.voice import (
    AudioInput,
    SingleAgentVoiceWorkflow,
    VoicePipeline,
)
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
import json
import wave
import io

# Load environment variables
load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Store conversation history
conversation_history = {}

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
    - Piano removals (as of Oct 23, our minimum local removal charge is £200 Plus VAT)
    - Piano Tuning (as of July 24, our local piano tuning charge is £85)
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

    # TOOLS
web_search_tool = WebSearchTool(
    user_location=None,
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
        "2. Piano Tuning Agent: For any questions about piano tuning, maintenance, or related technical aspects\n\n"
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
    model="gpt-4o",
    tools=[web_search_tool],
)

# Set up handoffs
triage_agent.handoffs = [agent_monty]
agent_monty.handoffs = [triage_agent]

# Voice pipeline setup
voice_pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(agent_monty))

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
        
        # If this is a follow-up question, use the last agent and include conversation history
        if conversation:
            input_list = conversation + [{"role": "user", "content": question}]
            try:
                result = asyncio.run(Runner.run(last_agent, input_list))
            except Exception as e:
                if "max decimal places exceeded" in str(e):
                    # If we hit the decimal precision error, try again with a simpler input
                    result = asyncio.run(Runner.run(last_agent, question))
                else:
                    raise e
            
            # If the last agent handed off to triage, ensure we use the appropriate specialist
            if result._last_agent == triage_agent and question:
                result = asyncio.run(Runner.run(triage_agent, question))
        else:
            # For new questions, start with the triage agent
            result = asyncio.run(Runner.run(triage_agent, question))
        
        # Update conversation history
        conversation_history[session_id]['conversation'] = result.to_input_list()
        conversation_history[session_id]['last_agent'] = result._last_agent
        
        # Generate audio response using OpenAI TTS
        try:
            speech_response = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=result.final_output,
                instructions="""Voice: Cheerful, slightly robotic, and full of warmth — Monty sounds like he loves helping, with a bright, enthusiastic tone that's friendly, fun, and just a little synthetic in a charming way.

Punctuation: Crisp and well-paced, with light, natural pauses that create clarity and rhythm, adding a sense of attentiveness and delight in every interaction.

Delivery: Energetic but polite, with a curious, can-do attitude — Monty is eager to assist, sounds genuinely excited to be helpful, and always delivers information with an encouraging, upbeat confidence.

Phrasing: Clear and concise, using customer-friendly language that avoids jargon while maintaining professionalism.

Tone: Empathetic and solution-focused, emphasizing both understanding and proactive assistance."""
            )
            
            # Convert the audio response to WAV format
            audio_data = speech_response.content
            wav_buffer = io.BytesIO()
            
            # Convert MP3 to WAV (you might need to add mp3 to wav conversion here)
            # For now, we'll just return the MP3 data
            return jsonify({
                'response': result.final_output,
                'agent': last_agent.name,
                'audio': audio_data.hex()  # Convert audio to hex string for JSON
            })
        except Exception as e:
            print(f"Error generating audio: {str(e)}")
            # If audio generation fails, still return the text response
            return jsonify({
                'response': result.final_output,
                'agent': last_agent.name,
                'audio': None
            })
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
