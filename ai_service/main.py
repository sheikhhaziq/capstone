from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from typing import List, Optional
import traceback
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-1.7B")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", 1000))

app = FastAPI()

SYSTEM_MSG = (
    "You are MindSpace, a compassionate AI counselor for college students. "
    "Validate feelings and offer gentle advice. "
    "If suggesting resources, refer ONLY to our app features using these exact Markdown links: "
    "1. [Book Appointment](https://mindspace.app/book-appointment) for professional therapists. "
    "2. [Peer Forum](https://mindspace.app/peer-forum) to talk anonymously. "
    "3. [Resource Library](https://mindspace.app/resource-library) for self-help content. "
    "Do not suggest external websites, phone numbers, or clinics."
)

FEW_SHOT_PROMPT = (
    f"<|im_start|>system\n{SYSTEM_MSG}<|im_end|>\n"
    "<|im_start|>user\nI feel really depressed and need professional help.<|im_end|>\n"
    "<|im_start|>assistant\n"
    "I'm truly sorry you're feeling this way, but I'm glad you reached out. You don't have to go through this alone.\n\n"
    "Here are the MindSpace resources available to you:\n"
    "1. [Book Appointment](https://mindspace.app/book-appointment) - Connect with a therapist.\n"
    "2. [Peer Forum](https://mindspace.app/peer-forum) - Share with students who understand.\n"
    "3. [Resource Library](https://mindspace.app/resource-library) - Helpful guides and articles.<|im_end|>\n"
)

logger.info(f"Loading AI Model ({MODEL_NAME}) on {DEVICE.upper()}...")
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(DEVICE)
    logger.info("Model Loaded Successfully!")
except Exception as e:
    logger.error(f"Failed to load model: {e}")
    raise e

class ChatRequest(BaseModel):
    text: str
    history_ids: Optional[List[List[int]]] = [] 

@app.post("/chat/")
def chat_response(request: ChatRequest):
    user_input = request.text
    
    try:
        if not request.history_ids or len(request.history_ids) == 0:
            full_prompt = FEW_SHOT_PROMPT + f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
            bot_input_ids = tokenizer.encode(full_prompt, return_tensors='pt').to(DEVICE)
        else:
            new_input_text = f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
            new_ids = tokenizer.encode(new_input_text, return_tensors='pt').to(DEVICE)
            
            past_history = torch.tensor(request.history_ids).to(DEVICE)
            
            if past_history.shape[-1] > MAX_HISTORY_TOKENS:
                few_shot_ids = tokenizer.encode(FEW_SHOT_PROMPT, return_tensors='pt').to(DEVICE)
                recent_history = past_history[:, -600:] 
                bot_input_ids = torch.cat([few_shot_ids, recent_history, new_ids], dim=-1)
            else:
                bot_input_ids = torch.cat([past_history, new_ids], dim=-1)

        attention_mask = torch.ones_like(bot_input_ids).to(DEVICE)

        chat_history_ids = model.generate(
            bot_input_ids, 
            attention_mask=attention_mask,
            max_new_tokens=200,       
            pad_token_id=tokenizer.eos_token_id,
            do_sample=True, 
            top_k=50, 
            top_p=0.95,
            temperature=0.2,          
            repetition_penalty=1.1    
        )

        new_tokens = chat_history_ids[:, bot_input_ids.shape[-1]:]
        response_text = tokenizer.decode(new_tokens[0], skip_special_tokens=True)

        return {
            "response": response_text,
            "history_ids": chat_history_ids.tolist(),
            "status": "OK"
        }

    except Exception as e:
        logger.error(f"Error during chat generation: {e}")
        traceback.print_exc()
        return {
            "response": "I am listening. Please go on.",
            "history_ids": [],
            "status": "ERROR"
        }