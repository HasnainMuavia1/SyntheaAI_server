import os
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
# winpty (pywinpty) is a Windows-only dependency used to spawn a PowerShell PTY.
# It is unavailable on Linux/macOS (e.g. inside a Docker container), so we import
# it lazily/defensively. The rest of the app (API + other websockets) must still
# boot when it is missing; only the terminal feature degrades gracefully.
try:
    from winpty import PTY  # type: ignore
    WINPTY_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PTY = None  # type: ignore
    WINPTY_AVAILABLE = False
from asgiref.sync import sync_to_async
from urllib.parse import parse_qs
from urllib.parse import parse_qs
from .models import Workspace, ChatSession, ChatMessage

class TerminalConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pty = None
        self.fd = None
        self.pid = None
        self.pty_task = None

    async def connect(self):
        print("Terminal WebSocket connecting...")
        await self.accept()
        print("Terminal WebSocket accepted.")

        query = parse_qs(self.scope.get("query_string", b"").decode())
        try:
            cols = int(query.get("cols", [80])[0])
            rows = int(query.get("rows", [24])[0])
        except (ValueError, TypeError):
            cols = 80
            rows = 24

        if WINPTY_AVAILABLE:
            # Start a PowerShell/Cmd PTY for Windows
            try:
                print(f"Spawning Windows PTY with {cols}x{rows}...")
                self.pty = PTY(cols, rows)
                
                # Spawn PowerShell without PSReadLine.
                self.pty.spawn(
                    "powershell.exe",
                    cmdline='powershell.exe -NoExit -Command "Remove-Module PSReadLine -ErrorAction SilentlyContinue"'
                )
                # Give the shell time to execute its profile + our init command
                await asyncio.sleep(1.0)

                # After shell starts, change directory into the requested workspace if provided
                try:
                    workspace_id = query.get("projectId", [None])[0]
                    if workspace_id:
                        workspace = await sync_to_async(Workspace.objects.get)(workspace_id=workspace_id)
                        cwd = workspace.get_absolute_path()
                        self.pty.write('\r\n')
                        self.pty.write(f'Set-Location "{cwd}"\r\n')
                except Exception as e:
                    print(f"Failed to change Windows PTY directory: {e}")
                
                # Start background task to read from PTY
                self.pty_task = asyncio.create_task(self.read_from_pty())
            except Exception as e:
                print(f"Error in TerminalConsumer.connect (Windows): {e}")
                await self.send(text_data=json.dumps({'error': str(e)}))
                await self.close()
        else:
            # Unix / Linux / macOS PTY spawning logic
            try:
                import pty
                import termios
                import fcntl
                import struct
            except ImportError as e:
                print(f"Unix PTY dependencies not available: {e}")
                await self.send(text_data=json.dumps({
                    'error': 'Terminal feature is unavailable on this platform (missing Unix pty/termios libs).'
                }))
                await self.close()
                return

            try:
                print(f"Spawning UNIX PTY with {cols}x{rows}...")
                pid, fd = pty.fork()
                if pid == 0:
                    # CHILD PROCESS (forked)
                    env = os.environ.copy()
                    env["TERM"] = "xterm-256color"
                    env["COLUMNS"] = str(cols)
                    env["LINES"] = str(rows)

                    workspace_id = query.get("projectId", [None])[0]
                    cwd = os.getcwd()
                    if workspace_id:
                        try:
                            # Synchronously query since we are in a clean fork
                            from .models import Workspace
                            workspace = Workspace.objects.get(workspace_id=workspace_id)
                            cwd = workspace.get_absolute_path()
                        except Exception as ex:
                            print(f"Child process failed to get workspace: {ex}")

                    try:
                        os.chdir(cwd)
                    except Exception as ex:
                        print(f"Child process failed to chdir to {cwd}: {ex}")

                    shell = "/bin/bash"
                    if not os.path.exists(shell):
                        shell = "/bin/sh"
                    
                    os.execvpe(shell, [shell], env)
                else:
                    # PARENT PROCESS
                    self.fd = fd
                    self.pid = pid
                    
                    # Set terminal size
                    try:
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
                    except Exception as e:
                        print(f"Failed to set initial terminal size: {e}")

                    # Start PTY read loop task
                    self.pty_task = asyncio.create_task(self.read_from_pty())
            except Exception as e:
                print(f"Error spawning Unix terminal: {e}")
                await self.send(text_data=json.dumps({'error': str(e)}))
                await self.close()

    async def disconnect(self, close_code):
        if self.pty_task:
            self.pty_task.cancel()
        if WINPTY_AVAILABLE:
            if self.pty:
                del self.pty
        else:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except:
                    pass
            if self.pid is not None:
                try:
                    import signal
                    os.kill(self.pid, signal.SIGKILL)
                    os.waitpid(self.pid, os.WNOHANG)
                except:
                    pass

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            command = text_data_json.get('command')
            resize = text_data_json.get('resize')
            
            if command:
                if WINPTY_AVAILABLE:
                    if self.pty:
                        self.pty.write(command)
                else:
                    if self.fd is not None:
                        await asyncio.to_thread(os.write, self.fd, command.encode())
            elif resize:
                if WINPTY_AVAILABLE:
                    if self.pty:
                        self.pty.set_size(resize['cols'], resize['rows'])
                else:
                    if self.fd is not None:
                        import fcntl
                        import termios
                        import struct
                        try:
                            winsize = struct.pack("HHHH", resize['rows'], resize['cols'], 0, 0)
                            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
                        except Exception as e:
                            print(f"Failed to resize Unix terminal: {e}")
        except Exception as e:
            print(f"Error handling receive: {e}")

    async def read_from_pty(self):
        print("Starting PTY read loop...")
        try:
            while True:
                if WINPTY_AVAILABLE:
                    if not self.pty:
                        break
                    output = await asyncio.to_thread(self.pty.read)
                    if output:
                        await self.send(text_data=json.dumps({
                            'output': output
                        }))
                    else:
                        await asyncio.sleep(0.01)
                else:
                    if self.fd is None:
                        break
                    # Use asyncio.to_thread to prevent blocking the event loop on os.read
                    data = await asyncio.to_thread(os.read, self.fd, 1024)
                    if not data:
                        # EOF from shell
                        break
                    # Decode text safely, handling partial UTF-8 sequences
                    output = data.decode('utf-8', errors='ignore')
                    if output:
                        await self.send(text_data=json.dumps({
                            'output': output
                        }))
        except asyncio.CancelledError:
            print("PTY read loop cancelled.")
        except Exception as e:
            print(f"Error in read_from_pty: {e}")
            try:
                await self.send(text_data=json.dumps({'error': str(e)}))
            except:
                pass



# Deferred imports for whisperflow to avoid crashing the whole app if not installed


class VoiceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        
        try:
            import whisperflow.streaming as st
            import whisperflow.transcriber as ts
            self.model = ts.get_model('tiny.en.pt') 
        except (ImportError, ModuleNotFoundError) as e:
            print(f"WhisperFlow not installed or missing: {e}")
            await self.send(text_data=json.dumps({'error': 'Voice features currently unavailable (missing backend dependencies).'}))
            await self.close()
            return
        except Exception as e:
            print(f"Error loading whisper model: {e}")
            await self.send(text_data=json.dumps({'error': f'Voice model error: {str(e)}'}))
            await self.close()
            return

        async def transcribe_async(chunks: list):
            import whisperflow.transcriber as ts
            return await ts.transcribe_pcm_chunks_async(self.model, chunks)


        async def send_back_async(data: dict):
            try:
                await self.send(text_data=json.dumps(data))
            except Exception as e:
                pass # Already disconnected

        self.session = st.TranscribeSession(transcribe_async, send_back_async)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data and hasattr(self, 'session'):
            self.session.add_chunk(bytes_data)

    async def disconnect(self, close_code):
        if hasattr(self, 'session') and self.session:
            await self.session.stop()

import subprocess

from langchain_groq import ChatGroq
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain.agents import create_agent
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

# Load environment variables (like GROQ_API_KEY from .env.local)
BASE_DIR_ENV = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR_ENV, ".env.local"))

class AgentCallbackHandler(AsyncCallbackHandler):
    def __init__(self, consumer):
        self.consumer = consumer
        self.last_path = None

    async def on_agent_action(self, action, **kwargs):
        """Run on agent action."""
        # Monitor all file-modifying tools
        modification_tools = ["write_file", "move_file", "copy_file", "file_delete", "create_directory", "delete_file"]
        if action.tool in modification_tools:
            try:
                tool_input = action.tool_input
                file_path = None
                
                # Extract dictionary if tool_input is a JSON string
                if isinstance(tool_input, str):
                    try:
                        import json
                        tool_input = json.loads(tool_input)
                    except:
                        pass # Fallback to using it as a string below if it wasn't JSON
                        
                if isinstance(tool_input, dict):
                    # For move_file / copy_file, the affected destination is destination_path
                    if action.tool in ["move_file", "copy_file"]:
                        file_path = tool_input.get("destination_path")
                    # For write_file, file_delete
                    elif action.tool in ["write_file", "file_delete", "delete_file"]: 
                        file_path = tool_input.get("file_path")
                    # For directory operations if any exist
                    elif action.tool == "create_directory":
                        file_path = tool_input.get("dir_path")
                        
                    # Catch-all
                    if not file_path:
                        file_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("destination_path") or tool_input.get("dir_path")
                elif isinstance(tool_input, str):
                    file_path = tool_input
                
                if file_path:
                    print(f"Agent modifying path: {file_path} via tool {action.tool}")
                    self.last_path = file_path
                    # Just store the path, send notification in on_tool_end
            except Exception as e:
                print(f"Error in on_agent_action path parsing: {e}")

        # Send reasoning/thought to frontend
        thought = getattr(action, 'log', '')
        if thought:
            clean_thought = thought.strip()
            # Remove standard LangChain Action JSON blocks
            if "```json" in clean_thought:
                clean_thought = clean_thought.split("```json")[0].strip()
            if "Action:" in clean_thought:
                clean_thought = clean_thought.split("Action:")[0].strip()
            
            if clean_thought and not (clean_thought.startswith('{') and clean_thought.endswith('}')):
                await self.consumer.send(text_data=json.dumps({
                    'type': 'reasoning',
                    'content': clean_thought + "\n"
                }))

    async def on_tool_end(self, output, **kwargs):
        """Run when tool ends."""
        # Notify frontend that a file was modified/created AFTER it's actually done
        if self.last_path:
            try:
                await self.consumer.send(text_data=json.dumps({
                    'type': 'file_event',
                    'event': 'modified',
                    'path': self.last_path
                }))
            except Exception as e:
                print(f"Error sending file_event: {e}")
            self.last_path = None

        # Optionally send tool output as reasoning
        await self.consumer.send(text_data=json.dumps({
            'type': 'reasoning',
            'content': f"\nTool Output: {output}\n"
        }))


# --- AGENT PROMPTS ---

# --- AGENT PROMPTS ---

PLANNER_PROMPT = """You are an elite software architect and engineer with 30 years of experience. Your goal is to formulate flawless implementation plans.

CRITICAL DIRECTIVES:
1. SCALE TO THE TASK: If the task is simple (e.g., "swap two numbers", "rename a variable"), DO NOT overcomplicate. Provide a simple, 1-2 step plan. Only use extensive breakdown for large, complex requirements.
2. EXPERT EXECUTION: Anticipate edge cases, plan clean refactoring, and prioritize efficiency.
3. FORMAT: Output ONLY clean human-readable planning text. DO NOT output raw JSON, internal thought processes, or verbose filler."""

CODER_PROMPT = """You are a senior execution engineer. Execute the Planner's strategy perfectly.

CRITICAL RULES:
1. TOOLS: Use ONLY the exact tools provided in your toolkit. NEVER hallucinate or attempt to use tools that do not exist (e.g., DO NOT use 'run_file').
2. FILE WRITING: When using 'write_file', provide ONLY the raw, runnable code. NEVER wrap code in markdown blocks (```python) in tool inputs.
3. NO CHAT: Be extremely direct. Zero conversational text."""

REVIEWER_PROMPT = """You are a senior tech lead reviewing the work.
Provide a final, EXTREMELY SHORT and concise summary to the user.
If the task was simple, just give a 1-2 sentence confirmation. Avoid walls of text. Be direct and concise."""

class LangChainAgentConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = None
        self.tools = None
        self.planner_agent = None
        self.coder_agent = None
        self.reviewer_agent = None
        self.workspace_id = None
        self.session_id = None
        self.agent_task = None  # To hold the currently running agent task

    async def connect(self):
        print("LangChain Multi-Agent WebSocket connecting...")
        await self.accept()
        
        try:
            query = parse_qs(self.scope.get("query_string", b"").decode())
            self.workspace_id = query.get("projectId", [None])[0]
            self.session_id = query.get("sessionId", [None])[0]
            cwd = os.getcwd()
            if self.workspace_id:
                try:
                    workspace = await sync_to_async(Workspace.objects.get)(workspace_id=self.workspace_id)
                    cwd = workspace.get_absolute_path()
                except: pass

            # Use forward slashes for cross-platform compatibility
            work_dir = cwd.replace('\\', '/')

            # Shared LLM Configuration
            self.llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0,
                max_tokens=None,
                reasoning_format="parsed",
            )
            
            # File Management Toolkit
            toolkit = FileManagementToolkit(root_dir=work_dir)
            self.tools = toolkit.get_tools()

            # Initialize Specialized Agents
            # 1. Planner (Simple Chain)
            planner_template = ChatPromptTemplate.from_messages([
                ("system", PLANNER_PROMPT),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ])
            self.planner_agent = planner_template | self.llm | StrOutputParser()

            # 2. Coder (Tool-augmented Agent)
            # We use create_agent for the Coder as it needs tools
            self.coder_agent = create_agent(
                model=self.llm,
                tools=self.tools,
                system_prompt=CODER_PROMPT,
            )

            # 3. Reviewer (Simple Chain)
            reviewer_template = ChatPromptTemplate.from_messages([
                ("system", REVIEWER_PROMPT),
                ("human", "User Request: {input}\nPlan: {plan}\nActions Done: {actions}"),
            ])
            self.reviewer_agent = reviewer_template | self.llm | StrOutputParser()
            
            # Removed hardcoded system ready message
            
        except Exception as e:
            print(f"Error in LangChainAgentConsumer.connect: {e}")
            await self.send(text_data=json.dumps({'error': str(e)}))

    async def get_history(self):
        """Fetch chat history from the database for this specific session."""
        if not self.workspace_id or not self.session_id:
            return []
        
        try:
            messages = await sync_to_async(list)(
                ChatMessage.objects.filter(session__id=self.session_id)
                .order_by('-created_at')[:10]
            )
            history = []
            for m in reversed(messages):
                if m.sender == 'user':
                    history.append(HumanMessage(content=m.text))
                else:
                    history.append(AIMessage(content=m.text))
            return history
        except Exception as e:
            print(f"Error fetching history: {e}")
            return []

    async def receive(self, text_data):
        if not self.planner_agent: return
        try:
            data = json.loads(text_data)
            
            # Handle Interrupt Command
            if data.get('type') == 'interrupt':
                print("Received interrupt command from user.")
                if self.agent_task and not self.agent_task.done():
                    self.agent_task.cancel()
                    self.agent_task = None
                    # Send an acknowledgement
                    await self.send(text_data=json.dumps({
                        'type': 'final_output',
                        'output': "User stopped agent to work.\n"
                    }))
                return

            user_input = data.get('message')
            mode = data.get('mode', 'agent')
            if not user_input: return

            print(f"Agent Processing Request: {user_input} (Mode: {mode})")
            callback = AgentCallbackHandler(self)
            history = await self.get_history()

            # Function to run the agent logic
            async def run_agent():
                try:
                    if mode == 'ask':
                        await self.send(text_data=json.dumps({'type': 'reasoning', 'content': "\n[SYSTEM] Generating response...\n"}))
                        
                        messages = [
                            SystemMessage(content="You are a helpful programming assistant inside the Synthea IDE. Answer the user's questions clearly, concisely, and accurately without using tools."),
                        ] + history + [HumanMessage(content=user_input)]
                        
                        ai_msg = await self.llm.ainvoke(messages)
                        final_response = ai_msg.content if hasattr(ai_msg, 'content') else str(ai_msg)
                        
                        await self.send(text_data=json.dumps({
                            'type': 'final_output',
                            'output': final_response + "\n"
                        }))
                        
                        await sync_to_async(ChatMessage.objects.create)(
                            project=await sync_to_async(Workspace.objects.get)(workspace_id=self.workspace_id),
                            session=await sync_to_async(ChatSession.objects.get)(id=self.session_id) if self.session_id else None,
                            sender='agent',
                            text=final_response
                        )
                        return

                    # PHASE 1: PLANNING
                    await self.send(text_data=json.dumps({'type': 'reasoning', 'content': "\n[SYSTEM] Planner is drafting an implementation strategy...\n"}))
                    plan = await self.planner_agent.ainvoke({"input": user_input, "history": history})
                    await self.send(text_data=json.dumps({'type': 'reasoning', 'content': f"Plan Created:\n{plan}\n"}))

                    # PHASE 2: CODING (Execution)
                    await self.send(text_data=json.dumps({'type': 'reasoning', 'content': "\n[SYSTEM] Coder is executing the plan and managing files...\n"}))
                    # The coder uses tools, so it will trigger callbacks for file_event and reasoning
                    coder_response = await self.coder_agent.ainvoke(
                        {"messages": [HumanMessage(content=f"User Request: {user_input}\nPlan to execute: {plan}")]},
                        {"callbacks": [callback]}
                    )
                    
                    # Extract coder output safely
                    coder_actions_summary = ""
                    if isinstance(coder_response, dict):
                        coder_actions_summary = coder_response.get("output", str(coder_response))
                    else:
                        coder_actions_summary = str(coder_response)

                    # PHASE 3: REVIEWING
                    await self.send(text_data=json.dumps({'type': 'reasoning', 'content': "\n[SYSTEM] Reviewer is finalizing the response...\n"}))
                    final_response = await self.reviewer_agent.ainvoke({
                        "input": user_input,
                        "plan": plan,
                        "actions": coder_actions_summary
                    })

                    # Clean up and Send
                    await self.send(text_data=json.dumps({
                        'type': 'final_output',
                        'output': final_response + "\n"
                    }))

                    # Save to History
                    await sync_to_async(ChatMessage.objects.create)(
                        project=await sync_to_async(Workspace.objects.get)(workspace_id=self.workspace_id),
                        session=await sync_to_async(ChatSession.objects.get)(id=self.session_id) if self.session_id else None,
                        sender='agent',
                        text=final_response
                    )
                except asyncio.CancelledError:
                    print("Agent task cancelled by user interrupt.")
                    # Let the interrupt handler manage the send output
                except Exception as ex:
                    print(f"Agent execution error: {ex}")
                    await self.send(text_data=json.dumps({'error': str(ex)}))

            # Cancel any existing task just in case
            if self.agent_task and not self.agent_task.done():
                self.agent_task.cancel()

            # Spawn the agent logic as an interruptible asyncio task
            self.agent_task = asyncio.create_task(run_agent())

        except Exception as e:
            print(f"Error in LangChainAgentConsumer.receive: {e}")
            await self.send(text_data=json.dumps({'error': str(e)}))

