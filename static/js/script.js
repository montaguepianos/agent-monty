document.addEventListener('DOMContentLoaded', function() {
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const chatContainer = document.getElementById('chatContainer');

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
            audio.style.display = 'none'; // Hide the audio element
            
            // Convert hex string back to Uint8Array
            const audioArray = new Uint8Array(audioData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
            const audioBlob = new Blob([audioArray], { type: 'audio/mp3' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            audio.src = audioUrl;
            
            // Play the audio automatically
            audio.play().catch(error => {
                console.error('Error playing audio:', error);
            });
            
            // Clean up the URL when audio is done playing
            audio.addEventListener('ended', () => {
                URL.revokeObjectURL(audioUrl);
                audio.remove(); // Remove the audio element from the DOM
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
            addMessage(message, true);
            userInput.value = '';

            fetch('/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                addMessage(data.response, false, data.audio);
            })
            .catch(error => {
                console.error('Error:', error);
                addMessage('Sorry, I encountered an error. Please try again.');
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