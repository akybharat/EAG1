import os
import asyncio
import threading
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Initialize Gemini
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.0-flash")

# Initialize Flask app
app = Flask(__name__, static_folder='static')

# Global variables
session = None
tools = []
function_results = {}
initialization_status = {"status": "not_started", "error": None}

def initialize_server():
    """Initialize connection to the MCP server in a separate thread"""
    global initialization_status
    initialization_status = {"status": "in_progress", "error": None}
    
    try:
        asyncio.run(setup_session())
    except Exception as e:
        initialization_status = {"status": "failed", "error": str(e)}

async def setup_session():
    """Set up the MCP client session"""
    global session, tools, initialization_status
    venv_python_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.venv', 'Scripts', 'python.exe'))    
    
    try:
        server_params = StdioServerParameters(
            command=venv_python_path,
            args=["src/gmail/server.py"]
        )
        
        async with asyncio.timeout(30):  # 30-second timeout for connection
            from mcp.client.stdio import stdio_client
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as client_session:
                    session = client_session
                    await session.initialize()
                    
                    # Get available tools
                    tools_result = await session.list_tools()
                    tools = tools_result.tools
                    
                    initialization_status = {"status": "success", "error": None}
                    
                    # Keep the session alive
                    while True:
                        await asyncio.sleep(1)
    except Exception as e:
        error_msg = str(e)
        if "credentials file not found" in error_msg.lower():
            error_msg = "Gmail credentials file not found. Please create a 'gmail_cred.json' file with your OAuth 2.0 credentials in the project root directory."
        elif "invalid_grant" in error_msg.lower():
            error_msg = "Invalid authentication credentials. Your OAuth token may have expired. Delete the token.json file and try again."
        elif "access_denied" in error_msg.lower():
            error_msg = "Access denied. You need to authorize the application to access your Gmail account."
        
        initialization_status = {"status": "failed", "error": error_msg}
        raise

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/initialize', methods=['POST'])
def api_initialize():
    global initialization_status
    
    # Start initialization in a separate thread if not already started
    if initialization_status["status"] == "not_started":
        threading.Thread(target=initialize_server, daemon=True).start()
        return jsonify({"success": True, "message": "Initialization started", "toolCount": 0})
    
    # Check initialization status
    if initialization_status["status"] == "in_progress":
        return jsonify({"success": True, "message": "Initialization in progress", "toolCount": 0})
    elif initialization_status["status"] == "success":
        return jsonify({"success": True, "message": "Already initialized", "toolCount": len(tools)})
    else:
        return jsonify({"success": False, "error": initialization_status["error"]})

@app.route('/api/process', methods=['POST'])
def process_message():
    data = request.json
    user_message = data.get('message', '')
    
    # Create system prompt
    tools_description = get_tools_description()
    system_prompt = create_system_prompt(tools_description)
    
    try:
        # Get AI response
        prompt = f"{system_prompt}\n\nUser: {user_message}"
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Check if response contains a function call
        if "FUNCTION_CALL:" in response_text:
            parts = response_text.split("FUNCTION_CALL:")
            explanation = parts[0].strip()
            
            # Parse function call
            function_info = parts[1].strip().split('\n')[0].strip()
            function_parts = [p.strip() for p in function_info.split("|")]
            func_name = function_parts[0]
            params = function_parts[1:] if len(function_parts) > 1 else []
            
            # Generate unique ID for this function execution
            execution_id = str(uuid.uuid4())
            
            # Start function execution in a separate thread
            threading.Thread(
                target=execute_function_call,
                args=(func_name, params, execution_id),
                daemon=True
            ).start()
            
            # Return response with function call info
            return jsonify({
                "type": "function_call",
                "explanation": explanation,
                "functionName": func_name,
                "executionId": execution_id
            })
        else:
            # Return regular message
            return jsonify({
                "type": "message",
                "content": response_text.strip()
            })
    except Exception as e:
        return jsonify({
            "type": "error",
            "error": str(e)
        })

@app.route('/api/function_result/<execution_id>')
def get_function_result(execution_id):
    """Get the result of a function execution"""
    global function_results
    
    if execution_id not in function_results:
        return jsonify({"status": "pending"})
    
    result = function_results[execution_id]
    
    if result["status"] == "error":
        return jsonify({
            "status": "error",
            "functionName": result["function_name"],
            "error": result["error"]
        })
    elif result["status"] == "completed":
        return jsonify({
            "status": "completed",
            "functionName": result["function_name"],
            "rawResult": result["raw_result"],
            "processedResult": result["processed_result"]
        })
    else:
        return jsonify({"status": "processing"})

def get_tools_description():
    """Create a description string for available tools"""
    global tools
    
    if not tools:
        return "No tools available. Server connection might be down."
    
    tools_description = []
    for i, tool in enumerate(tools):
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

def create_system_prompt(tools_description):
    """Create the system prompt for the LLM"""
    return f"""You are an intelligent email assistant with access to the user's Gmail account.
    
    Your job is to help the user manage their emails through conversation while using available email tools.

    Available email tools:
    {tools_description}

    When you need to use a tool, format your response exactly as follows:

    1. First explain your reasoning and what you're going to do
    2. Then put the function call on a separate line starting with FUNCTION_CALL:
    FUNCTION_CALL: function_name|parameter1_value|parameter2_value|...
    3. Wait for function results before proceeding with your response

    For example, when sending an email:
    I'll send an email to your colleague now.
    FUNCTION_CALL: send-email|example@gmail.com|Meeting Tomorrow|Hi there,\n\nI wanted to confirm our meeting tomorrow at 2pm.\n\nBest regards,\nYou

    Important guidelines:

    1. REASONING PROCESS:
    - Always explain your thought process before taking any action
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
    """

def execute_function_call(func_name, params, execution_id):
    """Execute a function call and store the results"""
    global session, tools, function_results
    
    # Initialize result entry
    function_results[execution_id] = {
        "status": "processing",
        "function_name": func_name,
        "error": None,
        "raw_result": None,
        "processed_result": None
    }
    
    try:
        # Find the matching tool
        tool = next((t for t in tools if t.name == func_name), None)
        if not tool:
            function_results[execution_id].update({
                "status": "error",
                "error": f"Unknown tool: {func_name}"
            })
            return
        
        # Prepare arguments
        arguments = {}
        schema_properties = tool.inputSchema.get('properties', {})
        
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
        
        # Check if session is initialized
        if not session:
            function_results[execution_id].update({
                "status": "error",
                "error": "Session not initialized. Please wait for connection to establish."
            })
            return
                
        # Execute the function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Add timeout to avoid hanging
        async def call_with_timeout():
            try:
                async with asyncio.timeout(30):  # 30 second timeout
                    return await session.call_tool(func_name, arguments=arguments)
            except asyncio.TimeoutError:
                return "Operation timed out"
                
        result = loop.run_until_complete(call_with_timeout())
        loop.close()
        
        # Process the result
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
        
        # Update the raw result
        function_results[execution_id].update({
            "raw_result": result_text
        })
        
        # Process the result with the AI to get a human-friendly response
        processed_result = process_function_result(func_name, arguments, result_text)
        
        # Update the processed result
        function_results[execution_id].update({
            "status": "completed",
            "processed_result": processed_result
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        function_results[execution_id].update({
            "status": "error",
            "error": f"Error executing {func_name}: {str(e)}\n\nDetails:\n{error_details}"
        })

def process_function_result(func_name, arguments, result):
    """Process function result with the LLM to get a human-friendly response"""
    try:
        prompt = f"""You are an email assistant. You just executed the function {func_name} 
        with arguments {arguments} and got this result:
        
        {result}
        
        Please interpret this result in a user-friendly way. If this contains email data, 
        format it nicely. If this is a confirmation of an action, summarize what happened.
        If there's an error, explain it clearly and suggest what to do next.
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"I processed the {func_name} request, but had trouble interpreting the results. You can see the raw output above."

if __name__ == "__main__":
    app.run(debug=True, port=5000)