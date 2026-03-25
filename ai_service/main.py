from fastapi import FastAPI
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from typing import List, Optional
import traceback
import os
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-1.7B")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", 1000))
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", 2000))

CRISIS_RESPONSE = os.getenv(
    "CRISIS_RESPONSE",
    "I am really glad you reached out. You deserve immediate support right now.\n\n"
    "If you are in immediate danger, please call your local emergency services now. "
    "If possible, contact someone you trust and stay with them.\n\n"
    "You can also use MindSpace resources now:\n"
    "1. [Book Appointment](https://mindspace.app/book-appointment)\n"
    "2. [Peer Forum](https://mindspace.app/peer-forum)\n"
    "3. [Resource Library](https://mindspace.app/resource-library)"
)

CRISIS_PATTERNS = [
    r"\bsuicid(e|al)\b",
    r"\bkill myself\b",
    r"\bend my life\b",
    r"\bself[-\s]?harm\b",
    r"\bhurt myself\b",
    r"\boverdos(e|ing)\b",
    r"\bwant to die\b",
    r"\bdon'?t want to live\b",
]

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
    text: str = Field(..., min_length=1, max_length=MAX_INPUT_CHARS)
    history_ids: Optional[List[List[int]]] = Field(default_factory=list)


def is_crisis_message(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in CRISIS_PATTERNS)


def build_history_tensor(history_ids: List[List[int]]) -> Optional[torch.Tensor]:
    if not history_ids:
        return None
    if len(history_ids) != 1:
        return None
    if not history_ids[0]:
        return None
    # Prevent unbounded user-controlled context growth.
    trimmed = history_ids[0][-MAX_HISTORY_TOKENS:]
    return torch.tensor([trimmed], dtype=torch.long, device=DEVICE)

@app.post("/chat/")
def chat_response(request: ChatRequest):
    user_input = request.text.strip()
    
    try:
        if is_crisis_message(user_input):
            return {
                "response": CRISIS_RESPONSE,
                "history_ids": [],
                "status": "CRISIS_ALERT",
            }

        if not request.history_ids or len(request.history_ids) == 0:
            full_prompt = FEW_SHOT_PROMPT + f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
            bot_input_ids = tokenizer.encode(full_prompt, return_tensors='pt').to(DEVICE)
        else:
            new_input_text = f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
            new_ids = tokenizer.encode(new_input_text, return_tensors='pt').to(DEVICE)
            
            past_history = build_history_tensor(request.history_ids)
            
            if past_history is None:
                logger.warning("Invalid or empty history_ids received, resetting context.")
                few_shot_ids = tokenizer.encode(FEW_SHOT_PROMPT, return_tensors='pt').to(DEVICE)
                bot_input_ids = torch.cat([few_shot_ids, new_ids], dim=-1)
            elif past_history.shape[-1] > MAX_HISTORY_TOKENS:
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