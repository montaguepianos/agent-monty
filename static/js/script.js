document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendMessage');
    const clearButton = document.getElementById('clearChat');
    const toggleVoiceButton = document.getElementById('toggleVoice');
    
    let isVoiceEnabled = false;
    let mediaRecorder = null;
    let audioChunks = [];
    let sessionId = generateSessionId();
    let currentAudio = null;

    // Initialize audio recording
    async function initializeAudioRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 24000
                } 
            });
            
            mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                await sendVoiceMessage(audioBlob);
            };

            return true;
        } catch (error) {
            console.error('Error accessing microphone:', error);
            return false;
        }
    }

    // Generate a unique session ID
    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // Update voice button appearance
    function updateVoiceButton() {
        toggleVoiceButton.innerHTML = isVoiceEnabled ? 
            '<i class="fas fa-microphone-slash"></i> Stop Recording' : 
            '<i class="fas fa-microphone"></i> Start Recording';
        toggleVoiceButton.classList.toggle('active', isVoiceEnabled);
    }

    // Add a message to the chat
    function addMessage(content, isUser = false, audioData = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user' : 'system'}`;
        
        let messageContent = `<div class="message-content">${content}</div>`;
        
        // Add audio player if audio data is available
        if (audioData && !isUser) {
            const audioPlayer = document.createElement('audio');
            audioPlayer.className = 'audio-player';
            audioPlayer.style.display = 'none'; // Hide the audio player
            
            // Convert hex string back to Uint8Array
            const audioArray = new Uint8Array(audioData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
            const audioBlob = new Blob([audioArray], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            audioPlayer.src = audioUrl;
            
            // Play the audio automatically
            audioPlayer.play().catch(error => {
                console.error('Error playing audio:', error);
            });
            
            // Clean up the URL when audio is done playing
            audioPlayer.addEventListener('ended', () => {
                URL.revokeObjectURL(audioUrl);
                audioPlayer.remove(); // Remove the audio element from the DOM
            });
            
            messageContent += audioPlayer.outerHTML;
        }
        
        messageDiv.innerHTML = messageContent;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Handle sending messages
    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        // Add user message to chat
        addMessage(message, true);
        userInput.value = '';

        try {
            const response = await fetch('/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId
                })
            });

            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }

            // Add Monty's response to chat with audio if available
            addMessage(data.response, false, data.audio);

        } catch (error) {
            console.error('Error:', error);
            addMessage('I apologize, but I encountered an error. Please try again.');
        }
    }

    // Handle voice recording
    async function toggleVoice() {
        if (!mediaRecorder) {
            const initialized = await initializeAudioRecording();
            if (!initialized) {
                alert('Could not access microphone. Please check your permissions.');
                return;
            }
        }

        isVoiceEnabled = !isVoiceEnabled;
        updateVoiceButton();

        if (isVoiceEnabled) {
            audioChunks = [];
            mediaRecorder.start(100); // Collect data every 100ms
            toggleVoiceButton.classList.add('recording');
        } else {
            mediaRecorder.stop();
            toggleVoiceButton.classList.remove('recording');
        }
    }

    // Send voice message to server
    async function sendVoiceMessage(audioBlob) {
        try {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');
            formData.append('session_id', sessionId);

            const response = await fetch('/voice', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }

            // Add a visual indicator that voice message was sent
            addMessage('🎤 Voice message sent', true);

        } catch (error) {
            console.error('Error sending voice message:', error);
            addMessage('I apologize, but there was an error processing your voice message.');
        }
    }

    // Event Listeners
    sendButton.addEventListener('click', sendMessage);
    clearButton.addEventListener('click', () => {
        fetch('/clear-chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        }).then(() => {
            chatMessages.innerHTML = `
                <div class="message system">
                    <div class="message-content">
                        Hello! I'm Monty, your friendly assistant at Montague Pianos. How can I help you today?
                    </div>
                </div>
            `;
        });
    });
    toggleVoiceButton.addEventListener('click', toggleVoice);

    // Handle Enter key in textarea
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
    });
}); 