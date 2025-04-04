document.addEventListener('DOMContentLoaded', function() {
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const chatContainer = document.getElementById('chatContainer');
    const typingIndicator = document.getElementById('typingIndicator');
    const errorMessage = document.getElementById('errorMessage');

    // Array of thinking sounds from Montague Pianos server
    const thinkingSounds = [
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/10/montyhumming3.mp3',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/11/montyhumming5.mp3',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/11/montyhumming6.mp3',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/11/montychristmashumming.mp3',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/11/montythinking.mp3',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/11/montythinking2.wav',
        'https://www.montaguepianos.co.uk/wp-content/uploads/2025/03/keyboard-typing.mp3'
    ];

    // Create thinking sound audio element
    const thinkingSound = new Audio();
    thinkingSound.volume = 0.5; // Set volume to 50%
    
    // Track current playing response audio
    let currentResponseAudio = null;
    
    // Flag to track if we're showing an intermediate message
    let isShowingIntermediate = false;
    // Store the intermediate message element for later removal
    let intermediateElement = null;

    // Preload all thinking sounds
    const preloadedSounds = thinkingSounds.map(src => {
        const audio = new Audio(src);
        audio.load();
        return audio;
    });

    function playRandomThinkingSound() {
        // Stop any currently playing sound
        thinkingSound.pause();
        thinkingSound.currentTime = 0;

        // Get a random sound
        const randomIndex = Math.floor(Math.random() * preloadedSounds.length);
        const selectedSound = preloadedSounds[randomIndex];
        
        // Clone the audio element to allow multiple plays
        const soundToPlay = selectedSound.cloneNode();
        soundToPlay.volume = 0.5;

        // Try to play the sound
        const playPromise = soundToPlay.play();
        
        if (playPromise !== undefined) {
            playPromise.then(() => {
                // Store the currently playing sound
                thinkingSound.src = soundToPlay.src;
            }).catch(error => {
                console.error('Error playing thinking sound:', error);
                // Try to play without user interaction
                soundToPlay.play().catch(e => console.error('Second attempt failed:', e));
            });
        }
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        setTimeout(() => {
            errorMessage.style.display = 'none';
        }, 5000);
    }
    
    function stopCurrentAudio() {
        // Stop any currently playing response audio
        if (currentResponseAudio) {
            console.log('Stopping currently playing audio');
            currentResponseAudio.pause();
            currentResponseAudio.currentTime = 0;
            // We don't remove the element here as it might still be in the DOM
        }
        
        // Also stop thinking sound
        thinkingSound.pause();
        thinkingSound.currentTime = 0;
    }

    function addMessage(content, isUser = false, audioData = null, isIntermediate = false) {
        console.log('Adding message:', { content, isUser, hasAudio: !!audioData, isIntermediate });
        
        // If this is a final response and we have an intermediate message showing, remove it
        if (!isIntermediate && isShowingIntermediate && intermediateElement) {
            console.log('Removing intermediate message');
            chatContainer.removeChild(intermediateElement);
            isShowingIntermediate = false;
            intermediateElement = null;
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user' : 'monty'}`;
        
        if (isIntermediate) {
            messageDiv.classList.add('intermediate-message');
            isShowingIntermediate = true;
            intermediateElement = messageDiv;
        }
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = content;
        messageDiv.appendChild(textDiv);

        if (!isUser && audioData) {
            console.log('Processing audio data, length:', audioData.length);
            
            // Stop any currently playing audio (both response and thinking sounds)
            stopCurrentAudio();
            
            const audioDiv = document.createElement('div');
            audioDiv.className = 'message-audio';
            const audio = document.createElement('audio');
            audio.style.display = 'none';
            
            try {
                console.log('Converting hex to audio array...');
                const audioArray = new Uint8Array(audioData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
                console.log('Audio array created, length:', audioArray.length);
                
                const audioBlob = new Blob([audioArray], { type: 'audio/mp3' });
                console.log('Audio blob created, size:', audioBlob.size);
                
                const audioUrl = URL.createObjectURL(audioBlob);
                console.log('Audio URL created:', audioUrl);
                
                audio.src = audioUrl;
                
                // Set as current audio before playing
                currentResponseAudio = audio;
                
                console.log('Attempting to play audio...');
                audio.play().then(() => {
                    console.log('Audio playback started successfully');
                }).catch(error => {
                    console.error('Error playing audio:', error);
                    showError('Error playing audio response');
                    currentResponseAudio = null;
                });
                
                audio.addEventListener('ended', () => {
                    console.log('Audio playback ended');
                    URL.revokeObjectURL(audioUrl);
                    if (currentResponseAudio === audio) {
                        currentResponseAudio = null;
                    }
                    audio.remove();
                });
                
                audioDiv.appendChild(audio);
                messageDiv.appendChild(audioDiv);
            } catch (error) {
                console.error('Error processing audio data:', error);
                showError('Error processing audio response');
                currentResponseAudio = null;
            }
        }

        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    async function sendMessage() {
        const message = userInput.value.trim();
        if (message) {
            userInput.disabled = true;
            sendButton.disabled = true;
            
            addMessage(message, true);
            userInput.value = '';
            
            // Notify parent window that we're sending a message
            window.parent.postMessage({ type: 'monty-send' }, '*');
            
            typingIndicator.style.display = 'block';
            playRandomThinkingSound();
            
            // Check if this is a postcode query for tuning availability
            const postcodeRegex = /[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}/i;
            const containsTuningKeywords = /piano|tuning|tuner|tune/i.test(message.toLowerCase());
            const hasTuningContext = chatContainer.innerHTML.toLowerCase().includes('tuning') || 
                                     chatContainer.innerHTML.includes('postcode');
            const isPostcodeQuery = postcodeRegex.test(message);

            // More precise detection of booking flow stages
            // This chat history analysis determines if we're already past the initial postcode check stage
            const inBookingFlowSignals = [
                // Already seen available slots (specific text in the response)
                chatContainer.innerHTML.includes("suitable tuning slots") || 
                chatContainer.innerHTML.includes("We have available piano tuning slots"),
                
                // Time selection indicators
                chatContainer.innerHTML.includes("Which slot would you prefer?") ||
                chatContainer.innerHTML.includes("Would any of these times work for you?"),
                
                // Date/time detection (checking for time patterns and day names)
                /\b([0-1]?[0-9]|2[0-3]):[0-5][0-9]\b/.test(chatContainer.innerHTML) || // Time pattern HH:MM
                /\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b/i.test(chatContainer.innerHTML) ||
                /\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/i.test(chatContainer.innerHTML),
                
                // Selection phrases - after user has chosen a slot
                /\bI('ll| will) book (slot|appointment|time|number) \d/i.test(chatContainer.innerHTML) ||
                /\bI('d| would) like (slot|appointment|time|number) \d/i.test(chatContainer.innerHTML) ||
                /\b(slot|appointment|time|number|option) \d\b/i.test(chatContainer.innerHTML),
                
                // Name/contact details collection phase 
                chatContainer.innerHTML.includes("What's your name?") ||
                chatContainer.innerHTML.includes("What's your full name?") ||
                chatContainer.innerHTML.includes("Could you provide your address?") ||
                chatContainer.innerHTML.includes("Could you provide your phone number?"),
                
                // User providing booking details (check for common name/address/phone patterns)
                /\bMy name is\b/i.test(chatContainer.innerHTML) ||
                /\bMy address is\b/i.test(chatContainer.innerHTML) ||
                /\bMy phone (number|is)\b/i.test(chatContainer.innerHTML) ||
                /\b\d{5,}\b/.test(chatContainer.innerHTML), // Phone number pattern
                
                // Specific confirmation phrases
                chatContainer.innerHTML.includes("appointment is all set") ||
                chatContainer.innerHTML.includes("Booking confirmed")
            ];

            // If ANY of these signals are true, we're already in the booking flow
            const isAlreadyInBookingFlow = inBookingFlowSignals.some(signal => signal === true);

            // Only show initial postcode message if:
            // 1. This is a postcode
            // 2. We have tuning context
            // 3. We're NOT already in the booking flow
            if (isPostcodeQuery && (containsTuningKeywords || hasTuningContext) && !isAlreadyInBookingFlow) {
                // Use HTML to make the first word bold
                const intermediateMessageText = "Got it, thanks! Please give me a little bit of time to check the calendar. Lee has got me doing a hundred things, like checking your post code is close enough to us, then checking the next 30 days in the diary. The suggested appointments will also need to be close enough to any other booked tunings so that our piano tuner doesn't need a helicopter or time machine to get there in time... give me just a few more moments and I'll be right with you!";
                const firstWord = intermediateMessageText.split(' ')[0];
                const restOfMessage = intermediateMessageText.substring(firstWord.length);
                const intermediateMessage = `<strong>${firstWord}</strong>${restOfMessage}`;
                
                // For simplicity, we'll request an audio response for this message
                try {
                    // Add the intermediate message first - use HTML instead of plain text
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message monty intermediate-message';
                    
                    const textDiv = document.createElement('div');
                    textDiv.className = 'message-text';
                    textDiv.innerHTML = intermediateMessage; // Use innerHTML to render the HTML
                    
                    messageDiv.appendChild(textDiv);
                    chatContainer.appendChild(messageDiv);
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                    
                    // Track this as an intermediate message
                    isShowingIntermediate = true;
                    intermediateElement = messageDiv;
                    
                    // Request audio for the intermediate message (audio will be for the full message)
                    const audioResponse = await fetch('/generate-audio', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ message: intermediateMessageText }) // Use plain text for audio
                    });
                    
                    if (audioResponse.ok) {
                        const audioData = await audioResponse.json();
                        if (audioData.audio) {
                            // Add audio to the existing intermediate message
                            const audioDiv = document.createElement('div');
                            audioDiv.className = 'message-audio';
                            const audio = document.createElement('audio');
                            audio.style.display = 'none';
                            
                            try {
                                console.log('Converting hex to audio array...');
                                const audioArray = new Uint8Array(audioData.audio.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
                                
                                const audioBlob = new Blob([audioArray], { type: 'audio/mp3' });
                                const audioUrl = URL.createObjectURL(audioBlob);
                                
                                audio.src = audioUrl;
                                
                                // Set as current audio before playing
                                currentResponseAudio = audio;
                                
                                audio.play().then(() => {
                                    console.log('Intermediate audio playback started successfully');
                                }).catch(error => {
                                    console.error('Error playing intermediate audio:', error);
                                    currentResponseAudio = null;
                                });
                                
                                audio.addEventListener('ended', () => {
                                    console.log('Intermediate audio playback ended');
                                    URL.revokeObjectURL(audioUrl);
                                    if (currentResponseAudio === audio) {
                                        currentResponseAudio = null;
                                    }
                                    audio.remove();
                                });
                                
                                audioDiv.appendChild(audio);
                                messageDiv.appendChild(audioDiv);
                            } catch (error) {
                                console.error('Error processing intermediate audio:', error);
                                currentResponseAudio = null;
                            }
                        }
                    }
                } catch (error) {
                    console.error('Error handling intermediate message:', error);
                    // If there's an error with HTML approach, fall back to the original method
                    addMessage(intermediateMessageText, false, null, true);
                }
            }
            
            console.log('Sending message to server...');
            try {
                console.log('Making API request to /ask endpoint...');
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
                });

                console.log('Response status:', response.status, response.statusText);
                
                // Try to get response content even if status is not OK
                let responseData;
                let responseText;
                
                try {
                    // Try to get response as text first
                    responseText = await response.text();
                    console.log('Response text (first 100 chars):', responseText.substring(0, 100));
                    
                    // Then try to parse as JSON if possible
                    if (responseText && responseText.trim()) {
                        try {
                            responseData = JSON.parse(responseText);
                            console.log('Successfully parsed response as JSON');
                        } catch (jsonErr) {
                            console.log('Response is not valid JSON, using as text');
                        }
                    }
                } catch (textErr) {
                    console.error('Failed to get response text:', textErr);
                }
                
                if (!response.ok) {
                    console.error(`Error response (${response.status}): `, responseText || response.statusText);
                    
                    // If we have error details from the response, use them
                    if (responseData && responseData.error) {
                        throw new Error(`Failed to get response: ${responseData.error}`);
                    } else {
                        // Handle 500 error from Flask backend
                        if (response.status === 500) {
                            // Add the mock data fallback directly here
                            const mockResponse = `I'm having some technical difficulties connecting to our booking system, but here are some typically available slots:

1. Monday, April 15 at 10:30
2. Monday, April 15 at 13:30
3. Tuesday, April 16 at 09:00
4. Tuesday, April 16 at 10:30
5. Wednesday, April 17 at 12:00
6. Wednesday, April 17 at 15:00

Would any of these times work for you? If so, please call Lee on 01442 876131 to confirm your booking.`;
                            
                            addMessage(mockResponse, false, null, false);
                            return; // Exit early after adding mock response
                        }
                        
                        throw new Error(`Failed to get response: ${response.status} ${response.statusText}`);
                    }
                }

                // At this point we have a successful response
                // Use parsed JSON if available, otherwise try to parse again
                const data = responseData || (responseText ? JSON.parse(responseText) : {});
                
                console.log('Response processed successfully:', data ? 'has data' : 'empty data');
                if (data.response) {
                    // Add the text message to the chat (not an intermediate message)
                    addMessage(data.response, false, data.audio, false);
                    
                    // Check if this is a booking confirmation message
                    const isBookingConfirmation = data.response.includes("appointment is all set") || 
                                                  data.response.includes("piano tuning appointment is all set") ||
                                                  data.response.includes("Booking confirmed") ||
                                                  data.response.includes("Your piano tuning appointment");
                    
                    // If this is a booking confirmation, add payment message
                    if (isBookingConfirmation) {
                        setTimeout(() => {
                            // Add payment message with link
                            const paymentMessageText = "To confirm and pay for your tuning please visit https://buy.stripe.com/aEUdTUaLId6EgBW9AA";
                            
                            // Create payment message element
                            const messageDiv = document.createElement('div');
                            messageDiv.className = 'message monty payment-message';
                            
                            const textDiv = document.createElement('div');
                            textDiv.className = 'message-text';
                            
                            // Convert the URL to a clickable link
                            const urlRegex = /(https?:\/\/[^\s]+)/g;
                            const htmlContent = paymentMessageText.replace(urlRegex, function(url) {
                                return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
                            });
                            
                            textDiv.innerHTML = htmlContent;
                            messageDiv.appendChild(textDiv);
                            chatContainer.appendChild(messageDiv);
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                            
                        }, 2000); // Add payment message after 2 seconds
                    }
                }
            } catch (error) {
                console.error('Error:', error);
                addMessage('Sorry, I encountered an error. Please try again.', 'system');
            } finally {
                typingIndicator.style.display = 'none';
                thinkingSound.pause();
                thinkingSound.currentTime = 0;
                userInput.disabled = false;
                sendButton.disabled = false;
                userInput.focus();
            }
        }
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}); 