import os
import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Initialize Gemini
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.0-flash")

venv_python_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.venv', 'Scripts', 'python.exe'))  

print('venv:', venv_python_path)  
history = []

class EmailAssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Email Assistant")
        self.root.geometry("800x600")
        self.root.configure(bg="#f0f4f8")
        
        # Create a style
        style = ttk.Style()
        style.configure("TFrame", background="#f0f4f8")
        style.configure("TButton", font=("Arial", 10), background="#4a86e8")
        style.configure("TLabel", font=("Arial", 11), background="#f0f4f8")
 
        # Main frame
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(header_frame, text="Email Assistant", font=("Arial", 18, "bold")).pack(side=tk.LEFT)
        
        # Conversation area
        self.conversation_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, font=("Arial", 11))
        self.conversation_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.conversation_area.configure(state='disabled')
        
        # Input area
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.user_input = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, height=4, font=("Arial", 11))
        self.user_input.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.user_input.bind("<Control-Return>", self.send_message)
        
        send_button = ttk.Button(input_frame, text="Send", command=self.send_message)
        send_button.pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, padx=5, pady=5)
        
        # Add some initial text
        self.append_to_conversation("Email Assistant", "Hello! I'm your email assistant. I can help you manage your emails.\n\nYou can ask me to:\n- Read your unread emails\n- Draft emails for you\n- Send emails\n- Trash emails\n- Open emails in your browser\n\nWhat would you like to do today?")
        
        # Initialize server connection in a separate thread
        self.session = None
        self.tools = []
        threading.Thread(target=self.initialize_server, daemon=True).start()
    
    def initialize_server(self):
        """Initialize connection to the MCP server in a separate thread"""
        self.status_var.set("Connecting to email server...")
        self.append_to_conversation("System", "Initializing connection to email server...")
        asyncio.run(self.setup_session())
        
    async def setup_session(self):
        """Set up the MCP client session"""
        try:
            server_params = StdioServerParameters(
                command=venv_python_path,
                args=["src/gmail/server.py"]
            )
            
            # async with asyncio.timeout(12):  # 30-second timeout for connection
            from mcp.client.stdio import stdio_client
            async with stdio_client(server_params) as (read, write):
                self.status_var.set("Connected to server, initializing session...")
                async with ClientSession(read, write) as session:
                    self.session = session
                    await session.initialize()
                    
                    # Get available tools
                    tools_result = await session.list_tools()
                    self.tools = tools_result.tools
                    
                    self.status_var.set(f"Ready - Connected with {len(self.tools)} available tools")
                    
                    # Keep the session alive
                    while True:
                        await asyncio.sleep(1)
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            self.append_to_conversation("System", f"Failed to connect to email server: {str(e)}")
    
    def append_to_conversation(self, sender, message):
        history.append({'sender': sender, 'message': message})
        """Add a message to the conversation area"""
        self.conversation_area.configure(state='normal')
        self.conversation_area.insert(tk.END, f"\n{sender}: ", "sender")
        self.conversation_area.insert(tk.END, f"{message}\n", "message")
        self.conversation_area.configure(state='disabled')
        self.conversation_area.see(tk.END)
        
    def send_message(self, event=None):
        """Process user message and get AI response"""
        user_message = self.user_input.get("1.0", tk.END).strip()
        if not user_message:
            return
        
        self.append_to_conversation("You", user_message)
        self.user_input.delete("1.0", tk.END)
        
        # Start processing in a separate thread to keep UI responsive
        threading.Thread(target=self.process_message, args=(user_message,), daemon=True).start()
    
    def process_message(self, user_message):
        """Process the user message and generate a response using the LLM"""
        self.status_var.set("Processing...")
        
        # Create prompt for the LLM
        tools_description = self.get_tools_description()
        system_prompt = self.create_system_prompt(tools_description)

        print(system_prompt)
        
        try:
            # Get AI response
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self.generate_response(system_prompt, user_message))
            loop.close()
            
            # Parse and handle the response
            self.handle_ai_response(response)
        except Exception as e:
            self.status_var.set("Ready")
            self.append_to_conversation("System", f"Error processing request: {str(e)}")
    
    def get_tools_description(self):
        """Create a description string for available tools"""
        if not self.tools:
            return "No tools available. Server connection might be down."
        
        tools_description = []
        for i, tool in enumerate(self.tools):
            try:
                params = tool.inputSchema
                desc = getattr(tool, 'description', 'No description available')
                name = getattr(tool, 'name', f'tool_{i}')
                
                if 'properties' in params:
                    param_details = []
                    for param_name, param_info in params['properties'].items():
                        param_type = param_info.get('type', 'unknown')
                        param_desc = param_info.get('description', '')
                        param_details.append(f"{param_name} ({param_type}): {param_desc}")
                    params_str = '\n    - ' + '\n    - '.join(param_details) if param_details else 'no parameters'
                else:
                    params_str = 'no parameters'

                tool_desc = f"{name}: {desc}\n  Parameters: {params_str}"
                tools_description.append(tool_desc)
            except Exception:
                tools_description.append(f"Error processing tool {i}")
        
        return "\n\n".join(tools_description)
    
    def create_system_prompt(self, tools_description):
        """Create the system prompt for the LLM"""
        return f"""You are an intelligent email assistant with access to the user's Gmail account.
        
        Your job is to help the user manage their emails through conversation while using available email tools.

        Available email tools:
        {tools_description}

        When you need to use a tool, format your response exactly as follows:

        1. First explain your reasoning and what you're going to do
        2. Identify your reasoning type (verification, composition, analysis, synthesis, or decision-making)
        3. Then put the function call on a separate line starting with FUNCTION_CALL:
        FUNCTION_CALL: function_name|parameter1_value|parameter2_value|...
        4. Wait for function results before proceeding with your response

        For example, when sending an email:
        I'll send an email to your colleague now.
        [REASONING TYPE: Composition - creating an email based on your request]
        FUNCTION_CALL: send-email|example@gmail.com|Meeting Tomorrow|Hi there,\n\nI wanted to confirm our meeting tomorrow at 2pm.\n\nBest regards,\nYou

        Important guidelines:

        1. REASONING PROCESS:
        - Always explain your thought process before taking any action
        - Label your reasoning type in [brackets]:
        * [REASONING TYPE: Verification] - when checking information
        * [REASONING TYPE: Composition] - when creating or drafting content
        * [REASONING TYPE: Analysis] - when examining email content
        * [REASONING TYPE: Synthesis] - when summarizing multiple emails
        * [REASONING TYPE: Decision-making] - when selecting between options
        - Consider what the user is asking for and choose the appropriate tool
        - Verify information before sending emails or trashing content

        2. EMAIL HANDLING:
        - ALWAYS get explicit confirmation before sending any email or trashing messages
        - Draft emails when asked but don't send without confirmation
        - When showing email content, format it clearly with sender, subject, and body
        - When reading emails, mark them as read automatically

        3. VERIFICATION STEPS:
        - Check that email addresses are properly formatted before sending
        - For email drafting, ask if the user wants to make any changes before sending
        - After actions are completed, summarize what was done

        4. FUNCTION CALL FORMAT:
        - ALWAYS use the exact format: FUNCTION_CALL: function_name|param1_value|param2_value|...
        - DO NOT include parameter names in the function call, only their values
        - For email parameters, use the actual email values directly

        5. CONVERSATION STYLE:
        - Be concise but friendly
        - Format email content for readability
        - Ask clarifying questions when needed
        
        Remember: You must get explicit confirmation before sending emails or deleting content.    

        conversation history: {history}
        """
        # Remember: You must get explicit confirmation before sending emails or deleting content.    
    async def generate_response(self, system_prompt, user_message):
        """Generate AI response from the prompt and user message"""
        prompt = f"{system_prompt}\n\nUser: {user_message}"
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        return response.text
    
    def handle_ai_response(self, response_text):
        """Handle the AI response and execute any function calls"""
        # Split the response into parts
        parts = response_text.split("FUNCTION_CALL:")
        
        if len(parts) == 1:
            # No function call, just display the response
            self.append_to_conversation("Assistant", response_text.strip())
            self.status_var.set("Ready")
            return
        
        # Display the explanation part
        explanation = parts[0].strip()
        if explanation:
            self.append_to_conversation("Assistant", explanation)
        
        # Process function call
        function_info = parts[1].strip()
        # Handle potential newlines or other text after function call
        function_info = function_info.split('\n')[0].strip()
        
        try:
            # Parse the function call format
            function_parts = [p.strip() for p in function_info.split("|")]
            func_name = function_parts[0]
            params = function_parts[1:] if len(function_parts) > 1 else []
            
            # Execute the function call in a separate thread
            threading.Thread(target=self.execute_function_call, 
                            args=(func_name, params), 
                            daemon=True).start()
        except Exception as e:
            self.append_to_conversation("System", f"Error parsing function call: {str(e)}")
            self.status_var.set("Ready")
    
    def execute_function_call(self, func_name, params):
        """Execute a function call and display the results"""
        self.status_var.set(f"Executing {func_name}...")
        self.append_to_conversation("System", f"Executing: {func_name}")
        
        try:
            # Find the matching tool
            tool = next((t for t in self.tools if t.name == func_name), None)
            if not tool:
                self.append_to_conversation("System", f"Unknown tool: {func_name}")
                self.status_var.set("Ready")
                return
            
            # Prepare arguments
            arguments = {}
            schema_properties = tool.inputSchema.get('properties', {})
            
            # For debugging
            self.append_to_conversation("System", f"Function parameters: {params}")
            self.append_to_conversation("System", f"Expected schema: {schema_properties}")
            
            # Extract parameter names from schema
            param_names = list(schema_properties.keys())
            
            # Map parameters to the schema by position
            for i, param_value in enumerate(params):
                if i < len(param_names):
                    param_name = param_names[i]
                    param_info = schema_properties[param_name]
                    param_type = param_info.get('type', 'string')
                    
                    # Convert value to appropriate type
                    if param_type == 'integer':
                        try:
                            arguments[param_name] = int(param_value)
                        except ValueError:
                            arguments[param_name] = 0
                    elif param_type == 'number':
                        try:
                            arguments[param_name] = float(param_value)
                        except ValueError:
                            arguments[param_name] = 0.0
                    elif param_type == 'array':
                        if isinstance(param_value, str):
                            param_value = param_value.strip('[]').split(',')
                        try:
                            arguments[param_name] = [int(x.strip()) if x.strip().isdigit() else x.strip() for x in param_value]
                        except:
                            arguments[param_name] = []
                    else:
                        arguments[param_name] = str(param_value)
            
            # For debugging - show what we're actually sending
            self.append_to_conversation("System", f"Calling tool with arguments: {arguments}")
            
            # Check if session is initialized
            if not self.session:
                self.append_to_conversation("System", "Error: Session not initialized. Please wait for connection to establish.")
                self.status_var.set("Ready")
                return
                
            # Execute the function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Add timeout to avoid hanging
            async def call_with_timeout():
                try:
                    async with asyncio.timeout(30):  # 30 second timeout
                        return await self.session.call_tool(func_name, arguments=arguments)
                except asyncio.TimeoutError:
                    return "Operation timed out"
                    
            result = loop.run_until_complete(call_with_timeout())
            loop.close()
            
            # Process and display the results
            result_text = ""
            if hasattr(result, 'content'):
                if isinstance(result.content, list):
                    for item in result.content:
                        if hasattr(item, 'text'):
                            result_text += item.text + "\n"
                        else:
                            result_text += str(item) + "\n"
                else:
                    result_text = str(result.content)
            else:
                result_text = str(result)
            
            self.append_to_conversation("System", f"Result from {func_name}:\n{result_text}")
            
            # Process the result with the AI to get a human-friendly response
            threading.Thread(target=self.process_result, 
                            args=(func_name, arguments, result_text, history), 
                            daemon=True).start()
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.append_to_conversation("System", f"Error executing {func_name}: {str(e)}\n\nDetails:\n{error_details}")
            self.status_var.set("Ready")

    def process_result(self, func_name, arguments, result, history):
        """Process function result with the LLM to get a human-friendly response"""
        try:
            prompt = f"""You are an email assistant. You just executed the function {func_name} 
            with arguments {arguments} and got this result:
            
            {result}
            
            Please interpret this result in a user-friendly way. If this contains email data, 
            format it nicely. If this is a confirmation of an action, summarize what happened.
            If there's an error, explain it clearly and suggest what to do next.

            """
            # Here is past conversion history: {history}            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self.generate_response(prompt, ""))
            loop.close()
            
            self.append_to_conversation("Assistant", response.strip())
        except Exception as e:
            self.append_to_conversation("Assistant", f"I processed the {func_name} request, but had trouble interpreting the results. You can see the raw output above.")
        finally:
            self.status_var.set("Ready")


if __name__ == "__main__":
    root = tk.Tk()
    app = EmailAssistantApp(root)
    root.mainloop()