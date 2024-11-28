from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os
from openai_client import OpenAIClient
from dotenv import load_dotenv

# Initialize FastAPI
app = FastAPI()

# Load .env file variables
load_dotenv()

# Load OpenAI API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

# Initialize OpenAI client
openai_client = OpenAIClient(api_key=OPENAI_API_KEY)

class TestStepsRequest(BaseModel):
    test_steps: list[str]

class TestCaseDescriptionResponse(BaseModel):
    description: str

@app.post("/generate-test-case-description", response_model=TestCaseDescriptionResponse)
async def generate_test_case_description(request: TestStepsRequest):
    """
    Generate a test case description from provided test steps.
    """
    try:
        description = await openai_client.generate_test_case_description(request.test_steps, response_model=TestCaseDescriptionResponse)
        return TestCaseDescriptionResponse(description=description)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Error with OpenAI API")

@app.get("/")
def read_root():
    return {"message": "AI Proxy Server is running"}
