from pydantic import BaseModel

class ChatRequest(BaseModel):
    user_message: str


class ChatAnswer(BaseModel):
    answer: str