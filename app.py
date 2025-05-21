from cgitb import Hook
import uvicorn
import uuid

from wasabi import msg
from redis import Redis
from fastapi import FastAPI , WebSocket
from fastapi.middleware.cors import CORSMiddleware
from tqdm import tqdm

import os
import ast
import json
import io 
import wave 

from dotenv import load_dotenv

from scripts.loader.loader import load_stt_client , load_llm_client , load_tts_client
from scripts.vad.vad import load_vad_model
from scripts.vad.services import find_speech_probablity
from scripts.services.main import transcribe_and_respond
from scripts.services.services import extract_hook , check_interruption , print_state , get_state
from scripts.llm.llm import get_title
from halo import Halo

sample_rate = 16000
threshold = 0.4
model = 'playai-tts'
voice = 'Arista-PlayAI'
silence_threshold = sample_rate * 2

load_dotenv()

stt_service = os.getenv('stt_service')
llm_service = os.getenv('llm_service')
tts_service = os.getenv('tts_service')

stt_client = load_stt_client(stt_service)
llm_client = load_llm_client(llm_service)
tts_client = load_tts_client(tts_service)

listening_spinner = Halo(text = 'Listening' , spinner = 'dots')

with open('assets/system_prompt.md') as system_prompt_file : system_prompt = system_prompt_file.read()

redis_client = Redis(
    host = 'localhost' ,  
    port = 6379 ,  
    decode_responses = True
)

keys = redis_client.keys()

if keys : 
    
    for key in tqdm(keys , total = len(keys) , desc = 'Cleaning Redis') : redis_client.delete(key)

else : print('Redis already empty')

app = FastAPI()
app.add_middleware(
    CORSMiddleware , 
    allow_origins = ['*'] , 
    allow_credentials = True , 
    allow_methods = ['*'] , 
    allow_headers = ['*'] , 
)

@app.websocket('/ws')
async def websocket_endpoint(websocket : WebSocket) : 

    with open('assets/info_template.json') as json_file : template_data = json.load(json_file)
    with open('assets/info.json' , 'w') as json_file : json.dump(template_data , json_file)

    await websocket.accept()

    session_id = str(uuid.uuid4())  # ! Use IP Address

    msg.good(f'Client connected with session ID: {session_id}, WEBSOCKET initialized')

    buffer_stream = bytes()
    state = 'idle'

    # await websocket.send_text(str(json.dumps({
    #     "isLoading" : 0
    # })))

    await websocket.send_json({
        'status' :  200 , 
        'message' : 'Ready to receive audio'
    })

    while True : 

        # hook = await websocket.receive_bytes()

        # print(type(hook))

        hook = await websocket.receive()
        hook = await get_state(hook)

        if isinstance(hook , str) : 
            
            state = hook

            if state == 'loading' : msg.good('Connecting with client')
            elif state == 'idle' : 
                
                msg.good('Client is idle')

                if buffer_stream : 

                    msg.good('Listening Stopped, Now processing')

                    # await websocket.send_text(str(json.dumps({
                    #     "isLoading" : 1
                    # })))
                    
                    response = await transcribe_and_respond(
                        websocket , 
                        buffer_stream , session_id , 
                        stt_client , llm_client ,
                        redis_client , 
                        system_prompt
                    ) 

                    await websocket.send_json(response)

                    # await websocket.send_text(str(json.dumps({
                    #     "isLoading" : 0
                    # })))

                    buffer_stream = bytes()

                msg.good('Didnt find any buffer stream')

        else : buffer_stream += hook ; print('\rListening' , end = '' , flush = True)

if __name__ == '__main__' : 
    
    uvicorn.run(
        app , 
        host = '0.0.0.0' , 
        port = 8888 , 
        # reload = True
    )
