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
        'https://www.montaguepianos.co.uk/wp-content/uploads/2023/10/keyboard-typing-5997.mp3'
    ];

    // Create thinking sound audio element
    const thinkingSound = new Audio();
    thinkingSound.volume = 0.5; // Set volume to 50%

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

    function addMessage(content, isUser = false, audioData = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user' : 'monty'}`;
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = content;
        messageDiv.appendChild(textDiv);

        if (!isUser && audioData) {
            const audioDiv = document.createElement('div');
            audioDiv.className = 'message-audio';
            const audio = document.createElement('audio');
            audio.style.display = 'none';
            
            const audioArray = new Uint8Array(audioData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
            const audioBlob = new Blob([audioArray], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            audio.src = audioUrl;
            
            audio.play().catch(error => {
                console.error('Error playing audio:', error);
                showError('Error playing audio response');
            });
            
            audio.addEventListener('ended', () => {
                URL.revokeObjectURL(audioUrl);
                audio.remove();
            });
            
            audioDiv.appendChild(audio);
            messageDiv.appendChild(audioDiv);
        }

        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function sendMessage() {
        const message = userInput.value.trim();
        if (message) {
            userInput.disabled = true;
            sendButton.disabled = true;
            
            addMessage(message, true);
            userInput.value = '';
            
            typingIndicator.style.display = 'block';
            playRandomThinkingSound();
            
            fetch('/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                typingIndicator.style.display = 'none';
                thinkingSound.pause();
                thinkingSound.currentTime = 0;
                
                if (data.error) {
                    showError(data.error);
                    return;
                }
                
                addMessage(data.response, false, data.audio);
            })
            .catch(error => {
                console.error('Error:', error);
                typingIndicator.style.display = 'none';
                thinkingSound.pause();
                thinkingSound.currentTime = 0;
                showError('Sorry, I encountered an error. Please try again.');
            })
            .finally(() => {
                userInput.disabled = false;
                sendButton.disabled = false;
                userInput.focus();
            });
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