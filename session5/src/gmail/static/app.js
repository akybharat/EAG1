document.addEventListener('DOMContentLoaded', function() {
    const conversationArea = document.getElementById('conversation');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const statusBar = document.getElementById('statusBar');
    
    // Check connection to server
    checkServerConnection();
    
    // Add initial greeting message
    appendMessage('Email Assistant', `Hello! I'm your email assistant. I can help you manage your emails.

You can ask me to:
- Read your unread emails
- Draft emails for you
- Send emails
- Trash emails
- Open emails in your browser

What would you like to do today?`, 'assistant');
    
    // Event listeners
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', function(e) {
        // Send message with Ctrl+Enter
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });
    
    function checkServerConnection() {
        setStatus('Connecting to email server...');
        appendMessage('System', 'Initializing connection to email server...', 'system');
        
        fetch('/api/initialize', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                setStatus(`Ready - Connected with ${data.toolCount} available tools`);
            } else {
                setStatus('Failed to connect to server');
                appendMessage('System', `Failed to connect to email server: ${data.error}`, 'system');
            }
        })
        .catch(error => {
            setStatus('Connection error');
            appendMessage('System', `Error connecting to server: ${error.message}`, 'system');
        });
    }
    
    function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;
        
        // Display user message
        appendMessage('You', message, 'you');
        
        // Clear input
        userInput.value = '';
        
        // Send to server
        setStatus('Processing...');
        fetch('/api/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => response.json())
        .then(data => {
            if (data.type === 'message') {
                appendMessage('Assistant', data.content, 'assistant');
            } 
            else if (data.type === 'function_call') {
                if (data.explanation) {
                    appendMessage('Assistant', data.explanation, 'assistant');
                }
                appendMessage('System', `Executing: ${data.functionName}`, 'system');
                
                // Poll for function execution results
                pollFunctionResult(data.executionId);
            }
            setStatus('Ready');
        })
        .catch(error => {
            appendMessage('System', `Error processing message: ${error.message}`, 'system');
            setStatus('Ready');
        });
    }
    
    function pollFunctionResult(executionId) {
        const checkResult = () => {
            fetch(`/api/function_result/${executionId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'completed') {
                        // Show raw result
                        if (data.rawResult) {
                            appendMessage('System', `Result from ${data.functionName}:\n${data.rawResult}`, 'system');
                        }
                        
                        // Show processed result if available
                        if (data.processedResult) {
                            appendMessage('Assistant', data.processedResult, 'assistant');
                        }
                        setStatus('Ready');
                    } else if (data.status === 'error') {
                        appendMessage('System', `Error executing ${data.functionName}: ${data.error}`, 'system');
                        setStatus('Ready');
                    } else {
                        // Still processing, check again after a delay
                        setTimeout(checkResult, 1000);
                    }
                })
                .catch(error => {
                    appendMessage('System', `Error checking function result: ${error.message}`, 'system');
                    setStatus('Ready');
                });
        };
        
        // Start polling
        checkResult();
    }
    
    function appendMessage(sender, content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        
        const senderDiv = document.createElement('div');
        senderDiv.className = `sender ${type}`;
        senderDiv.textContent = sender;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        messageDiv.appendChild(senderDiv);
        messageDiv.appendChild(contentDiv);
        
        conversationArea.appendChild(messageDiv);
        
        // Scroll to bottom
        conversationArea.scrollTop = conversationArea.scrollHeight;
    }
    
    function setStatus(message) {
        statusBar.textContent = message;
    }
});